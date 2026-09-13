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

from .i18n import translate
from .const import (
    DOMAIN, STORAGE_VERSION, SETTINGS_DEFAULTS, DIST_DEFAULTS, DEVICE_MAX_POWER,
    CONF_GRID_SENSOR, CONF_ACTUAL_SENSOR, CONF_SOLAR_SENSOR,
    CONF_SOC_SENSOR, CONF_TIMEOUT_COUNTDOWN, CONF_ACTIVE_POWER,
    CONF_DISCHARGE_CURRENT, CONF_TIMEOUT_SET, CONF_MODE_SELECT, CONF_EXPORT_LIMIT,
    MODE_DISABLED, MODE_DISCHARGE, MODE_AC_CHARGE,
    OUTPUT_STALL_SECONDS, OUTPUT_STALL_DEVIATION,
    TARIFF_UNIT_SUSPECT_PRICE, TARIFF_UNIT_SUSPECT_THRESHOLD, TARIFF_UNIT_SUSPECT_SECONDS,
    S_REGULATION_ENABLED,
    S_P_FACTOR, S_I_FACTOR, S_TOLERANCE, S_WAIT_TIME, S_STDDEV_WINDOW, S_STDDEV_TRIM_COUNT,
    S_ZONE1_LIMIT, S_ZONE3_LIMIT, S_DISCHARGE_MAX, S_HARD_LIMIT_Z0, S_HARD_LIMIT_Z1,
    S_OFFSET_1, S_OFFSET_2, S_PV_RESERVE,
    S_SURPLUS_ENABLED, S_SURPLUS_SOC_THRESHOLD, S_SURPLUS_SOC_HYST, S_SURPLUS_PV_HYST,
    S_SURPLUS_FORECAST_ENABLED, S_SURPLUS_FORECAST_THRESHOLD,
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

# Über Neustarts gespeicherte Zustandsflags: (Speicherschlüssel, Attribut, Default).
PERSISTED_FLAGS = (
    ("cycle_active", "cycle_active", False),
    ("surplus_active", "surplus_active", False),
    ("ac_charge_active", "ac_charge_active", False),
    ("tariff_charge_active", "tariff_charge_active", False),
    ("solar_zero_entry_armed", "_solar_zero_entry_armed", True),
)

# Instanzübergreifend pflegbare Sensor-Vorgaben: (lokaler Settings-Schlüssel, globaler
# Schlüssel der Verteilung). Lokal gewinnt, sonst der globale Wert.
SENSOR_SOURCES = {
    "tariff": (S_TARIFF_PRICE_SENSOR, "global_tariff_price_sensor"),
    "tariff_cheap": (S_TARIFF_CHEAP_ENTITY, "global_tariff_cheap_entity"),
    "tariff_exp": (S_TARIFF_EXP_ENTITY, "global_tariff_exp_entity"),
    "pv_forecast": (S_PV_FORECAST_SENSOR, "global_pv_forecast_today_sensor"),
    "surplus_lock": (S_SURPLUS_LOCK_SENSOR, "global_surplus_lock_sensor"),
    "zone1_force": (S_ZONE1_FORCE_SENSOR, "global_pv_forecast_tomorrow_sensor"),
}

# Zusätzliche Regel-Trigger in Registrierungsreihenfolge: (Name, Aktivierungsschlüssel,
# ODER-verknüpft). "periodic" ist ein Zeitintervall, alle übrigen lauschen auf ihren Sensor.
TRACKERS = (
    ("tariff", (S_TARIFF_ENABLED,)),
    ("periodic", (S_PERIODIC_ENABLED,)),
    ("pv_forecast", (S_PV_FORECAST_ENABLED, S_SURPLUS_FORECAST_ENABLED)),
    ("surplus_lock", (S_SURPLUS_LOCK_ENABLED,)),
    ("zone1_force", (S_ZONE1_FORCE_ENABLED,)),
)


class SolakonSettingsStore(Store):
    """Settings-Store mit Schemamigration."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict
    ) -> dict:
        """Hebt Version 1 auf 2: Hard-Limit aufgespalten, Forecast-Sensor umbenannt."""
        if old_major_version < 2:
            old_limit = old_data.pop("hard_limit", 800)
            old_data.setdefault(S_HARD_LIMIT_Z0, old_limit)
            old_data.setdefault(S_HARD_LIMIT_Z1, old_limit)

            old_forecast = old_data.pop("surplus_forecast_sensor", "")
            if old_forecast and not old_data.get(S_PV_FORECAST_SENSOR):
                old_data[S_PV_FORECAST_SENSOR] = old_forecast
        return old_data


class SolakonCoordinator:
    """Zentrale Logik-Klasse — PI-Regler, SOC-Zonen, Modbus-Steuerung."""

    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        self.hass = hass
        self.entry = entry
        self.settings: dict[str, Any] = SETTINGS_DEFAULTS.copy()
        self._store = SolakonSettingsStore(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")

        # Laufzeit-Zustände
        self.current_zone: int = 2
        self.zone_label: str = translate(hass.config.language, "zone_init")
        self.mode_key: str = "waiting"
        self.mode_label: str = translate(hass.config.language, "mode_waiting")
        self.last_action: str = ""
        self.last_action_key: str = ""
        self.last_action_params: dict = {}
        self.last_error: str = ""
        self.integral: float = 0.0
        self.active_fall: str = ""

        # Boolsche Status-Flags
        self.cycle_active: bool = False
        self.surplus_active: bool = False
        self.ac_charge_active: bool = False
        self.tariff_charge_active: bool = False
        self.is_night: bool = False
        # Entladung durch den Tarif gesperrt (Preis unter Teuer-Schwelle, keine
        # Lade-Session, kein Ueberschuss) — der Zustand hinter Fall TM.
        self.discharge_locked: bool = False
        # Zusammengefasster Betriebszustand fuer Panel und Sensor; "" bis zum
        # ersten Zyklus. Schluessel aus OPERATING_STATES.
        self.operating_state: str = ""
        self.operating_state_ts: float = time.time()
        # Zyklus an einem Guard abgebrochen (Kernsensor fehlt, SOC-Limits ungueltig)
        self._cycle_blocked: bool = False

        # Zeitstempel
        self.last_action_ts: float = time.time()
        self.last_output_ts: float = time.time()
        self.mode_label_ts: float = time.time()

        # StdDev-Ringpuffer für Netz-Standardabweichung
        self._grid_samples: deque[tuple[float, float]] = deque()  # (timestamp, value)
        self.grid_stddev: float = 0.0
        self.grid_stddev_raw: float = 0.0

        # Dynamischer Offset (berechnete Werte pro Zone)
        self.dyn_offset_z1: float = 0.0
        self.dyn_offset_z2: float = 0.0
        self.dyn_offset_ac: float = 0.0

        # Multi-Instanz: zugeteiltes Leistungslimit (None = Einzelbetrieb)
        self.allocated_power: float | None = None
        # Verwertbarer PV-Überschuss: Luft zwischen aktuellem Output und dem
        # Minimum aus Hard-Limit und aktueller PV-Leistung.
        self.surplus_power: float = 0.0
        # Transienter Warnkanal: von _all_shares() gesetzt wenn der Verteilungsmodus
        # wegen eines fehlenden/ungültigen Fremdinstanz-Sensors degradiert (z. B.
        # capacity → soc, soc/soc_switch → equal) — wird im selben Zyklus sofort
        # nach dem jeweiligen Aufruf in soft_errors übernommen, siehe _run_regulation_cycle.
        self._dist_warning: str = ""
        # Analog zu _dist_warning: von _confirm_zero_output() gesetzt wenn eine
        # sicherheitskritische Output-Nullung (Fall-Übergänge, PI-Ziel 0) trotz
        # Retries nicht bestätigt werden konnte — sofort im selben Zyklus nach dem
        # jeweiligen Aufruf in soft_errors übernommen, siehe _run_regulation_cycle.
        self._output_warning: str = ""
        self._output_stall_actions: int = 0
        self._output_stall_last_ts: float = 0.0
        # Beginn der laufenden Verdachtsphase auf eine EUR/kWh-Preiseinheit;
        # 0.0 solange der Preis zur ct/kWh-Schwelle passt.
        self._tariff_unit_suspect_since: float = 0.0
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
        # Abmeldefunktionen der TRACKERS, nach Name
        self._tracker_unsubs: dict[str, Callable] = {}
        self.forecast_tariff_suppressed: bool = False
        self.forecast_surplus_forced: bool = False
        self.forecast_exit_lock: bool = False
        self.zone1_forced: bool = False

    # ── Setup / Teardown ─────────────────────────────────────────────────────

    async def async_setup(self) -> None:
        """Einstellungen laden, State-Listener starten."""
        stored = await self._store.async_load()
        if stored:
            self.settings = {**SETTINGS_DEFAULTS, **stored}
            for key, attr, default in PERSISTED_FLAGS:
                setattr(self, attr, bool(stored.get(key, default)))
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

        for name, _ in TRACKERS:
            self._retrack(name)

    async def async_shutdown(self) -> None:
        """Listener abräumen, Integral speichern."""
        for unsub in self._unsub_trackers:
            unsub()
        self._unsub_trackers.clear()
        for name, _ in TRACKERS:
            self._untrack(name)
    # ── Settings-Management ──────────────────────────────────────────────────

    async def async_update_settings(self, changes: dict[str, Any]) -> None:
        turning_off = (
            self._regulation_on
            and S_REGULATION_ENABLED in changes
            and not changes[S_REGULATION_ENABLED]
        )
        if turning_off:
            # Aufräum-Sequenz solange regulation_enabled noch True ist,
            # danach blockt der Guard alle Modbus-Schreibbefehle
            async with self._lock:
                _LOGGER.info("Solakon: Regelung wird deaktiviert — setze Output 0, Modus Disabled")
                await self._transition(output=0, wait=False, timer=False)
                await self._set_discharge(float(self.settings.get(S_DISCHARGE_MAX, 40)))
                await self._transition(mode=MODE_DISABLED)
                if self.mode_key != "disabled_regulation_off":
                    self.mode_label_ts = time.time()
                self.mode_key = "disabled_regulation_off"
                self.mode_label = self._tr("mode_disabled_regulation_off")

        before = {name: self._tracker_input(name) for name, _ in TRACKERS}

        self.settings.update(changes)
        await self._store.async_save(self._store_data())
        _LOGGER.info("Solakon: Einstellungen gespeichert")

        for name, _ in TRACKERS:
            if self._tracker_input(name) != before[name]:
                self._retrack(name)

        self.notify_listeners()

        # Neuen Zustand sofort anwenden
        if self._regulation_on:
            self.hass.async_create_task(self._async_regulate())

    def _tracker_input(self, name: str) -> tuple:
        """Eingaben eines Triggers: Aktivierungswerte und Sensor bzw. Intervall."""
        keys = dict(TRACKERS)[name]
        target = self.settings.get(S_PERIODIC_INTERVAL, 10) if name == "periodic" else self._effective(name)
        return tuple(self.settings.get(k, False) for k in keys), target

    def _untrack(self, name: str) -> None:
        """Trigger `name` abmelden, falls registriert."""
        unsub = self._tracker_unsubs.pop(name, None)
        if unsub:
            unsub()

    def _retrack(self, name: str) -> None:
        """Trigger `name` abmelden und neu registrieren, wenn aktiviert und Sensor gesetzt.

        Der periodische Trigger läuft im Intervall S_PERIODIC_INTERVAL, mindestens 5 s.
        """
        self._untrack(name)
        if not any(self.settings.get(k, False) for k in dict(TRACKERS)[name]):
            return
        if name == "periodic":
            interval = max(5, int(self.settings.get(S_PERIODIC_INTERVAL, 10)))
            self._tracker_unsubs[name] = async_track_time_interval(
                self.hass, self._on_periodic, timedelta(seconds=interval)
            )
            return
        sensor = self._effective(name)
        if sensor:
            self._tracker_unsubs[name] = async_track_state_change_event(
                self.hass, [sensor], self._on_state_change
            )

    def update_sensor_trackers(self) -> None:
        """Sensorgebundene Trigger neu registrieren, etwa nach geänderten globalen Vorgaben."""
        for name, _ in TRACKERS:
            if name != "periodic":
                self._retrack(name)

    def _persisted_flags(self) -> dict[str, bool]:
        """Gespeicherte Zustandsflags unter ihrem Speicherschlüssel."""
        return {key: getattr(self, attr) for key, attr, _ in PERSISTED_FLAGS}

    def _store_data(self) -> dict:
        return {**self.settings, **self._persisted_flags()}

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
        self._set_last_action("act_integral_reset")
        self.notify_listeners()

    # ── Last-Action Setter ───────────────────────────────────────────────────

    def _tr(self, key: str, **params: object) -> str:
        """Textbaustein in der Sprache der Home-Assistant-Instanz."""
        return translate(self.hass.config.language, key, **params)

    def _set_last_action(self, key: str, **params: object) -> None:
        """Setzt Schlüssel, Parameter und gerenderten Text der letzten Aktion."""
        self.last_action_key = key
        self.last_action_params = params
        self.last_action = self._tr(key, **params)
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
            self.grid_stddev_raw = 0.0
            return

        values = [s[1] for s in self._grid_samples]
        self.grid_stddev_raw = self._stddev_of(values)

        # Getrimmte StdDev: die `trim` größten und kleinsten Samples im Fenster
        # ausschließen, bevor die Streuung berechnet wird.
        trim = int(self.settings.get(S_STDDEV_TRIM_COUNT, 0))
        if trim > 0 and n - 2 * trim >= 2:  # Fallback: mind. 2 Kernwerte nötig, sonst ungetrimmt
            core = sorted(values)[trim: n - trim]
            self.grid_stddev = self._stddev_of(core)
        else:
            self.grid_stddev = self.grid_stddev_raw

    @staticmethod
    def _stddev_of(values: list[float]) -> float:
        """Populations-Standardabweichung einer Werteliste."""
        n = len(values)
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        return round(variance ** 0.5, 1)

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
        """Float-Wert lesen; Einheiten kW/kWh ×1000 normalisieren.
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
        if unit in ("kW", "kWh"):
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

    def _effective(self, name: str) -> str:
        """Wirksamer Sensor aus SENSOR_SOURCES: lokaler Override, sonst globale Vorgabe.

        `zone1_force` liest ab 12 Uhr die Vorhersage für morgen, davor die für heute
        (`pv_forecast`) — derselbe Zieltag, nur der Sensor wechselt.
        """
        if name == "zone1_force" and dt_util.now().hour < 12:
            name = "pv_forecast"
        local, global_key = SENSOR_SOURCES[name]
        return str(self.settings.get(local, "")) or self._global_sensor(global_key)

    def _sensor_usable(self, soft_errors: list[str], enabled: bool, sensor: str, err_prefix: str) -> bool:
        """True, wenn das Feature aktiviert und sein Sensor gesetzt und verfügbar ist.

        Fehlt der Sensor oder ist er nicht verfügbar, geht `<err_prefix>_no_sensor` bzw.
        `<err_prefix>_sensor_unavailable` in die Fehlerkette.
        """
        if not enabled:
            return False
        if not sensor:
            self._add_soft_error(soft_errors, self._tr(f"{err_prefix}_no_sensor"))
            return False
        if not self._entity_ok(sensor):
            self._add_soft_error(soft_errors, self._tr(f"{err_prefix}_sensor_unavailable", sensor=sensor))
            return False
        return True

    def _tariff_unit_warning(self, entity_id: str, price: float, cheap: float) -> str:
        """Meldung, wenn der Preis-Sensor vermutlich €/kWh statt ct/kWh liefert, sonst "".

        Kriterium ist der Wert: ein Preis unter TARIFF_UNIT_SUSPECT_PRICE bei einer
        Günstig-Schwelle ab TARIFF_UNIT_SUSPECT_THRESHOLD ist in ct/kWh kaum erreichbar.
        Einzelne Billigstunden und negative Börsenpreise bleiben ausgenommen: gemeldet
        wird erst nach TARIFF_UNIT_SUSPECT_SECONDS ununterbrochenem Verdacht und nur bei
        price >= 0. `unit_of_measurement` wirkt nur bestätigend — eine ct-Einheit
        unterdrückt die Meldung, eine €-Einheit macht sie sofort. Umgerechnet wird nichts.
        """
        state = self.hass.states.get(entity_id)
        unit = str(state.attributes.get("unit_of_measurement", "")).lower() if state else ""

        if any(token in unit for token in ("ct", "cent", "öre", "ore")):
            self._tariff_unit_suspect_since = 0.0
            return ""

        if not (cheap >= TARIFF_UNIT_SUSPECT_THRESHOLD and 0.0 <= price < TARIFF_UNIT_SUSPECT_PRICE):
            self._tariff_unit_suspect_since = 0.0
            return ""

        now = time.time()
        if not self._tariff_unit_suspect_since:
            self._tariff_unit_suspect_since = now

        euro_unit = any(token in unit for token in ("€", "eur"))
        if not euro_unit and now - self._tariff_unit_suspect_since < TARIFF_UNIT_SUSPECT_SECONDS:
            return ""

        return self._tr("warn_tariff_unit", price=price, cheap=cheap)

    # ── Modbus-Schreibbefehle (nur wenn regulation_enabled) ──────────────────

    @property
    def _regulation_on(self) -> bool:
        """Regelung aktiviert; Voraussetzung für jeden Schreibzugriff."""
        return bool(self.settings.get(S_REGULATION_ENABLED, False))

    async def _set_number(
        self, entity_id: str, value: float, only_if_changed: bool = False,
        current: float | None = None,
    ) -> bool:
        """number.set_value — nur wenn Regulation aktiviert; True wenn geschrieben.

        `only_if_changed` schreibt nur bei Abweichung über 0,5 vom Ist-Wert. Der Ist-Wert
        ist `current` oder wird gelesen (fehlend: -1).
        """
        if not self._regulation_on:
            return False
        if only_if_changed:
            if current is None:
                current = self._flt(entity_id, -1)
            if abs(current - value) <= 0.5:
                return False
        await self.hass.services.async_call(
            "number", "set_value",
            {"entity_id": entity_id, "value": value},
        )
        return True

    async def _set_mode(self, mode: str) -> None:
        """select.select_option — nur wenn Regulation aktiviert."""
        if not self._regulation_on:
            return
        await self.hass.services.async_call(
            "select", "select_option",
            {"entity_id": self.entry.data[CONF_MODE_SELECT], "option": mode},
        )

    async def _set_output(self, value: float) -> None:
        """Ausgangsleistung setzen, geklemmt auf 0 bis DEVICE_MAX_POWER."""
        await self._set_number(
            self.entry.data[CONF_ACTIVE_POWER],
            max(0, min(round(value), DEVICE_MAX_POWER)),
        )
        self.last_output_ts = time.time()

    async def _set_output_and_wait(self, value: float, ac_charge_mode: bool = False) -> None:
        """Ausgangsleistung setzen und auf reale Konvergenz warten (_wait_for_target).

        `number.set_value` läuft ohne `blocking=True`: der Aufruf kehrt zurück,
        sobald der Service-Call eingereiht ist, nicht wenn CONF_ACTIVE_POWER den
        neuen Wert zeigt. Ein unmittelbar folgender Reread im selben Zyklus sieht
        ohne diesen Wait noch den alten Wert.

        Nullung (`value == 0`) gilt als sicherheitskritisch und wird zusätzlich
        über `_confirm_zero_output()` verifiziert und bei Bedarf erneut geschrieben.
        """
        value = max(0, min(value, DEVICE_MAX_POWER))
        await self._set_output(value)
        await self._wait_for_target(value, ac_charge_mode=ac_charge_mode)
        if value == 0:
            await self._confirm_zero_output(ac_charge_mode)

    async def _confirm_zero_output(self, ac_charge_mode: bool, max_retries: int = 2) -> None:
        """Bestätigt, dass die Ausgangsleistung real auf 0 gefallen ist — unabhängig
        von S_SELF_ADJUST, das `_wait_for_target()` sonst gar nicht nachprüfen lässt.
        Schreibt bei fehlender Konvergenz bis zu `max_retries`-mal erneut und meldet
        nach Ausschöpfung über `_output_warning` einen sichtbaren Fehler.

        CONF_ACTUAL_SENSOR stammt aus einer fremden Integration mit eigenem
        Poll-Intervall (1–300 s). Ein Read, der älter ist als unser letzter
        Schreibbefehl, belegt weder Erfolg noch Fehlschlag; dann unterbleibt nur
        die Warnung, Schreib- und Retry-Verhalten bleibt gleich.
        """
        actual_eid = self.entry.data.get(CONF_ACTUAL_SENSOR, "")
        if not self._entity_ok(actual_eid):
            return  # kein Sensor zur Verifikation verfügbar — nichts zu prüfen

        tolerance = float(self.settings.get(S_SELF_ADJUST_TOL, 2))

        def _confirmable() -> bool:
            """True nur wenn der Sensor seit unserem letzten Schreibbefehl neu
            gepollt hat — sonst ist der gelesene Wert kein Beleg für irgendetwas."""
            state = self.hass.states.get(actual_eid)
            return state is not None and state.last_updated.timestamp() >= self.last_output_ts

        for attempt in range(max_retries):
            if abs(self._flt_power(actual_eid)) <= tolerance:
                return
            if _confirmable():
                _LOGGER.warning(
                    "Solakon: Output-Nullung nicht bestätigt (Ist: %.0f W) — erneuter Schreibversuch %d/%d",
                    self._flt_power(actual_eid), attempt + 1, max_retries,
                )
            await self._set_output(0)
            await self._wait_for_target(0, ac_charge_mode=ac_charge_mode)

        actual = self._flt_power(actual_eid)
        if abs(actual) > tolerance and _confirmable():
            self._output_warning = self._tr("warn_output_zero_unconfirmed", attempts=max_retries, actual=actual)
            _LOGGER.error("Solakon: %s", self._output_warning)

    def _reset_output_stall_state(self) -> None:
        """Stillstandszähler zurücksetzen — Ausgang folgt dem Limit wieder oder ist
        nicht prüfbar."""
        self._output_stall_actions = 0
        self._output_stall_last_ts = 0.0

    async def _check_output_stall(self, limit: float) -> None:
        """Erkennt einen Wechselrichter, der dem Limit nicht folgt, und stößt ihn an.

        Nur aus dem gesättigten Zweig des Standard-PI aufgerufen; die übrigen
        PI-Pfade halten den Ausgang durch eigene Guards bewusst unterhalb ihres
        Limits. Kriterium: Abweichung über `OUTPUT_STALL_DEVIATION` bei einem
        Ist-Wert, dessen `last_updated` seit `OUTPUT_STALL_SECONDS` nicht vorrückt.

        Erster Treffer schreibt den Sollwert neu. Bleibt die Abweichung:
        Integral-Reset, Output 0, Timer-Toggle, Modus `'0'` — Fall D holt im
        Folgezyklus zurück. Mindestabstand zweier Aktionen: `OUTPUT_STALL_SECONDS`.
        """
        actual_eid = self.entry.data.get(CONF_ACTUAL_SENSOR, "")
        if limit <= 0 or not self._entity_ok(actual_eid):
            self._reset_output_stall_state()
            return

        actual = self._flt_power(actual_eid)
        if abs(actual - limit) <= limit * OUTPUT_STALL_DEVIATION:
            self._reset_output_stall_state()
            return

        state = self.hass.states.get(actual_eid)
        if state is None:
            self._reset_output_stall_state()
            return

        now = time.time()
        if now - state.last_updated.timestamp() < OUTPUT_STALL_SECONDS:
            return
        if self._output_stall_last_ts and now - self._output_stall_last_ts < OUTPUT_STALL_SECONDS:
            return

        self._output_stall_last_ts = now
        self._output_stall_actions += 1

        if self._output_stall_actions == 1:
            _LOGGER.warning(
                "Solakon: Ausgang %.0f W folgt Limit %.0f W nicht (unverändert seit %.0f s) "
                "— Sollwert wird neu geschrieben",
                actual, limit, now - state.last_updated.timestamp(),
            )
            await self._set_output(limit)
            self._set_last_action("act_output_rewritten", actual=actual, limit=limit)
            return

        self._output_warning = self._tr("warn_output_stuck", actual=actual, limit=limit)
        _LOGGER.error("Solakon: %s (Versuch %d)", self._output_warning, self._output_stall_actions)
        await self._transition(reset_integral=True, output=0, mode=MODE_DISABLED)
        self._set_last_action("act_output_recovery", actual=actual, limit=limit)

    async def _set_discharge(self, amps: float) -> None:
        """Entladestrom setzen — nur wenn aktueller Wert abweicht."""
        await self._set_number(self.entry.data[CONF_DISCHARGE_CURRENT], amps, only_if_changed=True)

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
        if await self._set_number(export_entity, target, only_if_changed=True, current=current):
            _LOGGER.info("Solakon: Export-Limit korrigiert %d → %d W", int(current), target)

    async def _transition(
        self, *, reset_integral: bool = False, flags: dict[str, bool] | None = None,
        output: float | None = None, wait: bool = True, ac_charge_mode: bool = False,
        timer: bool = True, timer_first: bool = False, mode: str | None = None,
    ) -> None:
        """Zustandsübergang in fester Folge: Integral, Flags, Output, Timer, Modus.

        `flags` setzt nur die übergebenen Zustandsflags. `output` None lässt die
        Ausgangsleistung unberührt, `wait=False` schreibt sie ohne Konvergenzwarten.
        `timer_first` schaltet den Timer vor den Output. `mode` None schreibt keinen Modus.
        """
        if reset_integral:
            self.integral = 0.0
        for name, value in (flags or {}).items():
            setattr(self, name, value)
        if timer and timer_first:
            await self._timer_toggle()
        if output is not None:
            if wait:
                await self._set_output_and_wait(output, ac_charge_mode=ac_charge_mode)
            else:
                await self._set_output(output)
        if timer and not timer_first:
            await self._timer_toggle()
        if mode is not None:
            await self._set_mode(mode)

    async def _set_fixed_output(
        self, target: float, current: float, action_key: str, ac_charge_mode: bool = False,
    ) -> None:
        """Fester Sollwert: schreibt nur bei Abweichung über 0,5 vom kommandierten Ist-Wert."""
        if abs(current - target) > 0.5:
            self._set_last_action(action_key, power=target)
            await self._set_output_and_wait(target, ac_charge_mode=ac_charge_mode)

    async def _pi_step(
        self, grid: float, power_base: float, offset: float, limit: float, p_factor: float,
        i_factor: float, share: float, current_power: float, action_key: str,
        ac_charge_mode: bool = False,
    ) -> None:
        """Ein PI-Schritt: Sollwert aus Poolanteil berechnen, Aktion setzen, schreiben."""
        new_pw = self._pi_calculate(
            grid, power_base, offset, limit, p_factor, i_factor,
            ac_charge_mode=ac_charge_mode, error_share=share,
        )
        self._set_last_action(action_key, frm=current_power, to=new_pw)
        await self._set_output_and_wait(new_pw, ac_charge_mode=ac_charge_mode)

    def _decay_integral(self) -> None:
        """Integral über 10 um 5 % abklingen lassen, wenn kein PI-Schritt schreibt."""
        if abs(self.integral) > 10:
            self.integral *= 0.95

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
        if not self._regulation_on:
            self._end_cycle(notify_on_change=True)
            return

        self._timer_toggled_in_cycle = False
        self._output_warning = ""
        self._cycle_blocked = False

        prev_flags = self._persisted_flags()

        # ── 1. Sensor-Werte lesen ────────────────────────────────────────────
        # Kernsensoren müssen verfügbar sein
        if not all(self._entity_ok(cfg[k]) for k in (
            CONF_GRID_SENSOR, CONF_SOLAR_SENSOR, CONF_ACTUAL_SENSOR, CONF_SOC_SENSOR
        )):
            _LOGGER.debug("Solakon: Kernsensoren nicht verfügbar, Zyklus übersprungen")
            self._end_cycle(blocked=True, notify_on_change=True)
            return

        soc = self._flt(cfg[CONF_SOC_SENSOR])
        grid = self._flt_power(cfg[CONF_GRID_SENSOR])
        solar = self._flt_power(cfg[CONF_SOLAR_SENSOR])
        actual = self._flt_power(cfg[CONF_ACTUAL_SENSOR])
        mode = self._str(cfg[CONF_MODE_SELECT])
        timer_val = self._flt(cfg[CONF_TIMEOUT_COUNTDOWN])

        # ── 1b. StdDev aktualisieren + dynamische Offsets berechnen ──────────
        # StdDev ist eine Eigenschaft der Netzgruppe, nicht der einzelnen Instanz:
        # nur der Gruppen-Leader pflegt den Ringpuffer, alle Instanzen übernehmen
        # seinen Wert.
        leader = self._group_leader()
        if leader is self:
            self._update_stddev(grid)
        self.grid_stddev = leader.grid_stddev
        self.grid_stddev_raw = leader.grid_stddev_raw
        if any(s.get(k, False) for k in (S_DYN_Z1_ENABLED, S_DYN_Z2_ENABLED, S_DYN_AC_ENABLED)):
            self._update_dynamic_offsets()

        # ── 2. Settings auslesen ─────────────────────────────────────────────
        zone1_limit = int(s[S_ZONE1_LIMIT])
        zone3_limit = int(s[S_ZONE3_LIMIT])
        hard_limit_z0 = int(s[S_HARD_LIMIT_Z0])
        hard_limit_z1 = int(s[S_HARD_LIMIT_Z1])
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
        tariff_sensor = self._effective("tariff")
        tariff_cheap = float(s[S_TARIFF_CHEAP_THRESHOLD])
        tariff_exp = float(s[S_TARIFF_EXP_THRESHOLD])

        cheap_entity = self._effective("tariff_cheap")
        if cheap_entity:
            raw = self.hass.states.get(cheap_entity)
            if raw and raw.state not in ("unknown", "unavailable"):
                try:
                    tariff_cheap = float(raw.state)
                except (ValueError, TypeError):
                    pass

        exp_entity = self._effective("tariff_exp")
        if exp_entity:
            raw = self.hass.states.get(exp_entity)
            if raw and raw.state not in ("unknown", "unavailable"):
                try:
                    tariff_exp = float(raw.state)
                except (ValueError, TypeError):
                    pass

        # Sammelt Meldungen zu Sensor-gated Features, die trotz aktivem Enable-Flag
        # wegen fehlendem/ungültigem Sensor wirkungslos bleiben; wird als last_error
        # ins Panel gespiegelt. Angelegt vor _compute_distribution(), dessen
        # Modus-Degradation ebenfalls hier einfließt.
        soft_errors: list[str] = []

        error_share, allocated_power = self._compute_distribution(soc)
        self.allocated_power = allocated_power
        if self._dist_warning:
            self._add_soft_error(soft_errors, self._dist_warning)
        # Panel-Limits gegen die Geraetegrenze gedeckelt.
        effective_hard    = int(min(int(allocated_power), hard_limit_z0, DEVICE_MAX_POWER)) if allocated_power is not None else int(min(hard_limit_z0, DEVICE_MAX_POWER))
        effective_hard_z1 = int(min(int(allocated_power), hard_limit_z1, DEVICE_MAX_POWER)) if allocated_power is not None else int(min(hard_limit_z1, DEVICE_MAX_POWER))

        # Verwertbarer PV-Überschuss: Luft zwischen dem aktuellen Output und dem
        # Minimum aus geltendem Hard-Limit und aktueller PV-Leistung, geklemmt auf ≥0.
        # Nutzt die Zone des vorherigen Zyklus — self.surplus_active ist hier noch
        # nicht aktualisiert.
        self.surplus_power = max(0.0, min(
            effective_hard if self.surplus_active else effective_hard_z1, solar
        ) - actual)

        pv_forecast_enabled = bool(s.get(S_PV_FORECAST_ENABLED, False))
        pv_forecast_threshold = float(s.get(S_PV_FORECAST_THRESHOLD, 0.0))

        surplus_forecast_enabled   = bool(s.get(S_SURPLUS_FORECAST_ENABLED, False))
        surplus_forecast_threshold = float(s.get(S_SURPLUS_FORECAST_THRESHOLD, 0.0))

        # Gemergtes Feld: beide Features lesen denselben "PV-Ertrag heute"-Sensor
        # (lokaler Override oder globaler Verteilungs-Tab-Wert).
        pv_forecast_today_sensor = self._effective("pv_forecast")

        # Forcierung nur solange die PV das Ausgangslimit übersteigt und der
        # SOC über der Zone-3-Schutzgrenze liegt.
        self.forecast_surplus_forced = self._sensor_usable(
            soft_errors, surplus_forecast_enabled, pv_forecast_today_sensor, "err_surplus_forecast"
        ) and (
            self._flt_kwh_normalized(pv_forecast_today_sensor) >= surplus_forecast_threshold
            and solar > hard_limit_z0
            and soc > zone3_limit
        )

        surplus_lock_enabled = bool(s.get(S_SURPLUS_LOCK_ENABLED, False))
        surplus_lock_sensor  = self._effective("surplus_lock")
        surplus_lock_factor  = float(s.get(S_SURPLUS_LOCK_FACTOR, 1.5))

        # Sperrt nur den PV-Austritt aus Zone 0, solange die Vorhersage über
        # dem Ausgabelimit liegt. Der SOC-Austritt bleibt ungesperrt.
        self.forecast_exit_lock = self._sensor_usable(
            soft_errors, surplus_lock_enabled, surplus_lock_sensor, "err_exit_lock"
        ) and (
            self._flt_kilo_normalized(surplus_lock_sensor) >= surplus_lock_factor * hard_limit_z0
            and soc > zone3_limit
        )

        self.forecast_tariff_suppressed = self._sensor_usable(
            soft_errors, pv_forecast_enabled, pv_forecast_today_sensor, "err_pv_forecast"
        ) and self._flt_kwh_normalized(pv_forecast_today_sensor) >= pv_forecast_threshold

        # Zone-1-Nacht-Forcierung: erlaubt Entladung unter das normale
        # Zone-1-Limit, wenn der morgige PV-Ertrag die Nacht ohnehin wieder auffüllt.
        zone1_force_enabled = bool(s.get(S_ZONE1_FORCE_ENABLED, False))
        zone1_force_threshold = float(s.get(S_ZONE1_FORCE_THRESHOLD, 0.0))
        zone1_force_min_soc = int(s.get(S_ZONE1_FORCE_MIN_SOC, 0))
        zone1_force_sensor = self._effective("zone1_force")

        self.zone1_forced = self._sensor_usable(
            soft_errors, zone1_force_enabled, zone1_force_sensor, "err_zone1_force"
        ) and (
            self._flt_kwh_normalized(zone1_force_sensor) >= zone1_force_threshold
            and solar < pv_reserve         # "gerade dunkel", gleiche Bedingung wie is_night
            and soc > zone1_force_min_soc  # eigener Floor, unabhängig von zone3_limit (Exit-Schwelle)
        )

        effective_tariff_enabled = tariff_enabled and bool(tariff_sensor) and not self.forecast_tariff_suppressed
        tariff_soc = int(s[S_TARIFF_SOC_TARGET])
        tariff_power = int(s[S_TARIFF_POWER])

        # Nacht-Parameter
        night_enabled = bool(s[S_NIGHT_ENABLED])

        # ── 3. Validierung ───────────────────────────────────────────────────
        if zone1_limit <= zone3_limit:
            self._end_cycle(blocked=True, error_key="err_soc_zone1_zone3")
            return

        if surplus_enabled and surplus_threshold <= zone1_limit:
            self._end_cycle(blocked=True, error_key="err_soc_surplus_zone1")
            return

        if zone1_force_enabled and not (zone3_limit < zone1_force_min_soc < zone1_limit):
            self._end_cycle(blocked=True, error_key="err_soc_zone1_force")
            return

        if not self._entity_ok(cfg[CONF_SOC_SENSOR]):
            self._end_cycle(blocked=True, error_key="err_soc_sensor")
            return

        if not self._entity_ok(cfg[CONF_MODE_SELECT]):
            self._end_cycle(blocked=True, error_key="err_mode_select")
            return

        # Preis vor der Fehlersammlung lesen: die Einheitenplausibilität geht als
        # soft_error in dieselbe Meldungskette ein.
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

        if self._sensor_usable(soft_errors, tariff_enabled, tariff_sensor, "err_tariff") and tariff_price_valid:
            unit_warning = self._tariff_unit_warning(tariff_sensor, tariff_price, tariff_cheap)
            if unit_warning:
                self._add_soft_error(soft_errors, unit_warning)

        # Verkettet statt überschrieben
        self.last_error = " • ".join(soft_errors)

        # ── 4. Abgeleitete Variablen ─────────────────────────────────────────
        target_offset = offset_1 if self.cycle_active else offset_2

        prev_actual = self._prev_actual
        self._prev_actual = actual

        total_actual = self._pool_sum(self._discharge_pool(), actual, CONF_ACTUAL_SENSOR,
                                      SolakonCoordinator._flt_power)

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

        # Zustand hinter Fall TM: die Sperrbedingung selbst, nicht ihr Auslöser.
        # TM feuert nur beim Übergang aus Modus '1' heraus; die Sperre gilt aber
        # weiter, solange der Preis unter der Teuer-Schwelle liegt und keine
        # Lade-Session oder Zone 0 läuft — dieselbe Bedingung, die in den Fällen
        # A und E den Wiedereintritt blockiert.
        self.discharge_locked = (
            effective_tariff_enabled
            and tariff_price_valid
            and tariff_price < tariff_exp
            and not (self.tariff_charge_active or self.ac_charge_active or self.surplus_active)
        )

        # ── 6. Entladestrom mit Regelzustand abgleichen (vor dem PI-Gate) ────
        await self._set_discharge(self._required_discharge(discharge_max))

        # ── 6b. Frische Werte nach Falls ─────────────────────────────────────
        grid = self._flt_power(cfg[CONF_GRID_SENSOR])
        solar = self._flt_power(cfg[CONF_SOLAR_SENSOR])
        mode = self._str(cfg[CONF_MODE_SELECT])

        if mode == MODE_AC_CHARGE:
            dynamic_max = int(min(ac_power_limit, DEVICE_MAX_POWER))
        elif self.cycle_active:
            dynamic_max = effective_hard_z1
        else:
            dynamic_max = min(effective_hard_z1, max(0, solar - pv_reserve))

        target_offset = offset_1 if self.cycle_active else offset_2

        # ── 7. PI-Gate ───────────────────────────────────────────────────────
        if mode not in (MODE_DISCHARGE, MODE_AC_CHARGE):
            self._end_cycle(soft_errors=soft_errors, display=(soc, zone1_limit, zone3_limit, mode),
                            prev_flags=prev_flags)
            return

        # ── 9. Timeout-Reset ─────────────────────────────────────────────────
        # Entfällt wenn ein Fall in diesem Zyklus bereits getoggelt hat
        if timer_val < 120 and not self._timer_toggled_in_cycle and self._entity_ok(cfg[CONF_TIMEOUT_COUNTDOWN]):
            await self._timer_toggle()

        # Einzige CONF_ACTIVE_POWER-Lesung dieses Zyklus, nach dem letzten Await vor
        # der PI-Entscheidung. Gemeinsam genutzt von Gate, PI-Basis und Log-Zeile.
        current_power = self._flt(cfg[CONF_ACTIVE_POWER])
        at_max_limit = current_power >= dynamic_max
        at_min_limit = current_power <= 0
        above_dynamic_max = current_power > dynamic_max

        # Eigener Pool für AC-Laden, nach den Falls berechnet.
        ac_error_share = self._compute_ac_distribution(soc)
        if self._dist_warning:
            self._add_soft_error(soft_errors, self._dist_warning)

        # ── PI-Pfade ─────────────────────────────────────────────────────────
        if self.surplus_active:
            await self._set_fixed_output(effective_hard, current_power, "act_zone0_output")

        elif self.ac_charge_active:
            if abs(grid - ac_offset) > tolerance:
                await self._pi_step(
                    grid,
                    self._pool_sum(self._ac_pool(), current_power, CONF_ACTIVE_POWER,
                                   SolakonCoordinator._flt) * ac_error_share,
                    ac_offset, ac_power_limit, ac_p, ac_i, ac_error_share, current_power,
                    "act_ac_pi", ac_charge_mode=True,
                )
            else:
                self._decay_integral()

        elif self.tariff_charge_active:
            await self._set_fixed_output(tariff_power, current_power, "act_tariff_power", ac_charge_mode=True)

        else:
            grid_error = grid - target_offset
            grid_error_abs = abs(grid_error)
            # Sättigung nach oben: der PI könnte hochregeln, darf aber nicht.
            saturated_high = at_max_limit and not above_dynamic_max and grid_error > 0

            if grid_error_abs > tolerance and not saturated_high and not (at_min_limit and grid_error < 0):
                await self._pi_step(
                    grid,
                    self._pool_sum(self._discharge_pool(), current_power, CONF_ACTIVE_POWER,
                                   SolakonCoordinator._flt) * error_share,
                    target_offset, dynamic_max, p_factor, i_factor, error_share, current_power,
                    "act_pi",
                )
            else:
                self._decay_integral()
                if saturated_high:
                    await self._check_output_stall(dynamic_max)
                else:
                    self._reset_output_stall_state()

        # ── 10. Display + Flag-Persistenz ────────────────────────────────────
        self._end_cycle(soft_errors=soft_errors, display=(soc, zone1_limit, zone3_limit, mode),
                        prev_flags=prev_flags)

    def _add_soft_error(self, soft_errors: list[str], text: str) -> None:
        """Meldung an die Fehlerkette hängen und `last_error` neu verketten."""
        soft_errors.append(text)
        self.last_error = " • ".join(soft_errors)

    def _end_cycle(
        self, *, blocked: bool = False, error_key: str = "", soft_errors: list[str] | None = None,
        display: tuple[float, int, int, str] | None = None, prev_flags: dict[str, bool] | None = None,
        notify_on_change: bool = False,
    ) -> None:
        """Zyklus abschließen: Fehler, Anzeige, Flag-Speicherung, Benachrichtigung.

        `error_key` ersetzt `last_error`, `soft_errors` erhält eine offene Output-Warnung.
        `display` (soc, zone1, zone3, mode) zieht Zonen- und Modusanzeige nach, sonst nur
        den Betriebszustand. Mit `prev_flags` wird bei geänderten Flags verzögert gespeichert.
        `notify_on_change` benachrichtigt nur, wenn der Betriebszustand gewechselt hat.
        """
        if error_key:
            self.last_error = self._tr(error_key)
        if blocked:
            self._cycle_blocked = True
        if soft_errors is not None and self._output_warning:
            self._add_soft_error(soft_errors, self._output_warning)
        if display is not None:
            self._update_zone_display(*display)
            changed = True
        else:
            changed = self._update_operating_state()
        if prev_flags is not None and self._persisted_flags() != prev_flags:
            self._store.async_delay_save(self._store_data, 5)
        if changed or not notify_on_change:
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
            switch = mode != MODE_DISCHARGE
            await self._transition(
                flags={"surplus_active": True, "cycle_active": True},
                timer=switch, mode=MODE_DISCHARGE if switch else None,
            )
            self._set_last_action("act_surplus_on")
            return "0A"

        # ── Fall 0B: Surplus Exit ────────────────────────────────────────────
        # Austritt bei erfüllter Austritts-Bedingung oder deaktivierter Überschuss-Option.
        if self.surplus_active and (not v["surplus_enabled"] or not v["new_surplus"]):
            # Zone nach Overlay-Ende aus dem SOC ableiten
            await self._transition(
                reset_integral=True,
                flags={"surplus_active": False, "cycle_active": soc > zone1},
                output=0, timer=False,
            )
            self._set_last_action("act_surplus_off")
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
            await self._transition(
                reset_integral=True,
                flags={"cycle_active": True, "surplus_active": False,
                       "ac_charge_active": False, "tariff_charge_active": False},
                mode=MODE_DISCHARGE,
            )
            if zone1_forced and soc <= zone1:
                self._set_last_action("act_fall_a_forced", soc=soc)
            else:
                self._set_last_action("act_fall_a", soc=soc)
            return "A"

        # ── Fall B: Zone 3 Stop (Zyklus on) ──────────────────────────────────
        if (
            not self.ac_charge_active
            and not self.tariff_charge_active
            and soc <= zone3
            and self.cycle_active
        ):
            await self._transition(
                reset_integral=True,
                flags={"cycle_active": False, "surplus_active": False,
                       "ac_charge_active": False, "tariff_charge_active": False},
                output=0, mode=MODE_DISABLED,
            )
            self._set_last_action("act_fall_b", soc=soc)
            return "B"

        # ── Fall C: Zone 3 Absicherung ───────────────────────────────────────
        if (
            not self.ac_charge_active
            and not self.tariff_charge_active
            and soc <= zone3
            and not self.cycle_active
            and mode != MODE_DISABLED
        ):
            await self._transition(
                flags={"surplus_active": False, "ac_charge_active": False,
                       "tariff_charge_active": False},
                output=0, mode=MODE_DISABLED,
            )
            self._set_last_action("act_fall_c")
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
            await self._transition(mode=MODE_AC_CHARGE if charging_session_active else MODE_DISCHARGE)
            self._set_last_action("act_fall_d")
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
            await self._transition(
                flags={"tariff_charge_active": True}, output=v["tariff_power"],
                ac_charge_mode=True, timer_first=True, mode=MODE_AC_CHARGE,
            )
            self._set_last_action("act_fall_gt", price=v["tariff_price"])
            return "GT"

        # ── Fall HT: Tarif-Laden Ende ────────────────────────────────────────
        if (
            self.tariff_charge_active
            and (
                soc >= v["tariff_soc"]
                or (v.get("tariff_price_valid", False) and v["tariff_price"] >= v["tariff_cheap"])
            )
        ):
            await self._transition(
                reset_integral=True, flags={"tariff_charge_active": False}, output=0,
                mode=MODE_DISCHARGE if self.cycle_active else MODE_DISABLED,
            )
            self._set_last_action("act_fall_ht")
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
            await self._transition(
                reset_integral=True, flags={"cycle_active": False}, output=0, mode=MODE_DISABLED,
            )
            self._set_last_action("act_fall_tm", price=v["tariff_price"])
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
            await self._transition(
                flags={"ac_charge_active": True}, output=0,
                ac_charge_mode=True, timer_first=True, mode=MODE_AC_CHARGE,
            )
            self._set_last_action("act_fall_g")
            return "G"

        # ── Fall H: AC Laden Ende ────────────────────────────────────────────
        if (
            mode == MODE_AC_CHARGE
            and self.ac_charge_active
            and not self.tariff_charge_active
            and (
                soc >= v["ac_soc_target"]
                or (
                    grid >= (v["ac_offset"] + v["ac_hysteresis"])
                    and abs(actual) <= float(self.settings.get(S_SELF_ADJUST_TOL, 2))
                )
            )
        ):
            await self._transition(
                reset_integral=True, flags={"ac_charge_active": False}, output=0,
                mode=MODE_DISCHARGE if self.cycle_active else MODE_DISABLED,
            )
            self._set_last_action("act_fall_h")
            return "H"

        # ── Fall I: Safety — Modus '3' ohne aktive Lade-Session ──────────────
        if (
            mode == MODE_AC_CHARGE
            and not self.ac_charge_active
            and not self.tariff_charge_active
        ):
            await self._transition(
                reset_integral=True, output=0,
                mode=MODE_DISCHARGE if self.cycle_active else MODE_DISABLED,
            )
            self._set_last_action("act_fall_i")
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
            await self._transition(reset_integral=True, mode=MODE_DISCHARGE)
            self._set_last_action("act_fall_e")
            return "E"

        # ── Fall F: Nachtabschaltung ─────────────────────────────────────────
        if (
            not self.ac_charge_active
            and not self.tariff_charge_active
            and v["is_night"]
            and not self.cycle_active
            and mode != MODE_DISABLED
        ):
            await self._transition(reset_integral=True, output=0, mode=MODE_DISABLED)
            self._set_last_action("act_fall_f")
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
        active = self._pool(lambda c: c._regulation_on) or self._group_coords()
        return active[min(active)]

    def _pool(self, pred: Callable[["SolakonCoordinator"], bool]) -> dict[str, "SolakonCoordinator"]:
        """Instanzen der Netzgruppe, für die `pred` gilt, in Reihenfolge der Gruppe."""
        return {eid: c for eid, c in self._group_coords().items() if pred(c)}

    def _discharge_pool(self) -> dict[str, "SolakonCoordinator"]:
        """Regelnde Instanzen der Netzgruppe in Modus '1'."""
        return self._pool(
            lambda c: c._regulation_on
            and c._str(c.entry.data.get(CONF_MODE_SELECT, "")) == MODE_DISCHARGE
        )

    def _ac_pool(self) -> dict[str, "SolakonCoordinator"]:
        """Regelnde Instanzen der Netzgruppe mit aktivem AC-Laden."""
        return self._pool(lambda c: c._regulation_on and c.ac_charge_active)

    def _pool_sum(
        self, pool: dict[str, "SolakonCoordinator"], own_value: float, conf_key: str,
        reader: Callable[["SolakonCoordinator", str], float],
    ) -> float:
        """Summe über `pool`: eigener Beitrag `own_value`, Fremdinstanzen über
        `reader(instanz, entity_id)` der Entität `conf_key`. Höchstens eine Instanz: `own_value`.

        `own_value` ist der im laufenden Zyklus bereits gelesene eigene Wert — keine zweite Lesung.
        """
        if len(pool) <= 1:
            return own_value
        return sum(
            own_value if c is self else reader(c, c.entry.data.get(conf_key, ""))
            for c in pool.values()
        )

    def _pool_socs(self, active: dict[str, "SolakonCoordinator"], own_soc: float) -> dict[str, float] | None:
        """SOC je Instanz in `active`; eigener Wert `own_soc`, Fremdinstanzen live gelesen.
        `None`, sobald ein Fremd-SOC nicht verfügbar ist."""
        socs: dict[str, float] = {}
        for eid, c in active.items():
            if c is self:
                socs[eid] = own_soc
                continue
            soc_eid = c.entry.data.get(CONF_SOC_SENSOR, "")
            if not c._entity_ok(soc_eid):
                return None
            socs[eid] = c._flt(soc_eid, 0)
        return socs

    def _degrade(self, mode: str, warn_key: str = "") -> None:
        """Tatsächlich angewandten Verteilungsmodus vermerken, mit Warnung bei `warn_key`."""
        if warn_key:
            self._dist_warning = self._tr(warn_key)
        self.dist_mode_effective = mode

    def _dist_cfg(self) -> dict:
        """Verteilungs-Config nur der eigenen Netzgruppe, mit Defaults aufgefüllt."""
        all_groups = self.hass.data.get(f"{DOMAIN}_dist_config") or {}
        group_key = self.entry.data.get(CONF_GRID_SENSOR, "")
        return {**DIST_DEFAULTS, **all_groups.get(group_key, {})}

    def _weighted_share(self, active: dict[str, "SolakonCoordinator"], own_soc: float) -> float:
        """SOC-/kapazitätsgewichteter oder gleichverteilter Fehler-Anteil dieser Instanz.

        `active` ist die Menge der aktuell gleichrangig teilnehmenden Instanzen
        (Pool-spezifisch — z. B. alle in Modus '1', oder alle mit aktivem AC-Laden).
        Ist diese Instanz nicht Teil von `active`, bekommt sie keinen Anteil (0.0).
        Dünner Wrapper um _all_shares() für den (häufigeren) Fall, dass nur der
        eigene Anteil gebraucht wird (z. B. AC-Lade-Pool ohne Hard-Limit-Verteilung).
        `own_soc` siehe `_all_shares`.
        """
        if self.entry.entry_id not in active:
            return 0.0
        return self._all_shares(active, own_soc).get(self.entry.entry_id, 0.0)

    def _all_shares(self, active: dict[str, "SolakonCoordinator"], own_soc: float) -> dict[str, float]:
        """SOC-/kapazitätsgewichteter oder gleichverteilter Fehler-Anteil für ALLE
        Instanzen in `active`. Grundlage für _weighted_share() (eigener Anteil)
        und für die Wasserfüll-Verteilung in _compute_distribution().

        `own_soc` ist der im laufenden Zyklus bereits gelesene eigene
        CONF_SOC_SENSOR-Wert; Fremdinstanzen werden live gelesen.

        Degradiert ein Modus mangels gültigem Fremdinstanz-Sensor (SOC oder
        Kapazität), wird das in self._dist_warning vermerkt und von
        _run_regulation_cycle in soft_errors überführt.
        """
        n = len(active)
        if n == 0:
            return {}
        dist = self._dist_cfg()
        mode = dist.get("distribution_mode", "equal")
        self.dist_mode_effective = mode

        if n <= 1:
            return {eid: 1.0 for eid in active}

        equal = {eid: 1.0 / n for eid in active}
        if mode == "equal":
            return equal

        if mode == "soc_switch":
            shares = self._soc_switch_shares(active, own_soc)
            if shares is None:
                self._degrade("equal", "warn_dist_soc_switch_sensor")
                return equal
            return shares

        # Modus "soc" und unbekannte Modi: reine SOC-Prozentpunkt-Gewichtung.
        caps = {eid: 1.0 for eid in active}
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
                    # Case-insensitiver Vergleich der Unit
                    unit = (cap_st.attributes.get("unit_of_measurement") or "").strip().lower()
                    return cv / 1000.0 if unit == "wh" else cv
                except (ValueError, TypeError):
                    return None

            # Kapazitäten pro Instanz; sobald eine keinen gültigen Wert liefert,
            # zählen alle neutral 1.0 (degradiert zu reiner SOC-Gewichtung)
            measured = {eid: _cap_kwh(eid, c) for eid, c in active.items()}
            if any(cap is None for cap in measured.values()):
                self._degrade("soc", "warn_dist_capacity_sensor")
            else:
                caps = measured

        socs = self._pool_socs(active, own_soc)
        if socs is None:
            self._degrade("equal", "warn_dist_soc_sensor")
            return equal

        # SOC-Gewichte: nutzbare kWh (mode "capacity") bzw. nutzbare SOC-% (mode "soc")
        soc_weights = {
            eid: max(0.0, (socs[eid] - float(c.settings.get(S_ZONE3_LIMIT, 20))) / 100.0 * caps[eid])
            for eid, c in active.items()
        }
        total_soc = sum(soc_weights.values())
        if total_soc <= 0:
            self._degrade("equal")
            return equal
        return {eid: w / total_soc for eid, w in soc_weights.items()}

    def _soc_switch_shares(self, active: dict[str, "SolakonCoordinator"], own_soc: float) -> dict[str, float] | None:
        """Anteile für Modus `soc_switch`, ein Eintrag je Instanz in `active`.
        `own_soc` siehe `_all_shares`. `None`: eine Fremdinstanz-SOC ist unsicher,
        der Aufrufer weicht dann auf Gleichverteilung aus.

        Regulär erhält genau eine Instanz vollen Anteil, alle anderen 0 — bis ihr
        SOC seit Übernahme um `soc_switch_divergence` Prozentpunkte gefallen ist,
        dann übernimmt die Instanz mit dem höchsten SOC. Zustand liegt Pool-weit in
        `_soc_switch_state`. Zone 0 übernimmt bedingungslos, mehrere Zone-0-Instanzen
        gleichmäßig; beim Rückgang in die Rotation wird `start_soc` neu verankert.
        """
        socs = self._pool_socs(active, own_soc)
        if socs is None:
            return None

        zone0 = {eid for eid, c in active.items() if c.surplus_active}

        state = self.hass.data.get(f"{DOMAIN}_soc_switch_state")
        if state is None:
            state = {"active_id": None, "start_soc": None, "was_zone0": False}
            self.hass.data[f"{DOMAIN}_soc_switch_state"] = state

        was_zone0 = bool(state.get("was_zone0", False))
        active_id = state.get("active_id")
        changed = False
        rebase = False

        if len(zone0) > 1:
            result = {eid: (1.0 / len(zone0) if eid in zone0 else 0.0) for eid in socs}
        else:
            dist = self._dist_cfg()
            divergence = float(dist.get("soc_switch_divergence", 5))

            if zone0:
                z0_leader = next(iter(zone0))
                if active_id != z0_leader:
                    active_id, rebase = z0_leader, True
            elif was_zone0 and active_id in socs:
                # Zone 0 gerade verlassen — Baseline für die Rotation neu setzen
                rebase = True
            elif active_id not in socs:
                active_id = max(socs, key=socs.get)
                rebase = True
            elif state.get("start_soc") is None:
                rebase = True
            elif state["start_soc"] - socs[active_id] >= divergence:
                remaining = {eid: s for eid, s in socs.items() if eid != active_id}
                active_id = max(remaining, key=remaining.get) if remaining else active_id
                rebase = True

            if rebase:
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

    def _compute_distribution(self, own_soc: float) -> tuple[float, float | None]:
        """Fehler-Anteil + zugeteilte Leistung für Nulleinspeisung-Instanzen (Modus '1').

        Gibt (error_share, allocated_power) zurück.
        Im Einzelbetrieb oder wenn diese Instanz gerade nicht in Modus '1' steht:
        (1.0 bzw. 0.0, None) — kein Einfluss auf hard_limit. `own_soc` siehe `_all_shares`.

        allocated_power kommt aus _waterfill_allocate(): proportionale Aufteilung
        von global_max_power, gekappt am lokalen Hard-Limit jeder Instanz,
        ungenutzter Spielraum wird an Instanzen mit Reserve weitergereicht.
        """
        active = self._discharge_pool()
        self._dist_warning = ""
        if self.entry.entry_id not in active or len(active) <= 1:
            return (1.0, None) if self.entry.entry_id in active else (0.0, None)

        shares = self._all_shares(active, own_soc)
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
                caps[eid] = float(c.settings[S_HARD_LIMIT_Z0])
            else:
                caps[eid] = float(c.settings[S_HARD_LIMIT_Z1])

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

    def _compute_ac_distribution(self, own_soc: float) -> float:
        """Fehler-Anteil unter gleichzeitig AC-ladenden Instanzen (Modus '3', `ac_charge_active`).

        Eigener Pool, unabhängig von der Nulleinspeisungs-Verteilung (Modus '1') —
        verhindert, dass mehrere AC-Lader denselben Netzüberschuss doppelt beanspruchen.
        Kein `allocated_power`: das AC-Leistungslimit bleibt unabhängig vom hard_limit.
        `own_soc` siehe `_all_shares`.
        """
        return self._weighted_share(self._ac_pool(), own_soc)

    # ── PI-Berechnung ────────────────────────────────────────────────────────

    def _pi_calculate(
        self,
        grid_power: float,
        current_power: float,
        target_offset: float,
        max_power: float,
        p_factor: float,
        i_factor: float,
        ac_charge_mode: bool = False,
        error_share: float = 1.0,
    ) -> float:
        """PI-Regler-Berechnung mit modusabhängiger Fehlerrichtung und Anti-Windup via Back-Calculation.
        max_power wird auf DEVICE_MAX_POWER gedeckelt, damit Klemmung und
        Back-Calculation gegen die real erreichbare Grenze rechnen."""
        max_power = min(max_power, DEVICE_MAX_POWER)

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
        if soc <= zone3:
            self.current_zone = 3
            self.zone_label = self._tr("zone_3")
        elif self.surplus_active:
            self.current_zone = 0
            self.zone_label = self._tr("zone_0")
        elif self.cycle_active:
            self.current_zone = 1
            self.zone_label = self._tr("zone_1")
        else:
            self.current_zone = 2
            self.zone_label = self._tr("zone_2")

        mode_map = {
            MODE_DISABLED: "disabled",
            MODE_DISCHARGE: "discharge",
            MODE_AC_CHARGE: "ac_charge",
        }
        new_mode_key = mode_map.get(mode, "unknown")
        if new_mode_key != self.mode_key:
            self.mode_label_ts = time.time()
        self.mode_key = new_mode_key
        # Beim unbekannten Modus den Rohwert an den Zustandstext anhängen.
        self.mode_label = self._tr(f"mode_{new_mode_key}")
        if new_mode_key == "unknown":
            self.mode_label = f"{self.mode_label}: {mode}"
        self._update_operating_state()

    def _update_operating_state(self) -> bool:
        """Betriebszustand aus den Zustandsflags ableiten; True bei Wechsel.

        Erster zutreffender Zustand gewinnt, Reihenfolge wie in OPERATING_STATES.
        Anders als `active_fall`, das den zuletzt ausgefuehrten Uebergang haelt,
        beschreibt der Zustand, was gerade gilt.
        """
        if not self._regulation_on:
            state = "disabled"
        elif self._cycle_blocked:
            state = "blocked"
        elif self.surplus_active:
            state = "exporting"
        elif self.tariff_charge_active:
            state = "tariff_charging"
        elif self.ac_charge_active:
            state = "ac_charging"
        elif self.discharge_locked:
            state = "discharge_locked"
        elif self.is_night:
            state = "night_off"
        elif self.cycle_active:
            state = "battery_supply"
        elif self.current_zone == 3:
            state = "safety_stop"
        else:
            state = "pv_direct"

        if state == self.operating_state:
            return False
        self.operating_state = state
        self.operating_state_ts = time.time()
        return True
