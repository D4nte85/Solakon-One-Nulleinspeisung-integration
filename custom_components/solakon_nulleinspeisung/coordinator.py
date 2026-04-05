"""Coordinator — vollständige Nulleinspeisung-Regellogik mit Schreibguard."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Callable

from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN, STORAGE_VERSION, SETTINGS_DEFAULTS,
    CONF_GRID_SENSOR, CONF_ACTUAL_SENSOR, CONF_SOLAR_SENSOR,
    CONF_SOC_SENSOR, CONF_TIMEOUT_COUNTDOWN, CONF_ACTIVE_POWER,
    CONF_DISCHARGE_CURRENT, CONF_TIMEOUT_SET, CONF_MODE_SELECT,
    MODE_DISABLED, MODE_DISCHARGE, MODE_AC_CHARGE,
    S_REGULATION_ENABLED,
    S_P_FACTOR, S_I_FACTOR, S_TOLERANCE, S_WAIT_TIME, S_STDDEV_WINDOW,
    S_ZONE1_LIMIT, S_ZONE3_LIMIT, S_DISCHARGE_MAX, S_HARD_LIMIT,
    S_OFFSET_1, S_OFFSET_2, S_PV_RESERVE,
    S_SURPLUS_ENABLED, S_SURPLUS_SOC_THRESHOLD, S_SURPLUS_SOC_HYST, S_SURPLUS_PV_HYST,
    S_AC_ENABLED, S_AC_SOC_TARGET, S_AC_POWER_LIMIT, S_AC_HYSTERESIS,
    S_AC_OFFSET, S_AC_P_FACTOR, S_AC_I_FACTOR,
    S_TARIFF_ENABLED, S_TARIFF_PRICE_SENSOR, S_TARIFF_CHEAP_THRESHOLD,
    S_TARIFF_EXP_THRESHOLD, S_TARIFF_SOC_TARGET, S_TARIFF_POWER,
    S_NIGHT_ENABLED,
    S_SELF_ADJUST, S_SELF_ADJUST_TOL,
    S_DYN_Z1_ENABLED, S_DYN_Z1_MIN, S_DYN_Z1_MAX, S_DYN_Z1_NOISE, S_DYN_Z1_FACTOR, S_DYN_Z1_NEGATIVE,
    S_DYN_Z2_ENABLED, S_DYN_Z2_MIN, S_DYN_Z2_MAX, S_DYN_Z2_NOISE, S_DYN_Z2_FACTOR, S_DYN_Z2_NEGATIVE,
    S_DYN_AC_ENABLED, S_DYN_AC_MIN, S_DYN_AC_MAX, S_DYN_AC_NOISE, S_DYN_AC_FACTOR, S_DYN_AC_NEGATIVE,
)

_LOGGER = logging.getLogger(__name__)


class SolakonCoordinator:
    """Zentrale Logik-Klasse — PI-Regler, SOC-Zonen, Modbus-Steuerung."""

    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        self.hass = hass
        self.entry = entry
        self.settings: dict[str, Any] = SETTINGS_DEFAULTS.copy()
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")

        # Laufzeit-Zustände
        self.current_zone: int = 2
        self.zone_label: str = "Initialisierung…"
        self.mode_label: str = "Warten auf Daten"
        self.last_action: str = "Keine"
        self.last_error: str = ""
        self.integral: float = 0.0

        # Boolsche Status-Flags
        self.cycle_active: bool = False
        self.surplus_active: bool = False
        self.ac_charge_active: bool = False
        self.tariff_charge_active: bool = False

        # Zeitstempel
        self.last_action_ts: float = time.time()
        self.last_output_ts: float = time.time()
        self.mode_label_ts: float = time.time()

        # StdDev-Ringpuffer für Netz-Standardabweichung
        self._grid_samples: deque[tuple[float, float]] = deque()  # (timestamp, value)
        self.grid_stddev: float = 0.0

        # Dynamischer Offset (berechnete Werte pro Zone)
        self.dyn_offset_z1: float = 0.0
        self.dyn_offset_z2: float = 0.0
        self.dyn_offset_ac: float = 0.0

        # Interne Mechanik
        self._lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._unsub_trackers: list[Callable] = []
        self._tariff_unsub: Callable | None = None

    # ── Setup / Teardown ─────────────────────────────────────────────────────

    async def async_setup(self) -> None:
        """Einstellungen laden, State-Listener starten."""
        stored = await self._store.async_load()
        if stored:
            self.settings = {**SETTINGS_DEFAULTS, **stored}
            _LOGGER.debug("Solakon: Einstellungen aus Speicher geladen")
        else:
            self.settings = SETTINGS_DEFAULTS.copy()
            _LOGGER.info("Solakon: Standardwerte geladen")

        if "integral" in (stored or {}):
            self.integral = float(stored["integral"])

        cfg = self.entry.data
        entities_to_track = [
            cfg.get(CONF_GRID_SENSOR, ""),
            cfg.get(CONF_SOLAR_SENSOR, ""),
            cfg.get(CONF_SOC_SENSOR, ""),
            cfg.get(CONF_MODE_SELECT, ""),
        ]
        entities_to_track = [e for e in entities_to_track if e]

        if entities_to_track:
            unsub = async_track_state_change_event(
                self.hass, entities_to_track, self._on_state_change
            )
            self._unsub_trackers.append(unsub)

        self._update_tariff_tracker()

    async def async_shutdown(self) -> None:
        """Listener abräumen, Integral speichern."""
        for unsub in self._unsub_trackers:
            unsub()
        self._unsub_trackers.clear()
        if self._tariff_unsub:
            self._tariff_unsub()
            self._tariff_unsub = None
        await self._save_integral()

    # ── Settings-Management ──────────────────────────────────────────────────

    async def async_update_settings(self, changes: dict[str, Any]) -> None:
        old_tariff = self.settings.get(S_TARIFF_PRICE_SENSOR, "")
        old_tariff_enabled = self.settings.get(S_TARIFF_ENABLED, False)

        self.settings.update(changes)
        await self._store.async_save({**self.settings, "integral": self.integral})
        _LOGGER.info("Solakon: Einstellungen gespeichert")

        new_tariff = self.settings.get(S_TARIFF_PRICE_SENSOR, "")
        new_tariff_enabled = self.settings.get(S_TARIFF_ENABLED, False)
        if old_tariff != new_tariff or old_tariff_enabled != new_tariff_enabled:
            self._update_tariff_tracker()

        self.notify_listeners()

    def _update_tariff_tracker(self) -> None:
        """Tarif-Sensor-Listener dynamisch (de-)registrieren."""
        if self._tariff_unsub:
            self._tariff_unsub()
            self._tariff_unsub = None

        tariff_enabled = self.settings.get(S_TARIFF_ENABLED, False)
        tariff_sensor = self.settings.get(S_TARIFF_PRICE_SENSOR, "")

        if tariff_enabled and tariff_sensor:
            self._tariff_unsub = async_track_state_change_event(
                self.hass, [tariff_sensor], self._on_state_change
            )

    async def _save_integral(self) -> None:
        await self._store.async_save({**self.settings, "integral": self.integral})

    # ── Entity-Listener-Pattern ──────────────────────────────────────────────

    def register_entity_listener(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def unregister_entity_listener(self, cb: Callable[[], None]) -> None:
        if cb in self._listeners:
            self._listeners.remove(cb)

    def notify_listeners(self) -> None:
        for cb in self._listeners:
            cb()

    def reset_integral(self) -> None:
        self.integral = 0.0
        self._set_last_action("Integral manuell zurückgesetzt")
        self.notify_listeners()

    # ── Last-Action Setter ───────────────────────────────────────────────────

    def _set_last_action(self, text: str) -> None:
        """Setzt last_action und aktualisiert den Zeitstempel."""
        self.last_action = text
        self.last_action_ts = time.time()

    # ── Self-Adjusting Wait ──────────────────────────────────────────────────

    async def _wait_for_target(self, target: float, ac_charge_mode: bool = False) -> None:
        """Wartet bis actual_power den Zielwert erreicht, oder max wait_time."""
        s = self.settings
        wait_max = float(s.get(S_WAIT_TIME, 3))

        if not s.get(S_SELF_ADJUST, False):
            await asyncio.sleep(wait_max)
            return

        tolerance = float(s.get(S_SELF_ADJUST_TOL, 2))
        actual_eid = self.entry.data.get(CONF_ACTUAL_SENSOR, "")

        compare_target = -target if ac_charge_mode else target

        await asyncio.sleep(1.0)

        start = time.monotonic()
        remaining = wait_max - 1.0

        while remaining > 0:
            actual = self._flt(actual_eid)
            if abs(actual - compare_target) <= tolerance:
                _LOGGER.debug(
                    "Solakon: Zielwert erreicht (actual=%.0f, target=%.0f) nach %.1fs",
                    actual, compare_target, time.monotonic() - start,
                )
                return
            await asyncio.sleep(min(1.0, remaining))
            remaining = wait_max - (time.monotonic() - start)

        _LOGGER.debug(
            "Solakon: Max-Wartezeit (%.0fs), actual=%.0f, target=%.0f",
            wait_max, self._flt(actual_eid), compare_target,
        )

    # ── StdDev-Berechnung (Ringpuffer) ───────────────────────────────────────

    def _update_stddev(self, grid_value: float) -> None:
        """Neuen Grid-Messwert in Ringpuffer aufnehmen und StdDev berechnen."""
        now = time.monotonic()
        window = int(self.settings.get(S_STDDEV_WINDOW, 60))
        cutoff = now - window

        self._grid_samples.append((now, grid_value))

        while self._grid_samples and self._grid_samples[0][0] < cutoff:
            self._grid_samples.popleft()

        n = len(self._grid_samples)
        if n < 2:
            self.grid_stddev = 0.0
            return

        values = [s[1] for s in self._grid_samples]
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        self.grid_stddev = round(variance ** 0.5, 1)

    # ── Dynamic Offset-Berechnung ────────────────────────────────────────────

    def _calc_dynamic_offset(
        self, stddev: float, min_off: int, max_off: int,
        noise: float, factor: float, negative: bool,
    ) -> float:
        """Offset = clamp(min + max(0, (StdDev − Rausch) × Faktor), min, max)."""
        if stddev < 0:
            result = min_off
        else:
            buf = max(0.0, (stddev - noise) * factor)
            result = min(max(min_off, round(min_off + buf)), max_off)
        return float(result * (-1 if negative else 1))

    def _update_dynamic_offsets(self) -> None:
        """Dynamische Offsets für alle drei Zonen berechnen."""
        s = self.settings
        sd = self.grid_stddev

        self.dyn_offset_z1 = self._calc_dynamic_offset(
            sd, int(s[S_DYN_Z1_MIN]), int(s[S_DYN_Z1_MAX]),
            float(s[S_DYN_Z1_NOISE]), float(s[S_DYN_Z1_FACTOR]),
            bool(s[S_DYN_Z1_NEGATIVE]),
        )
        self.dyn_offset_z2 = self._calc_dynamic_offset(
            sd, int(s[S_DYN_Z2_MIN]), int(s[S_DYN_Z2_MAX]),
            float(s[S_DYN_Z2_NOISE]), float(s[S_DYN_Z2_FACTOR]),
            bool(s[S_DYN_Z2_NEGATIVE]),
        )
        self.dyn_offset_ac = self._calc_dynamic_offset(
            sd, int(s[S_DYN_AC_MIN]), int(s[S_DYN_AC_MAX]),
            float(s[S_DYN_AC_NOISE]), float(s[S_DYN_AC_FACTOR]),
            bool(s[S_DYN_AC_NEGATIVE]),
        )

    # ── State-Helpers ────────────────────────────────────────────────────────

    def _flt(self, entity_id: str, default: float = 0.0) -> float:
        """Sicher Float-Wert aus HA-State lesen."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return default
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return default

    def _str(self, entity_id: str) -> str:
        """State als String lesen, 'unknown' bei Fehler."""
        state = self.hass.states.get(entity_id)
        return state.state if state and state.state not in ("unknown", "unavailable") else "unknown"

    def _entity_ok(self, entity_id: str) -> bool:
        """Prüft ob Entity verfügbar und nicht unknown/unavailable ist."""
        state = self.hass.states.get(entity_id)
        return state is not None and state.state not in ("unknown", "unavailable")

    # ── Modbus-Schreibbefehle (nur wenn regulation_enabled) ──────────────────

    async def _set_number(self, entity_id: str, value: float) -> None:
        """number.set_value — nur wenn Regulation aktiviert."""
        if not self.settings.get(S_REGULATION_ENABLED, False):
            return
        await self.hass.services.async_call(
            "number", "set_value",
            {"entity_id": entity_id, "value": value},
        )

    async def _set_mode(self, mode: str) -> None:
        """select.select_option — nur wenn Regulation aktiviert."""
        if not self.settings.get(S_REGULATION_ENABLED, False):
            return
        await self.hass.services.async_call(
            "select", "select_option",
            {"entity_id": self.entry.data[CONF_MODE_SELECT], "option": mode},
        )

    async def _set_output(self, value: float) -> None:
        """Ausgangsleistung setzen (min 0 W)."""
        await self._set_number(self.entry.data[CONF_ACTIVE_POWER], max(0, round(value)))
        self.last_output_ts = time.time()

    async def _set_discharge(self, amps: float) -> None:
        """Entladestrom setzen — nur wenn aktueller Wert abweicht."""
        current = self._flt(self.entry.data[CONF_DISCHARGE_CURRENT], -1)
        if abs(current - amps) > 0.5:
            await self._set_number(self.entry.data[CONF_DISCHARGE_CURRENT], amps)

    async def _timer_toggle(self) -> None:
        """Timer-Wechsel 3598↔3599 — erzwingt sichere Modus-Übernahme."""
        timer_eid = self.entry.data[CONF_TIMEOUT_SET]
        current = self._flt(timer_eid, 3599)
        new_val = 3598.0 if current >= 3599 else 3599.0
        await self._set_number(timer_eid, new_val)
        await asyncio.sleep(1)

    # ── Haupt-Trigger ────────────────────────────────────────────────────────

    @callback
    def _on_state_change(self, event: Event) -> None:
        self.hass.async_create_task(self._async_regulate())

    async def _async_regulate(self) -> None:
        """Komplette Regelschleife."""
        if self._lock.locked():
            return
        async with self._lock:
            try:
                await self._run_regulation_cycle()
            except Exception:
                _LOGGER.exception("Solakon: Fehler in Regelschleife")

    # ── Regelzyklus ──────────────────────────────────────────────────────────

    async def _run_regulation_cycle(self) -> None:
        cfg = self.entry.data
        s = self.settings

        # ── 1. Sensor-Werte lesen ────────────────────────────────────────────
        soc = self._flt(cfg[CONF_SOC_SENSOR])
        grid = self._flt(cfg[CONF_GRID_SENSOR])
        solar = self._flt(cfg[CONF_SOLAR_SENSOR])
        actual = self._flt(cfg[CONF_ACTUAL_SENSOR])
        current_power = self._flt(cfg[CONF_ACTIVE_POWER])
        mode = self._str(cfg[CONF_MODE_SELECT])
        timer_val = self._flt(cfg[CONF_TIMEOUT_COUNTDOWN])

        # ── 1b. StdDev aktualisieren + dynamische Offsets berechnen ──────────
        self._update_stddev(grid)
        if any(s.get(k, False) for k in (S_DYN_Z1_ENABLED, S_DYN_Z2_ENABLED, S_DYN_AC_ENABLED)):
            self._update_dynamic_offsets()

        # ── 2. Settings auslesen ─────────────────────────────────────────────
        zone1_limit = int(s[S_ZONE1_LIMIT])
        zone3_limit = int(s[S_ZONE3_LIMIT])
        hard_limit = int(s[S_HARD_LIMIT])
        tolerance = int(s[S_TOLERANCE])
        wait_time = int(s[S_WAIT_TIME])
        p_factor = float(s[S_P_FACTOR])
        i_factor = float(s[S_I_FACTOR])
        pv_reserve = int(s[S_PV_RESERVE])
        discharge_max = int(s[S_DISCHARGE_MAX])

        # Offsets: pro Zone dynamisch oder statisch
        dyn_z1_active = bool(s.get(S_DYN_Z1_ENABLED, False))
        dyn_z2_active = bool(s.get(S_DYN_Z2_ENABLED, False))
        dyn_ac_active = bool(s.get(S_DYN_AC_ENABLED, False))
        offset_1 = self.dyn_offset_z1 if dyn_z1_active else float(s[S_OFFSET_1])
        offset_2 = self.dyn_offset_z2 if dyn_z2_active else float(s[S_OFFSET_2])

        # Überschuss-Parameter
        surplus_enabled = bool(s[S_SURPLUS_ENABLED])
        surplus_threshold = int(s[S_SURPLUS_SOC_THRESHOLD])
        surplus_soc_hyst = int(s[S_SURPLUS_SOC_HYST])
        surplus_pv_hyst = int(s[S_SURPLUS_PV_HYST])

        # AC-Lade-Parameter
        ac_enabled = bool(s[S_AC_ENABLED])
        ac_soc_target = int(s[S_AC_SOC_TARGET])
        ac_power_limit = int(s[S_AC_POWER_LIMIT])
        ac_hysteresis = int(s[S_AC_HYSTERESIS])
        ac_offset_raw = float(s[S_AC_OFFSET])
        ac_offset = self.dyn_offset_ac if dyn_ac_active else ac_offset_raw
        ac_p = float(s[S_AC_P_FACTOR])
        ac_i = float(s[S_AC_I_FACTOR])

        # Tarif-Parameter
        tariff_enabled = bool(s[S_TARIFF_ENABLED])
        tariff_sensor = str(s[S_TARIFF_PRICE_SENSOR])
        tariff_cheap = float(s[S_TARIFF_CHEAP_THRESHOLD])
        tariff_exp = float(s[S_TARIFF_EXP_THRESHOLD])
        tariff_soc = int(s[S_TARIFF_SOC_TARGET])
        tariff_power = int(s[S_TARIFF_POWER])

        # Nacht-Parameter
        night_enabled = bool(s[S_NIGHT_ENABLED])

        # ── 3. Validierung ───────────────────────────────────────────────────
        if zone1_limit <= zone3_limit:
            self.last_error = "SOC-Limits ungültig (Zone1 muss > Zone3)"
            self.notify_listeners()
            return

        if not self._entity_ok(cfg[CONF_SOC_SENSOR]):
            self.last_error = "SOC-Sensor nicht verfügbar"
            self.notify_listeners()
            return

        if not self._entity_ok(cfg[CONF_MODE_SELECT]):
            self.last_error = "Modus-Selektor nicht verfügbar"
            self.notify_listeners()
            return

        self.last_error = ""

        # ── 4. Abgeleitete Variablen ─────────────────────────────────────────
        target_offset = offset_1 if self.cycle_active else offset_2

        if surplus_enabled:
            surplus_entry = (
                soc >= surplus_threshold
                and (solar > (actual + grid + surplus_pv_hyst) or solar == 0)
            )
            surplus_exit = (
                soc < (surplus_threshold - surplus_soc_hyst)
                or solar <= (actual + grid - surplus_pv_hyst)
            )
            new_surplus = (self.surplus_active and not surplus_exit) or surplus_entry
        else:
            new_surplus = False

        is_night = night_enabled and solar < pv_reserve and not self.cycle_active

        tariff_price = 0.0
        tariff_price_valid = False
        if tariff_enabled and tariff_sensor:
            raw = self.hass.states.get(tariff_sensor)
            tariff_price_valid = raw is not None and raw.state not in ("unknown", "unavailable")
            tariff_price = float(raw.state) if tariff_price_valid else 0.0

        # ── 5. Falls / Zonenwechsel ──────────────────────────────────────────
        fall_executed = await self._execute_falls(
            soc=soc, grid=grid, solar=solar, actual=actual, mode=mode,
            current_power=current_power,
            zone1_limit=zone1_limit, zone3_limit=zone3_limit,
            hard_limit=hard_limit, discharge_max=discharge_max,
            surplus_enabled=surplus_enabled, new_surplus=new_surplus,
            surplus_pv_hyst=surplus_pv_hyst,
            ac_enabled=ac_enabled, ac_soc_target=ac_soc_target,
            ac_hysteresis=ac_hysteresis, ac_offset=ac_offset,
            tariff_enabled=tariff_enabled, tariff_price=tariff_price,
            tariff_cheap=tariff_cheap, tariff_exp=tariff_exp,
            tariff_soc=tariff_soc, tariff_power=tariff_power,
            is_night=is_night, pv_reserve=pv_reserve,
        )

        # ── 6. Frische Werte nach Falls ──────────────────────────────────────
        grid = self._flt(cfg[CONF_GRID_SENSOR])
        solar = self._flt(cfg[CONF_SOLAR_SENSOR])
        current_power = self._flt(cfg[CONF_ACTIVE_POWER])
        mode = self._str(cfg[CONF_MODE_SELECT])

        if mode == MODE_AC_CHARGE:
            dynamic_max = ac_power_limit
        elif self.cycle_active:
            dynamic_max = hard_limit
        else:
            dynamic_max = max(0, solar - pv_reserve)

        target_offset = offset_1 if self.cycle_active else offset_2

        at_max_limit = current_power >= hard_limit
        at_min_limit = current_power <= 0

        # ── 7. PI-Gate ───────────────────────────────────────────────────────
        if mode not in (MODE_DISCHARGE, MODE_AC_CHARGE):
            self._update_zone_display(soc, zone1_limit, zone3_limit, mode)
            self.notify_listeners()
            return

        # ── 8. Entladestrom zonenabhängig ────────────────────────────────────
        if self.surplus_active:
            await self._set_discharge(2)
        elif self.ac_charge_active or self.tariff_charge_active:
            await self._set_discharge(0)
        elif self.cycle_active:
            await self._set_discharge(discharge_max)
        else:
            await self._set_discharge(0)

        # ── 9. Timeout-Reset ─────────────────────────────────────────────────
        if timer_val < 120 and self._entity_ok(cfg[CONF_TIMEOUT_COUNTDOWN]):
            await self._timer_toggle()

        # ── PI-Pfade ─────────────────────────────────────────────────────────
        if self.surplus_active:
            await self._set_output(hard_limit)
            self.mode_label = "Überschuss-Einspeisung"
            self._set_last_action(f"Zone 0: Output → {hard_limit} W")
            await self._wait_for_target(hard_limit)

        elif self.ac_charge_active:
            ac_grid_err = grid - ac_offset
            new_pw = current_power
            if abs(ac_grid_err) > tolerance:
                new_pw = self._pi_calculate(
                    grid, current_power, ac_offset, ac_power_limit,
                    tolerance, ac_p, ac_i, ac_charge_mode=True,
                )
                await self._set_output(new_pw)
                self._set_last_action(f"AC-PI: {current_power:.0f} → {new_pw:.0f} W")
            await self._wait_for_target(new_pw, ac_charge_mode=True)

        elif self.tariff_charge_active:
            await self._set_output(tariff_power)
            self._set_last_action(f"Tarif-Laden: {tariff_power} W")

        else:
            grid_error = grid - target_offset
            grid_error_abs = abs(grid_error)

            if grid_error_abs > tolerance and not (at_max_limit and grid_error > 0) and not (at_min_limit and grid_error < 0):
                new_pw = self._pi_calculate(
                    grid, current_power, target_offset, dynamic_max,
                    tolerance, p_factor, i_factor, ac_charge_mode=False,
                )
                await self._set_output(new_pw)
                self._set_last_action(f"PI: {current_power:.0f} → {new_pw:.0f} W")
                await self._wait_for_target(new_pw)
            else:
                if abs(self.integral) > 10:
                    self.integral *= 0.95
                    self._set_last_action("Integral-Decay (5%)")

        # ── 10. Persistieren + Display ───────────────────────────────────────
        await self._save_integral()
        self._update_zone_display(soc, zone1_limit, zone3_limit, mode)
        self.notify_listeners()

    # ── Falls (Zonenwechsel-Logik) ───────────────────────────────────────────

    async def _execute_falls(self, **v) -> str | None:
        """Prüft alle Falls in Reihenfolge. Gibt den Fall-Name zurück oder None."""

        soc = v["soc"]
        mode = v["mode"]
        grid = v["grid"]
        actual = v["actual"]
        zone1 = v["zone1_limit"]
        zone3 = v["zone3_limit"]
        hard = v["hard_limit"]
        discharge_max = v["discharge_max"]

        # ── Fall 0A: Surplus Entry ───────────────────────────────────────────
        if v["surplus_enabled"] and v["new_surplus"] and not self.surplus_active:
            self.surplus_active = True
            if self.cycle_active:
                await self._set_discharge(2)
            self._set_last_action("Zone 0: Surplus aktiviert")
            return "0A"

        # ── Fall 0B: Surplus Exit ────────────────────────────────────────────
        if v["surplus_enabled"] and self.surplus_active and not v["new_surplus"]:
            self.surplus_active = False
            self.integral = 0.0
            if self.cycle_active:
                await self._set_discharge(discharge_max)
            self._set_last_action("Zone 0: Surplus beendet")
            return "0B"

        # ── Fall A: Zone 1 Start ─────────────────────────────────────────────
        if (
            not self.ac_charge_active
            and v.get("tariff_price_valid", False)
            and not self.tariff_charge_active
            and not (v["tariff_enabled"] and v["tariff_price"] < v["tariff_exp"])
            and soc > zone1
            and not self.cycle_active
        ):
            self.integral = 0.0
            self.cycle_active = True
            self.surplus_active = False
            self.ac_charge_active = False
            self.tariff_charge_active = False
            await self._timer_toggle()
            await self._set_mode(MODE_DISCHARGE)
            self._set_last_action(f"Fall A: Zone 1 Start (SOC {soc:.0f}%)")
            return "A"

        # ── Fall B: Zone 3 Stop (Zyklus on) ──────────────────────────────────
        if (
            not self.ac_charge_active
            and not self.tariff_charge_active
            and soc < zone3
            and self.cycle_active
        ):
            self.integral = 0.0
            self.cycle_active = False
            self.surplus_active = False
            self.ac_charge_active = False
            self.tariff_charge_active = False
            await self._set_output(0)
            await self._set_mode(MODE_DISABLED)
            self._set_last_action(f"Fall B: Zone 3 Stop (SOC {soc:.0f}%)")
            return "B"

        # ── Fall C: Zone 3 Absicherung ───────────────────────────────────────
        if (
            not self.ac_charge_active
            and not self.tariff_charge_active
            and soc < zone3
            and not self.cycle_active
            and mode != MODE_DISABLED
        ):
            self.surplus_active = False
            self.ac_charge_active = False
            self.tariff_charge_active = False
            await self._set_output(0)
            await self._set_mode(MODE_DISABLED)
            self._set_last_action("Fall C: Zone 3 Absicherung")
            return "C"

        # ── Fall D: Recovery ─────────────────────────────────────────────────
        # Tarif-Lock blockiert Recovery für normalen Discharge (ac_charge_active-Recovery bleibt erlaubt)
        if (
            (self.cycle_active or self.ac_charge_active)
            and mode not in (MODE_DISCHARGE, MODE_AC_CHARGE)
            and soc > zone3
            and not (
                not self.ac_charge_active
                and not self.tariff_charge_active
                and v.get("tariff_price_valid", False)
                and v["tariff_enabled"]
                and v["tariff_price"] >= v["tariff_cheap"]
                and v["tariff_price"] < v["tariff_exp"]
            )
        ):
            await self._timer_toggle()
            if self.ac_charge_active or self.tariff_charge_active:
                await self._set_mode(MODE_AC_CHARGE)
            else:
                await self._set_mode(MODE_DISCHARGE)
            self._set_last_action("Fall D: Recovery")
            return "D"

        # ── Fall GT: Tarif-Laden Start ───────────────────────────────────────
        # Überschuss-Einspeisung hat Vorrang — kein Tarif-Laden während Zone 0 aktiv
        if (
            v["tariff_enabled"]
            and v.get("tariff_price_valid", False)
            and v["tariff_price"] < v["tariff_cheap"]
            and soc < v["tariff_soc"]
            and not self.tariff_charge_active
            and not self.surplus_active
            and mode != MODE_AC_CHARGE
        ):
            self.tariff_charge_active = True
            self.cycle_active = True
            await self._timer_toggle()
            await self._set_output(0)
            await self._set_mode(MODE_AC_CHARGE)
            self._set_last_action(f"Fall GT: Tarif-Laden (Preis {v['tariff_price']:.1f})")
            return "GT"

        # ── Fall HT: Tarif-Laden Ende ────────────────────────────────────────
        if (
            self.tariff_charge_active
            and (
                soc >= v["tariff_soc"]
                or (v.get("tariff_price_valid", False) and v["tariff_price"] >= v["tariff_cheap"])
            )
        ):
            self.integral = 0.0
            self.tariff_charge_active = False
            if self.cycle_active:
                await self._set_output(0)
                await self._timer_toggle()
                await self._set_mode(MODE_DISCHARGE)
            else:
                await self._set_output(0)
                await self._set_mode(MODE_DISABLED)
            self._set_last_action("Fall HT: Tarif-Laden beendet")
            return "HT"

        # ── Mittlere Tarifstufe — Discharge-Lock ─────────────────────────────
        # Sperrt Zone 1 und Zone 2 (cycle_active egal). Überschuss hat Vorrang.
        if (
            v["tariff_enabled"]
            and v.get("tariff_price_valid", False)
            and v["tariff_price"] >= v["tariff_cheap"]
            and v["tariff_price"] < v["tariff_exp"]
            and not self.tariff_charge_active
            and not self.ac_charge_active
            and not self.surplus_active
            and mode == MODE_DISCHARGE
        ):
            self.integral = 0.0
            await self._set_output(0)
            await self._set_mode(MODE_DISABLED)
            self._set_last_action(f"Tarif: Discharge-Lock (Preis {v['tariff_price']:.1f})")
            return "TM"

        # ── Fall G: AC Laden Start ───────────────────────────────────────────
        # Überschuss-Einspeisung hat Vorrang — kein AC Laden während Zone 0 aktiv
        if (
            v["ac_enabled"]
            and not self.ac_charge_active
            and not self.tariff_charge_active
            and not self.surplus_active
            and soc < v["ac_soc_target"]
            and mode != MODE_AC_CHARGE
            and (grid + actual) < -v["ac_hysteresis"]
        ):
            self.ac_charge_active = True
            await self._timer_toggle()
            await self._set_output(0)
            await self._set_mode(MODE_AC_CHARGE)
            self._set_last_action("Fall G: AC Laden Start")
            return "G"

        # ── Fall H: AC Laden Ende ────────────────────────────────────────────
        if (
            mode == MODE_AC_CHARGE
            and self.ac_charge_active
            and not self.tariff_charge_active
            and (
                soc >= v["ac_soc_target"]
                or (grid >= (v["ac_offset"] + v["ac_hysteresis"]) and actual == 0)
            )
        ):
            self.integral = 0.0
            self.ac_charge_active = False
            if self.cycle_active:
                await self._set_output(0)
                await self._timer_toggle()
                await self._set_mode(MODE_DISCHARGE)
            else:
                await self._set_output(0)
                await self._set_mode(MODE_DISABLED)
            self._set_last_action("Fall H: AC Laden Ende")
            return "H"

        # ── Fall I: Safety — Modus '3' ohne aktive Lade-Session ──────────────
        if (
            mode == MODE_AC_CHARGE
            and not self.ac_charge_active
            and not self.tariff_charge_active
        ):
            self.integral = 0.0
            if self.cycle_active:
                await self._set_output(0)
                await self._timer_toggle()
                await self._set_mode(MODE_DISCHARGE)
            else:
                await self._set_output(0)
                await self._set_mode(MODE_DISABLED)
            self._set_last_action("Fall I: Safety-Korrektur (Modus 3 ohne Session)")
            return "I"

        # ── Fall E: Zone 2 Start ─────────────────────────────────────────────
        # Tarif-Lock verhindert Re-Aktivierung bei mittlerem/günstigem Preis
        if (
            not self.ac_charge_active
            and not self.tariff_charge_active
            and v.get("tariff_price_valid", False)
            and not (v["tariff_enabled"] and v["tariff_price"] < v["tariff_exp"])
            and zone3 < soc <= zone1
            and not self.cycle_active
            and mode == MODE_DISABLED
            and not v["is_night"]
        ):
            self.integral = 0.0
            await self._timer_toggle()
            await self._set_mode(MODE_DISCHARGE)
            self._set_last_action("Fall E: Zone 2 Start")
            return "E"

        # ── Fall F: Nachtabschaltung ─────────────────────────────────────────
        if (
            not self.ac_charge_active
            and not self.tariff_charge_active
            and v["is_night"]
            and not self.cycle_active
            and mode != MODE_DISABLED
        ):
            self.integral = 0.0
            await self._set_output(0)
            await self._set_mode(MODE_DISABLED)
            self._set_last_action("Fall F: Nachtabschaltung")
            return "F"

        return None

    # ── PI-Berechnung ────────────────────────────────────────────────────────

    def _pi_calculate(
        self,
        grid_power: float,
        current_power: float,
        target_offset: float,
        max_power: float,
        tolerance: float,
        p_factor: float,
        i_factor: float,
        ac_charge_mode: bool = False,
    ) -> float:
        """PI-Regler-Berechnung mit modusabhängiger Fehlerrichtung."""
        if ac_charge_mode:
            raw_error = target_offset - grid_power
        else:
            raw_error = grid_power - target_offset

        if raw_error > 0:
            error = min(raw_error, max_power - current_power)
        else:
            error = max(raw_error, 0 - current_power)

        integral_new = max(-1000, min(1000, self.integral + error))
        self.integral = integral_new

        correction = error * p_factor + integral_new * i_factor
        new_power = current_power + correction

        final = max(0, min(max_power, new_power))
        return round(final, 1)

    # ── Zonen-Display ────────────────────────────────────────────────────────

    def _update_zone_display(
        self, soc: float, zone1: int, zone3: int, mode: str
    ) -> None:
        """Zone-Label und Modus-Label für Panel-Anzeige aktualisieren."""
        if self.surplus_active:
            self.current_zone = 0
            self.zone_label = "Zone 0 — Überschuss-Einspeisung"
        elif self.cycle_active:
            self.current_zone = 1
            self.zone_label = "Zone 1 — Aggressive Entladung"
        elif soc <= zone3:
            self.current_zone = 3
            self.zone_label = "Zone 3 — Sicherheitsstopp"
        else:
            self.current_zone = 2
            self.zone_label = "Zone 2 — Batterieschonend"

        mode_map = {
            MODE_DISABLED: "Disabled",
            MODE_DISCHARGE: "INV Discharge PV Priority",
            MODE_AC_CHARGE: "AC Charge (Netzladung)",
        }
        new_mode_label = mode_map.get(mode, f"Modus: {mode}")
        if new_mode_label != self.mode_label:
            self.mode_label_ts = time.time()
        self.mode_label = new_mode_label
