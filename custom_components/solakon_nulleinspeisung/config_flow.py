"""Config flow — Instanzname + 9 Pflicht-Entitäten. Alles weitere im Sidebar-Panel."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_INSTANCE_NAME,
    CONF_GRID_SENSOR, CONF_ACTUAL_SENSOR, CONF_SOLAR_SENSOR,
    CONF_SOC_SENSOR, CONF_TIMEOUT_COUNTDOWN, CONF_ACTIVE_POWER,
    CONF_DISCHARGE_CURRENT, CONF_TIMEOUT_SET, CONF_MODE_SELECT,
    REQUIRED_ENTITY_DEFAULTS_DE, REQUIRED_ENTITY_DEFAULTS_EN,
)


def _get_defaults(hass: HomeAssistant) -> dict:
    lang = hass.config.language or "de"
    return REQUIRED_ENTITY_DEFAULTS_EN if lang.startswith("en") else REQUIRED_ENTITY_DEFAULTS_DE


def _schema(current: dict, defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(
            CONF_INSTANCE_NAME,
            default=current.get(CONF_INSTANCE_NAME, "Speicher 1"),
        ): selector.selector({"text": {}}),

        vol.Required(
            CONF_GRID_SENSOR,
            default=current.get(CONF_GRID_SENSOR, ""),
        ): selector.selector({"entity": {"domain": "sensor", "device_class": "power"}}),

        vol.Required(
            CONF_ACTUAL_SENSOR,
            default=current.get(CONF_ACTUAL_SENSOR, defaults[CONF_ACTUAL_SENSOR]),
        ): selector.selector({"entity": {"domain": "sensor", "device_class": "power"}}),

        vol.Required(
            CONF_SOLAR_SENSOR,
            default=current.get(CONF_SOLAR_SENSOR, defaults[CONF_SOLAR_SENSOR]),
        ): selector.selector({"entity": {"domain": "sensor", "device_class": "power"}}),

        vol.Required(
            CONF_SOC_SENSOR,
            default=current.get(CONF_SOC_SENSOR, defaults[CONF_SOC_SENSOR]),
        ): selector.selector({"entity": {"domain": "sensor", "device_class": "battery"}}),

        vol.Required(
            CONF_TIMEOUT_COUNTDOWN,
            default=current.get(CONF_TIMEOUT_COUNTDOWN, defaults[CONF_TIMEOUT_COUNTDOWN]),
        ): selector.selector({"entity": {"domain": "sensor"}}),

        vol.Required(
            CONF_ACTIVE_POWER,
            default=current.get(CONF_ACTIVE_POWER, defaults[CONF_ACTIVE_POWER]),
        ): selector.selector({"entity": {"domain": "number"}}),

        vol.Required(
            CONF_DISCHARGE_CURRENT,
            default=current.get(CONF_DISCHARGE_CURRENT, defaults[CONF_DISCHARGE_CURRENT]),
        ): selector.selector({"entity": {"domain": "number"}}),

        vol.Required(
            CONF_TIMEOUT_SET,
            default=current.get(CONF_TIMEOUT_SET, defaults[CONF_TIMEOUT_SET]),
        ): selector.selector({"entity": {"domain": "number"}}),

        vol.Required(
            CONF_MODE_SELECT,
            default=current.get(CONF_MODE_SELECT, defaults[CONF_MODE_SELECT]),
        ): selector.selector({"entity": {"domain": "select"}}),
    })


class SolakonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get(CONF_INSTANCE_NAME, "Solakon ONE"),
                data=user_input,
            )

        defaults = _get_defaults(self.hass)
        return self.async_show_form(
            step_id="user",
            data_schema=_schema({}, defaults),
            description_placeholders={
                "hint": "https://github.com/D4nte85/Solakon-One-Nulleinspeisung-Blueprint-homeassistant",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        entry: config_entries.ConfigEntry,
    ) -> "SolakonOptionsFlow":
        return SolakonOptionsFlow(entry)


class SolakonOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        defaults = _get_defaults(self.hass)
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(self._entry.data, defaults),
        )
