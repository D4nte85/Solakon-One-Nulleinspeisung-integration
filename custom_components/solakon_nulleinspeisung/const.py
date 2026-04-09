"""Constants for Solakon ONE Nulleinspeisung."""
from __future__ import annotations

DOMAIN = "solakon_nulleinspeisung"
STORAGE_VERSION = 1

# -- Config-Entry Keys (User wählt im ConfigFlow) -----------------------------
CONF_GRID_SENSOR = "grid_power_sensor"
CONF_ACTUAL_SENSOR = "actual_power_sensor"
CONF_SOLAR_SENSOR = "solar_power_sensor"
CONF_SOC_SENSOR = "soc_sensor"
CONF_TIMEOUT_COUNTDOWN = "remote_timeout_countdown_sensor"
CONF_ACTIVE_POWER = "active_power_number"
CONF_DISCHARGE_CURRENT = "max_discharge_current_number"
CONF_TIMEOUT_SET = "remote_timeout_set_number"
CONF_MODE_SELECT = "mode_select"

# -- Config-Entry Entity Defaults (sprachabhängig) ----------------------------
REQUIRED_ENTITY_DEFAULTS_DE = {
    CONF_ACTUAL_SENSOR:     "sensor.solakon_one_leistung",
    CONF_SOLAR_SENSOR:      "sensor.solakon_one_pv_leistung",
    CONF_SOC_SENSOR:        "sensor.solakon_one_batterie_ladestand",
    CONF_TIMEOUT_COUNTDOWN: "sensor.solakon_one_fernsteuerung_zeituberschreitung",
    CONF_ACTIVE_POWER:      "number.solakon_one_fernsteuerung_leistung",
    CONF_DISCHARGE_CURRENT: "number.solakon_one_maximaler_entladestrom",
    CONF_TIMEOUT_SET:       "number.solakon_one_fernsteuerung_zeituberschreitung",
    CONF_MODE_SELECT:       "select.solakon_one_modus_fernsteuern",
}

REQUIRED_ENTITY_DEFAULTS_EN = {
    CONF_ACTUAL_SENSOR:     "sensor.solakon_one_active_power",
    CONF_SOLAR_SENSOR:      "sensor.solakon_one_pv_power",
    CONF_SOC_SENSOR:        "sensor.solakon_one_battery_state_of_charge",
    CONF_TIMEOUT_COUNTDOWN: "sensor.solakon_one_remote_timeout_countdown",
    CONF_ACTIVE_POWER:      "number.solakon_one_remote_control_power",
    CONF_DISCHARGE_CURRENT: "number.solakon_one_maximum_discharge_current",
    CONF_TIMEOUT_SET:       "number.solakon_one_remote_control_timeout",
    CONF_MODE_SELECT:       "select.solakon_one_remote_control_mode",
}

PLATFORMS = ["sensor", "switch", "binary_sensor"]

# -- Inverter Mode Values ------------------------------------------------------
MODE_DISABLED = "0"
MODE_DISCHARGE = "1"
MODE_AC_CHARGE = "3"

# -- Settings Keys (Panel / Storage) ------------------------------------------
S_REGULATION_ENABLED = "regulation_enabled"

S_P_FACTOR = "p_factor"
S_I_FACTOR = "i_factor"
S_TOLERANCE = "tolerance"
S_WAIT_TIME = "wait_time"
S_STDDEV_WINDOW = "stddev_window"

S_ZONE1_LIMIT = "zone1_limit"
S_ZONE3_LIMIT = "zone3_limit"
S_DISCHARGE_MAX = "discharge_max"
S_HARD_LIMIT = "hard_limit"
S_OFFSET_1 = "offset_1"
S_OFFSET_2 = "offset_2"
S_PV_RESERVE = "pv_reserve"

S_SURPLUS_ENABLED = "surplus_enabled"
S_SURPLUS_SOC_THRESHOLD = "surplus_soc_threshold"
S_SURPLUS_SOC_HYST = "surplus_soc_hyst"
S_SURPLUS_PV_HYST = "surplus_pv_hyst"

S_AC_ENABLED = "ac_enabled"
S_AC_SOC_TARGET = "ac_soc_target"
S_AC_POWER_LIMIT = "ac_power_limit"
S_AC_HYSTERESIS = "ac_hysteresis"
S_AC_OFFSET = "ac_offset"
S_AC_P_FACTOR = "ac_p_factor"
S_AC_I_FACTOR = "ac_i_factor"

S_TARIFF_ENABLED = "tariff_enabled"
S_TARIFF_PRICE_SENSOR = "tariff_price_sensor"
S_TARIFF_CHEAP_THRESHOLD = "tariff_cheap_threshold"
S_TARIFF_EXP_THRESHOLD = "tariff_exp_threshold"
S_TARIFF_SOC_TARGET = "tariff_soc_target"
S_TARIFF_POWER = "tariff_power"

S_TARIFF_CHEAP_ENTITY = "tariff_cheap_entity"
S_TARIFF_EXP_ENTITY = "tariff_exp_entity"

S_PV_FORECAST_ENABLED = "pv_forecast_enabled"
S_PV_FORECAST_SENSOR = "pv_forecast_sensor"
S_PV_FORECAST_THRESHOLD = "pv_forecast_threshold"

S_NIGHT_ENABLED = "night_enabled"

# -- Self-Adjusting Wait -------------------------------------------------------
S_SELF_ADJUST = "self_adjust_enabled"
S_SELF_ADJUST_TOL = "self_adjust_tolerance"

# -- Dynamic Offset Settings (pro Zone, einzeln schaltbar) --------------------
S_DYN_Z1_ENABLED = "dyn_z1_enabled"
S_DYN_Z1_MIN = "dyn_z1_min"
S_DYN_Z1_MAX = "dyn_z1_max"
S_DYN_Z1_NOISE = "dyn_z1_noise"
S_DYN_Z1_FACTOR = "dyn_z1_factor"
S_DYN_Z1_NEGATIVE = "dyn_z1_negative"

S_DYN_Z2_ENABLED = "dyn_z2_enabled"
S_DYN_Z2_MIN = "dyn_z2_min"
S_DYN_Z2_MAX = "dyn_z2_max"
S_DYN_Z2_NOISE = "dyn_z2_noise"
S_DYN_Z2_FACTOR = "dyn_z2_factor"
S_DYN_Z2_NEGATIVE = "dyn_z2_negative"

S_DYN_AC_ENABLED = "dyn_ac_enabled"
S_DYN_AC_MIN = "dyn_ac_min"
S_DYN_AC_MAX = "dyn_ac_max"
S_DYN_AC_NOISE = "dyn_ac_noise"
S_DYN_AC_FACTOR = "dyn_ac_factor"
S_DYN_AC_NEGATIVE = "dyn_ac_negative"

# -- SETTINGS DEFAULTS (konservativ, Schreibteil startet DEAKTIVIERT) ----------
SETTINGS_DEFAULTS: dict = {
    S_REGULATION_ENABLED: False,

    S_P_FACTOR: 1.3,
    S_I_FACTOR: 0.05,
    S_TOLERANCE: 15,
    S_WAIT_TIME: 3,
    S_STDDEV_WINDOW: 60,

    S_ZONE1_LIMIT: 50,
    S_ZONE3_LIMIT: 20,
    S_DISCHARGE_MAX: 40,
    S_HARD_LIMIT: 800,
    S_OFFSET_1: 30,
    S_OFFSET_2: 10,
    S_PV_RESERVE: 50,

    S_SURPLUS_ENABLED: False,
    S_SURPLUS_SOC_THRESHOLD: 95,
    S_SURPLUS_SOC_HYST: 5,
    S_SURPLUS_PV_HYST: 50,

    S_AC_ENABLED: False,
    S_AC_SOC_TARGET: 90,
    S_AC_POWER_LIMIT: 800,
    S_AC_HYSTERESIS: 50,
    S_AC_OFFSET: -50,
    S_AC_P_FACTOR: 0.3,
    S_AC_I_FACTOR: 0.07,

    S_TARIFF_ENABLED: False,
    S_TARIFF_PRICE_SENSOR: "",
    S_TARIFF_CHEAP_THRESHOLD: 10.0,
    S_TARIFF_EXP_THRESHOLD: 25.0,
    S_TARIFF_SOC_TARGET: 90,
    S_TARIFF_POWER: 800,

    S_TARIFF_CHEAP_ENTITY: "",
    S_TARIFF_EXP_ENTITY: "",

    S_PV_FORECAST_ENABLED: False,
    S_PV_FORECAST_SENSOR: "",
    S_PV_FORECAST_THRESHOLD: 5.0,

    S_NIGHT_ENABLED: False,

    # Self-Adjusting Wait
    S_SELF_ADJUST: False,
    S_SELF_ADJUST_TOL: 2,

    # Dynamic Offset (pro Zone einzeln schaltbar)
    S_DYN_Z1_ENABLED: False,
    S_DYN_Z1_MIN: 30,
    S_DYN_Z1_MAX: 250,
    S_DYN_Z1_NOISE: 15,
    S_DYN_Z1_FACTOR: 1.5,
    S_DYN_Z1_NEGATIVE: False,

    S_DYN_Z2_ENABLED: False,
    S_DYN_Z2_MIN: 30,
    S_DYN_Z2_MAX: 250,
    S_DYN_Z2_NOISE: 15,
    S_DYN_Z2_FACTOR: 1.5,
    S_DYN_Z2_NEGATIVE: False,

    S_DYN_AC_ENABLED: False,
    S_DYN_AC_MIN: 30,
    S_DYN_AC_MAX: 250,
    S_DYN_AC_NOISE: 15,
    S_DYN_AC_FACTOR: 1.5,
    S_DYN_AC_NEGATIVE: False,
}
