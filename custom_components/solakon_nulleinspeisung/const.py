"""Constants for Solakon ONE Nulleinspeisung."""
from __future__ import annotations

DOMAIN = "solakon_nulleinspeisung"
STORAGE_VERSION = 1

# ── Config-Entry keys (required entities only) ─────────────────────────────────
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
    CONF_MODE_SELECT:       "select.solakon_one_modus_fernsteuern",
}

# ── Settings-Store keys (all tunable parameters) ───────────────────────────────
# PI
S_P_FACTOR      = "p_factor"
S_I_FACTOR      = "i_factor"
S_TOLERANCE     = "tolerance"
S_WAIT_TIME     = "wait_time"

# SOC zones
S_ZONE1_LIMIT   = "zone1_limit"
S_ZONE3_LIMIT   = "zone3_limit"
S_DISCHARGE_MAX = "discharge_current_max"

# Zone 1/2 offsets & limits
S_OFFSET_1      = "offset_1"
S_OFFSET_2      = "offset_2"
S_PV_RESERVE    = "pv_charge_reserve"
S_HARD_LIMIT    = "hard_limit"

# Dynamic offset — Zone 1
S_DYN_OFFSET_1_ENABLED    = "dyn_offset_1_enabled"
S_DYN_OFFSET_1_SENSOR     = "dyn_offset_1_stddev_sensor"
S_DYN_OFFSET_1_MIN        = "dyn_offset_1_min"
S_DYN_OFFSET_1_MAX        = "dyn_offset_1_max"
S_DYN_OFFSET_1_NOISE      = "dyn_offset_1_noise_floor"
S_DYN_OFFSET_1_FACTOR     = "dyn_offset_1_factor"
S_DYN_OFFSET_1_NEGATIVE   = "dyn_offset_1_negative"

# Dynamic offset — Zone 2
S_DYN_OFFSET_2_ENABLED    = "dyn_offset_2_enabled"
S_DYN_OFFSET_2_SENSOR     = "dyn_offset_2_stddev_sensor"
S_DYN_OFFSET_2_MIN        = "dyn_offset_2_min"
S_DYN_OFFSET_2_MAX        = "dyn_offset_2_max"
S_DYN_OFFSET_2_NOISE      = "dyn_offset_2_noise_floor"
S_DYN_OFFSET_2_FACTOR     = "dyn_offset_2_factor"
S_DYN_OFFSET_2_NEGATIVE   = "dyn_offset_2_negative"

# Surplus (Zone 0)
S_SURPLUS_ENABLED         = "surplus_enabled"
S_SURPLUS_SOC_THRESHOLD   = "surplus_soc_threshold"
S_SURPLUS_SOC_HYST        = "surplus_soc_hysteresis"
S_SURPLUS_PV_HYST         = "surplus_pv_hysteresis"

# AC charging
S_AC_ENABLED              = "ac_charge_enabled"
S_AC_SOC_TARGET           = "ac_charge_soc_target"
S_AC_POWER_LIMIT          = "ac_charge_power_limit"
S_AC_HYSTERESIS           = "ac_charge_hysteresis"
S_AC_OFFSET               = "ac_charge_offset"
S_AC_P_FACTOR             = "ac_charge_p_factor"
S_AC_I_FACTOR             = "ac_charge_i_factor"

# Dynamic offset — AC zone
S_DYN_OFFSET_AC_ENABLED   = "dyn_offset_ac_enabled"
S_DYN_OFFSET_AC_SENSOR    = "dyn_offset_ac_stddev_sensor"
S_DYN_OFFSET_AC_MIN       = "dyn_offset_ac_min"
S_DYN_OFFSET_AC_MAX       = "dyn_offset_ac_max"
S_DYN_OFFSET_AC_NOISE     = "dyn_offset_ac_noise_floor"
S_DYN_OFFSET_AC_FACTOR    = "dyn_offset_ac_factor"
S_DYN_OFFSET_AC_NEGATIVE  = "dyn_offset_ac_negative"

# Tariff arbitrage
S_TARIFF_ENABLED          = "tariff_enabled"
S_TARIFF_PRICE_SENSOR     = "tariff_price_sensor"
S_TARIFF_CHEAP_THRESHOLD  = "tariff_cheap_threshold"
S_TARIFF_EXP_THRESHOLD    = "tariff_expensive_threshold"
S_TARIFF_SOC_TARGET       = "tariff_soc_target"
S_TARIFF_POWER            = "tariff_charge_power"

# Night shutdown
S_NIGHT_ENABLED           = "night_shutdown_enabled"

# ── Settings defaults ──────────────────────────────────────────────────────────
SETTINGS_DEFAULTS: dict = {
    S_P_FACTOR: 1.3,
    S_I_FACTOR: 0.05,
    S_TOLERANCE: 25,
    S_WAIT_TIME: 3,
    S_ZONE1_LIMIT: 50,
    S_ZONE3_LIMIT: 20,
    S_DISCHARGE_MAX: 40,
    S_OFFSET_1: 30,
    S_OFFSET_2: 30,
    S_PV_RESERVE: 50,
    S_HARD_LIMIT: 800,
    S_DYN_OFFSET_1_ENABLED: False,
    S_DYN_OFFSET_1_SENSOR: "",
    S_DYN_OFFSET_1_MIN: 30,
    S_DYN_OFFSET_1_MAX: 250,
    S_DYN_OFFSET_1_NOISE: 15,
    S_DYN_OFFSET_1_FACTOR: 1.5,
    S_DYN_OFFSET_1_NEGATIVE: False,
    S_DYN_OFFSET_2_ENABLED: False,
    S_DYN_OFFSET_2_SENSOR: "",
    S_DYN_OFFSET_2_MIN: 30,
    S_DYN_OFFSET_2_MAX: 250,
    S_DYN_OFFSET_2_NOISE: 15,
    S_DYN_OFFSET_2_FACTOR: 1.5,
    S_DYN_OFFSET_2_NEGATIVE: False,
    S_SURPLUS_ENABLED: False,
    S_SURPLUS_SOC_THRESHOLD: 90,
    S_SURPLUS_SOC_HYST: 5,
    S_SURPLUS_PV_HYST: 50,
    S_AC_ENABLED: False,
    S_AC_SOC_TARGET: 90,
    S_AC_POWER_LIMIT: 800,
    S_AC_HYSTERESIS: 50,
    S_AC_OFFSET: -50,
    S_AC_P_FACTOR: 0.5,
    S_AC_I_FACTOR: 0.07,
    S_DYN_OFFSET_AC_ENABLED: False,
    S_DYN_OFFSET_AC_SENSOR: "",
    S_DYN_OFFSET_AC_MIN: 30,
    S_DYN_OFFSET_AC_MAX: 250,
    S_DYN_OFFSET_AC_NOISE: 15,
    S_DYN_OFFSET_AC_FACTOR: 1.5,
    S_DYN_OFFSET_AC_NEGATIVE: False,
    S_TARIFF_ENABLED: False,
    S_TARIFF_PRICE_SENSOR: "",
    S_TARIFF_CHEAP_THRESHOLD: 10.0,
    S_TARIFF_EXP_THRESHOLD: 25.0,
    S_TARIFF_SOC_TARGET: 90,
    S_TARIFF_POWER: 800,
    S_NIGHT_ENABLED: False,
}

# ── Internal runtime state keys (persisted in own store) ──────────────────────
RS_CYCLE_ACTIVE          = "cycle_active"
RS_INTEGRAL              = "integral"
RS_SURPLUS_ACTIVE        = "surplus_active"
RS_AC_CHARGE_ACTIVE      = "ac_charge_active"
RS_TARIFF_CHARGE_ACTIVE  = "tariff_charge_active"

# ── Platforms ──────────────────────────────────────────────────────────────────
PLATFORMS = ["sensor", "switch", "number"]

# ── Human-readable mode labels ─────────────────────────────────────────────────
MODE_LABELS = {
    "0": "Deaktiviert",
    "1": "Entladen (INV Discharge PV Priority)",
    "3": "Laden (INV Charge PV Priority)",
}

ZONE_LABELS = {
    0: "Zone 0 — Überschuss-Einspeisung",
    1: "Zone 1 — Aggressive Entladung",
    2: "Zone 2 — Batterieschonend",
    3: "Zone 3 — Sicherheitsstopp",
}
