"""Coordinator — vollständige Nulleinspeisung-Regellogik mit Schreibguard."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import namedtuple
from typing import Any, Callable

from datetime import timedelta

from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .dynamic_offset import DynamicOffset
from .i18n import Msg, translate, translate_msgs
from .pi import SATURATED, STEP, PIController
from .readings import (
    NO_SENSOR, NOT_NUMERIC, UNAVAILABLE, UNIT_SCALE_KILO, UNIT_SCALE_KWH, UNIT_SCALE_W,
    WRONG_DOMAIN, read_number, read_scaled, unit_of, valid_state,
)
from .grid_group import NetGroup, Shares, pool_sum
from .group_store import group_for
from .limits import PowerLimits, power_limits
from .messages import CycleMessages
from .output import Actual, Output, Stall
from .schema import InvalidSettings, check, notify_reset, sanitize
from .tariff import Tariff, forecast_suppressed
from .zones import SurplusState, ZoneInputs, decide, forecast_flags, surplus_and_night
from .const import (
    DOMAIN, STORAGE_VERSION, SETTINGS_DEFAULTS, SETTINGS_SCHEMA,
    CONF_GRID_SENSOR, CONF_ACTUAL_SENSOR, CONF_SOLAR_SENSOR,
    CONF_SOC_SENSOR, CONF_TIMEOUT_COUNTDOWN, CONF_ACTIVE_POWER,
    CONF_DISCHARGE_CURRENT, CONF_TIMEOUT_SET, CONF_MODE_SELECT, CONF_EXPORT_LIMIT,
    MODE_DISABLED, MODE_DISCHARGE, MODE_AC_CHARGE,
    S_REGULATION_ENABLED,
    S_P_FACTOR, S_I_FACTOR, S_TOLERANCE,
    S_ZONE1_LIMIT, S_ZONE3_LIMIT, S_DISCHARGE_MAX, S_HARD_LIMIT_Z0, S_HARD_LIMIT_Z1,
    S_PV_RESERVE,
    S_SURPLUS_ENABLED, S_SURPLUS_SOC_THRESHOLD, S_SURPLUS_SOC_HYST, S_SURPLUS_PV_HYST,
    S_SURPLUS_FORECAST_ENABLED, S_SURPLUS_FORECAST_THRESHOLD,
    S_SURPLUS_LOCK_ENABLED, S_SURPLUS_LOCK_SENSOR, S_SURPLUS_LOCK_FACTOR,
    S_AC_ENABLED, S_AC_SOC_TARGET, S_AC_POWER_LIMIT, S_AC_HYSTERESIS,
    S_AC_P_FACTOR, S_AC_I_FACTOR,
    S_PERIODIC_ENABLED, S_PERIODIC_INTERVAL,
    S_TARIFF_ENABLED, S_TARIFF_PRICE_SENSOR, S_TARIFF_CHEAP_THRESHOLD,
    S_TARIFF_EXP_THRESHOLD, S_TARIFF_SOC_TARGET, S_TARIFF_SOC_HYST, S_TARIFF_POWER,
    S_TARIFF_CHEAP_ENTITY, S_TARIFF_EXP_ENTITY,
    S_PV_FORECAST_ENABLED, S_PV_FORECAST_SENSOR, S_PV_FORECAST_THRESHOLD,
    S_ZONE1_FORCE_ENABLED, S_ZONE1_FORCE_SENSOR, S_ZONE1_FORCE_THRESHOLD, S_ZONE1_FORCE_MIN_SOC,
    S_NIGHT_ENABLED, S_NIGHT_HYSTERESIS, S_REST_IN_DISCHARGE,
    S_SELF_ADJUST_TOL,
    S_DYN_Z1_ENABLED, S_DYN_Z2_ENABLED, S_DYN_AC_ENABLED,
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

# Fehlerschlüssel je Grund ohne Zahl, `{p}` ist das Präfix des Features.
FEATURE_ERRORS = {
    NO_SENSOR: "{p}_no_sensor",
    WRONG_DOMAIN: "{p}_sensor_wrong_domain",
    UNAVAILABLE: "{p}_sensor_unavailable",
    NOT_NUMERIC: "{p}_sensor_not_numeric",
}

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

# Sensorgebundene Werte des Regelzyklus: (Name, SENSOR_SOURCES-Schlüssel, Enable-Feld
# in CycleSettings, Fehlerpräfix, Einheitenskala, Entität optional). Ohne optionale
# Entität wird nicht gelesen und nichts gemeldet.
FEATURE_READINGS = (
    ("cheap", "tariff_cheap", "tariff_enabled", "err_tariff_cheap", {}, True),
    ("exp", "tariff_exp", "tariff_enabled", "err_tariff_exp", {}, True),
    ("surplus_forecast", "pv_forecast", "surplus_forecast_enabled", "err_surplus_forecast", UNIT_SCALE_KWH, False),
    ("surplus_lock", "surplus_lock", "surplus_lock_enabled", "err_exit_lock", UNIT_SCALE_KILO, False),
    ("pv_forecast", "pv_forecast", "pv_forecast_enabled", "err_pv_forecast", UNIT_SCALE_KWH, False),
    ("zone1_force", "zone1_force", "zone1_force_enabled", "err_zone1_force", UNIT_SCALE_KWH, False),
)

# Kernsensoren der Instanz: (Konfigschlüssel, löst Regelzyklus aus, Pflicht für den Zyklus).
# Ist-Leistung und Leistungssollwert werden gepollt und lösen keinen Zyklus aus.
CORE_SENSORS = (
    (CONF_GRID_SENSOR, True, True),
    (CONF_SOLAR_SENSOR, True, True),
    (CONF_ACTUAL_SENSOR, False, True),
    (CONF_ACTIVE_POWER, False, True),
    (CONF_SOC_SENSOR, True, True),
    (CONF_MODE_SELECT, True, False),
)

# Regelzustand → Kenngrößen. Laden liegt als Zustand über dem Entladezyklus.
OPERATING_BY_STATE = {
    "surplus": "exporting",
    "tariff_charge": "tariff_charging",
    "ac_charge": "ac_charging",
    "cycle": "battery_supply",
    "pv": "pv_direct",
}
# Entladestrom in A; der Zyklus nutzt den eingestellten Maximalstrom.
DISCHARGE_BY_STATE = {"surplus": 2.0, "tariff_charge": 0.0, "ac_charge": 0.0, "pv": 0.0}

# Settings, die der Regelzyklus einmal je Durchlauf liest: (Feld, Schlüssel, Typ).
CYCLE_SETTINGS = (
    ("zone1_limit", S_ZONE1_LIMIT, int),
    ("zone3_limit", S_ZONE3_LIMIT, int),
    ("hard_limit_z0", S_HARD_LIMIT_Z0, int),
    ("hard_limit_z1", S_HARD_LIMIT_Z1, int),
    ("tolerance", S_TOLERANCE, int),
    ("p_factor", S_P_FACTOR, float),
    ("i_factor", S_I_FACTOR, float),
    ("pv_reserve", S_PV_RESERVE, int),
    ("discharge_max", S_DISCHARGE_MAX, int),
    ("surplus_enabled", S_SURPLUS_ENABLED, bool),
    ("surplus_threshold", S_SURPLUS_SOC_THRESHOLD, int),
    ("surplus_soc_hyst", S_SURPLUS_SOC_HYST, int),
    ("surplus_pv_hyst", S_SURPLUS_PV_HYST, int),
    ("ac_enabled", S_AC_ENABLED, bool),
    ("ac_soc_target", S_AC_SOC_TARGET, int),
    ("ac_power_limit", S_AC_POWER_LIMIT, int),
    ("ac_hysteresis", S_AC_HYSTERESIS, int),
    ("ac_p", S_AC_P_FACTOR, float),
    ("ac_i", S_AC_I_FACTOR, float),
    ("tariff_enabled", S_TARIFF_ENABLED, bool),
    ("tariff_cheap", S_TARIFF_CHEAP_THRESHOLD, float),
    ("tariff_exp", S_TARIFF_EXP_THRESHOLD, float),
    ("tariff_soc", S_TARIFF_SOC_TARGET, int),
    ("tariff_soc_hyst", S_TARIFF_SOC_HYST, int),
    ("tariff_power", S_TARIFF_POWER, int),
    ("pv_forecast_enabled", S_PV_FORECAST_ENABLED, bool),
    ("pv_forecast_threshold", S_PV_FORECAST_THRESHOLD, float),
    ("surplus_forecast_enabled", S_SURPLUS_FORECAST_ENABLED, bool),
    ("surplus_forecast_threshold", S_SURPLUS_FORECAST_THRESHOLD, float),
    ("surplus_lock_enabled", S_SURPLUS_LOCK_ENABLED, bool),
    ("surplus_lock_factor", S_SURPLUS_LOCK_FACTOR, float),
    ("zone1_force_enabled", S_ZONE1_FORCE_ENABLED, bool),
    ("zone1_force_threshold", S_ZONE1_FORCE_THRESHOLD, float),
    ("zone1_force_min_soc", S_ZONE1_FORCE_MIN_SOC, int),
    ("night_enabled", S_NIGHT_ENABLED, bool),
    ("night_hysteresis", S_NIGHT_HYSTERESIS, int),
)
CycleSettings = namedtuple("CycleSettings", [field for field, _, _ in CYCLE_SETTINGS])

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
        self.last_action_key: str = ""
        self.last_action_params: dict = {}
        # Bausteine von last_error als (Schlüssel, Parameter), für andere Sprachen.
        self.last_error_msgs: list[Msg] = []
        self.pi = PIController()
        self.active_fall: str = ""

        # Boolsche Status-Flags
        self.cycle_active: bool = False
        self.surplus_active: bool = False
        self.ac_charge_active: bool = False
        self.tariff_charge_active: bool = False
        # Ruhezustand: Output 0 im Ruhemodus, keine PI-Regelung.
        self.resting: bool = False
        self.is_night: bool = False
        # Dunkelheit mit Hysterese: an unter PV-Ladereserve, aus ab Reserve + Hysterese.
        self._dark: bool = False
        # Entladung durch den Tarif gesperrt (Preis unter Teuer-Schwelle, keine
        # Lade-Session, kein Überschuss) — der Zustand hinter Fall TM.
        self.discharge_locked: bool = False
        # Zusammengefasster Betriebszustand für Panel und Sensor; "" bis zum
        # ersten Zyklus. Schlüssel aus OPERATING_STATES.
        self.operating_state: str = ""
        self.operating_state_ts: float = time.time()
        # Zyklus an einem Guard abgebrochen (Kernsensor fehlt, SOC-Limits ungültig)
        self._cycle_blocked: bool = False

        # Zeitstempel
        self.last_action_ts: float = time.time()
        self.out = Output(
            lambda value: self._set_number(self.entry.data[CONF_ACTIVE_POWER], value),
            self._read_actual, lambda: self.settings, self._warn_hardware,
        )
        self.mode_label_ts: float = time.time()

        self.dyn = DynamicOffset()

        # Multi-Instanz: zugeteiltes Leistungslimit (None = Einzelbetrieb)
        self.allocated_power: float | None = None
        # Verwertbarer PV-Überschuss: Luft zwischen aktuellem Output und dem
        # Minimum aus Hard-Limit und aktueller PV-Leistung.
        self.surplus_power: float = 0.0
        # Meldungen des laufenden Zyklus, von _end_cycle nach last_error_msgs übernommen.
        self._messages = CycleMessages()
        # Tariflage je Zyklus; hält den Verdacht auf eine EUR/kWh-Preiseinheit über Zyklen.
        self.tariff = Tariff()
        # Zuletzt angewandter Verteilungsmodus aus _apply_shares(); weicht bei
        # Degradation vom konfigurierten distribution_mode ab.
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

    # ── Lesen: Settings ──────────────────────────────────────────────────────

    def _setting(self, key: str, cast: Callable[[Any], Any]) -> Any:
        """Setting typisiert lesen; `self.settings` ist stets mit SETTINGS_DEFAULTS gefüllt."""
        return cast(self.settings[key])

    @property
    def _regulation_on(self) -> bool:
        """Regelung aktiviert; Voraussetzung für jeden Schreibzugriff."""
        return self._setting(S_REGULATION_ENABLED, bool)

    def _cycle_settings(self) -> CycleSettings:
        """Schnappschuss aller CYCLE_SETTINGS für einen Regelzyklus."""
        return CycleSettings(*(self._setting(key, cast) for _, key, cast in CYCLE_SETTINGS))

    # ── Lesen: Sensoren ──────────────────────────────────────────────────────

    def _read_scaled(self, entity_id: str, default: float, scale: dict[str, float]) -> float:
        """Zahl lesen und mit dem Faktor ihrer Einheit aus `scale` multiplizieren.

        Einheiten ohne Eintrag bleiben unverändert; ohne Zahl `default`.
        """
        value = read_scaled(self.hass, entity_id, scale).value
        return default if value is None else value

    def _flt(self, entity_id: str, default: float = 0.0) -> float:
        """Zahl ohne Einheitenumrechnung lesen."""
        return self._read_scaled(entity_id, default, {})

    def _flt_power(self, entity_id: str, default: float = 0.0) -> float:
        """Leistung in W lesen (kW ×1000)."""
        return self._read_scaled(entity_id, default, UNIT_SCALE_W)

    def _flt_kwh_normalized(self, entity_id: str, default: float | None = 0.0) -> float | None:
        """Energie in kWh lesen (Wh ÷1000, MWh ×1000).

        Ohne erkannte Energie-Einheit (z. B. input_number ohne Einheit) bleibt der
        Rohwert unverändert, wie es der kWh-Vertrag der Schwellenfelder vorsieht.
        """
        return self._read_scaled(entity_id, default, UNIT_SCALE_KWH)

    def _str(self, entity_id: str) -> str:
        """State als String lesen, 'unknown' bei Fehler."""
        state = valid_state(self.hass, entity_id)
        return state.state if state else "unknown"

    def _entity_ok(self, entity_id: str) -> bool:
        """Prüft ob Entity verfügbar und nicht unknown/unavailable ist."""
        return valid_state(self.hass, entity_id) is not None

    def _read_actual(self) -> Actual:
        """Schnappschuss des Ist-Sensors für die Ausgangsleistung."""
        eid = self.entry.data.get(CONF_ACTUAL_SENSOR, "")
        state = self.hass.states.get(eid)
        return Actual(
            self.actual_power(), self._entity_ok(eid),
            state.last_updated.timestamp() if state is not None else None,
        )

    # ── Lesen: Sensor-Vorgaben ───────────────────────────────────────────────

    def _global_sensor(self, key: str) -> str:
        """Globale Vorgabe `key` aus dem Verteilungs-Tab der Netzgruppe; leer ohne Eintrag."""
        return str(self.group.dist_cfg().get(key, ""))

    def _effective(self, name: str) -> str:
        """Wirksamer Sensor aus SENSOR_SOURCES: lokaler Override, sonst globale Vorgabe.

        `zone1_force` liest ab 12 Uhr die Vorhersage für morgen, davor die für heute
        (`pv_forecast`) — derselbe Zieltag, nur der Sensor wechselt.
        """
        if name == "zone1_force" and dt_util.now().hour < 12:
            name = "pv_forecast"
        local, global_key = SENSOR_SOURCES[name]
        return str(self.settings[local]) or self._global_sensor(global_key)

    def _feature_value(
        self, enabled: bool, sensor: str, err_prefix: str, scale: dict[str, float],
    ) -> float | None:
        """Wert des Feature-Sensors in der Zieleinheit; None, wenn das Feature aus ist oder keine Zahl kommt.

        Ohne Zahl geht der Fehlerschlüssel des Grundes aus FEATURE_ERRORS in die Fehlerkette.
        """
        if not enabled:
            return None
        reading = read_scaled(self.hass, sensor, scale)
        if reading.reason:
            params = {} if reading.reason == NO_SENSOR else {"sensor": sensor}
            self._messages.warn((FEATURE_ERRORS[reading.reason].format(p=err_prefix), params))
        return reading.value

    def _feature_values(self, cs: CycleSettings) -> dict[str, float | None]:
        """Alle Werte aus FEATURE_READINGS nach Name, in Tabellenreihenfolge gelesen."""
        values = {}
        for name, source, enabled, err_prefix, scale, optional in FEATURE_READINGS:
            sensor = self._effective(source)
            on = getattr(cs, enabled) and (bool(sensor) or not optional)
            values[name] = self._feature_value(on, sensor, err_prefix, scale)
        return values

    # ── Lesen: Netzgruppe ────────────────────────────────────────────────────

    @property
    def group(self) -> NetGroup:
        """Netzgruppe dieser Instanz aus dem Register."""
        return group_for(self.hass, self.grid_sensor)

    @property
    def member_id(self) -> str:
        """Kennung in der Netzgruppe: die entry_id."""
        return self.entry.entry_id

    @property
    def grid_sensor(self) -> str:
        """Netzsensor der Instanz; er bestimmt die Netzgruppe."""
        return self.entry.data.get(CONF_GRID_SENSOR, "")

    @property
    def regulating(self) -> bool:
        """Regelung aktiviert."""
        return self._regulation_on

    def in_discharge_pool(self) -> bool:
        """Regelung an, Modus '1' und nicht darin ruhend."""
        if not self._regulation_on:
            return False
        mode = self._str(self.entry.data.get(CONF_MODE_SELECT, ""))
        return mode == MODE_DISCHARGE and not self._at_rest(MODE_DISCHARGE)

    def soc_reading(self) -> float | None:
        """SOC-Sensor dieser Instanz; `None`, wenn er nicht verfügbar ist."""
        soc_eid = self.entry.data.get(CONF_SOC_SENSOR, "")
        if not self._entity_ok(soc_eid):
            return None
        return self._flt(soc_eid, 0)

    def hard_limit(self) -> float:
        """Hard-Limit der aktuellen Zone (Zone 0 bei Überschuss, sonst Zone 1/2), gedeckelt auf die Gerätegrenze."""
        return float(power_limits(
            hard_limit_z0=self._setting(S_HARD_LIMIT_Z0, int), hard_limit_z1=self._setting(S_HARD_LIMIT_Z1, int),
            ac_power_limit=self._setting(S_AC_POWER_LIMIT, int), pv_reserve=self._setting(S_PV_RESERVE, int),
            allocated=None,
        ).zone_max(self.surplus_active))

    def zone3_limit(self) -> float:
        """SOC-Grenze der Zone 3 in % aus den Settings."""
        return self._setting(S_ZONE3_LIMIT, float)

    def ac_soc_target(self) -> float:
        """SOC-Ziel des AC-Ladens in % aus den Settings."""
        return self._setting(S_AC_SOC_TARGET, float)

    def capacity_kwh(self, entity_id: str) -> float | None:
        """Kapazität aus `entity_id` in kWh; None ohne Zahl."""
        return self._flt_kwh_normalized(entity_id, None)

    def actual_power(self) -> float:
        """Ist-Leistung in W."""
        return self._flt_power(self.entry.data.get(CONF_ACTUAL_SENSOR, ""))

    def output_setpoint(self) -> float:
        """Gesetzte Ausgangsleistung."""
        return self._flt(self.entry.data.get(CONF_ACTIVE_POWER, ""))

    # ── Ableiten: Regelzustand ───────────────────────────────────────────────

    @property
    def _control_state(self) -> str:
        """Regelzustand aus den Flags; es gilt surplus → tariff_charge → ac_charge → cycle → pv."""
        if self.surplus_active:
            return "surplus"
        if self.tariff_charge_active:
            return "tariff_charge"
        if self.ac_charge_active:
            return "ac_charge"
        if self.cycle_active:
            return "cycle"
        return "pv"

    @property
    def _rest_mode(self) -> str:
        """Modus des Ruhezustands: '1' mit aktivem `S_REST_IN_DISCHARGE`, sonst '0'."""
        return MODE_DISCHARGE if self._setting(S_REST_IN_DISCHARGE, bool) else MODE_DISABLED

    def _at_rest(self, mode: str) -> bool:
        """True, wenn `mode` der Ruhemodus ist und die Instanz darin ruht.

        Modus '0' wird nur vom Ruhezustand geschrieben und gilt stets als Ruhe;
        in Modus '1' entscheidet das Flag `resting`.
        """
        return mode == self._rest_mode and (mode == MODE_DISABLED or self.resting)

    def _required_discharge(self, discharge_max: int, mode: str) -> float:
        """Entladestrom für den aktuellen Regelzustand laut DISCHARGE_BY_STATE.

        Ohne Zyklus und Lade-Session gilt 0 A nur in Modus '1' (Zone 2, Ruhe in Modus 1);
        in jedem anderen Modus `discharge_max`.
        """
        state = self._control_state
        if state == "pv" and mode != MODE_DISCHARGE:
            return float(discharge_max)
        return DISCHARGE_BY_STATE.get(state, float(discharge_max))

    def _persisted_flags(self) -> dict[str, bool]:
        """Gespeicherte Zustandsflags unter ihrem Speicherschlüssel."""
        return {key: getattr(self, attr) for key, attr, _ in PERSISTED_FLAGS}

    def _store_data(self) -> dict:
        """Speicherinhalt: Settings plus gespeicherte Zustandsflags."""
        return {**self.settings, **self._persisted_flags()}

    # ── Ableiten: Verteilung ─────────────────────────────────────────────────

    def _apply_shares(self, shares: Shares | None) -> Msg | None:
        """Angewandten Verteilungsmodus übernehmen; liefert die Degradierungswarnung dieser Rechnung."""
        if shares is None:
            return None
        if shares.mode is not None:
            self.dist_mode_effective = shares.mode
        return (shares.warning, {}) if shares.warning else None

    # ── Darstellen: Texte ────────────────────────────────────────────────────

    def _tr(self, key: str, **params: object) -> str:
        """Textbaustein in der Sprache der Home-Assistant-Instanz."""
        return translate(self.hass.config.language, key, **params)

    def _set_last_action(self, key: str, **params: object) -> None:
        """Setzt Schlüssel, Parameter und Zeitstempel der letzten Aktion."""
        self.last_action_key = key
        self.last_action_params = params
        self.last_action_ts = time.time()

    @property
    def last_action(self) -> str:
        """Letzte Aktion in der Instanzsprache."""
        return self.status_texts(self.hass.config.language)["last_action"]

    @property
    def last_error(self) -> str:
        """Fehlerkette in der Instanzsprache."""
        return self.status_texts(self.hass.config.language)["last_error"]

    def status_texts(self, language: str) -> dict[str, str]:
        """Letzte Aktion und Fehlerkette in `language`."""
        return {
            "last_action": (translate(language, self.last_action_key, **self.last_action_params)
                            if self.last_action_key else ""),
            "last_error": translate_msgs(language, self.last_error_msgs),
        }

    # ── Darstellen: Anzeigezustand ───────────────────────────────────────────

    def _update_zone_display(
        self, soc: float, zone1: int, zone3: int, mode: str
    ) -> None:
        """Zone-Label und Modus-Label für Panel-Anzeige aktualisieren."""
        if soc <= zone3:
            self.current_zone = 3
        elif self.surplus_active:
            self.current_zone = 0
        elif self.cycle_active:
            self.current_zone = 1
        else:
            self.current_zone = 2
        self.zone_label = self._tr(f"zone_{self.current_zone}")

        mode_map = {
            MODE_DISABLED: "disabled",
            MODE_DISCHARGE: "discharge",
            MODE_AC_CHARGE: "ac_charge",
        }
        new_mode_key = mode_map.get(mode, "unknown")
        if mode == MODE_DISCHARGE and self._at_rest(mode):
            new_mode_key = "rest_discharge"
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
        Anders als `active_fall`, das den zuletzt ausgeführten Übergang hält,
        beschreibt der Zustand, was gerade gilt.
        """
        control = self._control_state
        if not self._regulation_on:
            state = "disabled"
        elif self._cycle_blocked:
            state = "blocked"
        elif control in ("surplus", "tariff_charge", "ac_charge"):
            state = OPERATING_BY_STATE[control]
        elif self.discharge_locked:
            state = "discharge_locked"
        elif self.is_night:
            state = "night_off"
        elif control == "pv" and self.current_zone == 3:
            state = "safety_stop"
        else:
            state = OPERATING_BY_STATE[control]

        if state == self.operating_state:
            return False
        self.operating_state = state
        self.operating_state_ts = time.time()
        return True

    def snapshot(self) -> dict[str, Any]:
        """Anzeigezustand unter internen Namen, ohne Live-Sensorwerte.

        Offsetzone: AC-Laden, sonst Zone 1 bei aktivem Zyklus, sonst Zone 2.
        Kapazität in kWh aus dem Verteilungs-Sensor der Instanz, None ohne gültigen Wert.
        """
        offset_zone = "ac" if self.ac_charge_active else "z1" if self.cycle_active else "z2"
        offset_dynamic, offset_static, offset_value = self.dyn.offset(offset_zone, self.settings)
        cap_sensor = str(self.group.dist_cfg().get(f"inst_{self.entry.entry_id}_capacity_sensor", ""))
        return {
            "offset_zone": offset_zone,
            "offset_dynamic": offset_dynamic,
            "offset_static": offset_static,
            "offset_value": offset_value,
            "capacity_kwh": self._flt_kwh_normalized(cap_sensor, None) if cap_sensor else None,
            "current_zone": self.current_zone,
            "zone_label": self.zone_label,
            "mode_key": self.mode_key,
            "mode_label": self.mode_label,
            "last_action": self.last_action,
            "last_action_ts": self.last_action_ts,
            "last_output_ts": self.out.last_ts,
            "mode_label_ts": self.mode_label_ts,
            "last_error": self.last_error,
            "integral": round(self.integral, 2),
            "cycle_active": self.cycle_active,
            "surplus_active": self.surplus_active,
            "ac_charge_active": self.ac_charge_active,
            "tariff_charge_active": self.tariff_charge_active,
            "regulation_enabled": self.settings.get(S_REGULATION_ENABLED, False),
            "grid_stddev": self.dyn.stddev,
            "grid_stddev_raw": self.dyn.stddev_raw,
            "dyn_z1_enabled": self.settings.get(S_DYN_Z1_ENABLED, False),
            "dyn_z2_enabled": self.settings.get(S_DYN_Z2_ENABLED, False),
            "dyn_ac_enabled": self.settings.get(S_DYN_AC_ENABLED, False),
            "dyn_offset_z1": self.dyn.z1,
            "dyn_offset_z2": self.dyn.z2,
            "dyn_offset_ac": self.dyn.ac,
            "active_fall": self.active_fall,
            "operating_state": self.operating_state,
            "operating_state_ts": self.operating_state_ts,
            "discharge_locked": self.discharge_locked,
            "dist_mode_effective": self.dist_mode_effective,
            "is_night": self.is_night,
            "forecast_tariff_suppressed": self.forecast_tariff_suppressed,
            "forecast_surplus_forced": self.forecast_surplus_forced,
            "forecast_exit_lock": self.forecast_exit_lock,
            "allocated_power": self.allocated_power,
        }

    def snapshot_view(self, names: tuple[str | tuple[str, str], ...]) -> dict[str, Any]:
        """Auswahl aus `snapshot()`; ein Paar (außen, innen) benennt den Schlüssel um."""
        snap = self.snapshot()
        pairs = (n if isinstance(n, tuple) else (n, n) for n in names)
        return {outer: snap[inner] for outer, inner in pairs}

    # ── Darstellen: Entity-Listener ──────────────────────────────────────────

    def register_entity_listener(self, cb: Callable[[], None]) -> None:
        """Callback anmelden, den `notify_listeners` aufruft."""
        self._listeners.append(cb)

    def unregister_entity_listener(self, cb: Callable[[], None]) -> None:
        """Callback abmelden; ein unbekannter Callback wird ignoriert."""
        if cb in self._listeners:
            self._listeners.remove(cb)

    def notify_listeners(self) -> None:
        """Alle Callbacks aufrufen; eine Exception wird geloggt, die übrigen laufen weiter."""
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                _LOGGER.exception("Solakon: Fehler in Entity-Listener")

    # ── Schreiben: Gerät ─────────────────────────────────────────────────────

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

    async def _set_discharge(self, amps: float) -> None:
        """Entladestrom setzen — nur wenn aktueller Wert abweicht."""
        await self._set_number(self.entry.data[CONF_DISCHARGE_CURRENT], amps, only_if_changed=True)

    async def _sync_export_limit(self, target: int) -> None:
        """grid_export_power_limit korrigieren wenn von Soll abgewichen — nur wenn Entity konfiguriert."""
        export_entity = self.entry.data.get(CONF_EXPORT_LIMIT, "")
        if not export_entity:
            return
        current = self._flt(export_entity, -1)
        if await self._set_number(export_entity, target, only_if_changed=True, current=current):
            _LOGGER.info("Solakon: Export-Limit korrigiert %d → %d W", int(current), target)

    async def _timer_toggle(self) -> None:
        """Timer-Wechsel 3598↔3599 — erzwingt sichere Modus-Übernahme."""
        timer_eid = self.entry.data[CONF_TIMEOUT_SET]
        current = self._flt(timer_eid, 3599)
        new_val = 3598.0 if current >= 3599 else 3599.0
        await self._set_number(timer_eid, new_val)
        self._timer_toggled_in_cycle = True
        await asyncio.sleep(1)

    # ── Schreiben: Ausgangsleistung ──────────────────────────────────────────

    def _warn_hardware(self, key: str, params: dict) -> None:
        """Schreibwarnung in die Fehlerkette des laufenden Regelzyklus und ins Log."""
        self._messages.hardware((key, params))
        _LOGGER.error("Solakon: %s", self._tr(key, **params))

    async def _handle_output_stall(self, limit: float) -> None:
        """Stillstand prüfen und das Urteil umsetzen.

        `REWRITTEN` setzt nur die letzte Aktion. `RECOVERY`: Schreibwarnung,
        Integral-Reset, Output 0, Timer-Toggle, Ruhezustand — Fall D holt im
        Folgezyklus zurück.
        """
        verdict = await self.out.check_stall(limit)
        if verdict is None:
            return
        stall, actual = verdict
        if stall is Stall.REWRITTEN:
            self._set_last_action("act_output_rewritten", actual=actual, limit=limit)
            return
        self._messages.hardware(("warn_output_stuck", {"actual": actual, "limit": limit}))
        _LOGGER.error("Solakon: %s (Versuch %d)", self._tr("warn_output_stuck", actual=actual, limit=limit),
                      self.out.stall_actions)
        await self._transition(reset_integral=True, output=0, rest=True)
        self._set_last_action("act_output_recovery", actual=actual, limit=limit)

    async def _set_fixed_output(
        self, target: float, current: float, action_key: str, ac_charge_mode: bool = False,
    ) -> None:
        """Fester Sollwert: schreibt nur bei Abweichung über 0,5 vom kommandierten Ist-Wert."""
        if abs(current - target) > 0.5:
            self._set_last_action(action_key, power=target)
            await self.out.set_and_wait(target, ac_charge_mode=ac_charge_mode)

    async def _pi_step(
        self, grid: float, power_base: float, offset: float, limit: float, p_factor: float,
        i_factor: float, share: float, current_power: float, action_key: str,
        ac_charge_mode: bool = False,
    ) -> None:
        """Ein PI-Schritt: Sollwert aus Poolanteil berechnen, Aktion setzen, schreiben."""
        new_pw = self.pi.calculate(
            grid, power_base, offset, limit, p_factor, i_factor,
            ac_charge_mode=ac_charge_mode, error_share=share,
        )
        self._set_last_action(action_key, frm=current_power, to=new_pw)
        await self.out.set_and_wait(new_pw, ac_charge_mode=ac_charge_mode)

    # ── Schreiben: Zustandsübergang und Integral ─────────────────────────────

    async def _transition(
        self, *, reset_integral: bool = False, flags: dict[str, bool] | None = None,
        output: float | None = None, wait: bool = True, ac_charge_mode: bool = False,
        timer: bool = True, timer_first: bool = False, mode: str | None = None,
        rest: bool = False,
    ) -> None:
        """Zustandsübergang in fester Folge: Integral, Flags, Output, Timer, Modus.

        `flags` setzt nur die übergebenen Zustandsflags. `output` None lässt die
        Ausgangsleistung unberührt, `wait=False` schreibt sie ohne Konvergenzwarten.
        `timer_first` schaltet den Timer vor den Output. `mode` None schreibt keinen Modus.
        `rest` schreibt den Ruhemodus statt `mode`; jeder geschriebene Modus setzt `resting`.
        """
        if reset_integral:
            self.pi.reset()
        for name, value in (flags or {}).items():
            setattr(self, name, value)
        if timer and timer_first:
            await self._timer_toggle()
        if output is not None:
            if wait:
                await self.out.set_and_wait(output, ac_charge_mode=ac_charge_mode)
            else:
                await self.out.set(output)
        if timer and not timer_first:
            await self._timer_toggle()
        if rest:
            mode = self._rest_mode
        if mode is not None:
            self.resting = rest
            await self._set_mode(mode)

    @property
    def integral(self) -> float:
        """Integralanteil des PI-Reglers."""
        return self.pi.integral

    @integral.setter
    def integral(self, value: float) -> None:
        """Integralanteil des PI-Reglers setzen."""
        self.pi.integral = value

    def reset_integral(self) -> None:
        """Integral nullen, als letzte Aktion vermerken, Listener benachrichtigen."""
        self.pi.reset()
        self._set_last_action("act_integral_reset")
        self.notify_listeners()

    # ── Lebenszyklus: Setup und Settings ─────────────────────────────────────

    async def async_setup(self) -> None:
        """Settings und Zustandsflags laden, Trigger registrieren.

        Gespeicherte Werte, die das Schema verletzen, werden durch den Standard ersetzt,
        zurückgespeichert und per Benachrichtigung gemeldet.
        """
        stored = await self._store.async_load()
        if stored:
            stored, reset = sanitize(stored, SETTINGS_SCHEMA)
            self.settings = {**SETTINGS_DEFAULTS, **stored}
            for key, attr, default in PERSISTED_FLAGS:
                setattr(self, attr, bool(stored.get(key, default)))
            if reset:
                notify_reset(self.hass, f"{DOMAIN}_settings_reset_{self.entry.entry_id}", self.entry.title, reset)
                await self._store.async_save(self._store_data())
            _LOGGER.debug("Solakon: Einstellungen aus Speicher geladen")
        else:
            self.settings = SETTINGS_DEFAULTS.copy()
            _LOGGER.info("Solakon: Standardwerte geladen")

        cfg = self.entry.data
        entities_to_track = [cfg.get(key, "") for key, triggers, _ in CORE_SENSORS if triggers]
        entities_to_track = [e for e in entities_to_track if e]

        if entities_to_track:
            unsub = async_track_state_change_event(
                self.hass, entities_to_track, self._on_state_change
            )
            self._unsub_trackers.append(unsub)

        for name, _ in TRACKERS:
            self._retrack(name)

    async def async_shutdown(self) -> None:
        """Listener abräumen."""
        for unsub in self._unsub_trackers:
            unsub()
        self._unsub_trackers.clear()
        for name, _ in TRACKERS:
            self._untrack(name)

    async def async_update_settings(self, changes: dict[str, Any]) -> None:
        """Änderungen prüfen, übernehmen und speichern; InvalidSettings, wenn eine das Schema verletzt."""
        if findings := check(changes, SETTINGS_SCHEMA):
            raise InvalidSettings(findings)
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
                await self._set_discharge(self._setting(S_DISCHARGE_MAX, float))
                await self._transition(mode=MODE_DISABLED)
                off_key = "disabled_regulation_off"
                if self.mode_key != off_key:
                    self.mode_label_ts = time.time()
                self.mode_key = off_key
                self.mode_label = self._tr(f"mode_{off_key}")

        before = {name: self._tracker_input(name) for name, _ in TRACKERS}

        if S_REST_IN_DISCHARGE in changes:
            self.resting = False
        self.settings.update(changes)
        await self._store.async_save(self._store_data())
        _LOGGER.info("Solakon: Einstellungen gespeichert")

        for name, _ in TRACKERS:
            if self._tracker_input(name) != before[name]:
                self._retrack(name)

        self.notify_listeners()

        # Neuen Zustand sofort anwenden
        if self._regulation_on:
            self.request_regulation()

    def schedule_save(self) -> None:
        """Settings und Zustandsflags nach 5 s speichern."""
        self._store.async_delay_save(self._store_data, 5)

    # ── Lebenszyklus: Trigger ────────────────────────────────────────────────

    def _tracker_input(self, name: str) -> tuple:
        """Eingaben eines Triggers: Aktivierungswerte und Sensor bzw. Intervall."""
        keys = dict(TRACKERS)[name]
        target = self.settings[S_PERIODIC_INTERVAL] if name == "periodic" else self._effective(name)
        return tuple(self.settings[k] for k in keys), target

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
        if not any(self.settings[k] for k in dict(TRACKERS)[name]):
            return
        if name == "periodic":
            interval = max(5, self._setting(S_PERIODIC_INTERVAL, int))
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

    def apply_group_change(self) -> None:
        """Nach geänderter Verteilung der Netzgruppe: Trigger neu anmelden, Regelzyklus anstoßen."""
        self.update_sensor_trackers()
        self.request_regulation()

    def request_regulation(self) -> None:
        """Regelzyklus als Task anstoßen."""
        self.hass.async_create_task(self._async_regulate())

    # ── Ausführung: Regelzyklus ──────────────────────────────────────────────

    @callback
    def _on_state_change(self, event: Event) -> None:
        """Zustandsänderung eines Trigger-Sensors: Regelzyklus anstoßen."""
        self.request_regulation()

    @callback
    def _on_periodic(self, _now: object) -> None:
        """Periodischer Trigger: Regelzyklus anstoßen."""
        self.request_regulation()

    async def _async_regulate(self) -> None:
        """Regelzyklus unter dem Lock; läuft bereits einer, entfällt dieser Aufruf.

        Eine Exception wird geloggt und beendet nur diesen Zyklus.
        """
        if self._lock.locked():
            return
        async with self._lock:
            try:
                await self._run_regulation_cycle()
            except Exception:
                _LOGGER.exception("Solakon: Fehler in Regelschleife")

    async def _run_regulation_cycle(self) -> None:
        """Ein Regelzyklus, aufgerufen unter dem Lock von `_async_regulate`.

        Liest die Sensoren, rechnet Verteilung, Grenzen, Prognoseflags und Tariflage, führt
        den fälligen Fall aus, gleicht den Entladestrom ab und regelt in Modus '1' oder '3'
        die Ausgangsleistung. Regelung aus, ein Kernsensor ohne Zahl oder ungültige
        Settings beenden den Zyklus vorzeitig über `_end_cycle`.
        """
        cfg = self.entry.data

        # ── 0. Regelung aktiv? ───────────────────────────────────────────────
        if not self._regulation_on:
            self._end_cycle(notify_on_change=True)
            return

        self._timer_toggled_in_cycle = False
        self._messages = CycleMessages()
        self._cycle_blocked = False

        prev_flags = self._persisted_flags()

        # ── 1. Kernsensoren lesen ────────────────────────────────────────────
        # Pflichtsensoren müssen eine Zahl liefern
        missing = next((cfg[key] for key, _, required in CORE_SENSORS
                        if required and read_number(self.hass, cfg[key]).value is None), None)
        if missing is not None:
            _LOGGER.debug("Solakon: Kernsensor %s ohne Zahlenwert, Zyklus übersprungen", missing)
            self._messages.fail(("err_core_sensor", {"sensor": missing}))
            self._end_cycle(blocked=True, notify_on_change=self._messages.msgs == self.last_error_msgs)
            return

        soc = self._flt(cfg[CONF_SOC_SENSOR])
        grid = self._flt_power(cfg[CONF_GRID_SENSOR])
        solar = self._flt_power(cfg[CONF_SOLAR_SENSOR])
        actual = self._flt_power(cfg[CONF_ACTUAL_SENSOR])
        mode = self._str(cfg[CONF_MODE_SELECT])
        timer_val = self._flt(cfg[CONF_TIMEOUT_COUNTDOWN])

        # ── 2. StdDev und dynamische Offsets ─────────────────────────────────
        # StdDev ist eine Eigenschaft der Netzgruppe, nicht der einzelnen Instanz:
        # nur der Gruppen-Leader nimmt in den σ-Puffer auf, alle Instanzen übernehmen
        # σ aus der Netzgruppe.
        if self.group.leader() is self:
            self.group.sigma.record(grid, time.monotonic(), self.settings)
        self.dyn.update(self.group.sigma, self.settings)

        # ── 3. Settings und Feature-Sensoren ─────────────────────────────────
        cs = self._cycle_settings()

        ac_offset = float(self.dyn.offset("ac", self.settings)[2])

        tariff_sensor = self._effective("tariff")
        feature = self._feature_values(cs)

        # ── 4. Verteilung und Leistungsgrenzen ───────────────────────────────
        error_share, allocated_power, shares = self.group.distribution(self, soc)
        self.allocated_power = allocated_power
        if dist_warning := self._apply_shares(shares):
            self._messages.warn(dist_warning)
        limits = power_limits(
            hard_limit_z0=cs.hard_limit_z0, hard_limit_z1=cs.hard_limit_z1,
            ac_power_limit=cs.ac_power_limit, pv_reserve=cs.pv_reserve, allocated=allocated_power,
        )

        # Verwertbarer PV-Überschuss: Luft zwischen dem aktuellen Output und dem
        # Minimum aus geltendem Hard-Limit und aktueller PV-Leistung, geklemmt auf ≥0.
        # Nutzt die Zone des vorherigen Zyklus — self.surplus_active ist hier noch
        # nicht aktualisiert.
        self.surplus_power = max(0.0, min(limits.zone_max(self.surplus_active), solar) - actual)

        # ── 5. Prognoseflags ─────────────────────────────────────────────────
        forecast = forecast_flags(
            surplus_forecast=feature["surplus_forecast"], surplus_lock=feature["surplus_lock"],
            zone1_force=feature["zone1_force"], solar=solar, soc=soc,
            surplus_forecast_threshold=cs.surplus_forecast_threshold, hard_limit_z0=cs.hard_limit_z0,
            zone3_limit=cs.zone3_limit, surplus_lock_factor=cs.surplus_lock_factor,
            zone1_force_threshold=cs.zone1_force_threshold, pv_reserve=cs.pv_reserve,
            zone1_force_min_soc=cs.zone1_force_min_soc,
        )
        self.forecast_surplus_forced = forecast.surplus_forced
        self.forecast_exit_lock = forecast.exit_lock
        self.forecast_tariff_suppressed = forecast_suppressed(feature["pv_forecast"], cs.pv_forecast_threshold)
        self.zone1_forced = forecast.zone1_forced

        # ── 6. Validierung ───────────────────────────────────────────────────
        invalid = next((key for failed, key in (
            (cs.zone1_limit <= cs.zone3_limit, "err_soc_zone1_zone3"),
            (cs.surplus_enabled and cs.surplus_threshold <= cs.zone1_limit, "err_soc_surplus_zone1"),
            (cs.zone1_force_enabled and not (cs.zone3_limit < cs.zone1_force_min_soc < cs.zone1_limit),
             "err_soc_zone1_force"),
            (not self._entity_ok(cfg[CONF_MODE_SELECT]), "err_mode_select"),
        ) if failed), None)
        if invalid:
            self._messages.fail((invalid, {}))
            self._end_cycle(blocked=True)
            return

        # ── 7. Export-Limit und Tariflage ────────────────────────────────────
        await self._sync_export_limit(limits.export)

        # Preis ohne Einheitenumrechnung; die Einheitenwarnung der Tariflage geht als
        # weicher Fehler in dieselbe Meldungskette ein.
        price = self._feature_value(cs.tariff_enabled, tariff_sensor, "err_tariff", {})
        tariff = self.tariff.assess(
            enabled=cs.tariff_enabled and bool(tariff_sensor), suppressed=self.forecast_tariff_suppressed,
            price=price, cheap_entity=feature["cheap"], cheap_setting=cs.tariff_cheap,
            exp_entity=feature["exp"], exp_setting=cs.tariff_exp,
            unit=unit_of(self.hass.states.get(tariff_sensor)) if price is not None else "", now=time.time(),
        )
        if tariff.unit_warning:
            self._messages.warn(tariff.unit_warning)

        # ── 8. Überschuss und Nacht ──────────────────────────────────────────
        prev_actual = self._prev_actual
        self._prev_actual = actual

        total_actual = pool_sum(self.group.discharge_pool(), self, actual,
                                           lambda m: m.actual_power())

        stage = surplus_and_night(
            state=SurplusState(self._solar_zero_entry_armed, self._dark),
            surplus_enabled=cs.surplus_enabled, surplus_active=self.surplus_active,
            cycle_active=self.cycle_active, forced=self.forecast_surplus_forced,
            exit_lock=self.forecast_exit_lock, solar=solar, soc=soc, actual=actual,
            prev_actual=prev_actual, total_actual=total_actual, grid=grid, error_share=error_share,
            surplus_threshold=cs.surplus_threshold, surplus_soc_hyst=cs.surplus_soc_hyst,
            surplus_pv_hyst=cs.surplus_pv_hyst, pv_reserve=cs.pv_reserve,
            night_hysteresis=cs.night_hysteresis, night_enabled=cs.night_enabled,
        )
        self._solar_zero_entry_armed = stage.state.armed
        self._dark = stage.state.dark
        new_surplus = stage.new_surplus
        is_night = stage.is_night
        self.is_night = is_night

        # ── 9. Falls / Zonenwechsel ──────────────────────────────────────────
        fall_executed = await self._execute_falls(
            soc=soc, grid=grid, actual=actual, mode=mode,
            zone1_limit=cs.zone1_limit, zone3_limit=cs.zone3_limit,
            surplus_enabled=cs.surplus_enabled, new_surplus=new_surplus,
            ac_enabled=cs.ac_enabled, ac_soc_target=cs.ac_soc_target,
            ac_hysteresis=cs.ac_hysteresis, ac_offset=ac_offset,
            tariff=tariff, tariff_soc=cs.tariff_soc, tariff_soc_hyst=cs.tariff_soc_hyst,
            tariff_power=cs.tariff_power,
            is_night=is_night, total_actual=total_actual,
            zone1_forced=self.zone1_forced,
        )
        if fall_executed:
            self.active_fall = fall_executed

        # Zustand hinter Fall TM: die Sperre selbst mit den Flags nach den Falls,
        # nicht ihr Auslöser.
        self.discharge_locked = tariff.discharge_locked(
            self.tariff_charge_active or self.ac_charge_active, self.surplus_active)

        # ── 10. Entladestrom mit Regelzustand abgleichen ─────────────────────
        mode = self._str(cfg[CONF_MODE_SELECT])
        await self._set_discharge(self._required_discharge(cs.discharge_max, mode))

        # ── 11. PI-Phase (Modus '1' und '3') ─────────────────────────────────
        blocked = False
        if mode in (MODE_DISCHARGE, MODE_AC_CHARGE):
            blocked = await self._run_pi_phase(cs, soc, mode, timer_val, error_share, limits, ac_offset)

        # ── 12. Anzeige und Flag-Speicherung ─────────────────────────────────
        self._end_cycle(blocked=blocked, display=(soc, cs.zone1_limit, cs.zone3_limit, mode),
                        prev_flags=prev_flags)

    async def _execute_falls(self, **v) -> str | None:
        """Fall per `zones.decide` bestimmen, Übergang und Aktionstext ausführen, Kennung zurückgeben."""
        d = decide(ZoneInputs(
            **v,
            self_adjust_tol=self._setting(S_SELF_ADJUST_TOL, float),
            surplus_active=self.surplus_active,
            ac_charge_active=self.ac_charge_active,
            tariff_charge_active=self.tariff_charge_active,
            cycle_active=self.cycle_active,
            at_rest=self._at_rest(v["mode"]),
        ))
        if d is None:
            return None
        await self._transition(**d.transition)
        if d.warn:
            self._messages.warn(d.warn)
        self._set_last_action(d.action, **d.params)
        return d.name

    async def _run_pi_phase(
        self, cs: CycleSettings, soc: float, mode: str, timer_val: float, error_share: float,
        limits: PowerLimits, ac_offset: float,
    ) -> bool:
        """PI-Phase in Modus '1' oder '3': Timeout-Reset, dann ein Pfad je Regelzustand.

        Pfade: Zone-0-Festwert, AC-PI, Tarif-Festwert oder Entlade-PI mit Stillstandsprüfung.
        Im Ruhemodus endet die Phase nach dem Timeout-Reset. Liefert die Zweitlesung von
        Netz oder PV keine Zahl, endet sie mit `err_core_sensor` ohne Schreibbefehl.
        True, wenn der Regelzyklus damit blockiert ist.
        """
        cfg = self.entry.data

        # ── 11a. Zweitlesung nach den Falls ──────────────────────────────────
        grid = read_scaled(self.hass, cfg[CONF_GRID_SENSOR], UNIT_SCALE_W).value
        solar = read_scaled(self.hass, cfg[CONF_SOLAR_SENSOR], UNIT_SCALE_W).value

        # Eine Energierichtung je Netzgruppe: lädt eine Schwester, entlädt Zone 1 nur PV.
        sister_charging = self.group.sister_charging(self)
        capped = sister_charging and self.cycle_active and mode == MODE_DISCHARGE

        target_offset = float(self.dyn.offset("z1" if self.cycle_active else "z2", self.settings)[2])

        # ── 11b. Timeout-Reset ───────────────────────────────────────────────
        # Entfällt wenn ein Fall in diesem Zyklus bereits getoggelt hat
        if timer_val < 120 and not self._timer_toggled_in_cycle and self._entity_ok(cfg[CONF_TIMEOUT_COUNTDOWN]):
            await self._timer_toggle()

        if self._at_rest(mode):
            return False

        missing = next((cfg[key] for key, value in ((CONF_GRID_SENSOR, grid), (CONF_SOLAR_SENSOR, solar))
                        if value is None), None)
        if missing is not None:
            self._messages.fail(("err_core_sensor", {"sensor": missing}))
            return True
        dynamic_max = limits.pi_max(mode, self.cycle_active, solar, sister_charging)

        # Einzige CONF_ACTIVE_POWER-Lesung dieses Zyklus, nach dem letzten Await vor
        # der PI-Entscheidung. Gemeinsam genutzt von Gate, PI-Basis und Log-Zeile.
        current_power = self._flt(cfg[CONF_ACTIVE_POWER])

        # Eigener Pool für AC-Laden, nach den Falls berechnet.
        ac_error_share, shares = self.group.ac_share(self, soc)
        if dist_warning := self._apply_shares(shares):
            self._messages.warn(dist_warning)

        # ── 11c. PI-Pfade ────────────────────────────────────────────────────
        if self.surplus_active:
            await self._set_fixed_output(limits.zone0, current_power, "act_zone0_output")

        elif self.ac_charge_active:
            if self.pi.gate_ac(grid, ac_offset, cs.tolerance) == STEP:
                await self._pi_step(
                    grid,
                    pool_sum(self.group.ac_pool(), self, current_power,
                                        lambda m: m.output_setpoint()) * ac_error_share,
                    ac_offset, limits.ac, cs.ac_p, cs.ac_i, ac_error_share, current_power,
                    "act_ac_pi", ac_charge_mode=True,
                )

        elif self.tariff_charge_active:
            await self._set_fixed_output(cs.tariff_power, current_power, "act_tariff_power", ac_charge_mode=True)

        else:
            gate = self.pi.gate_discharge(grid, current_power, target_offset, dynamic_max, cs.tolerance)
            if gate == STEP:
                await self._pi_step(
                    grid,
                    pool_sum(self.group.discharge_pool(), self, current_power,
                                        lambda m: m.output_setpoint()) * error_share,
                    target_offset, dynamic_max, cs.p_factor, cs.i_factor, error_share, current_power,
                    "act_pi_sister_charging" if capped else "act_pi",
                )
            elif gate == SATURATED:
                await self._handle_output_stall(dynamic_max)
            else:
                self.out.reset_stall()
            if capped and gate != STEP and self.last_action_key != "act_zone1_sister_charging":
                self._set_last_action("act_zone1_sister_charging")
        return False

    def _end_cycle(
        self, *, blocked: bool = False,
        display: tuple[float, int, int, str] | None = None, prev_flags: dict[str, bool] | None = None,
        notify_on_change: bool = False,
    ) -> None:
        """Zyklus abschließen: Fehler, Anzeige, Flag-Speicherung, Benachrichtigung.

        Übernimmt die Meldungen des Zyklus nach `last_error_msgs`.
        `display` (soc, zone1, zone3, mode) zieht Zonen- und Modusanzeige nach, sonst nur
        den Betriebszustand. Mit `prev_flags` wird bei geänderten Flags verzögert gespeichert.
        `notify_on_change` benachrichtigt nur, wenn der Betriebszustand gewechselt hat.
        """
        self.last_error_msgs = self._messages.msgs
        if blocked:
            self._cycle_blocked = True
        if display is not None:
            self._update_zone_display(*display)
            changed = True
        else:
            changed = self._update_operating_state()
        if prev_flags is not None and self._persisted_flags() != prev_flags:
            self.schedule_save()
        if changed or not notify_on_change:
            self.notify_listeners()
