"""Config flow for Solakon ONE Nulleinspeisung."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN, DEFAULTS,
    CONF_GRID_POWER_SENSOR, CONF_ACTUAL_POWER_SENSOR, CONF_SOLAR_POWER_SENSOR,
    CONF_SOC_SENSOR, CONF_REMOTE_TIMEOUT_COUNTDOWN, CONF_ACTIVE_POWER_NUMBER,
    CONF_MAX_DISCHARGE_CURRENT, CONF_REMOTE_TIMEOUT_SET, CONF_MODE_SELECT,
    CONF_P_FACTOR, CONF_I_FACTOR, CONF_TOLERANCE, CONF_WAIT_TIME,
    CONF_SOC_FAST_LIMIT, CONF_SOC_CONSERVATION_LIMIT, CONF_DISCHARGE_CURRENT_MAX,
    CONF_OFFSET_1, CONF_OFFSET_1_ENTITY, CONF_OFFSET_2, CONF_OFFSET_2_ENTITY,
    CONF_PV_CHARGE_RESERVE, CONF_MAX_ACTIVE_POWER,
    CONF_SURPLUS_ENABLED, CONF_SOC_EXPORT_LIMIT, CONF_SURPLUS_EXIT_HYSTERESIS,
    CONF_SURPLUS_PV_HYSTERESIS,
    CONF_AC_CHARGE_ENABLED, CONF_SOC_AC_CHARGE_LIMIT, CONF_AC_CHARGE_POWER_LIMIT,
    CONF_AC_CHARGE_HYSTERESIS, CONF_AC_CHARGE_OFFSET, CONF_AC_CHARGE_OFFSET_ENTITY,
    CONF_AC_CHARGE_P_FACTOR, CONF_AC_CHARGE_I_FACTOR,
    CONF_TARIFF_ENABLED, CONF_PRICE_SENSOR, CONF_CHEAP_THRESHOLD,
    CONF_EXPENSIVE_THRESHOLD, CONF_TARIFF_SOC_TARGET, CONF_TARIFF_CHARGE_POWER,
    CONF_NIGHT_SHUTDOWN,
)


# ─────────────────────────────────────────────────────────────────────────────
# Schema builders
# ─────────────────────────────────────────────────────────────────────────────

def _required_entities_schema(current: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_GRID_POWER_SENSOR,
                     default=current.get(CONF_GRID_POWER_SENSOR, '')): selector.selector(
            {"entity": {"domain": "sensor", "device_class": "power"}}
        ),
        vol.Required(CONF_ACTUAL_POWER_SENSOR,
                     default=current.get(CONF_ACTUAL_POWER_SENSOR, DEFAULTS[CONF_ACTUAL_POWER_SENSOR])): selector.selector(
            {"entity": {"domain": "sensor", "device_class": "power"}}
        ),
        vol.Required(CONF_SOLAR_POWER_SENSOR,
                     default=current.get(CONF_SOLAR_POWER_SENSOR, DEFAULTS[CONF_SOLAR_POWER_SENSOR])): selector.selector(
            {"entity": {"domain": "sensor", "device_class": "power"}}
        ),
        vol.Required(CONF_SOC_SENSOR,
                     default=current.get(CONF_SOC_SENSOR, DEFAULTS[CONF_SOC_SENSOR])): selector.selector(
            {"entity": {"domain": "sensor", "device_class": "battery"}}
        ),
        vol.Required(CONF_REMOTE_TIMEOUT_COUNTDOWN,
                     default=current.get(CONF_REMOTE_TIMEOUT_COUNTDOWN, DEFAULTS[CONF_REMOTE_TIMEOUT_COUNTDOWN])): selector.selector(
            {"entity": {"domain": "sensor"}}
        ),
        vol.Required(CONF_ACTIVE_POWER_NUMBER,
                     default=current.get(CONF_ACTIVE_POWER_NUMBER, DEFAULTS[CONF_ACTIVE_POWER_NUMBER])): selector.selector(
            {"entity": {"domain": "number"}}
        ),
        vol.Required(CONF_MAX_DISCHARGE_CURRENT,
                     default=current.get(CONF_MAX_DISCHARGE_CURRENT, DEFAULTS[CONF_MAX_DISCHARGE_CURRENT])): selector.selector(
            {"entity": {"domain": "number"}}
        ),
        vol.Required(CONF_REMOTE_TIMEOUT_SET,
                     default=current.get(CONF_REMOTE_TIMEOUT_SET, DEFAULTS[CONF_REMOTE_TIMEOUT_SET])): selector.selector(
            {"entity": {"domain": "number"}}
        ),
        vol.Required(CONF_MODE_SELECT,
                     default=current.get(CONF_MODE_SELECT, DEFAULTS[CONF_MODE_SELECT])): selector.selector(
            {"entity": {"domain": "select"}}
        ),
    })


def _pi_schema(current: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_P_FACTOR,       default=current.get(CONF_P_FACTOR,   DEFAULTS[CONF_P_FACTOR])): selector.selector(
            {"number": {"min": 0.1, "max": 5.0, "step": 0.1}}
        ),
        vol.Required(CONF_I_FACTOR,       default=current.get(CONF_I_FACTOR,   DEFAULTS[CONF_I_FACTOR])): selector.selector(
            {"number": {"min": 0.0, "max": 0.2, "step": 0.01}}
        ),
        vol.Required(CONF_TOLERANCE,      default=current.get(CONF_TOLERANCE,  DEFAULTS[CONF_TOLERANCE])): selector.selector(
            {"number": {"min": 0, "max": 200, "unit_of_measurement": "W"}}
        ),
        vol.Required(CONF_WAIT_TIME,      default=current.get(CONF_WAIT_TIME,  DEFAULTS[CONF_WAIT_TIME])): selector.selector(
            {"number": {"min": 0, "max": 30, "step": 1, "unit_of_measurement": "s"}}
        ),
    })


def _soc_schema(current: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_SOC_FAST_LIMIT,       default=current.get(CONF_SOC_FAST_LIMIT,       DEFAULTS[CONF_SOC_FAST_LIMIT])): selector.selector(
            {"number": {"min": 1, "max": 99, "unit_of_measurement": "%"}}
        ),
        vol.Required(CONF_SOC_CONSERVATION_LIMIT, default=current.get(CONF_SOC_CONSERVATION_LIMIT, DEFAULTS[CONF_SOC_CONSERVATION_LIMIT])): selector.selector(
            {"number": {"min": 1, "max": 49, "unit_of_measurement": "%"}}
        ),
        vol.Required(CONF_DISCHARGE_CURRENT_MAX,  default=current.get(CONF_DISCHARGE_CURRENT_MAX, DEFAULTS[CONF_DISCHARGE_CURRENT_MAX])): selector.selector(
            {"number": {"min": 0, "max": 40, "unit_of_measurement": "A"}}
        ),
        vol.Required(CONF_OFFSET_1,              default=current.get(CONF_OFFSET_1, DEFAULTS[CONF_OFFSET_1])): selector.selector(
            {"number": {"min": -100, "max": 100, "unit_of_measurement": "W"}}
        ),
        vol.Optional(CONF_OFFSET_1_ENTITY,       default=current.get(CONF_OFFSET_1_ENTITY, '')): selector.selector(
            {"entity": {"domain": "input_number"}}
        ),
        vol.Required(CONF_OFFSET_2,              default=current.get(CONF_OFFSET_2, DEFAULTS[CONF_OFFSET_2])): selector.selector(
            {"number": {"min": -100, "max": 100, "unit_of_measurement": "W"}}
        ),
        vol.Optional(CONF_OFFSET_2_ENTITY,       default=current.get(CONF_OFFSET_2_ENTITY, '')): selector.selector(
            {"entity": {"domain": "input_number"}}
        ),
        vol.Required(CONF_PV_CHARGE_RESERVE,     default=current.get(CONF_PV_CHARGE_RESERVE, DEFAULTS[CONF_PV_CHARGE_RESERVE])): selector.selector(
            {"number": {"min": 0, "max": 1000, "unit_of_measurement": "W"}}
        ),
        vol.Required(CONF_MAX_ACTIVE_POWER,      default=current.get(CONF_MAX_ACTIVE_POWER, DEFAULTS[CONF_MAX_ACTIVE_POWER])): selector.selector(
            {"number": {"min": 0, "max": 1200, "unit_of_measurement": "W"}}
        ),
    })


def _optional_schema(current: dict) -> vol.Schema:
    return vol.Schema({
        # ── Surplus (Zone 0) ──────────────────────────────────────────────────────────
        vol.Required(CONF_SURPLUS_ENABLED,        default=current.get(CONF_SURPLUS_ENABLED, False)): selector.selector({"boolean": {}}),
        vol.Required(CONF_SOC_EXPORT_LIMIT,       default=current.get(CONF_SOC_EXPORT_LIMIT, 90)): selector.selector(
            {"number": {"min": 50, "max": 99, "unit_of_measurement": "%"}}
        ),
        vol.Required(CONF_SURPLUS_EXIT_HYSTERESIS, default=current.get(CONF_SURPLUS_EXIT_HYSTERESIS, 5)): selector.selector(
            {"number": {"min": 1, "max": 20, "unit_of_measurement": "%"}}
        ),
        vol.Required(CONF_SURPLUS_PV_HYSTERESIS,  default=current.get(CONF_SURPLUS_PV_HYSTERESIS, 50)): selector.selector(
            {"number": {"min": 10, "max": 200, "unit_of_measurement": "W"}}
        ),
        # ── AC charging ───────────────────────────────────────────────────────────────
        vol.Required(CONF_AC_CHARGE_ENABLED,      default=current.get(CONF_AC_CHARGE_ENABLED, False)): selector.selector({"boolean": {}}),
        vol.Required(CONF_SOC_AC_CHARGE_LIMIT,    default=current.get(CONF_SOC_AC_CHARGE_LIMIT, 90)): selector.selector(
            {"number": {"min": 10, "max": 99, "unit_of_measurement": "%"}}
        ),
        vol.Required(CONF_AC_CHARGE_POWER_LIMIT,  default=current.get(CONF_AC_CHARGE_POWER_LIMIT, 800)): selector.selector(
            {"number": {"min": 50, "max": 1200, "unit_of_measurement": "W"}}
        ),
        vol.Required(CONF_AC_CHARGE_HYSTERESIS,   default=current.get(CONF_AC_CHARGE_HYSTERESIS, 50)): selector.selector(
            {"number": {"min": 0, "max": 300, "unit_of_measurement": "W"}}
        ),
        vol.Required(CONF_AC_CHARGE_OFFSET,       default=current.get(CONF_AC_CHARGE_OFFSET, -50)): selector.selector(
            {"number": {"min": -100, "max": 100, "unit_of_measurement": "W"}}
        ),
        vol.Optional(CONF_AC_CHARGE_OFFSET_ENTITY, default=current.get(CONF_AC_CHARGE_OFFSET_ENTITY, '')): selector.selector(
            {"entity": {"domain": "input_number"}}
        ),
        vol.Required(CONF_AC_CHARGE_P_FACTOR,     default=current.get(CONF_AC_CHARGE_P_FACTOR, 0.5)): selector.selector(
            {"number": {"min": 0.1, "max": 5.0, "step": 0.1}}
        ),
        vol.Required(CONF_AC_CHARGE_I_FACTOR,     default=current.get(CONF_AC_CHARGE_I_FACTOR, 0.07)): selector.selector(
            {"number": {"min": 0.0, "max": 0.2, "step": 0.01}}
        ),
        # ── Tariff arbitrage ──────────────────────────────────────────────────────────
        vol.Required(CONF_TARIFF_ENABLED,         default=current.get(CONF_TARIFF_ENABLED, False)): selector.selector({"boolean": {}}),
        vol.Optional(CONF_PRICE_SENSOR,           default=current.get(CONF_PRICE_SENSOR, '')): selector.selector(
            {"entity": {"domain": "sensor"}}
        ),
        vol.Required(CONF_CHEAP_THRESHOLD,        default=current.get(CONF_CHEAP_THRESHOLD, 10.0)): selector.selector(
            {"number": {"min": -100, "max": 100, "step": 0.1}}
        ),
        vol.Required(CONF_EXPENSIVE_THRESHOLD,    default=current.get(CONF_EXPENSIVE_THRESHOLD, 25.0)): selector.selector(
            {"number": {"min": -100, "max": 100, "step": 0.1}}
        ),
        vol.Required(CONF_TARIFF_SOC_TARGET,      default=current.get(CONF_TARIFF_SOC_TARGET, 90)): selector.selector(
            {"number": {"min": 10, "max": 99, "unit_of_measurement": "%"}}
        ),
        vol.Required(CONF_TARIFF_CHARGE_POWER,    default=current.get(CONF_TARIFF_CHARGE_POWER, 800)): selector.selector(
            {"number": {"min": 50, "max": 1200, "unit_of_measurement": "W"}}
        ),
        # ── Night shutdown ────────────────────────────────────────────────────────────
        vol.Required(CONF_NIGHT_SHUTDOWN,         default=current.get(CONF_NIGHT_SHUTDOWN, False)): selector.selector({"boolean": {}}),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Config flow — initial setup
# ─────────────────────────────────────────────────────────────────────────────

class SolakonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Multi-step config flow."""

    VERSION = 1
    _user_input: dict = {}

    async def async_step_user(self, user_input: dict | None = None) -> config_entries.FlowResult:
        """Step 1: Required entities."""
        errors: dict[str, str] = {}
        current = self._user_input

        if user_input is not None:
            zone1 = user_input.get(CONF_SOC_FAST_LIMIT, 50)
            zone3 = user_input.get(CONF_SOC_CONSERVATION_LIMIT, 20)
            if zone1 <= zone3:
                errors["base"] = "soc_limits_invalid"
            else:
                self._user_input.update(user_input)
                return await self.async_step_pi()

        return self.async_show_form(
            step_id="user",
            data_schema=_required_entities_schema(current),
            errors=errors,
            description_placeholders={"doc_url": "https://github.com/D4nte85/Solakon-One-Nulleinspeisung-Blueprint-homeassistant"},
        )

    async def async_step_pi(self, user_input: dict | None = None) -> config_entries.FlowResult:
        """Step 2: PI parameters."""
        if user_input is not None:
            self._user_input.update(user_input)
            return await self.async_step_soc()

        return self.async_show_form(
            step_id="pi",
            data_schema=_pi_schema(self._user_input),
        )

    async def async_step_soc(self, user_input: dict | None = None) -> config_entries.FlowResult:
        """Step 3: SOC zones + offsets."""
        if user_input is not None:
            self._user_input.update(user_input)
            return await self.async_step_optional()

        return self.async_show_form(
            step_id="soc",
            data_schema=_soc_schema(self._user_input),
        )

    async def async_step_optional(self, user_input: dict | None = None) -> config_entries.FlowResult:
        """Step 4: Optional features."""
        if user_input is not None:
            self._user_input.update(user_input)
            return self.async_create_entry(
                title="Solakon ONE Nulleinspeisung",
                data=self._user_input,
            )

        return self.async_show_form(
            step_id="optional",
            data_schema=_optional_schema(self._user_input),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "SolakonOptionsFlow":
        return SolakonOptionsFlow(config_entry)


# ─────────────────────────────────────────────────────────────────────────────
# Options flow — change settings after setup
# ─────────────────────────────────────────────────────────────────────────────

class SolakonOptionsFlow(config_entries.OptionsFlow):
    """Options flow: same 4-step structure."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry
        self._data: dict = {}

    def _current(self) -> dict:
        return {**self._entry.data, **self._entry.options, **self._data}

    async def async_step_init(self, user_input: dict | None = None) -> config_entries.FlowResult:
        return await self.async_step_entities(user_input)

    async def async_step_entities(self, user_input: dict | None = None) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_pi_opts()

        return self.async_show_form(
            step_id="entities",
            data_schema=_required_entities_schema(self._current()),
            errors=errors,
        )

    async def async_step_pi_opts(self, user_input: dict | None = None) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_soc_opts()

        return self.async_show_form(
            step_id="pi_opts",
            data_schema=_pi_schema(self._current()),
        )

    async def async_step_soc_opts(self, user_input: dict | None = None) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_optional_opts()

        return self.async_show_form(
            step_id="soc_opts",
            data_schema=_soc_schema(self._current()),
        )

    async def async_step_optional_opts(self, user_input: dict | None = None) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="", data=self._data)

        return self.async_show_form(
            step_id="optional_opts",
            data_schema=_optional_schema(self._current()),
        )
