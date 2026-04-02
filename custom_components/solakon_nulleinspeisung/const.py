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

REQUIRED_ENTITY_DEFAULTS = {
    CONF_ACTUAL_SENSOR: "sensor.solakon_one_leistung",
    CONF_SOLAR_SENSOR: "sensor.solakon_one_pv_leistung",
    CONF_SOC_SENSOR: "sensor.solakon_one_batterie_ladestand",
    CONF_TIMEOUT_COUNTDOWN: "sensor.solakon_one_fernsteuerung_zeituberschreitung",
    CONF_ACTIVE_POWER: "number.solakon_one_fernsteuerung_leistung",
    CONF_DISCHARGE_CURRENT: "number.solakon_one_maximaler_entladestrom",
    CONF_TIMEOUT_SET: "number.solakon_one_fernsteuerung_zeituberschreitung",
    CONF_MODE_SELECT: "select.solakon_one_modus_fernsteuern",
}

PLATFORMS = ["sensor", "number", "switch"]

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

S_NIGHT_ENABLED = "night_enabled"

# -- SETTINGS DEFAULTS (konservativ, Schreibteil startet DEAKTIVIERT) ----------
SETTINGS_DEFAULTS: dict = {
    S_REGULATION_ENABLED: False,

    S_P_FACTOR: 1.3,
    S_I_FACTOR: 0.05,
    S_TOLERANCE: 15,
    S_WAIT_TIME: 3,

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

    S_NIGHT_ENABLED: False,
}
