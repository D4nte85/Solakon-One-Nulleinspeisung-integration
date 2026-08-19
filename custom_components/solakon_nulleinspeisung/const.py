"""Constants for Solakon ONE Nulleinspeisung."""
from __future__ import annotations

import json
from pathlib import Path

DOMAIN = "solakon_nulleinspeisung"
STORAGE_VERSION = 1
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

S_ZONE1_LIMIT   = "zone1_limit"
S_ZONE3_LIMIT   = "zone3_limit"
S_DISCHARGE_MAX  = "discharge_max"
S_HARD_LIMIT     = "hard_limit"
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
# Nur noch Migrationsquelle — der Sensor selbst kommt aus dem gemergten
# PV-Vorhersage-Feld (S_PV_FORECAST_SENSOR + globaler Fallback), siehe
# _effective_pv_forecast_today_sensor(). Kein eigener Default mehr in SETTINGS_DEFAULTS.
S_SURPLUS_FORECAST_SENSOR    = "surplus_forecast_sensor"
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
S_TARIFF_POWER            = "tariff_power"
S_TARIFF_CHEAP_ENTITY     = "tariff_cheap_entity"
S_TARIFF_EXP_ENTITY       = "tariff_exp_entity"

S_PV_FORECAST_ENABLED    = "pv_forecast_enabled"
S_PV_FORECAST_SENSOR     = "pv_forecast_sensor"
S_PV_FORECAST_THRESHOLD  = "pv_forecast_threshold"

# Zone-1-Nacht-Forcierung. Sensor ist zeitabhängig "heute" (S_PV_FORECAST_SENSOR
# + globaler Fallback) oder "morgen" (S_ZONE1_FORCE_SENSOR + globaler Fallback) — siehe
# _effective_zone1_force_sensor() in coordinator.py.
S_ZONE1_FORCE_ENABLED   = "zone1_force_enabled"
S_ZONE1_FORCE_SENSOR    = "zone1_force_sensor"
S_ZONE1_FORCE_THRESHOLD = "zone1_force_threshold"
S_ZONE1_FORCE_MIN_SOC   = "zone1_force_min_soc"

S_NIGHT_ENABLED = "night_enabled"

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

SETTINGS_DEFAULTS: dict = {
    S_REGULATION_ENABLED: False,

    S_P_FACTOR:   1.3,
    S_I_FACTOR:   0.05,
    S_TOLERANCE:  15,
    S_WAIT_TIME:  3,
    S_STDDEV_WINDOW: 60,

    S_ZONE1_LIMIT:   50,
    S_ZONE3_LIMIT:   20,
    S_DISCHARGE_MAX:  40,
    S_HARD_LIMIT:     800,
    S_HARD_LIMIT_Z0:  800,
    S_HARD_LIMIT_Z1:  800,
    S_OFFSET_1:      30,
    S_OFFSET_2:      10,
    S_PV_RESERVE:    50,

    S_SURPLUS_ENABLED:       False,
    S_SURPLUS_SOC_THRESHOLD: 95,
    S_SURPLUS_SOC_HYST:      5,
    S_SURPLUS_PV_HYST:       50,
    S_SURPLUS_FORECAST_ENABLED:   False,
    S_SURPLUS_FORECAST_THRESHOLD: 5000.0,
    S_SURPLUS_LOCK_ENABLED: False,
    S_SURPLUS_LOCK_SENSOR:  "",
    S_SURPLUS_LOCK_FACTOR:  1.5,

    S_AC_ENABLED:     False,
    S_AC_SOC_TARGET:  90,
    S_AC_POWER_LIMIT: 800,
    S_AC_HYSTERESIS:  50,
    S_AC_OFFSET:      -50,
    S_AC_P_FACTOR:    0.3,
    S_AC_I_FACTOR:    0.0,

    S_TARIFF_ENABLED:         False,
    S_TARIFF_PRICE_SENSOR:    "",
    S_TARIFF_CHEAP_THRESHOLD: 10.0,
    S_TARIFF_EXP_THRESHOLD:   25.0,
    S_TARIFF_SOC_TARGET:      90,
    S_TARIFF_POWER:           800,
    S_TARIFF_CHEAP_ENTITY:    "",
    S_TARIFF_EXP_ENTITY:      "",

    S_PV_FORECAST_ENABLED:   False,
    S_PV_FORECAST_SENSOR:    "",
    S_PV_FORECAST_THRESHOLD: 5000.0,

    S_ZONE1_FORCE_ENABLED:   False,
    S_ZONE1_FORCE_SENSOR:    "",
    S_ZONE1_FORCE_THRESHOLD: 15.0,
    S_ZONE1_FORCE_MIN_SOC:   20,

    S_NIGHT_ENABLED: False,

    S_PERIODIC_ENABLED:  False,
    S_PERIODIC_INTERVAL: 10,

    S_SELF_ADJUST:     False,
    S_SELF_ADJUST_TOL: 2,

    S_DYN_Z1_ENABLED:  False,
    S_DYN_Z1_MIN:      30,
    S_DYN_Z1_MAX:      250,
    S_DYN_Z1_NOISE:    15,
    S_DYN_Z1_FACTOR:   1.5,
    S_DYN_Z1_NEGATIVE: False,

    S_DYN_Z2_ENABLED:  False,
    S_DYN_Z2_MIN:      30,
    S_DYN_Z2_MAX:      250,
    S_DYN_Z2_NOISE:    15,
    S_DYN_Z2_FACTOR:   1.5,
    S_DYN_Z2_NEGATIVE: False,

    S_DYN_AC_ENABLED:  False,
    S_DYN_AC_MIN:      30,
    S_DYN_AC_MAX:      250,
    S_DYN_AC_NOISE:    15,
    S_DYN_AC_FACTOR:   1.5,
    S_DYN_AC_NEGATIVE: False,
}

DIST_DEFAULTS: dict = {
    "global_max_power":  800,
    "distribution_mode": "equal",  # equal | soc | capacity | soc_switch
    # Divergenz-Schwelle (Prozentpunkte) für Modus `soc_switch`: exklusiv
    # aktive Instanz gibt ab, sobald ihr SOC seit Aktivierung um diesen Wert
    # gefallen ist — Rotation an die Instanz mit dem höchsten verbleibenden SOC.
    "soc_switch_divergence": 5,
    # Instanzübergreifende Sensor-Vorgaben — jede Instanz kann
    # diese optional lokal überschreiben (S_PV_FORECAST_SENSOR, S_ZONE1_FORCE_SENSOR,
    # S_SURPLUS_LOCK_SENSOR, S_TARIFF_PRICE_SENSOR, S_TARIFF_CHEAP_ENTITY,
    # S_TARIFF_EXP_ENTITY); lokal gewinnt, sonst greift dieser globale Wert. Nur bei
    # >1 Instanz im Panel sichtbar, siehe coordinator.py _effective_*_sensor()-Helper.
    "global_pv_forecast_today_sensor":    "",
    "global_pv_forecast_tomorrow_sensor": "",
    "global_surplus_lock_sensor":         "",
    "global_tariff_price_sensor":         "",
    "global_tariff_cheap_entity":         "",
    "global_tariff_exp_entity":           "",
}
