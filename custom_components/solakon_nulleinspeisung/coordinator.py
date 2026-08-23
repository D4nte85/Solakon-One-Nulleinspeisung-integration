"""Coordinator — vollständige Nulleinspeisung-Regellogik mit Schreibguard."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Callable

from datetime import timedelta

from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.state import state_as_number
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN, STORAGE_VERSION, SETTINGS_DEFAULTS, DIST_DEFAULTS,
    CONF_GRID_SENSOR, CONF_ACTUAL_SENSOR, CONF_SOLAR_SENSOR,
    CONF_SOC_SENSOR, CONF_TIMEOUT_COUNTDOWN, CONF_ACTIVE_POWER,
    CONF_DISCHARGE_CURRENT, CONF_TIMEOUT_SET, CONF_MODE_SELECT, CONF_EXPORT_LIMIT,
    MODE_DISABLED, MODE_DISCHARGE, MODE_AC_CHARGE,
    S_REGULATION_ENABLED,
    S_P_FACTOR, S_I_FACTOR, S_TOLERANCE, S_WAIT_TIME, S_STDDEV_WINDOW,
    S_ZONE1_LIMIT, S_ZONE3_LIMIT, S_DISCHARGE_MAX, S_HARD_LIMIT, S_HARD_LIMIT_Z0, S_HARD_LIMIT_Z1,
    S_OFFSET_1, S_OFFSET_2, S_PV_RESERVE,
    S_SURPLUS_ENABLED, S_SURPLUS_SOC_THRESHOLD, S_SURPLUS_SOC_HYST, S_SURPLUS_PV_HYST,
    S_SURPLUS_FORECAST_ENABLED, S_SURPLUS_FORECAST_SENSOR, S_SURPLUS_FORECAST_THRESHOLD,
    S_SURPLUS_LOCK_ENABLED, S_SURPLUS_LOCK_SENSOR, S_SURPLUS_LOCK_FACTOR,
    S_AC_ENABLED, S_AC_SOC_TARGET, S_AC_POWER_LIMIT, S_AC_HYSTERESIS,
    S_AC_OFFSET, S_AC_P_FACTOR, S_AC_I_FACTOR,
    S_PERIODIC_ENABLED, S_PERIODIC_INTERVAL,
    S_TARIFF_ENABLED, S_TARIFF_PRICE_SENSOR, S_TARIFF_CHEAP_THRESHOLD,
    S_TARIFF_EXP_THRESHOLD, S_TARIFF_SOC_TARGET, S_TARIFF_POWER,
    S_TARIFF_CHEAP_ENTITY, S_TARIFF_EXP_ENTITY,
    S_PV_FORECAST_ENABLED, S_PV_FORECAST_SENSOR, S_PV_FORECAST_THRESHOLD,
    S_ZONE1_FORCE_ENABLED, S_ZONE1_FORCE_SENSOR, S_ZONE1_FORCE_THRESHOLD, S_ZONE1_FORCE_MIN_SOC,
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
        self.active_fall: str = "—"

        # Boolsche Status-Flags
        self.cycle_active: bool = False
        self.surplus_active: bool = False
        self.ac_charge_active: bool = False
        self.tariff_charge_active: bool = False
        self.is_night: bool = False

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

        # Multi-Instanz: zugeteiltes Leistungslimit (None = Einzelbetrieb)
        self.allocated_power: float | None = None
        # Verwertbarer PV-Überschuss: Luft zwischen aktuellem Output und dem
        # Maximum aus Hard-Limit UND aktueller PV-Leistung.
        self.surplus_power: float = 0.0
        # Transienter Warnkanal: von _all_shares() gesetzt wenn der Verteilungsmodus
        # wegen eines fehlenden/ungültigen Fremdinstanz-Sensors degradiert (z. B.
        # capacity → soc, soc/soc_switch → equal) — wird im selben Zyklus sofort
        # nach dem jeweiligen Aufruf in soft_errors übernommen, siehe _run_regulation_cycle.
        self._dist_warning: str = ""
        # Tatsächlich angewandter Verteilungs-Modus des letzten _all_shares()-Aufrufs
        # — kann vom konfigurierten distribution_mode abweichen (Degradation, siehe oben).
        self.dist_mode_effective: str = ""

        # Vorheriger actual-Wert (für Surplus-Einstiegs-Entprellung)
        self._prev_actual: float = 0.0

        # Sperrt den solar==0-Sonderfall-Eintritt nach einem Austritt, bis wieder
        # echtes Solar > 0 gemessen wurde
        self._solar_zero_entry_armed: bool = True

        # Interne Mechanik
        self._timer_toggled_in_cycle: bool = False
        self._lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._unsub_trackers: list[Callable] = []
        self._tariff_unsub = None
        self._periodic_unsub = None
        # Ein Listener für beide Features, die das gemergte "PV-Vorhersage heute"-Feld
        # lesen (Surplus-Forecast-Erzwingung + Tarif-Lock-Unterdrückung), siehe
        # _update_pv_forecast_tracker() / _effective_pv_forecast_today_sensor().
        self._forecast_unsub = None
        self.forecast_tariff_suppressed: bool = False
        self.forecast_surplus_forced: bool = False
        self._surplus_lock_unsub = None
        self.forecast_exit_lock: bool = False
        self._zone1_force_unsub = None
        self.zone1_forced: bool = False

    # ── Setup / Teardown ─────────────────────────────────────────────────────

    async def async_setup(self) -> None:
        """Einstellungen laden, State-Listener starten."""
        stored = await self._store.async_load()
        if stored:
            if S_HARD_LIMIT_Z0 not in stored and S_HARD_LIMIT_Z1 not in stored:
                old = stored.get(S_HARD_LIMIT, SETTINGS_DEFAULTS[S_HARD_LIMIT])
                stored[S_HARD_LIMIT_Z0] = old
                stored[S_HARD_LIMIT_Z1] = old
                await self._store.async_save({**SETTINGS_DEFAULTS, **stored})
            # Einmalige Migration: surplus_forecast_sensor und pv_forecast_sensor
            # sind zum gemeinsamen PV-Vorhersage-heute-Feld gemergt — alter Wert
            # übernimmt nur wenn pv_forecast_sensor noch leer ist, kein
            # Datenverlust bei bereits gepflegtem Feld.
            old_surplus_forecast_sensor = stored.get(S_SURPLUS_FORECAST_SENSOR, "")
            if old_surplus_forecast_sensor and not stored.get(S_PV_FORECAST_SENSOR):
                stored[S_PV_FORECAST_SENSOR] = old_surplus_forecast_sensor
                await self._store.async_save({**SETTINGS_DEFAULTS, **stored})
            self.settings = {**SETTINGS_DEFAULTS, **stored}
            self.cycle_active = bool(stored.get("cycle_active", False))
            self.surplus_active = bool(stored.get("surplus_active", False))
            self.ac_charge_active = bool(stored.get("ac_charge_active", False))
            self.tariff_charge_active = bool(stored.get("tariff_charge_active", False))
            self._solar_zero_entry_armed = bool(stored.get("solar_zero_entry_armed", True))
            _LOGGER.debug("Solakon: Einstellungen aus Speicher geladen")
        else:
            self.settings = SETTINGS_DEFAULTS.copy()
            _LOGGER.info("Solakon: Standardwerte geladen")

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
        self._update_periodic_tracker()
        self._update_pv_forecast_tracker()
        self._update_surplus_lock_tracker()
        self._update_zone1_force_tracker()

    async def async_shutdown(self) -> None:
        """Listener abräumen, Integral speichern."""
        for unsub in self._unsub_trackers:
            unsub()
        self._unsub_trackers.clear()
        if self._tariff_unsub:
            self._tariff_unsub()
            self._tariff_unsub = None
        if self._periodic_unsub:
            self._periodic_unsub()
            self._periodic_unsub = None
        if self._forecast_unsub:
            self._forecast_unsub()
            self._forecast_unsub = None
        if self._surplus_lock_unsub:
            self._surplus_lock_unsub()
            self._surplus_lock_unsub = None
        if self._zone1_force_unsub:
            self._zone1_force_unsub()
            self._zone1_force_unsub = None
    # ── Settings-Management ──────────────────────────────────────────────────

    async def async_update_settings(self, changes: dict[str, Any]) -> None:
        turning_off = (
            self.settings.get(S_REGULATION_ENABLED, False)
            and S_REGULATION_ENABLED in changes
            and not changes[S_REGULATION_ENABLED]
        )
        if turning_off:
            # Aufräum-Sequenz solange regulation_enabled noch True ist,
            # danach blockt der Guard alle Modbus-Schreibbefehle
            async with self._lock:
                _LOGGER.info("Solakon: Regelung wird deaktiviert — setze Output 0, Modus Disabled")
                await self._set_output(0)
                await self._set_discharge(float(self.settings.get(S_DISCHARGE_MAX, 40)))
                await self._timer_toggle()
                await self._set_mode(MODE_DISABLED)
                if self.mode_label != "Disabled (Regelung inaktiv)":
                    self.mode_label_ts = time.time()
                self.mode_label = "Disabled (Regelung inaktiv)"

        old_tariff = self._effective_tariff_price_sensor()
        old_tariff_enabled = self.settings.get(S_TARIFF_ENABLED, False)
        old_periodic_en = self.settings.get(S_PERIODIC_ENABLED, False)
        old_periodic_iv = self.settings.get(S_PERIODIC_INTERVAL, 10)
        old_pv = self._effective_pv_forecast_today_sensor()
        old_pv_en = self.settings.get(S_PV_FORECAST_ENABLED, False)
        old_sf_en = self.settings.get(S_SURPLUS_FORECAST_ENABLED, False)
        old_sl = self._effective_surplus_lock_sensor()
        old_sl_en = self.settings.get(S_SURPLUS_LOCK_ENABLED, False)
        old_zf = self._effective_zone1_force_sensor()
        old_zf_en = self.settings.get(S_ZONE1_FORCE_ENABLED, False)

        self.settings.update(changes)
        await self._store.async_save(self._store_data())
        _LOGGER.info("Solakon: Einstellungen gespeichert")

        new_tariff = self._effective_tariff_price_sensor()
        new_tariff_enabled = self.settings.get(S_TARIFF_ENABLED, False)
        if old_tariff != new_tariff or old_tariff_enabled != new_tariff_enabled:
            self._update_tariff_tracker()

        new_periodic_en = self.settings.get(S_PERIODIC_ENABLED, False)
        new_periodic_iv = self.settings.get(S_PERIODIC_INTERVAL, 10)
        if old_periodic_en != new_periodic_en or old_periodic_iv != new_periodic_iv:
            self._update_periodic_tracker()

        new_pv = self._effective_pv_forecast_today_sensor()
        new_pv_en = self.settings.get(S_PV_FORECAST_ENABLED, False)
        new_sf_en = self.settings.get(S_SURPLUS_FORECAST_ENABLED, False)
        if old_pv != new_pv or old_pv_en != new_pv_en or old_sf_en != new_sf_en:
            self._update_pv_forecast_tracker()

        new_sl = self._effective_surplus_lock_sensor()
        new_sl_en = self.settings.get(S_SURPLUS_LOCK_ENABLED, False)
        if old_sl != new_sl or old_sl_en != new_sl_en:
            self._update_surplus_lock_tracker()

        new_zf = self._effective_zone1_force_sensor()
        new_zf_en = self.settings.get(S_ZONE1_FORCE_ENABLED, False)
        if old_zf != new_zf or old_zf_en != new_zf_en:
            self._update_zone1_force_tracker()

        self.notify_listeners()

        # Neuen Zustand sofort anwenden statt erst beim nächsten Sensor-Event.
        if self.settings.get(S_REGULATION_ENABLED, False):
            self.hass.async_create_task(self._async_regulate())

    def _update_tariff_tracker(self) -> None:
        """Tarif-Sensor-Listener dynamisch (de-)registrieren."""
        if self._tariff_unsub:
            self._tariff_unsub()
            self._tariff_unsub = None

        tariff_enabled = self.settings.get(S_TARIFF_ENABLED, False)
        tariff_sensor = self._effective_tariff_price_sensor()

        if tariff_enabled and tariff_sensor:
            self._tariff_unsub = async_track_state_change_event(
                self.hass, [tariff_sensor], self._on_state_change
            )

    def _update_pv_forecast_tracker(self) -> None:
        """PV-Vorhersage-heute-Listener dynamisch (de-)registrieren — gemergtes
        Feld, gemeinsam genutzt von Surplus-Forecast-Erzwingung, Tarif-Lock-
        Unterdrückung (vorher zwei separate Sensoren/Tracker) und zwischen
        0–12 Uhr zusätzlich von der Zone-1-Nacht-Forcierung (_effective_zone1_force_sensor
        fällt in diesem Fenster auf denselben Sensor zurück, eigener Tracker
        bleibt trotzdem aktiv — zwei Listener auf derselben Entity in dem Fenster)."""
        if self._forecast_unsub:
            self._forecast_unsub()
            self._forecast_unsub = None

        enabled = self.settings.get(S_PV_FORECAST_ENABLED, False) or self.settings.get(S_SURPLUS_FORECAST_ENABLED, False)
        sensor = self._effective_pv_forecast_today_sensor()

        if enabled and sensor:
            self._forecast_unsub = async_track_state_change_event(
                self.hass, [sensor], self._on_state_change
            )

    def _update_surplus_lock_tracker(self) -> None:
        if self._surplus_lock_unsub:
            self._surplus_lock_unsub()
            self._surplus_lock_unsub = None

        enabled = self.settings.get(S_SURPLUS_LOCK_ENABLED, False)
        sensor  = self._effective_surplus_lock_sensor()

        if enabled and sensor:
            self._surplus_lock_unsub = async_track_state_change_event(
                self.hass, [sensor], self._on_state_change
            )

    def _update_zone1_force_tracker(self) -> None:
        """Zone-1-Nacht-Forcierung-Listener dynamisch (de-)registrieren.
        Der effektive Sensor wechselt selbst an der Mitternachtsgrenze (siehe
        _effective_zone1_force_sensor) — ein Aufruf hier registriert immer nur den
        aktuell zutreffenden. Der Wechsel um Mitternacht selbst braucht keinen
        Trigger, da bis dahin ohnehin andere Regelzyklen laufen (Grid/Solar/SOC)."""
        if self._zone1_force_unsub:
            self._zone1_force_unsub()
            self._zone1_force_unsub = None

        enabled = self.settings.get(S_ZONE1_FORCE_ENABLED, False)
        sensor  = self._effective_zone1_force_sensor()

        if enabled and sensor:
            self._zone1_force_unsub = async_track_state_change_event(
                self.hass, [sensor], self._on_state_change
            )

    def _store_data(self) -> dict:
        return {
            **self.settings,
            "cycle_active":        self.cycle_active,
            "surplus_active":      self.surplus_active,
            "ac_charge_active":    self.ac_charge_active,
            "tariff_charge_active": self.tariff_charge_active,
            "solar_zero_entry_armed": self._solar_zero_entry_armed,
        }

    # ── Entity-Listener-Pattern ──────────────────────────────────────────────

    def register_entity_listener(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def unregister_entity_listener(self, cb: Callable[[], None]) -> None:
        if cb in self._listeners:
            self._listeners.remove(cb)

    def notify_listeners(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                _LOGGER.exception("Solakon: Fehler in Entity-Listener")

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
            actual = self._flt_power(actual_eid)
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
            wait_max, self._flt_power(actual_eid), compare_target,
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
        if min_off >= max_off:
            result = min_off
        elif stddev < 0:
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
        """Sicher Float-Wert aus HA-State lesen; toleriert Unit-Suffixe."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return default
        try:
            return state_as_number(state)
        except (ValueError, TypeError):
            return default

    def _flt_power(self, entity_id: str, default: float = 0.0) -> float:
        """Float-Wert lesen und bei kW-Sensor auf W normalisieren."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return default
        try:
            value = state_as_number(state)
        except (ValueError, TypeError):
            return default
        if state.attributes.get("unit_of_measurement") == "kW":
            value *= 1000.0
        return value

    def _flt_kilo_normalized(self, entity_id: str, default: float = 0.0) -> float:
        """Float-Wert lesen; k-Präfix-Einheiten (kW, kWh, …) ×1000 normalisieren.
        Nur für Vergleiche gegen einen Watt-Referenzwert (z. B. hard_limit_z0).
        Für kWh-Schwellenfelder (im Panel als kWh beschriftet) stattdessen
        _flt_kwh_normalized() verwenden — sonst vergleicht der ×1000-normalisierte
        Wert gegen eine kWh-Zahl und die Schwelle greift praktisch nie."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return default
        try:
            value = state_as_number(state)
        except (ValueError, TypeError):
            return default
        unit = state.attributes.get("unit_of_measurement", "")
        if unit.startswith("k") or unit.startswith("K"):
            value *= 1000.0
        return value

    def _flt_kwh_normalized(self, entity_id: str, default: float = 0.0) -> float:
        """Float-Wert lesen und auf kWh normalisieren (Wh ÷1000, MWh ×1000).
        Für die kWh-Schwellenfelder (Surplus-/Tarif-/Zone-1-Forecast), deren
        Sensor laut Panel „erwarteten kWh-Ertrag" liefern soll — ein Sensor mit
        Einheit Wh oder MWh soll trotzdem korrekt mit der kWh-Schwelle vergleichbar
        sein. Ohne erkannte Energie-Einheit (z. B. input_number ohne unit_of_measurement)
        bleibt der Rohwert unverändert, wie es der dokumentierte kWh-Vertrag vorsieht."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return default
        try:
            value = state_as_number(state)
        except (ValueError, TypeError):
            return default
        unit = state.attributes.get("unit_of_measurement", "")
        if unit == "Wh":
            value /= 1000.0
        elif unit == "MWh":
            value *= 1000.0
        return value

    def _str(self, entity_id: str) -> str:
        """State als String lesen, 'unknown' bei Fehler."""
        state = self.hass.states.get(entity_id)
        return state.state if state and state.state not in ("unknown", "unavailable") else "unknown"

    def _entity_ok(self, entity_id: str) -> bool:
        """Prüft ob Entity verfügbar und nicht unknown/unavailable ist."""
        state = self.hass.states.get(entity_id)
        return state is not None and state.state not in ("unknown", "unavailable")

    # ── Globale Sensor-Vorgaben ───────────────────────────────────────────────
    # Entity-Picker sind instanzübergreifend im Verteilungs-Tab pflegbar, jede
    # Instanz kann optional lokal überschreiben. Lokal gewinnt, sonst globaler Wert.

    def _global_sensor(self, key: str) -> str:
        return str(self._dist_cfg().get(key, ""))

    def _effective_pv_forecast_today_sensor(self) -> str:
        """PV-Ertrag heute (kWh) — gemergtes Feld, gemeinsam genutzt von
        Surplus-Forecast-Erzwingung UND Tarif-Lock-Unterdrückung."""
        return str(self.settings.get(S_PV_FORECAST_SENSOR, "")) or self._global_sensor("global_pv_forecast_today_sensor")

    def _effective_zone1_force_sensor(self) -> str:
        """PV-Vorhersage für Zone-1-Nacht-Forcierung: vor Mitternacht 'morgen',
        danach 'heute' — derselbe Zieltag, nur der Sensor wechselt."""
        if dt_util.now().hour >= 12:
            return str(self.settings.get(S_ZONE1_FORCE_SENSOR, "")) or self._global_sensor("global_pv_forecast_tomorrow_sensor")
        return self._effective_pv_forecast_today_sensor()

    def _effective_surplus_lock_sensor(self) -> str:
        return str(self.settings.get(S_SURPLUS_LOCK_SENSOR, "")) or self._global_sensor("global_surplus_lock_sensor")

    def _effective_tariff_price_sensor(self) -> str:
        return str(self.settings.get(S_TARIFF_PRICE_SENSOR, "")) or self._global_sensor("global_tariff_price_sensor")

    def _effective_tariff_cheap_entity(self) -> str:
        return str(self.settings.get(S_TARIFF_CHEAP_ENTITY, "")) or self._global_sensor("global_tariff_cheap_entity")

    def _effective_tariff_exp_entity(self) -> str:
        return str(self.settings.get(S_TARIFF_EXP_ENTITY, "")) or self._global_sensor("global_tariff_exp_entity")

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

    def _required_discharge(self, discharge_max: int) -> float:
        """Entladestrom für den aktuellen Regelzustand.

        - Surplus aktiv          → 2 A
        - AC-/Tarif-Laden aktiv  → 0 A
        - Entladezyklus (Zone 1) → max. Entladestrom
        - sonst                  → 0 A
        """
        if self.surplus_active:
            return 2.0
        if self.ac_charge_active or self.tariff_charge_active:
            return 0.0
        if self.cycle_active:
            return float(discharge_max)
        return 0.0

    async def _sync_export_limit(self, target: int) -> None:
        """grid_export_power_limit korrigieren wenn von Soll abgewichen — nur wenn Entity konfiguriert."""
        export_entity = self.entry.data.get(CONF_EXPORT_LIMIT, "")
        if not export_entity:
            return
        current = self._flt(export_entity, -1)
        if abs(current - target) > 0.5:
            _LOGGER.info("Solakon: Export-Limit korrigiert %d → %d W", int(current), target)
            await self._set_number(export_entity, target)

    async def _timer_toggle(self) -> None:
        """Timer-Wechsel 3598↔3599 — erzwingt sichere Modus-Übernahme."""
        timer_eid = self.entry.data[CONF_TIMEOUT_SET]
        current = self._flt(timer_eid, 3599)
        new_val = 3598.0 if current >= 3599 else 3599.0
        await self._set_number(timer_eid, new_val)
        self._timer_toggled_in_cycle = True
        await asyncio.sleep(1)

    # ── Haupt-Trigger ────────────────────────────────────────────────────────

    @callback
    def _on_state_change(self, event: Event) -> None:
        self.hass.async_create_task(self._async_regulate())

    def _update_periodic_tracker(self) -> None:
        """Periodischen Fallback-Trigger (de-)registrieren."""
        if self._periodic_unsub:
            self._periodic_unsub()
            self._periodic_unsub = None

        if not self.settings.get(S_PERIODIC_ENABLED, False):
            return

        interval = max(5, int(self.settings.get(S_PERIODIC_INTERVAL, 10)))
        self._periodic_unsub = async_track_time_interval(
            self.hass, self._on_periodic, timedelta(seconds=interval)
        )

    @callback
    def _on_periodic(self, _now: object) -> None:
        # Periodischer Fallback-Trigger der Regelschleife.
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

        # ── 0. Regelung aktiv? ───────────────────────────────────────────────
        if not s.get(S_REGULATION_ENABLED, False):
            return

        self._timer_toggled_in_cycle = False

        _prev_flags = (self.cycle_active, self.surplus_active, self.ac_charge_active, self.tariff_charge_active, self._solar_zero_entry_armed)

        # ── 1. Sensor-Werte lesen ────────────────────────────────────────────
        # Kernsensoren müssen verfügbar sein — 0.0-Fallback würde Regler fehlleiten
        if not all(self._entity_ok(cfg[k]) for k in (
            CONF_GRID_SENSOR, CONF_SOLAR_SENSOR, CONF_ACTUAL_SENSOR, CONF_SOC_SENSOR
        )):
            _LOGGER.debug("Solakon: Kernsensoren nicht verfügbar, Zyklus übersprungen")
            return

        soc = self._flt(cfg[CONF_SOC_SENSOR])
        grid = self._flt_power(cfg[CONF_GRID_SENSOR])
        solar = self._flt_power(cfg[CONF_SOLAR_SENSOR])
        actual = self._flt_power(cfg[CONF_ACTUAL_SENSOR])
        current_power = self._flt(cfg[CONF_ACTIVE_POWER])
        mode = self._str(cfg[CONF_MODE_SELECT])
        timer_val = self._flt(cfg[CONF_TIMEOUT_COUNTDOWN])

        # ── 1b. StdDev aktualisieren + dynamische Offsets berechnen ──────────
        # StdDev ist eine Eigenschaft der Netzgruppe (des physischen Messpunkts),
        # nicht der einzelnen Instanz — nur der Gruppen-Leader pflegt den
        # Ringpuffer, alle Instanzen übernehmen seinen Wert. Verhindert, dass
        # mehrere Instanzen am selben Sensor unabhängige, leicht phasenversetzte
        # StdDev-Historien berechnen und sich darüber gegenseitig hochschaukeln.
        leader = self._group_leader()
        if leader is self:
            self._update_stddev(grid)
        self.grid_stddev = leader.grid_stddev
        if any(s.get(k, False) for k in (S_DYN_Z1_ENABLED, S_DYN_Z2_ENABLED, S_DYN_AC_ENABLED)):
            self._update_dynamic_offsets()

        # ── 2. Settings auslesen ─────────────────────────────────────────────
        zone1_limit = int(s[S_ZONE1_LIMIT])
        zone3_limit = int(s[S_ZONE3_LIMIT])
        hard_limit_z0 = int(s.get(S_HARD_LIMIT_Z0, s.get(S_HARD_LIMIT, 800)))
        hard_limit_z1 = int(s.get(S_HARD_LIMIT_Z1, s.get(S_HARD_LIMIT, 800)))
        await self._sync_export_limit(max(hard_limit_z0, hard_limit_z1))
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
        tariff_sensor = self._effective_tariff_price_sensor()
        tariff_cheap = float(s[S_TARIFF_CHEAP_THRESHOLD])
        tariff_exp = float(s[S_TARIFF_EXP_THRESHOLD])

        cheap_entity = self._effective_tariff_cheap_entity()
        if cheap_entity:
            raw = self.hass.states.get(cheap_entity)
            if raw and raw.state not in ("unknown", "unavailable"):
                try:
                    tariff_cheap = float(raw.state)
                except (ValueError, TypeError):
                    pass

        exp_entity = self._effective_tariff_exp_entity()
        if exp_entity:
            raw = self.hass.states.get(exp_entity)
            if raw and raw.state not in ("unknown", "unavailable"):
                try:
                    tariff_exp = float(raw.state)
                except (ValueError, TypeError):
                    pass

        # Sammelt Meldungen zu Sensor-gated Features, die trotz aktivem Enable-Flag
        # wegen fehlendem/ungültigem Sensor wirkungslos bleiben — sonst scheitern sie
        # still, ohne dass der Nutzer einen Hinweis bekommt (siehe last_error unten).
        # Vor _compute_distribution() angelegt, damit eine dort erkannte Verteilungs-
        # Degradation (Sensor einer Fremdinstanz fehlt) ebenfalls sichtbar wird.
        soft_errors: list[str] = []

        error_share, allocated_power = self._compute_distribution()
        self.allocated_power = allocated_power
        if self._dist_warning:
            soft_errors.append(self._dist_warning)
        effective_hard    = min(int(allocated_power), hard_limit_z0) if allocated_power is not None else hard_limit_z0
        effective_hard_z1 = min(int(allocated_power), hard_limit_z1) if allocated_power is not None else hard_limit_z1

        # Verwertbarer PV-Überschuss: Luft zwischen dem, was diese Instanz gerade
        # ausgibt, und dem Maximum aus aktuell geltendem Hard-Limit UND aktueller
        # PV-Leistung (mehr als die Sonne liefert, ginge nur zulasten des Akkus —
        # kein "verwertbarer" Überschuss). Geklemmt auf ≥0. Nutzt die Zone des
        # *vorherigen* Zyklus (self.surplus_active ist hier noch nicht aktualisiert)
        # — konsistent, weil `actual` ebenfalls aus dieser Zone stammt.
        self.surplus_power = max(0.0, min(
            effective_hard if self.surplus_active else effective_hard_z1, solar
        ) - actual)

        pv_forecast_enabled = bool(s.get(S_PV_FORECAST_ENABLED, False))
        pv_forecast_threshold = float(s.get(S_PV_FORECAST_THRESHOLD, 0.0))

        surplus_forecast_enabled   = bool(s.get(S_SURPLUS_FORECAST_ENABLED, False))
        surplus_forecast_threshold = float(s.get(S_SURPLUS_FORECAST_THRESHOLD, 0.0))

        # Gemergtes Feld: beide Features lesen denselben "PV-Ertrag
        # heute"-Sensor (lokaler Override oder globaler Verteilungs-Tab-Wert),
        # vorher zwei unabhängig konfigurierbare Sensoren für denselben Werttyp.
        pv_forecast_today_sensor = self._effective_pv_forecast_today_sensor()

        if surplus_forecast_enabled and not pv_forecast_today_sensor:
            soft_errors.append("Surplus-Forecast: Kein Vorhersage-Sensor konfiguriert — Funktion inaktiv")
            self.forecast_surplus_forced = False
        elif surplus_forecast_enabled and pv_forecast_today_sensor:
            if self._entity_ok(pv_forecast_today_sensor):
                # Forcierung nur solange die PV das Ausgangslimit übersteigt (Abregel-Risiko)
                # und der SOC über der Zone-3-Schutzgrenze liegt; sonst greift wieder die
                # normale SOC-/Verbrauchslogik.
                self.forecast_surplus_forced = (
                    self._flt_kwh_normalized(pv_forecast_today_sensor) >= surplus_forecast_threshold
                    and solar > hard_limit_z0
                    and soc > zone3_limit
                )
            else:
                soft_errors.append(f"Surplus-Forecast: Sensor {pv_forecast_today_sensor!r} nicht verfügbar")
                self.forecast_surplus_forced = False
        else:
            self.forecast_surplus_forced = False

        surplus_lock_enabled = bool(s.get(S_SURPLUS_LOCK_ENABLED, False))
        surplus_lock_sensor  = self._effective_surplus_lock_sensor()
        surplus_lock_factor  = float(s.get(S_SURPLUS_LOCK_FACTOR, 1.5))

        if surplus_lock_enabled and not surplus_lock_sensor:
            soft_errors.append("Austritts-Sperre: Kein Leistungs-Vorhersage-Sensor konfiguriert — Funktion inaktiv")
            self.forecast_exit_lock = False
        elif surplus_lock_enabled and surplus_lock_sensor:
            if self._entity_ok(surplus_lock_sensor):
                # Sperrt nur den PV-Austritt aus Zone 0: liegt die Vorhersage deutlich über
                # dem Ausgabelimit, ist ein gemessener PV-Einbruch transient (Wolke) und
                # Zone 0 wird gehalten. Der SOC-Austritt bleibt ungesperrt; die Zone-3-Grenze
                # verhindert ein Ankämpfen gegen den Sicherheitsstopp.
                self.forecast_exit_lock = (
                    self._flt_kilo_normalized(surplus_lock_sensor) >= surplus_lock_factor * hard_limit_z0
                    and soc > zone3_limit
                )
            else:
                soft_errors.append(f"Austritts-Sperre: Sensor {surplus_lock_sensor!r} nicht verfügbar")
                self.forecast_exit_lock = False
        else:
            self.forecast_exit_lock = False

        if pv_forecast_enabled and not pv_forecast_today_sensor:
            soft_errors.append("PV-Vorhersage: Kein Sensor konfiguriert — Funktion inaktiv")
            self.forecast_tariff_suppressed = False
        elif pv_forecast_enabled and pv_forecast_today_sensor:
            if self._entity_ok(pv_forecast_today_sensor):
                self.forecast_tariff_suppressed = (
                    self._flt_kwh_normalized(pv_forecast_today_sensor) >= pv_forecast_threshold
                )
            else:
                soft_errors.append(f"PV-Vorhersage: Sensor {pv_forecast_today_sensor!r} nicht verfügbar")
                self.forecast_tariff_suppressed = False
        else:
            self.forecast_tariff_suppressed = False

        # Zone-1-Nacht-Forcierung: erlaubt Entladung unter das normale
        # Zone-1-Limit, wenn der morgige PV-Ertrag die Nacht ohnehin wieder auffüllt.
        # Sensor wechselt an der Mitternachtsgrenze selbst zwischen "morgen" und
        # "heute" (_effective_zone1_force_sensor) — der Zieltag bleibt derselbe.
        zone1_force_enabled = bool(s.get(S_ZONE1_FORCE_ENABLED, False))
        zone1_force_threshold = float(s.get(S_ZONE1_FORCE_THRESHOLD, 0.0))
        zone1_force_min_soc = int(s.get(S_ZONE1_FORCE_MIN_SOC, 0))
        zone1_force_sensor = self._effective_zone1_force_sensor()

        if zone1_force_enabled and not zone1_force_sensor:
            soft_errors.append("Zone-1-Forcierung: Kein PV-Vorhersage-Sensor konfiguriert — Funktion inaktiv")
            self.zone1_forced = False
        elif zone1_force_enabled and zone1_force_sensor:
            if self._entity_ok(zone1_force_sensor):
                self.zone1_forced = (
                    self._flt_kwh_normalized(zone1_force_sensor) >= zone1_force_threshold
                    and solar < pv_reserve         # "gerade dunkel", gleiche Bedingung wie is_night
                    and soc > zone1_force_min_soc  # eigener Floor, unabhängig von zone3_limit (Exit-Schwelle)
                )
            else:
                soft_errors.append(f"Zone-1-Forcierung: Sensor {zone1_force_sensor!r} nicht verfügbar")
                self.zone1_forced = False
        else:
            self.zone1_forced = False

        effective_tariff_enabled = tariff_enabled and bool(tariff_sensor) and not self.forecast_tariff_suppressed
        tariff_soc = int(s[S_TARIFF_SOC_TARGET])
        tariff_power = int(s[S_TARIFF_POWER])

        # Nacht-Parameter
        night_enabled = bool(s[S_NIGHT_ENABLED])

        # ── 3. Validierung ───────────────────────────────────────────────────
        if zone1_limit <= zone3_limit:
            self.last_error = "SOC-Limits ungültig (Zone1 muss > Zone3)"
            self.notify_listeners()
            return

        if surplus_enabled and surplus_threshold <= zone1_limit:
            self.last_error = "SOC-Limits ungültig (Überschuss-Schwelle muss > Zone1)"
            self.notify_listeners()
            return

        if zone1_force_enabled and not (zone3_limit < zone1_force_min_soc < zone1_limit):
            self.last_error = "SOC-Limits ungültig (Zone-1-Forcierung-Mindest-SOC muss zwischen Zone3 und Zone1 liegen)"
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

        if tariff_enabled and not tariff_sensor:
            soft_errors.append("Tarif: Kein Preis-Sensor konfiguriert — Tarif-Funktion inaktiv")
        elif tariff_enabled and tariff_sensor and not self._entity_ok(tariff_sensor):
            soft_errors.append(f"Tarif: Preis-Sensor {tariff_sensor!r} nicht verfügbar")

        # Verkettet statt überschrieben — mehrere gleichzeitig fehlkonfigurierte
        # Sensor-Features sollen alle sichtbar sein, nicht nur der zuletzt geprüfte.
        self.last_error = " • ".join(soft_errors)

        # ── 4. Abgeleitete Variablen ─────────────────────────────────────────
        target_offset = offset_1 if self.cycle_active else offset_2

        prev_actual = self._prev_actual
        self._prev_actual = actual

        total_actual = self._total_actual_power()

        if surplus_enabled:
            if solar > 0:
                self._solar_zero_entry_armed = True

            # Lastanteil dieser Instanz für Ein- und Austritt: (Σactual + grid) × error_share.
            consumption_share = (total_actual + grid) * error_share
            pv_hyst_share = surplus_pv_hyst * error_share

            normal_entry = (
                soc >= surplus_threshold
                and (
                    solar > (consumption_share + pv_hyst_share)
                    or (
                        solar == 0
                        and actual == 0
                        and prev_actual == 0
                        and self._solar_zero_entry_armed
                    )
                )
            )
            # Forcierung ist bereits an solar > hard_limit_z0 gekoppelt → SOC-unabhängiger Eintritt.
            surplus_entry = normal_entry or self.forecast_surplus_forced

            # Austritt: bei aktiver Forcierung gesperrt (SOC- und Verbrauchsterm ausgeklammert),
            # sonst normal über SOC- oder Verbrauchsschwelle. Der Exit-Lock sperrt nur den
            # Verbrauchsterm — der SOC-Austritt greift immer.
            soc_exit = soc < (surplus_threshold - surplus_soc_hyst)
            power_exit = solar <= (consumption_share - pv_hyst_share) and not self.forecast_exit_lock
            surplus_exit = not self.forecast_surplus_forced and (soc_exit or power_exit)
            if self.surplus_active:
                new_surplus = not surplus_exit
                if surplus_exit and solar == 0:
                    self._solar_zero_entry_armed = False
            else:
                new_surplus = surplus_entry
        else:
            new_surplus = False

        is_night = night_enabled and solar < pv_reserve and not self.cycle_active
        self.is_night = is_night

        tariff_price = 0.0
        tariff_price_valid = False
        if tariff_enabled and tariff_sensor:
            raw = self.hass.states.get(tariff_sensor)
            if raw and raw.state not in ("unknown", "unavailable"):
                try:
                    tariff_price = float(raw.state)
                    tariff_price_valid = True
                except (ValueError, TypeError):
                    pass

        # ── 5. Falls / Zonenwechsel ──────────────────────────────────────────
        fall_executed = await self._execute_falls(
            soc=soc, grid=grid, actual=actual, mode=mode,
            zone1_limit=zone1_limit, zone3_limit=zone3_limit,
            surplus_enabled=surplus_enabled, new_surplus=new_surplus,
            ac_enabled=ac_enabled, ac_soc_target=ac_soc_target,
            ac_hysteresis=ac_hysteresis, ac_offset=ac_offset,
            tariff_enabled=effective_tariff_enabled, tariff_price=tariff_price,
            tariff_price_valid=tariff_price_valid,
            tariff_cheap=tariff_cheap, tariff_exp=tariff_exp,
            tariff_soc=tariff_soc, tariff_power=tariff_power,
            is_night=is_night, total_actual=total_actual,
            zone1_forced=self.zone1_forced,
        )
        if fall_executed:
            self.active_fall = fall_executed

        # ── 6. Entladestrom mit Regelzustand abgleichen (vor dem PI-Gate) ────
        await self._set_discharge(self._required_discharge(discharge_max))

        # ── 6b. Frische Werte nach Falls ─────────────────────────────────────
        grid = self._flt_power(cfg[CONF_GRID_SENSOR])
        solar = self._flt_power(cfg[CONF_SOLAR_SENSOR])
        current_power = self._flt(cfg[CONF_ACTIVE_POWER])
        mode = self._str(cfg[CONF_MODE_SELECT])

        if mode == MODE_AC_CHARGE:
            dynamic_max = ac_power_limit
        elif self.cycle_active:
            dynamic_max = effective_hard_z1
        else:
            dynamic_max = min(effective_hard_z1, max(0, solar - pv_reserve))

        target_offset = offset_1 if self.cycle_active else offset_2

        at_max_limit = current_power >= dynamic_max
        at_min_limit = current_power <= 0
        above_dynamic_max = current_power > dynamic_max

        # ── 7. PI-Gate ───────────────────────────────────────────────────────
        if mode not in (MODE_DISCHARGE, MODE_AC_CHARGE):
            self._update_zone_display(soc, zone1_limit, zone3_limit, mode)
            if (self.cycle_active, self.surplus_active, self.ac_charge_active, self.tariff_charge_active, self._solar_zero_entry_armed) != _prev_flags:
                self._store.async_delay_save(self._store_data, 5)
            self.notify_listeners()
            return

        # ── 9. Timeout-Reset ─────────────────────────────────────────────────
        # Entfällt wenn ein Fall in diesem Zyklus bereits getoggelt hat (timer_val wäre stale)
        if timer_val < 120 and not self._timer_toggled_in_cycle and self._entity_ok(cfg[CONF_TIMEOUT_COUNTDOWN]):
            await self._timer_toggle()

        # Eigener Pool für AC-Laden — erst nach den Falls berechnet, damit ein in
        # diesem Zyklus per Fall G neu gesetztes ac_charge_active bereits zählt.
        ac_error_share = self._compute_ac_distribution()
        if self._dist_warning:
            soft_errors.append(self._dist_warning)
            self.last_error = " • ".join(soft_errors)

        # ── PI-Pfade ─────────────────────────────────────────────────────────
        if self.surplus_active:
            # Nur schreiben wenn der Ist-Sollwert abweicht — kein Modbus-Traffic im eingeschwungenen Zustand
            if abs(current_power - effective_hard) > 0.5:
                await self._set_output(effective_hard)
                self._set_last_action(f"Zone 0: Output → {effective_hard} W")
                await self._wait_for_target(effective_hard)

        elif self.ac_charge_active:
            ac_grid_err = grid - ac_offset
            if abs(ac_grid_err) > tolerance:
                ac_power_base = self._total_commanded_ac_power() * ac_error_share
                new_pw = self._pi_calculate(
                    grid, ac_power_base, ac_offset, ac_power_limit,
                    tolerance, ac_p, ac_i, ac_charge_mode=True,
                    error_share=ac_error_share,
                )
                await self._set_output(new_pw)
                self._set_last_action(f"AC-PI: {current_power:.0f} → {new_pw:.0f} W")
                await self._wait_for_target(new_pw, ac_charge_mode=True)
            else:
                if abs(self.integral) > 10:
                    self.integral *= 0.95

        elif self.tariff_charge_active:
            await self._set_output(tariff_power)
            self._set_last_action(f"Tarif-Laden: {tariff_power} W")

        else:
            grid_error = grid - target_offset
            grid_error_abs = abs(grid_error)

            if grid_error_abs > tolerance and not (at_max_limit and not above_dynamic_max and grid_error > 0) and not (at_min_limit and grid_error < 0):
                power_base = self._total_commanded_power() * error_share
                new_pw = self._pi_calculate(
                    grid, power_base, target_offset, dynamic_max,
                    tolerance, p_factor, i_factor, ac_charge_mode=False,
                    error_share=error_share,
                )
                await self._set_output(new_pw)
                self._set_last_action(f"PI: {current_power:.0f} → {new_pw:.0f} W")
                await self._wait_for_target(new_pw)
            else:
                if abs(self.integral) > 10:
                    self.integral *= 0.95

        # ── 10. Display + Flag-Persistenz ────────────────────────────────────
        self._update_zone_display(soc, zone1_limit, zone3_limit, mode)
        if (self.cycle_active, self.surplus_active, self.ac_charge_active, self.tariff_charge_active, self._solar_zero_entry_armed) != _prev_flags:
            self._store.async_delay_save(self._store_data, 5)
        self.notify_listeners()

    # ── Falls (Zonenwechsel-Logik) ───────────────────────────────────────────

    async def _execute_falls(self, **v) -> str | None:
        """Prüft alle Falls in Reihenfolge. Gibt den Fall-Name zurück oder None."""

        soc = v["soc"]
        mode = v["mode"]
        grid = v["grid"]
        actual = v["actual"]
        total_actual = v["total_actual"]
        zone1 = v["zone1_limit"]
        zone3 = v["zone3_limit"]

        # ── Fall 0A: Surplus Entry ───────────────────────────────────────────
        if (
            v["surplus_enabled"]
            and v["new_surplus"]
            and not self.surplus_active
            and not self.ac_charge_active
            and not self.tariff_charge_active
        ):
            # Zone 0 setzt immer auf einem aktiven Zone-1-Zyklus auf
            self.surplus_active = True
            self.cycle_active = True
            if mode != MODE_DISCHARGE:
                await self._timer_toggle()
                await self._set_mode(MODE_DISCHARGE)
            self._set_last_action("Zone 0: Surplus aktiviert")
            return "0A"

        # ── Fall 0B: Surplus Exit ────────────────────────────────────────────
        # Austritt bei erfüllter Austritts-Bedingung oder deaktivierter Überschuss-Option.
        if self.surplus_active and (not v["surplus_enabled"] or not v["new_surplus"]):
            self.surplus_active = False
            # Zone nach Overlay-Ende aus dem SOC ableiten
            self.cycle_active = soc > zone1
            self.integral = 0.0
            await self._set_output(0)
            self._set_last_action("Zone 0: Surplus beendet")
            return "0B"

        # ── Fall A: Zone 1 Start ─────────────────────────────────────────────
        # zone1_forced erlaubt den Eintritt auch unter dem normalen
        # Zone-1-Limit, wenn der morgige PV-Ertrag die Nacht ohnehin wieder
        # auffüllt. Reiner Einweg-Trigger für den Eintritt — der Austritt läuft
        # unabhängig davon ausschließlich über Fall B (soc < zone3).
        zone1_forced = v.get("zone1_forced", False)
        if (
            not self.ac_charge_active
            and (not v["tariff_enabled"] or v.get("tariff_price_valid", False))
            and not self.tariff_charge_active
            and not (v["tariff_enabled"] and v.get("tariff_price_valid", False) and v["tariff_price"] < v["tariff_exp"])
            and (soc > zone1 or zone1_forced)
            and not self.cycle_active
        ):
            self.integral = 0.0
            self.cycle_active = True
            self.surplus_active = False
            self.ac_charge_active = False
            self.tariff_charge_active = False
            await self._timer_toggle()
            await self._set_mode(MODE_DISCHARGE)
            if zone1_forced and soc <= zone1:
                self._set_last_action(f"Fall A: Zone 1 Start forciert (SOC {soc:.0f}%, Vorhersage morgen gut)")
            else:
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
            await self._timer_toggle()
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
            await self._timer_toggle()
            await self._set_mode(MODE_DISABLED)
            self._set_last_action("Fall C: Zone 3 Absicherung")
            return "C"

        # ── Fall D: Recovery ─────────────────────────────────────────────────
        # Tarif-Lock blockiert Recovery für normalen Discharge (ac/tariff_charge_active-Recovery bleibt erlaubt)
        # Recovery einer aktiven Lade-Session ignoriert die Zone-3-Schwelle — Laden bleibt bei jedem SOC möglich
        tariff_lock_active = (
            v["tariff_enabled"]
            and v.get("tariff_price_valid", False)
            and v["tariff_price"] >= v["tariff_cheap"]
            and v["tariff_price"] < v["tariff_exp"]
            and not self.ac_charge_active
            and not self.tariff_charge_active
            and not self.surplus_active
        )
        charging_session_active = self.ac_charge_active or self.tariff_charge_active
        if (
            (self.cycle_active or charging_session_active)
            and mode not in (MODE_DISCHARGE, MODE_AC_CHARGE)
            and (charging_session_active or soc > zone3)
            and not tariff_lock_active
        ):
            await self._timer_toggle()
            if charging_session_active:
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
            await self._timer_toggle()
            await self._set_output(v["tariff_power"])
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
                await self._timer_toggle()
                await self._set_mode(MODE_DISABLED)
            self._set_last_action("Fall HT: Tarif-Laden beendet")
            return "HT"

        # ── Discharge-Lock (Preis < Teuer-Schwelle) ──────────────────────────
        # Sperrt Zone 1 und Zone 2 solange Preis < teuer (günstig UND mittel).
        if (
            v["tariff_enabled"]
            and v.get("tariff_price_valid", False)
            and v["tariff_price"] < v["tariff_exp"]
            and not self.tariff_charge_active
            and not self.ac_charge_active
            and not self.surplus_active
            and mode == MODE_DISCHARGE
        ):
            self.integral = 0.0
            if self.cycle_active:
                self.cycle_active = False
            await self._set_output(0)
            await self._timer_toggle()
            await self._set_mode(MODE_DISABLED)
            self._set_last_action(f"Tarif: Discharge-Lock (Preis {v['tariff_price']:.1f})")
            return "TM"

        # ── Fall G: AC Laden Start ───────────────────────────────────────────
        # Überschuss-Einspeisung hat Vorrang — kein AC Laden während Zone 0 aktiv
        # total_actual summiert über alle entladenden Instanzen (Einzelbetrieb: eigener Wert)
        if (
            v["ac_enabled"]
            and not self.ac_charge_active
            and not self.tariff_charge_active
            and not self.surplus_active
            and soc < v["ac_soc_target"]
            and mode != MODE_AC_CHARGE
            and (grid + total_actual) < -v["ac_hysteresis"]
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
                or (grid >= (v["ac_offset"] + v["ac_hysteresis"]) and actual <= 0)
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
                await self._timer_toggle()
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
                await self._timer_toggle()
                await self._set_mode(MODE_DISABLED)
            self._set_last_action("Fall I: Safety-Korrektur (Modus 3 ohne Session)")
            return "I"

        # ── Fall E: Zone 2 Start ─────────────────────────────────────────────
        if (
            not self.ac_charge_active
            and not self.tariff_charge_active
            and (not v["tariff_enabled"] or v.get("tariff_price_valid", False))
            and not (v["tariff_enabled"] and v.get("tariff_price_valid", False) and v["tariff_price"] < v["tariff_exp"])
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
            await self._timer_toggle()
            await self._set_mode(MODE_DISABLED)
            self._set_last_action("Fall F: Nachtabschaltung")
            return "F"

        return None

    # ── Multi-Instanz Verteilung ─────────────────────────────────────────────

    def _group_coords(self) -> dict[str, "SolakonCoordinator"]:
        """Alle Coordinatoren mit demselben grid_power_sensor wie diese Instanz —
        die Netzgruppe. Instanzen an unterschiedlichen Smartmetern teilen sich
        physisch keinen Netzpunkt und dürfen sich nicht gegenseitig in die
        Verteilung/Summenbildung einrechnen."""
        my_grid = self.entry.data.get(CONF_GRID_SENSOR, "")
        return {
            eid: c for eid, c in self.hass.data.get(DOMAIN, {}).items()
            if c.entry.data.get(CONF_GRID_SENSOR, "") == my_grid
        }

    def _group_leader(self) -> "SolakonCoordinator":
        """Deterministisch bestimmte Instanz der Netzgruppe, die den geteilten
        StdDev-Ringpuffer pflegt — kleinste entry_id unter den Instanzen mit
        aktiver Regelung (Fallback: kleinste entry_id der Gesamtgruppe, falls
        gerade keine aktiv ist). Kein persistenter Zustand: fällt die aktuelle
        Leader-Instanz aus (deaktiviert/entfernt), übernimmt automatisch die
        nächste, ohne Übergabelogik. Einzelinstanz: Leader ist immer sich selbst.
        """
        group = self._group_coords()
        active = {
            eid: c for eid, c in group.items()
            if c.settings.get(S_REGULATION_ENABLED, False)
        } or group
        return active[min(active)]

    def _dist_cfg(self) -> dict:
        """Verteilungs-Config nur der eigenen Netzgruppe, mit Defaults aufgefüllt."""
        all_groups = self.hass.data.get(f"{DOMAIN}_dist_config") or {}
        group_key = self.entry.data.get(CONF_GRID_SENSOR, "")
        return {**DIST_DEFAULTS, **all_groups.get(group_key, {})}

    def _weighted_share(self, active: dict[str, "SolakonCoordinator"]) -> float:
        """SOC-/kapazitätsgewichteter oder gleichverteilter Fehler-Anteil dieser Instanz.

        `active` ist die Menge der aktuell gleichrangig teilnehmenden Instanzen
        (Pool-spezifisch — z. B. alle in Modus '1', oder alle mit aktivem AC-Laden).
        Ist diese Instanz nicht Teil von `active`, bekommt sie keinen Anteil (0.0).
        Dünner Wrapper um _all_shares() für den (häufigeren) Fall, dass nur der
        eigene Anteil gebraucht wird (z. B. AC-Lade-Pool ohne Hard-Limit-Verteilung).
        """
        if self.entry.entry_id not in active:
            return 0.0
        return self._all_shares(active).get(self.entry.entry_id, 0.0)

    def _all_shares(self, active: dict[str, "SolakonCoordinator"]) -> dict[str, float]:
        """SOC-/kapazitätsgewichteter oder gleichverteilter Fehler-Anteil für ALLE
        Instanzen in `active` — Grundlage sowohl für _weighted_share() (eigener
        Anteil) als auch für die Wasserfüll-Verteilung in _compute_distribution()
        (dort werden alle Anteile gleichzeitig gebraucht, um kapp-limitierten
        Instanzen ungenutzten Spielraum an andere weiterzureichen).

        Degradiert ein Modus mangels gültigem Fremdinstanz-Sensor (SOC oder
        Kapazität), wird das in self._dist_warning vermerkt statt still zu
        bleiben — siehe _run_regulation_cycle, das den Kanal in soft_errors überführt.
        """
        n = len(active)
        if n == 0:
            return {}
        eq = 1.0 / n
        dist = self._dist_cfg()
        mode = dist.get("distribution_mode", "equal")
        self.dist_mode_effective = mode

        if n <= 1:
            return {eid: 1.0 for eid in active}

        if mode == "equal":
            return {eid: eq for eid in active}

        if mode == "soc_switch":
            shares = self._soc_switch_shares(active)
            if shares is None:
                self._dist_warning = (
                    "Verteilung (SOC-Switch): SOC-Sensor einer Instanz nicht "
                    "verfügbar — auf Gleichverteilung zurückgefallen"
                )
                self.dist_mode_effective = "equal"
                return {eid: eq for eid in active}
            return shares

        if mode == "capacity":
            def _cap_kwh(eid: str, c) -> float | None:
                cap_s = str(dist.get(f"inst_{eid}_capacity_sensor", ""))
                if not cap_s:
                    return None
                cap_st = c.hass.states.get(cap_s)
                if not cap_st or cap_st.state in ("unknown", "unavailable"):
                    return None
                try:
                    cv = state_as_number(cap_st)
                    # Case-insensitiver Vergleich — HA liefert die Unit i. d. R. als "Wh", nicht "wh".
                    unit = (cap_st.attributes.get("unit_of_measurement") or "").strip().lower()
                    return cv / 1000.0 if unit == "wh" else cv
                except (ValueError, TypeError):
                    return None

            # Kapazitäten pro Instanz; sobald eine keinen gültigen Wert liefert,
            # zählen alle neutral 1.0 (degradiert zu reiner SOC-Gewichtung)
            caps = {eid: _cap_kwh(eid, c) for eid, c in active.items()}
            if any(cap is None for cap in caps.values()):
                self._dist_warning = (
                    "Verteilung: Kapazitätssensor einer Instanz nicht verfügbar "
                    "— auf SOC-Gewichtung zurückgefallen"
                )
                self.dist_mode_effective = "soc"
                caps = {eid: 1.0 for eid in caps}
        else:
            # mode == "soc": reine SOC-Prozentpunkt-Gewichtung, keine
            # Kapazitätssensoren beteiligt.
            caps = {eid: 1.0 for eid in active}

        # SOC-Gewichte: nutzbare kWh (mode "capacity") bzw. nutzbare SOC-% (mode "soc")
        soc_weights: dict[str, float] = {}
        for eid, c in active.items():
            soc_eid = c.entry.data.get(CONF_SOC_SENSOR, "")
            if not c._entity_ok(soc_eid):
                # SOC-Read einer Fremdinstanz unsicher — auf Gleichverteilung ausweichen
                # statt eine falsche 0 in die Gewichtung einfließen zu lassen.
                self._dist_warning = (
                    "Verteilung: SOC-Sensor einer anderen Instanz nicht verfügbar "
                    "— auf Gleichverteilung zurückgefallen"
                )
                self.dist_mode_effective = "equal"
                return {eid: eq for eid in active}
            soc   = c._flt(soc_eid, 0)
            zone3 = float(c.settings.get(S_ZONE3_LIMIT, 20))
            soc_weights[eid] = max(0.0, (soc - zone3) / 100.0 * caps[eid])

        total_soc = sum(soc_weights.values())
        if total_soc <= 0:
            self.dist_mode_effective = "equal"
            return {eid: eq for eid in active}
        return {eid: w / total_soc for eid, w in soc_weights.items()}

    def _soc_switch_shares(self, active: dict[str, "SolakonCoordinator"]) -> dict[str, float] | None:
        """Anteile für Modus `soc_switch`, ein Eintrag je Instanz in `active`.

        Regulärer Fall (keine oder eine Zone-0-Instanz im Pool): exakt eine Instanz
        erhält vollen Anteil, alle anderen 0 — bis ihr SOC seit Übernahme um
        `soc_switch_divergence` Prozentpunkte gefallen ist, dann übernimmt die Instanz
        mit dem höchsten SOC unter den übrigen (Rotation, nie zweimal in Folge dieselbe).
        Zustand ist Pool-weit über einen eigenen Store persistiert (`_soc_switch_state`)
        — getrennt von `_dist_config`, damit ein Speichern der Nutzereinstellungen im
        Verteilungs-Tab diesen Laufzeitzustand nicht überschreibt.

        Zone 0 (Überschuss-Einspeisung) hat absoluten Vorrang vor der regulären
        Entladung anderer Instanzen — konsistent mit dem bestehenden Zone-0-Vorrang
        gegenüber AC-/Tarif-Laden derselben Instanz. Eine einzelne Zone-0-Instanz
        übernimmt bedingungslos und sofort die Führung, ohne Divergenz-Wartezeit (das
        gemeinsame Leistungslimit bleibt dabei unverändert über die reguläre
        `_compute_distribution`-Formel gewahrt, kein Bypass). Sind mehrere Instanzen
        gleichzeitig in Zone 0 (z. B. beide Akkus voll bei gemeinsamem PV-Überschuss),
        teilen sie sich den Anteil gleichmäßig statt exklusiv — bei den kleinen Zone-0-
        Leistungen ist der zusätzliche Wechselrichterverlust vernachlässigbar, und eine
        0-W-Zwangslage mit Abschaltrisiko für eine der beiden wird so vermieden.

        Verlässt die zuletzt aktive Instanz Zone 0 (oder war Zone 0 zuvor mehrfach
        besetzt) und geht in die reguläre Rotation über, wird `start_soc` auf den
        aktuellen SOC neu verankert (`was_zone0`-Flag) — sonst zählt der während
        Zone 0 bereits verbrauchte SOC-Abstand gegen das Divergenz-Budget der
        Rotation und löst den nächsten Wechsel vorzeitig aus, da Zone 0 selbst
        (Ausgabe auf effective_hard, nicht nur den 2-A-Puffer) den SOC spürbar senken kann.

        `None`: eine Fremdinstanz-SOC ist unsicher (unknown/unavailable) — Aufrufer
        weicht dann auf Gleichverteilung aus statt mit einem falschen Wert weiterzurechnen.
        """
        socs: dict[str, float] = {}
        for eid, c in active.items():
            soc_eid = c.entry.data.get(CONF_SOC_SENSOR, "")
            if not c._entity_ok(soc_eid):
                return None
            socs[eid] = c._flt(soc_eid, 0)

        zone0 = {eid for eid, c in active.items() if c.surplus_active}

        state = self.hass.data.get(f"{DOMAIN}_soc_switch_state")
        if state is None:
            state = {"active_id": None, "start_soc": None, "was_zone0": False}
            self.hass.data[f"{DOMAIN}_soc_switch_state"] = state

        was_zone0 = bool(state.get("was_zone0", False))
        active_id = state.get("active_id")
        changed = False

        if len(zone0) > 1:
            result = {eid: (1.0 / len(zone0) if eid in zone0 else 0.0) for eid in socs}
        else:
            dist = self._dist_cfg()
            divergence = float(dist.get("soc_switch_divergence", 5))

            if zone0:
                z0_leader = next(iter(zone0))
                if active_id != z0_leader:
                    active_id, changed = z0_leader, True
                    state["start_soc"] = socs[active_id]
            elif was_zone0 and active_id in socs:
                # Zone 0 gerade verlassen (einzelne oder mehrere Instanzen) — Baseline
                # für die Rotation neu setzen statt mit dem alten Zone-0-Eintrittswert
                # weiterzurechnen.
                state["start_soc"] = socs[active_id]
                changed = True
            elif active_id not in socs:
                active_id = max(socs, key=socs.get)
                state["start_soc"] = socs[active_id]
                changed = True
            elif state.get("start_soc") is None:
                state["start_soc"] = socs[active_id]
                changed = True
            elif state["start_soc"] - socs[active_id] >= divergence:
                remaining = {eid: s for eid, s in socs.items() if eid != active_id}
                active_id = max(remaining, key=remaining.get) if remaining else active_id
                state["start_soc"] = socs[active_id]
                changed = True

            result = {eid: (1.0 if eid == active_id else 0.0) for eid in socs}

        if bool(zone0) != was_zone0:
            state["was_zone0"] = bool(zone0)
            changed = True

        if changed:
            state["active_id"] = active_id
            store = self.hass.data.get(f"{DOMAIN}_soc_switch_store")
            if store is not None:
                snapshot = dict(state)
                store.async_delay_save(lambda: snapshot, 2)

        return result

    def _compute_distribution(self) -> tuple[float, float | None]:
        """Fehler-Anteil + zugeteilte Leistung für Nulleinspeisung-Instanzen (Modus '1').

        Gibt (error_share, allocated_power) zurück.
        Im Einzelbetrieb oder wenn diese Instanz gerade nicht in Modus '1' steht:
        (1.0 bzw. 0.0, None) — kein Einfluss auf hard_limit.

        allocated_power kommt aus einer Wasserfüll-Verteilung (_waterfill_allocate):
        eine rein proportionale Aufteilung von global_max_power nach Anteil würde bei
        heterogenen Hard-Limits (unterschiedlich starke Wechselrichter/Instanzen)
        ungenutzten Spielraum kapp-limitierter Instanzen verschenken statt ihn an
        Instanzen mit Reserve weiterzureichen — der Pool würde global_max_power dann
        strukturell nie erreichen, selbst wenn andere Instanzen noch Kapazität hätten.
        """
        all_coords = self._group_coords()
        active = {
            eid: c for eid, c in all_coords.items()
            if c.settings.get(S_REGULATION_ENABLED, False)
            and c._str(c.entry.data.get(CONF_MODE_SELECT, "")) == MODE_DISCHARGE
        }
        self._dist_warning = ""
        if self.entry.entry_id not in active or len(active) <= 1:
            return (1.0, None) if self.entry.entry_id in active else (0.0, None)

        shares = self._all_shares(active)
        dist = self._dist_cfg()
        global_max = float(dist.get("global_max_power", 800))
        allocations = self._waterfill_allocate(active, shares, global_max)
        return shares.get(self.entry.entry_id, 0.0), allocations.get(self.entry.entry_id)

    def _waterfill_allocate(
        self,
        active: dict[str, "SolakonCoordinator"],
        shares: dict[str, float],
        global_max: float,
    ) -> dict[str, float]:
        """Verteilt global_max proportional zu `shares`, gekappt am lokalen Hard-Limit
        jeder Instanz (Zone-0- oder Zone-1/2-Wert, je nachdem ob die Instanz gerade
        surplus_active ist), und reicht dabei ungenutzten Spielraum kapp-limitierter
        Instanzen iterativ an die übrigen weiter (Wasserfüllverfahren) — terminiert
        garantiert, da pro Runde mindestens eine Instanz endgültig aus dem Rest-Pool
        entfernt wird, sobald `newly_capped` nicht leer ist.
        """
        caps: dict[str, float] = {}
        for eid, c in active.items():
            if c.surplus_active:
                caps[eid] = float(c.settings.get(S_HARD_LIMIT_Z0, c.settings.get(S_HARD_LIMIT, 800)))
            else:
                caps[eid] = float(c.settings.get(S_HARD_LIMIT_Z1, c.settings.get(S_HARD_LIMIT, 800)))

        remaining_ids = set(shares.keys())
        allocations: dict[str, float] = {}
        remaining_power = global_max

        while remaining_ids:
            share_sum = sum(shares[eid] for eid in remaining_ids)
            if share_sum <= 0:
                for eid in remaining_ids:
                    allocations[eid] = 0.0
                break

            newly_capped = [
                eid for eid in remaining_ids
                if remaining_power * (shares[eid] / share_sum) >= caps[eid] - 0.01
            ]

            if not newly_capped:
                for eid in remaining_ids:
                    allocations[eid] = remaining_power * (shares[eid] / share_sum)
                break

            for eid in newly_capped:
                allocations[eid] = caps[eid]
                remaining_power -= caps[eid]
            remaining_ids -= set(newly_capped)

        return {eid: round(v) for eid, v in allocations.items()}

    def _compute_ac_distribution(self) -> float:
        """Fehler-Anteil unter gleichzeitig AC-ladenden Instanzen (Modus '3', `ac_charge_active`).

        Eigener Pool, unabhängig von der Nulleinspeisungs-Verteilung (Modus '1') —
        verhindert, dass mehrere AC-Lader denselben Netzüberschuss doppelt beanspruchen.
        Kein `allocated_power`: das AC-Leistungslimit bleibt unabhängig vom hard_limit.
        """
        all_coords = self._group_coords()
        active = {
            eid: c for eid, c in all_coords.items()
            if c.settings.get(S_REGULATION_ENABLED, False) and c.ac_charge_active
        }
        return self._weighted_share(active)

    def _total_actual_power(self) -> float:
        """Summe der Wechselrichter-Ist-Leistung über alle Nulleinspeisung-Instanzen (Modus '1').

        Einzelbetrieb bzw. kein Modus-'1'-Teilnehmer: eigener actual-Wert.
        """
        all_coords = self._group_coords()
        active = [
            c for c in all_coords.values()
            if c.settings.get(S_REGULATION_ENABLED, False)
            and c._str(c.entry.data.get(CONF_MODE_SELECT, "")) == MODE_DISCHARGE
        ]
        if len(active) <= 1:
            return self._flt_power(self.entry.data.get(CONF_ACTUAL_SENSOR, ""))
        return sum(
            c._flt_power(c.entry.data.get(CONF_ACTUAL_SENSOR, ""))
            for c in active
        )

    def _total_commanded_power(self) -> float:
        """Summe der von allen Nulleinspeisung-Instanzen kommandierten Sollleistung (Modus '1').

        Einzelbetrieb bzw. kein Modus-'1'-Teilnehmer: eigener kommandierter Wert.
        """
        all_coords = self._group_coords()
        active = [
            c for c in all_coords.values()
            if c.settings.get(S_REGULATION_ENABLED, False)
            and c._str(c.entry.data.get(CONF_MODE_SELECT, "")) == MODE_DISCHARGE
        ]
        if len(active) <= 1:
            return self._flt(self.entry.data.get(CONF_ACTIVE_POWER, ""))
        return sum(
            c._flt(c.entry.data.get(CONF_ACTIVE_POWER, ""))
            for c in active
        )

    def _total_commanded_ac_power(self) -> float:
        """Summe der von allen gleichzeitig AC-ladenden Instanzen kommandierten Leistung.

        Einzelbetrieb bzw. keine weitere ladende Instanz: eigener kommandierter Wert.
        """
        all_coords = self._group_coords()
        active = [
            c for c in all_coords.values()
            if c.settings.get(S_REGULATION_ENABLED, False) and c.ac_charge_active
        ]
        if len(active) <= 1:
            return self._flt(self.entry.data.get(CONF_ACTIVE_POWER, ""))
        return sum(
            c._flt(c.entry.data.get(CONF_ACTIVE_POWER, ""))
            for c in active
        )

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
        error_share: float = 1.0,
    ) -> float:
        """PI-Regler-Berechnung mit modusabhängiger Fehlerrichtung und Anti-Windup via Back-Calculation."""
        if ac_charge_mode:
            raw_error = (target_offset - grid_power) * error_share
        else:
            raw_error = (grid_power - target_offset) * error_share

        if raw_error > 0:
            error = min(raw_error, max(0.0, max_power - current_power))
        else:
            error = max(raw_error, 0 - current_power)

        integral_candidate = self.integral + error
        correction = error * p_factor + integral_candidate * i_factor
        new_power = current_power + correction
        final = max(0, min(max_power, new_power))

        if i_factor != 0:
            back_calc = (final - current_power - error * p_factor) / i_factor
            self.integral = max(-max_power, min(max_power, back_calc))
        else:
            self.integral = max(-max_power, min(max_power, integral_candidate))

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
