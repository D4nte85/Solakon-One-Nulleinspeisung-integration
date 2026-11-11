"""Config flow — Geräteauswahl, dann Instanzname + Entitäten-Zuweisung. Alles weitere im Sidebar-Panel."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    DOMAIN,
    CONF_INSTANCE_NAME,
    FALLBACK_INSTANCE_NAME,
    CONF_GRID_SENSOR, CONF_ACTUAL_SENSOR, CONF_SOLAR_SENSOR,
    CONF_SOC_SENSOR, CONF_TIMEOUT_COUNTDOWN, CONF_ACTIVE_POWER,
    CONF_DISCHARGE_CURRENT, CONF_TIMEOUT_SET, CONF_MODE_SELECT,
    CONF_EXPORT_LIMIT,
    DEVICE_DOMAIN, DEVICE_KEYS,
)

CONF_DEVICE = "device"
CONF_ENABLE_DISABLED = "enable_disabled"
DEFAULT_INSTANCE_NAME = "Speicher 1"
DOC_URL = "https://github.com/D4nte85/Solakon-One-Nulleinspeisung-integration"

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


def _mode_select_taken(hass: HomeAssistant, value: str, exclude_entry_id: str | None = None) -> bool:
    """True, wenn eine andere Instanz den Modus-Select `value` bereits nutzt."""
    return any(
        entry.entry_id != exclude_entry_id and entry.data.get(CONF_MODE_SELECT) == value
        for entry in hass.config_entries.async_entries(DOMAIN)
    )


def _device_name(device) -> str:
    """Anzeigename eines Geräts: vom Nutzer vergebener Name, sonst Gerätename."""
    return device.name_by_user or device.name or device.id


def _device_entities(hass: HomeAssistant, device_id: str) -> dict:
    """Entitäten-Zuweisung aus dem Solakon-Gerät `device_id`: Feld → entity_id, über den Schlüssel der unique_id."""
    by_key = {}
    for entry in er.async_entries_for_device(er.async_get(hass), device_id, include_disabled_entities=True):
        if entry.platform == DEVICE_DOMAIN and entry.unique_id.startswith(f"{entry.config_entry_id}_"):
            by_key[entry.unique_id[len(entry.config_entry_id) + 1:]] = entry.entity_id
    return {field: by_key[key] for field, key in DEVICE_KEYS.items() if key in by_key}


def _free_devices(hass: HomeAssistant, exclude_entry_id: str | None = None) -> list:
    """Solakon-Geräte, deren Modus-Select keine andere Instanz nutzt."""
    devices = [d for d in dr.async_get(hass).devices.values()
               if any(ident[0] == DEVICE_DOMAIN for ident in d.identifiers)]
    return [d for d in devices
            if not _mode_select_taken(hass, _device_entities(hass, d.id).get(CONF_MODE_SELECT, ""), exclude_entry_id)]


def _entity_exists(hass: HomeAssistant, entity_id: str) -> bool:
    """True, wenn `entity_id` registriert ist oder einen Zustand hat."""
    return bool(entity_id) and (er.async_get(hass).async_get(entity_id) is not None
                                or hass.states.get(entity_id) is not None)


def _disabled(hass: HomeAssistant, values: dict) -> list:
    """Zugewiesene Entitäten der Entitätsfelder, die in der Registrierung deaktiviert sind."""
    registry = er.async_get(hass)
    out = []
    for key, *_ in ENTITY_FIELDS:
        entry = registry.async_get(values.get(key) or "")
        if entry is not None and entry.disabled_by is not None:
            out.append(entry.entity_id)
    return out


def _enable(hass: HomeAssistant, entity_ids: list) -> None:
    """Entitäten in der Registrierung aktivieren."""
    registry = er.async_get(hass)
    for entity_id in entity_ids:
        registry.async_update_entity(entity_id, disabled_by=None)


def _device_schema(devices: list, current: str | None) -> vol.Schema:
    """Formular der Geräteauswahl; `current` ist vorgewählt, wenn es in der Liste steht."""
    options = [SelectOptionDict(value=d.id, label=_device_name(d)) for d in devices]
    key = vol.Required(CONF_DEVICE, default=current) if current in {d.id for d in devices} \
        else vol.Required(CONF_DEVICE)
    return vol.Schema({key: SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN))})


def _schema(values: dict, disabled: list) -> vol.Schema:
    """Formular: Instanzname, ENTITY_FIELDS mit Vorbelegung `values`, bei deaktivierten Zuweisungen das Ankreuzfeld."""
    fields = {
        vol.Required(CONF_INSTANCE_NAME, default=values.get(CONF_INSTANCE_NAME, DEFAULT_INSTANCE_NAME)): TextSelector(),
    }
    for key, domain, device_class, required in ENTITY_FIELDS:
        marker = vol.Required if required else vol.Optional
        config = EntitySelectorConfig(domain=domain, device_class=device_class) if device_class \
            else EntitySelectorConfig(domain=domain)
        fields[marker(key, default=values[key]) if values.get(key) else marker(key)] = EntitySelector(config)
    if disabled:
        fields[vol.Required(CONF_ENABLE_DISABLED, default=True)] = BooleanSelector()
    return vol.Schema(fields)


class _EntityFlow:
    """Gemeinsame Schritte Geräteauswahl → Entitäten-Zuweisung; `_finish` legt an oder speichert."""

    _values: dict
    _device_step: str
    _exclude: str | None = None

    async def _show_device(self, current: str | None) -> FlowResult:
        """Geräteauswahl mit den freien Solakon-Geräten; ohne Gerät der Hinweisschritt."""
        devices = _free_devices(self.hass, self._exclude)
        if not devices:
            return self.async_show_form(step_id="no_device", data_schema=vol.Schema({}),
                                        description_placeholders={"hint": DOC_URL})
        return self.async_show_form(step_id=self._device_step, data_schema=_device_schema(devices, current),
                                    description_placeholders={"hint": DOC_URL})

    async def async_step_no_device(self, user_input: dict | None = None) -> FlowResult:
        """Kein Solakon-Gerät gefunden: Hinweis, danach die Zuweisung ohne Vorbelegung aus dem Gerät."""
        return await self.async_step_entities()

    def _apply_device(self, device_id: str) -> None:
        """Vorbelegung aus dem Gerät; fehlt die bisherige Entität eines Felds, ersetzt sie die des Geräts."""
        device = dr.async_get(self.hass).devices.get(device_id)
        for key, entity_id in _device_entities(self.hass, device_id).items():
            if not _entity_exists(self.hass, self._values.get(key, "")):
                self._values[key] = entity_id
        if device is not None and CONF_INSTANCE_NAME not in self._values:
            self._values[CONF_INSTANCE_NAME] = _device_name(device)

    async def async_step_entities(self, user_input: dict | None = None) -> FlowResult:
        """Entitäten-Zuweisung; Abbruch, wenn der Modus-Select schon vergeben ist."""
        if user_input is not None:
            data = dict(user_input)
            if data.pop(CONF_ENABLE_DISABLED, False):
                _enable(self.hass, _disabled(self.hass, data))
            if _mode_select_taken(self.hass, data.get(CONF_MODE_SELECT, ""), self._exclude):
                return self.async_abort(reason="already_configured")
            return self._finish(data)
        disabled = _disabled(self.hass, self._values)
        return self.async_show_form(
            step_id="entities",
            data_schema=_schema(self._values, disabled),
            description_placeholders={"hint": DOC_URL, "disabled": ", ".join(disabled)},
        )


class SolakonOptionsFlow(_EntityFlow, config_entries.OptionsFlow):
    _device_step = "init"

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Geräteauswahl; vorgewählt ist das Gerät des gespeicherten Modus-Selects."""
        self._values = dict(self.config_entry.data)
        self._exclude = self.config_entry.entry_id
        if user_input is not None:
            self._apply_device(user_input[CONF_DEVICE])
            return await self.async_step_entities()
        entry = er.async_get(self.hass).async_get(self._values.get(CONF_MODE_SELECT, ""))
        return await self._show_device(entry.device_id if entry is not None else None)

    def _finish(self, data: dict) -> FlowResult:
        """Entitäten-Zuweisung in `entry.data` speichern; der Reload läuft über den Update-Listener."""
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, **data},
        )
        return self.async_create_entry(title="", data={})


class SolakonConfigFlow(_EntityFlow, config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 2
    _device_step = "user"

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Geräteauswahl für eine neue Instanz."""
        self._values = {}
        if user_input is not None:
            self._apply_device(user_input[CONF_DEVICE])
            return await self.async_step_entities()
        return await self._show_device(None)

    def _finish(self, data: dict) -> FlowResult:
        """Neue Instanz anlegen."""
        return self.async_create_entry(title=data.get(CONF_INSTANCE_NAME, FALLBACK_INSTANCE_NAME), data=data)

    @staticmethod
    @callback
    def async_get_options_flow(
        entry: config_entries.ConfigEntry,
    ) -> "SolakonOptionsFlow":
        """OptionsFlow für die Entitäten-Zuweisung."""
        return SolakonOptionsFlow()
