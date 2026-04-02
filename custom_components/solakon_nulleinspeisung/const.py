"""Constants for Solakon ONE Nulleinspeisung."""
from __future__ import annotations

DOMAIN = "solakon_nulleinspeisung"
STORAGE_VERSION = 1

# -- Config-Entry keys ---------------------------------------------------------
CONF_GRID_SENSOR        = "grid_power_sensor"
CONF_ACTUAL_SENSOR      = "actual_power_sensor"
CONF_SOLAR_SENSOR       = "solar_power_sensor"
CONF_SOC_SENSOR         = "soc_sensor"
CONF_TIMEOUT_COUNTDOWN  = "remote_timeout_countdown_sensor"
CONF_ACTIVE_POWER       = "active_power_number"
CONF_DISCHARGE_CURRENT  = "max_discharge_current_number"
CONF_TIMEOUT_SET        = "remote_timeout_set_number"
CONF_MODE_SELECT        = "mode_select"

REQUIRED_ENTITY_DEFAULTS = {
    CONF_ACTUAL_SENSOR:     "sensor.solakon_one_leistung",
    CONF_SOLAR_SENSOR:      "sensor.solakon_one_pv_leistung",
    CONF_SOC_SENSOR:        "sensor.solakon_one_batterie_ladestand",
    CONF_TIMEOUT_COUNTDOWN: "sensor.solakon_one_fernsteuerung_zeituberschreitung",
    CONF_ACTIVE_POWER:      "number.solakon_one_fernsteuerung_leistung",
    CONF_DISCHARGE_CURRENT: "number.solakon_one_maximaler_entladestrom",
    CONF_TIMEOUT_SET:       "number.solakon_one_fernsteuerung_zeituberschreitung",
    CONF_MODE_SELECT:       "select.solakon_one_betriebsmodus",
}

PLATFORMS = ["sensor"]

# -- Settings keys -------------------------------------------------------------
S_P_FACTOR, S_I_FACTOR, S_TOLERANCE, S_WAIT_TIME = "p_factor", "i_factor", "tolerance", "wait_time"
S_STDDEV_WINDOW = "stddev_window"
S_ZONE1_LIMIT, S_ZONE3_LIMIT, S_DISCHARGE_MAX = "zone1_limit", "zone3_limit", "discharge_max"
S_OFFSET_1, S_OFFSET_2, S_PV_RESERVE, S_HARD_LIMIT = "offset_1", "offset_2", "pv_reserve", "hard_limit"
S_SURPLUS_ENABLED, S_SURPLUS_SOC_THRESHOLD = "surplus_enabled", "surplus_soc_threshold"
S_SURPLUS_SOC_HYST, S_SURPLUS_PV_HYST = "surplus_soc_hyst", "surplus_pv_hyst"
S_AC_ENABLED, S_AC_SOC_TARGET, S_AC_POWER_LIMIT = "ac_enabled", "ac_soc_target", "ac_power_limit"
S_AC_HYSTERESIS, S_AC_OFFSET, S_AC_P_FACTOR, S_AC_I_FACTOR = "ac_hysteresis", "ac_offset", "ac_p_factor", "ac_i_factor"
S_TARIFF_ENABLED, S_TARIFF_PRICE_SENSOR, S_TARIFF_SOC_TARGET, S_TARIFF_POWER = "tariff_enabled", "tariff_price_sensor", "tariff_soc_target", "tariff_power"
S_TARIFF_CHEAP_THRESHOLD, S_TARIFF_EXP_THRESHOLD = "tariff_cheap_threshold", "tariff_exp_threshold"
S_NIGHT_ENABLED = "night_enabled"

# -- SETTINGS DEFAULTS --------------------------------------------------------
SETTINGS_DEFAULTS = {
    S_P_FACTOR: 1.3,
    S_I_FACTOR: 0.02,
    S_TOLERANCE: 15,
    S_WAIT_TIME: 3,
    S_STDDEV_WINDOW: 60,
    S_ZONE1_LIMIT: 20,
    S_ZONE3_LIMIT: 10,
    S_DISCHARGE_MAX: 40,
    S_HARD_LIMIT: 800,
    
    # Zone 1 Offsets
    S_OFFSET_1: 30,
    "dyn_offset_1_enabled": False,
    "dyn_offset_1_min": 0,
    "dyn_offset_1_max": 1000,
    "dyn_offset_1_noise_floor": 0,
    "dyn_offset_1_factor": 1.0,
    "dyn_offset_1_negative": False,

    # Zone 2 Offsets
    S_OFFSET_2: 10,
    "dyn_offset_2_enabled": False,
    "dyn_offset_2_min": 0,
    "dyn_offset_2_max": 1000,
    "dyn_offset_2_noise_floor": 0,
    "dyn_offset_2_factor": 1.0,
    "dyn_offset_2_negative": False,

    # AC Offsets
    S_AC_OFFSET: 0,
    "dyn_offset_ac_enabled": False,
    "dyn_offset_ac_min": 0,
    "dyn_offset_ac_max": 1000,
    "dyn_offset_ac_noise_floor": 0,
    "dyn_offset_ac_factor": 1.0,
    "dyn_offset_ac_negative": False,

    S_PV_RESERVE: 50,
    S_SURPLUS_ENABLED: False,
    S_SURPLUS_SOC_THRESHOLD: 95,
    S_SURPLUS_SOC_HYST: 5,
    S_SURPLUS_PV_HYST: 50,
    S_AC_ENABLED: False,
    S_AC_SOC_TARGET: 80,
    S_AC_POWER_LIMIT: 300,
    S_AC_HYSTERESIS: 50,
    S_AC_P_FACTOR: 1.0,
    S_AC_I_FACTOR: 0.05,
    S_TARIFF_ENABLED: False,
    S_TARIFF_PRICE_SENSOR: "",
    S_TARIFF_SOC_TARGET: 80,
    S_TARIFF_POWER: 500,
    S_TARIFF_CHEAP_THRESHOLD: 20.0,
    S_TARIFF_EXP_THRESHOLD: 30.0,
    S_NIGHT_ENABLED: False,
}
