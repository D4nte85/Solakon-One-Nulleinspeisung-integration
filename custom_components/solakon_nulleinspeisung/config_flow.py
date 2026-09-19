"""Config flow — Instanzname + 9 Pflicht-Entitäten. Alles weitere im Sidebar-Panel."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
)

from .const import (
    DOMAIN,
    CONF_INSTANCE_NAME,
    CONF_GRID_SENSOR, CONF_ACTUAL_SENSOR, CONF_SOLAR_SENSOR,
    CONF_SOC_SENSOR, CONF_TIMEOUT_COUNTDOWN, CONF_ACTIVE_POWER,
    CONF_DISCHARGE_CURRENT, CONF_TIMEOUT_SET, CONF_MODE_SELECT,
    CONF_EXPORT_LIMIT,
    REQUIRED_ENTITY_DEFAULTS_DE, REQUIRED_ENTITY_DEFAULTS_EN,
)


# Entitätsfelder: (Schlüssel, Domain, device_class, Pflicht).
ENTITY_FIELDS = (
    (CONF_GRID_SENSOR, "sensor", "power", True),
    (CONF_ACTUAL_SENSOR, "sensor", "power", True),
    (CONF_SOLAR_SENSOR, "sensor", "power", True),
    (CONF_SOC_SENSOR, "sensor", "battery", True),
    (CONF_TIMEOUT_COUNTDOWN, "sensor", None, True),
    (CONF_ACTIVE_POWER, "number", None, True),
    (CONF_DISCHARGE_CURRENT, "number", None, True),
    (CONF_TIMEOUT_SET, "number", None, True),
    (CONF_MODE_SELECT, "select", None, True),
    (CONF_EXPORT_LIMIT, "number", None, False),
)


def _get_defaults(hass: HomeAssistant) -> dict:
    lang = hass.config.language or "de"
    return REQUIRED_ENTITY_DEFAULTS_EN if lang.startswith("en") else REQUIRED_ENTITY_DEFAULTS_DE


def _schema(current: dict, defaults: dict) -> vol.Schema:
    """Formular: Instanzname, dann ENTITY_FIELDS; Vorbelegung aktueller Wert, sonst Geräte-Default."""
    fields = {
        vol.Required(CONF_INSTANCE_NAME, default=current.get(CONF_INSTANCE_NAME, "Speicher 1")): TextSelector(),
    }
    for key, domain, device_class, required in ENTITY_FIELDS:
        marker = vol.Required if required else vol.Optional
        config = EntitySelectorConfig(domain=domain, device_class=device_class) if device_class \
            else EntitySelectorConfig(domain=domain)
        fields[marker(key, default=current.get(key, defaults.get(key, "")))] = EntitySelector(config)
    return vol.Schema(fields)


def _mode_select_taken(hass: HomeAssistant, value: str, exclude_entry_id: str | None = None) -> bool:
    """True, wenn eine andere Instanz den Modus-Select `value` bereits nutzt."""
    return any(
        entry.entry_id != exclude_entry_id and entry.data.get(CONF_MODE_SELECT) == value
        for entry in hass.config_entries.async_entries(DOMAIN)
    )


class SolakonOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            if _mode_select_taken(
                self.hass, user_input.get(CONF_MODE_SELECT, ""), self.config_entry.entry_id,
            ):
                return self.async_abort(reason="already_configured")
            # Entitäten-Zuweisung liegt in entry.data, nicht in entry.options.
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, **user_input},
            )
            return self.async_create_entry(title="", data={})

        defaults = _get_defaults(self.hass)
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(self.config_entry.data, defaults),
        )


class SolakonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            if _mode_select_taken(self.hass, user_input.get(CONF_MODE_SELECT, "")):
                return self.async_abort(reason="already_configured")
            return self.async_create_entry(
                title=user_input.get(CONF_INSTANCE_NAME, "Solakon ONE"),
                data=user_input,
            )

        defaults = _get_defaults(self.hass)
        return self.async_show_form(
            step_id="user",
            data_schema=_schema({}, defaults),
            description_placeholders={
                "hint": "https://github.com/D4nte85/Solakon-One-Nulleinspeisung-integration",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        entry: config_entries.ConfigEntry,
    ) -> "SolakonOptionsFlow":
        return SolakonOptionsFlow()
