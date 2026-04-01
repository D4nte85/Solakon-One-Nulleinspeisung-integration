"""Constants for the Solakon ONE Nulleinspeisung integration."""
from __future__ import annotations

DOMAIN = "solakon_nulleinspeisung"
STORAGE_VERSION = 1
STORAGE_KEY_TEMPLATE = "solakon_state_{entry_id}"

# ── Required entities ──────────────────────────────────────────────────────────
CONF_GRID_POWER_SENSOR           = "grid_power_sensor"
CONF_ACTUAL_POWER_SENSOR         = "actual_power_sensor"
CONF_SOLAR_POWER_SENSOR          = "solar_power_sensor"
CONF_SOC_SENSOR                  = "soc_sensor"
CONF_REMOTE_TIMEOUT_COUNTDOWN    = "remote_timeout_countdown_sensor"
CONF_ACTIVE_POWER_NUMBER         = "active_power_number"
CONF_MAX_DISCHARGE_CURRENT       = "max_discharge_current_number"
CONF_REMOTE_TIMEOUT_SET          = "remote_timeout_set_number"
CONF_MODE_SELECT                 = "mode_select"

# ── PI parameters ──────────────────────────────────────────────────────────────
CONF_P_FACTOR                    = "p_factor"
CONF_I_FACTOR                    = "i_factor"
CONF_TOLERANCE                   = "tolerance"
CONF_WAIT_TIME                   = "wait_time"

# ── SOC zone parameters ────────────────────────────────────────────────────────
CONF_SOC_FAST_LIMIT              = "soc_fast_limit"
CONF_SOC_CONSERVATION_LIMIT      = "soc_conservation_limit"
CONF_DISCHARGE_CURRENT_MAX       = "discharge_current_max"

# ── Zone 1/2 parameters ────────────────────────────────────────────────────────
CONF_OFFSET_1                    = "offset_1"
CONF_OFFSET_1_ENTITY             = "offset_1_entity"
CONF_OFFSET_2                    = "offset_2"
CONF_OFFSET_2_ENTITY             = "offset_2_entity"
CONF_PV_CHARGE_RESERVE           = "pv_charge_reserve"

# ── Safety ─────────────────────────────────────────────────────────────────────
CONF_MAX_ACTIVE_POWER            = "max_active_power_limit"

# ── Surplus export (Zone 0) ────────────────────────────────────────────────────
CONF_SURPLUS_ENABLED             = "surplus_export_enabled"
CONF_SOC_EXPORT_LIMIT            = "soc_export_limit"
CONF_SURPLUS_EXIT_HYSTERESIS     = "surplus_exit_hysteresis"
CONF_SURPLUS_PV_HYSTERESIS       = "surplus_pv_hysteresis"

# ── AC charging ────────────────────────────────────────────────────────────────
CONF_AC_CHARGE_ENABLED           = "ac_charge_enabled"
CONF_SOC_AC_CHARGE_LIMIT         = "soc_ac_charge_limit"
CONF_AC_CHARGE_POWER_LIMIT       = "ac_charge_power_limit"
CONF_AC_CHARGE_HYSTERESIS        = "ac_charge_hysteresis"
CONF_AC_CHARGE_OFFSET            = "ac_charge_offset"
CONF_AC_CHARGE_OFFSET_ENTITY     = "ac_charge_offset_entity"
CONF_AC_CHARGE_P_FACTOR          = "ac_charge_p_factor"
CONF_AC_CHARGE_I_FACTOR          = "ac_charge_i_factor"

# ── Tariff arbitrage ───────────────────────────────────────────────────────────
CONF_TARIFF_ENABLED              = "tariff_arbitrage_enabled"
CONF_PRICE_SENSOR                = "price_sensor"
CONF_CHEAP_THRESHOLD             = "cheap_threshold"
CONF_EXPENSIVE_THRESHOLD         = "expensive_threshold"
CONF_TARIFF_SOC_TARGET           = "tariff_soc_charge_target"
CONF_TARIFF_CHARGE_POWER         = "tariff_charge_power"

# ── Night shutdown ─────────────────────────────────────────────────────────────
CONF_NIGHT_SHUTDOWN              = "night_shutdown_enabled"

# ── Default values ─────────────────────────────────────────────────────────────
DEFAULTS = {
    CONF_ACTUAL_POWER_SENSOR:      "sensor.solakon_one_leistung",
    CONF_SOLAR_POWER_SENSOR:       "sensor.solakon_one_pv_leistung",
    CONF_SOC_SENSOR:               "sensor.solakon_one_batterie_ladestand",
    CONF_REMOTE_TIMEOUT_COUNTDOWN: "sensor.solakon_one_fernsteuerung_zeituberschreitung",
    CONF_ACTIVE_POWER_NUMBER:      "number.solakon_one_fernsteuerung_leistung",
    CONF_MAX_DISCHARGE_CURRENT:    "number.solakon_one_maximaler_entladestrom",
    CONF_REMOTE_TIMEOUT_SET:       "number.solakon_one_fernsteuerung_zeituberschreitung",
    CONF_MODE_SELECT:              "select.solakon_one_modus_fernsteuern",
    CONF_P_FACTOR:                 1.3,
    CONF_I_FACTOR:                 0.05,
    CONF_TOLERANCE:                25,
    CONF_WAIT_TIME:                3,
    CONF_SOC_FAST_LIMIT:           50,
    CONF_SOC_CONSERVATION_LIMIT:   20,
    CONF_DISCHARGE_CURRENT_MAX:    40,
    CONF_OFFSET_1:                 30,
    CONF_OFFSET_2:                 30,
    CONF_PV_CHARGE_RESERVE:        50,
    CONF_MAX_ACTIVE_POWER:         800,
    CONF_SURPLUS_ENABLED:          False,
    CONF_SOC_EXPORT_LIMIT:         90,
    CONF_SURPLUS_EXIT_HYSTERESIS:  5,
    CONF_SURPLUS_PV_HYSTERESIS:    50,
    CONF_AC_CHARGE_ENABLED:        False,
    CONF_SOC_AC_CHARGE_LIMIT:      90,
    CONF_AC_CHARGE_POWER_LIMIT:    800,
    CONF_AC_CHARGE_HYSTERESIS:     50,
    CONF_AC_CHARGE_OFFSET:         -50,
    CONF_AC_CHARGE_P_FACTOR:       0.5,
    CONF_AC_CHARGE_I_FACTOR:       0.07,
    CONF_TARIFF_ENABLED:           False,
    CONF_CHEAP_THRESHOLD:          10.0,
    CONF_EXPENSIVE_THRESHOLD:      25.0,
    CONF_TARIFF_SOC_TARGET:        90,
    CONF_TARIFF_CHARGE_POWER:      800,
    CONF_NIGHT_SHUTDOWN:           False,
}

# ── Platforms ──────────────────────────────────────────────────────────────────
PLATFORMS = ["sensor", "switch", "number"]

# ── Internal state store keys ──────────────────────────────────────────────────
STATE_CYCLE_ACTIVE       = "cycle_active"
STATE_INTEGRAL           = "integral"
STATE_SURPLUS_ACTIVE     = "surplus_active"
STATE_AC_CHARGE_ACTIVE   = "ac_charge_active"
STATE_TARIFF_CHARGE_ACTIVE = "tariff_charge_active"
