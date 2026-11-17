"""Minimale Home-Assistant-Attrappen für die Charakterisierungstests.

Bildet nur die Schnittstellen nach, die die Integration importiert. Service-Aufrufe,
Tracker-Registrierungen, Store-Zugriffe und erzeugte Tasks landen im Protokoll des
jeweiligen FakeHass (siehe harness.py).
"""
from __future__ import annotations

import copy
import sys
import types
from datetime import datetime, timezone
from enum import Enum


def _module(name: str, **attrs) -> types.ModuleType:
    mod = sys.modules.get(name) or types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    parent, _, child = name.rpartition(".")
    if parent:
        setattr(_module(parent), child, mod)
    return mod


# ── core ─────────────────────────────────────────────────────────────────────

class HomeAssistant:  # nur Typangabe
    pass


def callback(func):
    return func


# ── helpers.event ────────────────────────────────────────────────────────────

def async_track_state_change_event(hass, entity_ids, action):
    return hass.log_tracker("state", list(entity_ids))


def async_track_time_interval(hass, action, interval):
    return hass.log_tracker("interval", interval.total_seconds())


# ── helpers.storage ──────────────────────────────────────────────────────────

class UnsupportedStorageVersionError(Exception):
    """Gespeicherte Hauptversion ist neuer als die des Stores."""


class Store:
    """Nachbau von homeassistant.helpers.storage.Store.

    `hass.storage[key]` hält den Umschlag wie die Datei in `.storage`: `version`,
    `minor_version`, `key`, `data`. Laden migriert ältere Stände über
    `_async_migrate_func` und speichert das Ergebnis. `async_delay_save` merkt den
    Schreibauftrag dieser Instanz vor; `data_func` läuft erst beim Schreiben, das
    `FakeHass.write_due_stores` nach Ablauf der Frist auslöst, und erst dort wird der Inhalt
    protokolliert. `async_remove` verwirft nur den Auftrag der eigenen Instanz.
    """

    def __init__(self, hass, version, key, *args, minor_version=1, **kwargs):
        self.hass = hass
        self.version = version
        self.minor_version = minor_version
        self.key = key
        self._pending = None      # data_func des vorgemerkten Schreibauftrags
        self.due = None           # Zeitpunkt des vorgemerkten Schreibauftrags

    def _envelope(self, data):
        return {"version": self.version, "minor_version": self.minor_version, "key": self.key, "data": data}

    def _write(self, data):
        # Wie die JSON-Datei: kein geteilter Zustand zwischen Speicher und Aufrufer.
        self.hass.storage[self.key] = copy.deepcopy(self._envelope(data))

    def _cancel(self):
        self._pending = self.due = None
        self.hass.pending_stores.discard(self)

    async def async_load(self):
        if self._pending is not None:
            data = self._envelope(self._pending())
        else:
            data = self.hass.storage.get(self.key)
            if data is None:
                return None
        data = copy.deepcopy(data)
        data.setdefault("minor_version", 1)
        if data["version"] == self.version and data["minor_version"] == self.minor_version:
            return data["data"]
        if data["version"] > self.version:
            raise UnsupportedStorageVersionError(self.key, data["version"], self.version)
        try:
            stored = await self._async_migrate_func(data["version"], data["minor_version"], data["data"])
        except NotImplementedError:
            if data["version"] != self.version:
                raise
            stored = data["data"]
        await self.async_save(stored)
        return stored

    async def async_save(self, data):
        self.hass.log_store("store_save", self.key, data)
        self._cancel()
        self._write(data)

    def async_delay_save(self, data_func, delay=0):
        # HA ruft `data_func` erst beim Schreiben auf; den Inhalt protokolliert `write_pending`.
        self.hass.log("store_delay_save", self.key, delay)
        self._pending = data_func
        self.due = self.hass.clock_now() + delay
        self.hass.pending_stores.add(self)

    def write_pending(self):
        """Vorgemerkten Schreibauftrag ausführen (Fristablauf in HA)."""
        data_func = self._pending
        self._cancel()
        if data_func is not None:
            data = data_func()
            self.hass.log_store("store_write", self.key, data)
            self._write(data)

    async def _async_migrate_func(self, old_major_version, old_minor_version, old_data):
        raise NotImplementedError

    async def async_remove(self):
        self.hass.log("store_remove", self.key)
        self._cancel()
        self.hass.storage.pop(self.key, None)


# ── util.dt ──────────────────────────────────────────────────────────────────

class _DtState:
    now = datetime(2026, 9, 13, 14, 0, tzinfo=timezone.utc)


def dt_now():
    return _DtState.now


def utc_from_timestamp(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc)


# ── Entitäten ────────────────────────────────────────────────────────────────

_ENTITY_ATTRS = (
    "unique_id", "translation_key", "icon", "entity_category", "device_class",
    "state_class", "native_unit_of_measurement", "suggested_display_precision",
    "options", "has_entity_name", "should_poll", "device_info",
    "native_min_value", "native_max_value", "native_step", "mode",
)


class Entity:
    """Löst Attribute wie HA auf: `_attr_*` vor `entity_description`."""

    entity_description = None

    def __getattr__(self, name):
        if name in _ENTITY_ATTRS:
            attr = "_attr_" + name
            if attr in self.__dict__:
                return self.__dict__[attr]
            for klass in type(self).__mro__:
                if attr in klass.__dict__:
                    return klass.__dict__[attr]
            desc = self.__dict__.get("entity_description") or type(self).entity_description
            if desc is not None and hasattr(desc, name):
                return getattr(desc, name)
            return None
        raise AttributeError(name)

    def async_write_ha_state(self):
        pass

    async def async_remove(self):
        """Wie HA: Hook `async_will_remove_from_hass`, dann entfernt."""
        hook = getattr(type(self), "async_will_remove_from_hass", None)
        if hook is not None:
            await hook(self)
        self.__dict__["removed"] = True


class SensorEntity(Entity):
    pass


class BinarySensorEntity(Entity):
    pass


class SwitchEntity(Entity):
    pass


class NumberEntity(Entity):
    pass


class NumberMode(str, Enum):
    AUTO = "auto"
    BOX = "box"
    SLIDER = "slider"


class SensorDeviceClass(str, Enum):
    ENUM = "enum"
    POWER = "power"
    ENERGY = "energy"


class SensorStateClass(str, Enum):
    MEASUREMENT = "measurement"


class EntityCategory(str, Enum):
    DIAGNOSTIC = "diagnostic"
    CONFIG = "config"


class UnitOfPower(str, Enum):
    WATT = "W"


# ── Config-Flow ──────────────────────────────────────────────────────────────

class ConfigFlow:
    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.domain = domain

    def async_abort(self, reason):
        return {"type": "abort", "reason": reason}

    def async_create_entry(self, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, step_id, data_schema=None, description_placeholders=None):
        return {"type": "form", "step_id": step_id, "data_schema": data_schema,
                "description_placeholders": description_placeholders}


class OptionsFlow(ConfigFlow):
    pass


class ConfigEntry:
    pass


class _Selector:
    def __init__(self, config=None):
        self.config = config

    def __call__(self, value):
        return value

    def __repr__(self):
        return f"{type(self).__name__}({self.config!r})"


class EntitySelector(_Selector):
    pass


class SelectSelector(_Selector):
    pass


class BooleanSelector(_Selector):
    pass


class SelectSelectorMode:
    DROPDOWN = "dropdown"


def SelectOptionDict(value, label):
    return {"value": value, "label": label}


class SelectSelectorConfig(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __repr__(self):
        return "SelectSelectorConfig(" + ", ".join(f"{k}={v!r}" for k, v in sorted(self.items())) + ")"


class TextSelector(_Selector):
    pass


class EntitySelectorConfig(dict):
    def __repr__(self):
        return "EntitySelectorConfig(" + ", ".join(f"{k}={v!r}" for k, v in sorted(self.items())) + ")"


class RegistryEntry:
    """Eintrag der Entitätsregistrierung mit Gerät, Config-Entry und Deaktivierung."""

    def __init__(self, entity_id, platform, unique_id, config_entry_id=None, device_id=None, disabled_by=None):
        self.entity_id = entity_id
        self.platform = platform
        self.unique_id = unique_id
        self.config_entry_id = config_entry_id
        self.device_id = device_id
        self.disabled_by = disabled_by


class EntityRegistry:
    """Entitätsregistrierung: entity_id → (Plattform-Domain, Integration, unique_id); `records` mit Geräte-Bezug."""

    def __init__(self, hass):
        self.hass = hass
        self.entities = {}
        self.records = {}

    def add(self, entry):
        self.records[entry.entity_id] = entry

    def async_get(self, entity_id):
        return self.records.get(entity_id)

    def async_update_entity(self, entity_id, **changes):
        self.hass.log("registry_update", entity_id, changes)
        if "new_unique_id" in changes and entity_id in self.entities:
            domain, platform, _ = self.entities[entity_id]
            self.entities[entity_id] = (domain, platform, changes["new_unique_id"])
        for key, value in changes.items():
            if entity_id in self.records:
                setattr(self.records[entity_id], "unique_id" if key == "new_unique_id" else key, value)

    def async_get_entity_id(self, domain, platform, unique_id):
        return next((eid for eid, key in self.entities.items() if key == (domain, platform, unique_id)), None)

    def async_remove(self, entity_id):
        self.hass.log("registry_remove", entity_id)
        self.entities.pop(entity_id, None)


class DeviceEntry:
    def __init__(self, device_id, identifiers, name=None, name_by_user=None):
        self.id = device_id
        self.identifiers = identifiers
        self.name = name
        self.name_by_user = name_by_user


class DeviceRegistry:
    """Geräteregistrierung: device_id → DeviceEntry."""

    def __init__(self, hass):
        self.hass = hass
        self.devices = {}

    def async_get_device(self, identifiers):
        return next((d for d in self.devices.values() if d.identifiers & identifiers), None)

    def async_remove_device(self, device_id):
        self.hass.log("device_remove", device_id)
        self.devices.pop(device_id, None)


def device_registry_get(hass):
    if getattr(hass, "device_registry", None) is None:
        hass.device_registry = DeviceRegistry(hass)
    return hass.device_registry


def entities_for_device(registry, device_id, include_disabled_entities=False):
    return [e for e in registry.records.values()
            if e.device_id == device_id and (include_disabled_entities or e.disabled_by is None)]


def entity_registry_get(hass):
    if getattr(hass, "entity_registry", None) is None:
        hass.entity_registry = EntityRegistry(hass)
    return hass.entity_registry


class HomeAssistantError(Exception):
    pass


class ConfigEntryNotReady(HomeAssistantError):
    pass


class StaticPathConfig(tuple):
    def __new__(cls, url, path, cache):
        return tuple.__new__(cls, (url, path, cache))


# ── websocket_api ────────────────────────────────────────────────────────────

def websocket_command(schema):
    def deco(func):
        func.ws_schema = schema
        return func
    return deco


def async_response(func):
    return func


def require_admin(func):
    func.ws_require_admin = True
    return func


def async_register_command(hass, handler):
    hass.log("ws_register", handler.__name__)


class ActiveConnection:
    def __init__(self):
        self.sent = []

    def send_result(self, msg_id, result=None):
        self.sent.append(("result", msg_id, result))

    def send_error(self, msg_id, code, message):
        self.sent.append(("error", msg_id, code, message))


async def async_register_panel(hass, **kwargs):
    hass.log("panel_register", kwargs)


def async_remove_panel(hass, path):
    hass.log("panel_remove", path)


def persistent_notification_create(hass, message, title=None, notification_id=None):
    hass.log("notify", notification_id, title, message)


def install() -> None:
    _module("homeassistant.core", HomeAssistant=HomeAssistant, callback=callback)
    _module("homeassistant.helpers.event",
            async_track_state_change_event=async_track_state_change_event,
            async_track_time_interval=async_track_time_interval)
    _module("homeassistant.helpers.storage", Store=Store)
    _module("homeassistant.helpers.entity_registry", async_get=entity_registry_get,
            async_entries_for_device=entities_for_device)
    _module("homeassistant.helpers.device_registry", async_get=device_registry_get)
    _module("homeassistant.helpers.config_validation",
            config_entry_only_config_schema=lambda domain: {})
    _module("homeassistant.util.dt", now=dt_now, utc_from_timestamp=utc_from_timestamp)
    _module("homeassistant.helpers.entity", Entity=Entity)
    _module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
    _module("homeassistant.components.sensor", SensorEntity=SensorEntity,
            SensorDeviceClass=SensorDeviceClass, SensorStateClass=SensorStateClass)
    _module("homeassistant.components.binary_sensor", BinarySensorEntity=BinarySensorEntity)
    _module("homeassistant.components.switch", SwitchEntity=SwitchEntity)
    _module("homeassistant.components.number", NumberEntity=NumberEntity, NumberMode=NumberMode)
    _module("homeassistant.const", EntityCategory=EntityCategory, UnitOfPower=UnitOfPower,
            PERCENTAGE="%", STATE_UNKNOWN="unknown", STATE_UNAVAILABLE="unavailable")
    _module("homeassistant.config_entries", ConfigFlow=ConfigFlow, OptionsFlow=OptionsFlow,
            ConfigEntry=ConfigEntry)
    _module("homeassistant.data_entry_flow", FlowResult=dict)
    _module("homeassistant.helpers.selector", EntitySelector=EntitySelector,
            EntitySelectorConfig=EntitySelectorConfig, TextSelector=TextSelector,
            SelectSelector=SelectSelector, SelectSelectorConfig=SelectSelectorConfig,
            SelectSelectorMode=SelectSelectorMode, SelectOptionDict=SelectOptionDict,
            BooleanSelector=BooleanSelector)
    _module("homeassistant.exceptions", ConfigEntryNotReady=ConfigEntryNotReady,
            HomeAssistantError=HomeAssistantError,
            UnsupportedStorageVersionError=UnsupportedStorageVersionError)
    _module("homeassistant.components.http", StaticPathConfig=StaticPathConfig)
    _module("homeassistant.components.websocket_api", websocket_command=websocket_command,
            async_response=async_response, require_admin=require_admin,
            async_register_command=async_register_command, ActiveConnection=ActiveConnection)
    _module("homeassistant.components.panel_custom", async_register_panel=async_register_panel)
    _module("homeassistant.components.frontend", async_remove_panel=async_remove_panel)
    _module("homeassistant.components.persistent_notification", async_create=persistent_notification_create)
