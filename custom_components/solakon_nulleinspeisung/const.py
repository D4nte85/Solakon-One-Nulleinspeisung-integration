"""Constants for Solakon ONE Nulleinspeisung."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, NamedTuple

DOMAIN = "solakon_nulleinspeisung"
STORAGE_VERSION = 2
VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text())["version"]

# -- Config-Entry Keys --------------------------------------------------------
CONF_INSTANCE_NAME    = "instance_name"
CONF_GRID_SENSOR      = "grid_power_sensor"
CONF_ACTUAL_SENSOR    = "actual_power_sensor"
CONF_SOLAR_SENSOR     = "solar_power_sensor"
CONF_SOC_SENSOR       = "soc_sensor"
CONF_TIMEOUT_COUNTDOWN = "remote_timeout_countdown_sensor"
CONF_ACTIVE_POWER     = "active_power_number"
CONF_DISCHARGE_CURRENT = "max_discharge_current_number"
CONF_TIMEOUT_SET      = "remote_timeout_set_number"
CONF_MODE_SELECT      = "mode_select"
CONF_EXPORT_LIMIT     = "export_power_limit_number"

# -- Config-Entry Entity Defaults (sprachabhängig) ----------------------------
REQUIRED_ENTITY_DEFAULTS_DE = {
    CONF_ACTUAL_SENSOR:      "sensor.solakon_one_leistung",
    CONF_SOLAR_SENSOR:       "sensor.solakon_one_pv_leistung",
    CONF_SOC_SENSOR:         "sensor.solakon_one_batterie_ladestand",
    CONF_TIMEOUT_COUNTDOWN:  "sensor.solakon_one_fernsteuerung_zeituberschreitung",
    CONF_ACTIVE_POWER:       "number.solakon_one_fernsteuerung_leistung",
    CONF_DISCHARGE_CURRENT:  "number.solakon_one_maximaler_entladestrom",
    CONF_TIMEOUT_SET:        "number.solakon_one_fernsteuerung_zeituberschreitung",
    CONF_MODE_SELECT:        "select.solakon_one_modus_fernsteuern",
    CONF_EXPORT_LIMIT:       "number.solakon_one_netz_ausgangsleistungsgrenze",
}

REQUIRED_ENTITY_DEFAULTS_EN = {
    CONF_ACTUAL_SENSOR:      "sensor.solakon_one_active_power",
    CONF_SOLAR_SENSOR:       "sensor.solakon_one_pv_power",
    CONF_SOC_SENSOR:         "sensor.solakon_one_battery_state_of_charge",
    CONF_TIMEOUT_COUNTDOWN:  "sensor.solakon_one_remote_timeout_countdown",
    CONF_ACTIVE_POWER:       "number.solakon_one_remote_control_power",
    CONF_DISCHARGE_CURRENT:  "number.solakon_one_maximum_discharge_current",
    CONF_TIMEOUT_SET:        "number.solakon_one_remote_control_timeout",
    CONF_MODE_SELECT:        "select.solakon_one_remote_control_mode",
    CONF_EXPORT_LIMIT:       "number.solakon_one_grid_export_power_limit",
}

PLATFORMS = ["sensor", "switch", "binary_sensor"]

# -- Geraetegrenze ------------------------------------------------------------
# Maximale Ein- und Ausgangsleistung des Solakon ONE laut Datenblatt. Deckelt jeden
# Sollwert.
DEVICE_MAX_POWER = 1200
# Maximaler Entladestrom in A, Grenze der Geräte-Entity.
DEVICE_MAX_CURRENT = 40

# -- Ausgangs-Stillstandserkennung --------------------------------------------
# Greift nur im gesaettigten Standard-PI-Zweig (at_max_limit). Weicht die tatsaechliche
# Wechselrichter-Ausgabe um mehr als OUTPUT_STALL_DEVIATION vom Limit ab und steht der
# Messwert dabei laenger als OUTPUT_STALL_SECONDS unveraendert, wird der Sollwert neu
# geschrieben und bei Fortbestand die Recovery aus Fall D gefahren.
OUTPUT_STALL_SECONDS = 300
OUTPUT_STALL_DEVIATION = 0.05

# -- Tarif-Einheitenplausibilitaet --------------------------------------------
# Die Preisschwellen sind ct/kWh. Liegt der Preis im Fenster
# [0, TARIFF_UNIT_SUSPECT_PRICE) bei einer Guenstig-Schwelle ab
# TARIFF_UNIT_SUSPECT_THRESHOLD und haelt das laenger als
# TARIFF_UNIT_SUSPECT_SECONDS an, liefert der Sensor vermutlich EUR/kWh.
# Gemeldet wird nur, umgerechnet nichts.
TARIFF_UNIT_SUSPECT_PRICE = 1.0
TARIFF_UNIT_SUSPECT_THRESHOLD = 3.0
TARIFF_UNIT_SUSPECT_SECONDS = 21600

# -- Betriebszustaende --------------------------------------------------------
# Zusammengefasster Zustand der Instanz, ausgewertet in dieser Reihenfolge: der
# erste zutreffende gewinnt. Abgeleitet aus den Zustandsflags, nicht aus dem
# zuletzt ausgefuehrten Fall. Reihenfolge und Schluessel muessen mit den
# Uebersetzungen (translations, panel.*.json) uebereinstimmen.
OPERATING_STATES = [
    "disabled",
    "blocked",
    "exporting",
    "tariff_charging",
    "ac_charging",
    "discharge_locked",
    "night_off",
    "battery_supply",
    "safety_stop",
    "pv_direct",
]

# Fall-Schlüssel des Regelzyklus, Reihenfolge wie im Zyklus durchlaufen.
FALL_KEYS = [
    "0A", "0B",
    "A", "B", "C", "D", "E", "F",
    "G", "H", "I",
    "GT", "HT", "TM",
]

# Modus-Schlüssel des Betriebsmodus-Sensors.
MODE_KEYS = [
    "waiting",
    "disabled",
    "discharge",
    "ac_charge",
    "disabled_regulation_off",
    "rest_discharge",
    "unknown",
]

# -- Inverter Mode Values -----------------------------------------------------
MODE_DISABLED  = "0"
MODE_DISCHARGE = "1"
MODE_AC_CHARGE = "3"

# -- Settings Keys (Panel / Storage) ------------------------------------------
S_REGULATION_ENABLED = "regulation_enabled"

S_P_FACTOR   = "p_factor"
S_I_FACTOR   = "i_factor"
S_TOLERANCE  = "tolerance"
S_WAIT_TIME  = "wait_time"
S_STDDEV_WINDOW = "stddev_window"
S_STDDEV_TRIM_COUNT = "stddev_trim_count"

S_ZONE1_LIMIT   = "zone1_limit"
S_ZONE3_LIMIT   = "zone3_limit"
S_DISCHARGE_MAX  = "discharge_max"
S_HARD_LIMIT_Z0  = "hard_limit_z0"
S_HARD_LIMIT_Z1  = "hard_limit_z1"
S_OFFSET_1      = "offset_1"
S_OFFSET_2      = "offset_2"
S_PV_RESERVE    = "pv_reserve"

S_SURPLUS_ENABLED       = "surplus_enabled"
S_SURPLUS_SOC_THRESHOLD = "surplus_soc_threshold"
S_SURPLUS_SOC_HYST      = "surplus_soc_hyst"
S_SURPLUS_PV_HYST       = "surplus_pv_hyst"
S_SURPLUS_FORECAST_ENABLED   = "surplus_forecast_enabled"
# Schwelle in kWh Tagesertrag.
S_SURPLUS_FORECAST_THRESHOLD = "surplus_forecast_threshold"
S_SURPLUS_LOCK_ENABLED = "surplus_lock_enabled"
S_SURPLUS_LOCK_SENSOR  = "surplus_lock_sensor"
S_SURPLUS_LOCK_FACTOR  = "surplus_lock_factor"

S_AC_ENABLED     = "ac_enabled"
S_AC_SOC_TARGET  = "ac_soc_target"
S_AC_POWER_LIMIT = "ac_power_limit"
S_AC_HYSTERESIS  = "ac_hysteresis"
S_AC_OFFSET      = "ac_offset"
S_AC_P_FACTOR    = "ac_p_factor"
S_AC_I_FACTOR    = "ac_i_factor"

S_TARIFF_ENABLED          = "tariff_enabled"
S_TARIFF_PRICE_SENSOR     = "tariff_price_sensor"
S_TARIFF_CHEAP_THRESHOLD  = "tariff_cheap_threshold"
S_TARIFF_EXP_THRESHOLD    = "tariff_exp_threshold"
S_TARIFF_SOC_TARGET       = "tariff_soc_target"
S_TARIFF_SOC_HYST         = "tariff_soc_hyst"
S_TARIFF_POWER            = "tariff_power"
S_TARIFF_CHEAP_ENTITY     = "tariff_cheap_entity"
S_TARIFF_EXP_ENTITY       = "tariff_exp_entity"

S_PV_FORECAST_ENABLED    = "pv_forecast_enabled"
S_PV_FORECAST_SENSOR     = "pv_forecast_sensor"
# Schwelle in kWh Tagesertrag.
S_PV_FORECAST_THRESHOLD  = "pv_forecast_threshold"

# Zone-1-Nacht-Forcierung. Sensor ist zeitabhängig "heute" (S_PV_FORECAST_SENSOR
# + globaler Fallback) oder "morgen" (S_ZONE1_FORCE_SENSOR + globaler Fallback) — siehe
# _effective() in coordinator.py.
S_ZONE1_FORCE_ENABLED   = "zone1_force_enabled"
S_ZONE1_FORCE_SENSOR    = "zone1_force_sensor"
S_ZONE1_FORCE_THRESHOLD = "zone1_force_threshold"
S_ZONE1_FORCE_MIN_SOC   = "zone1_force_min_soc"

S_NIGHT_ENABLED = "night_enabled"
# Einschaltschwelle der Nacht = PV-Ladereserve + Hysterese.
S_NIGHT_HYSTERESIS = "night_hysteresis"

# Ruhezustand in Modus '1' mit 0 W statt Modus '0'.
S_REST_IN_DISCHARGE = "rest_in_discharge"

S_PERIODIC_ENABLED  = "periodic_enabled"
S_PERIODIC_INTERVAL = "periodic_interval"

S_SELF_ADJUST     = "self_adjust_enabled"
S_SELF_ADJUST_TOL = "self_adjust_tolerance"

S_DYN_Z1_ENABLED  = "dyn_z1_enabled"
S_DYN_Z1_MIN      = "dyn_z1_min"
S_DYN_Z1_MAX      = "dyn_z1_max"
S_DYN_Z1_NOISE    = "dyn_z1_noise"
S_DYN_Z1_FACTOR   = "dyn_z1_factor"
S_DYN_Z1_NEGATIVE = "dyn_z1_negative"

S_DYN_Z2_ENABLED  = "dyn_z2_enabled"
S_DYN_Z2_MIN      = "dyn_z2_min"
S_DYN_Z2_MAX      = "dyn_z2_max"
S_DYN_Z2_NOISE    = "dyn_z2_noise"
S_DYN_Z2_FACTOR   = "dyn_z2_factor"
S_DYN_Z2_NEGATIVE = "dyn_z2_negative"

S_DYN_AC_ENABLED  = "dyn_ac_enabled"
S_DYN_AC_MIN      = "dyn_ac_min"
S_DYN_AC_MAX      = "dyn_ac_max"
S_DYN_AC_NOISE    = "dyn_ac_noise"
S_DYN_AC_FACTOR   = "dyn_ac_factor"
S_DYN_AC_NEGATIVE = "dyn_ac_negative"

# Harte Grenzen (min, max) je Gruppe; None heißt offen.
POWER = (0, DEVICE_MAX_POWER)
CURRENT = (0, DEVICE_MAX_CURRENT)
PERCENT = (0, 100)
AMOUNT = (0, None)
POSITIVE = (1, None)
SIGNED = (None, None)

DIST_MODES = ("equal", "soc", "capacity", "soc_switch")


class Field(NamedTuple):
    """Ein Setting: Standardwert, Typ, harte Grenzen und Anzeigebereich des Panels.

    `min` und `max` folgen aus Gerät, Einheit oder Vorzeichen; nur sie prüfen
    Speichern und Laden. `ui` ist (min, max, step) des Panelfelds.
    """

    default: Any
    kind: str                       # int | float | bool | str | enum
    min: float | None = None
    max: float | None = None
    ui: tuple[float, float, float] | None = None
    choices: tuple[str, ...] = ()



def _int(default: int, hard: tuple, lo: int, hi: int, step: int) -> Field:
    """Ganzzahl-Setting mit harten Grenzen und Anzeigebereich."""
    return Field(default, "int", *hard, (lo, hi, step))


def _float(default: float, hard: tuple, lo: float, hi: float, step: float) -> Field:
    """Kommazahl-Setting mit harten Grenzen und Anzeigebereich."""
    return Field(default, "float", *hard, (lo, hi, step))


def _bool(default: bool = False) -> Field:
    """Schalter-Setting."""
    return Field(default, "bool")


def _str() -> Field:
    """Entity-Setting, leer heißt nicht zugeordnet."""
    return Field("", "str")


def _dyn_offset(prefix: str) -> dict[str, Field]:
    """Felder eines dynamischen Offsets `dyn_<prefix>_*`."""
    return {
        f"dyn_{prefix}_enabled":  _bool(),
        f"dyn_{prefix}_min":      _int(30, AMOUNT, 0, 500, 1),
        f"dyn_{prefix}_max":      _int(250, AMOUNT, 50, 1000, 10),
        f"dyn_{prefix}_noise":    _int(15, AMOUNT, 0, 100, 1),
        f"dyn_{prefix}_factor":   _float(1.5, AMOUNT, 0.5, 5, 0.1),
        f"dyn_{prefix}_negative": _bool(),
    }


SETTINGS_SCHEMA: dict[str, Field] = {
    S_REGULATION_ENABLED: _bool(),

    S_P_FACTOR:   _float(1.3, AMOUNT, 0.1, 5, 0.1),
    S_I_FACTOR:   _float(0.05, AMOUNT, 0, 0.5, 0.01),
    S_TOLERANCE:  _int(15, AMOUNT, 0, 200, 1),
    S_WAIT_TIME:  _int(3, AMOUNT, 0, 30, 1),
    S_STDDEV_WINDOW:     _int(60, AMOUNT, 30, 300, 10),
    S_STDDEV_TRIM_COUNT: _int(0, AMOUNT, 0, 10, 1),

    S_ZONE1_LIMIT:   _int(50, PERCENT, 0, 100, 1),
    S_ZONE3_LIMIT:   _int(20, PERCENT, 0, 100, 1),
    S_DISCHARGE_MAX: _int(40, CURRENT, 1, 100, 1),
    S_HARD_LIMIT_Z0: _int(800, POWER, 100, 1200, 50),
    S_HARD_LIMIT_Z1: _int(800, POWER, 100, 1200, 50),
    S_OFFSET_1:      _int(30, SIGNED, -200, 300, 1),
    S_OFFSET_2:      _int(10, SIGNED, -200, 300, 1),
    S_PV_RESERVE:    _int(50, AMOUNT, 0, 500, 10),

    S_SURPLUS_ENABLED:            _bool(),
    S_SURPLUS_SOC_THRESHOLD:      _int(95, PERCENT, 0, 100, 1),
    S_SURPLUS_SOC_HYST:           _int(5, PERCENT, 1, 20, 1),
    S_SURPLUS_PV_HYST:            _int(50, AMOUNT, 10, 200, 10),
    S_SURPLUS_FORECAST_ENABLED:   _bool(),
    S_SURPLUS_FORECAST_THRESHOLD: _float(15.0, AMOUNT, 0, 100, 0.5),
    S_SURPLUS_LOCK_ENABLED:       _bool(),
    S_SURPLUS_LOCK_SENSOR:        _str(),
    S_SURPLUS_LOCK_FACTOR:        _float(1.5, AMOUNT, 1.0, 3.0, 0.1),

    S_AC_ENABLED:     _bool(),
    S_AC_SOC_TARGET:  _int(90, PERCENT, 0, 100, 1),
    S_AC_POWER_LIMIT: _int(800, POWER, 100, 1200, 50),
    S_AC_HYSTERESIS:  _int(50, AMOUNT, 10, 500, 10),
    S_AC_OFFSET:      _int(-50, SIGNED, -500, 200, 5),
    S_AC_P_FACTOR:    _float(0.3, AMOUNT, 0.1, 3, 0.1),
    S_AC_I_FACTOR:    _float(0.0, AMOUNT, 0, 0.5, 0.01),

    S_TARIFF_ENABLED:         _bool(),
    S_TARIFF_PRICE_SENSOR:    _str(),
    S_TARIFF_CHEAP_THRESHOLD: _float(10.0, SIGNED, 0, 100, 0.5),
    S_TARIFF_EXP_THRESHOLD:   _float(25.0, SIGNED, 0, 100, 0.5),
    S_TARIFF_SOC_TARGET:      _int(90, PERCENT, 0, 100, 1),
    S_TARIFF_SOC_HYST:        _int(3, PERCENT, 0, 20, 1),
    S_TARIFF_POWER:           _int(800, POWER, 100, 1200, 50),
    S_TARIFF_CHEAP_ENTITY:    _str(),
    S_TARIFF_EXP_ENTITY:      _str(),

    S_PV_FORECAST_ENABLED:   _bool(),
    S_PV_FORECAST_SENSOR:    _str(),
    S_PV_FORECAST_THRESHOLD: _float(15.0, AMOUNT, 0, 50, 0.5),

    S_ZONE1_FORCE_ENABLED:   _bool(),
    S_ZONE1_FORCE_SENSOR:    _str(),
    S_ZONE1_FORCE_THRESHOLD: _float(15.0, AMOUNT, 0, 50, 0.5),
    S_ZONE1_FORCE_MIN_SOC:   _int(20, PERCENT, 0, 100, 1),

    S_NIGHT_ENABLED:     _bool(),
    S_NIGHT_HYSTERESIS:  _int(0, AMOUNT, 0, 500, 10),
    S_REST_IN_DISCHARGE: _bool(),

    S_PERIODIC_ENABLED:  _bool(),
    S_PERIODIC_INTERVAL: _int(10, POSITIVE, 5, 300, 5),

    S_SELF_ADJUST:     _bool(),
    S_SELF_ADJUST_TOL: _int(2, AMOUNT, 1, 50, 1),

    **_dyn_offset("z1"),
    **_dyn_offset("z2"),
    **_dyn_offset("ac"),
}
SETTINGS_DEFAULTS: dict = {key: field.default for key, field in SETTINGS_SCHEMA.items()}

DIST_SCHEMA: dict[str, Field] = {
    "global_max_power":  _int(800, AMOUNT, 0, 9600, 10),
    "distribution_mode": Field("equal", "enum", choices=DIST_MODES),
    # Divergenz-Schwelle (Prozentpunkte) für Modus `soc_switch`: exklusiv
    # aktive Instanz gibt ab, sobald ihr SOC seit Aktivierung um diesen Wert
    # gefallen ist — Rotation an die Instanz mit dem höchsten verbleibenden SOC.
    "soc_switch_divergence": _int(5, PERCENT, 1, 50, 1),
    # Instanzübergreifende Sensor-Vorgaben — jede Instanz kann
    # diese optional lokal überschreiben (S_PV_FORECAST_SENSOR, S_ZONE1_FORCE_SENSOR,
    # S_SURPLUS_LOCK_SENSOR, S_TARIFF_PRICE_SENSOR, S_TARIFF_CHEAP_ENTITY,
    # S_TARIFF_EXP_ENTITY); lokal gewinnt, sonst greift dieser globale Wert. Nur bei
    # >1 Instanz im Panel sichtbar, siehe coordinator.py _effective().
    "global_pv_forecast_today_sensor":    _str(),
    "global_pv_forecast_tomorrow_sensor": _str(),
    "global_surplus_lock_sensor":         _str(),
    "global_tariff_price_sensor":         _str(),
    "global_tariff_cheap_entity":         _str(),
    "global_tariff_exp_entity":           _str(),
}
DIST_DEFAULTS: dict = {key: field.default for key, field in DIST_SCHEMA.items()}
# Werte je Instanz in der Verteilung: `inst_<entry_id>_capacity_sensor`.
DIST_INST_FIELDS = (re.compile(r"inst_.+_capacity_sensor"), _str())
