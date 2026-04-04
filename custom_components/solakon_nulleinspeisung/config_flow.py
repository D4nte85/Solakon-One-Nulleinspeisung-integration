"""Config flow — 9 Pflicht-Entitäten. Alles weitere im Sidebar-Panel."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_GRID_SENSOR, CONF_ACTUAL_SENSOR, CONF_SOLAR_SENSOR,
    CONF_SOC_SENSOR, CONF_TIMEOUT_COUNTDOWN, CONF_ACTIVE_POWER,
    CONF_DISCHARGE_CURRENT, CONF_TIMEOUT_SET, CONF_MODE_SELECT,
    REQUIRED_ENTITY_DEFAULTS,
)

_D = REQUIRED_ENTITY_DEFAULTS


def _schema(current: dict) -> vol.Schema:
    """Erstellt das Voluptuous-Schema für Config- und Options-Flow."""
    return vol.Schema({
        vol.Required(
            CONF_GRID_SENSOR,
            default=current.get(CONF_GRID_SENSOR, ""),
        ): selector.selector({"entity": {"domain": "sensor", "device_class": "power"}}),

        vol.Required(
            CONF_ACTUAL_SENSOR,
            default=current.get(CONF_ACTUAL_SENSOR, _D[CONF_ACTUAL_SENSOR]),
        ): selector.selector({"entity": {"domain": "sensor", "device_class": "power"}}),

        vol.Required(
            CONF_SOLAR_SENSOR,
            default=current.get(CONF_SOLAR_SENSOR, _D[CONF_SOLAR_SENSOR]),
        ): selector.selector({"entity": {"domain": "sensor", "device_class": "power"}}),

        vol.Required(
            CONF_SOC_SENSOR,
            default=current.get(CONF_SOC_SENSOR, _D[CONF_SOC_SENSOR]),
        ): selector.selector({"entity": {"domain": "sensor", "device_class": "battery"}}),

        vol.Required(
            CONF_TIMEOUT_COUNTDOWN,
            default=current.get(CONF_TIMEOUT_COUNTDOWN, _D[CONF_TIMEOUT_COUNTDOWN]),
        ): selector.selector({"entity": {"domain": "sensor"}}),

        vol.Required(
            CONF_ACTIVE_POWER,
            default=current.get(CONF_ACTIVE_POWER, _D[CONF_ACTIVE_POWER]),
        ): selector.selector({"entity": {"domain": "number"}}),

        vol.Required(
            CONF_DISCHARGE_CURRENT,
            default=current.get(CONF_DISCHARGE_CURRENT, _D[CONF_DISCHARGE_CURRENT]),
        ): selector.selector({"entity": {"domain": "number"}}),

        vol.Required(
            CONF_TIMEOUT_SET,
            default=current.get(CONF_TIMEOUT_SET, _D[CONF_TIMEOUT_SET]),
        ): selector.selector({"entity": {"domain": "number"}}),

        vol.Required(
            CONF_MODE_SELECT,
            default=current.get(CONF_MODE_SELECT, _D[CONF_MODE_SELECT]),
        ): selector.selector({"entity": {"domain": "select"}}),
    })


class SolakonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Single-step Config-Flow — nur Pflicht-Entitäten."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="Solakon ONE Nulleinspeisung",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema({}),
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
    """Options-Flow — Entitäten nachträglich ändern."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry
