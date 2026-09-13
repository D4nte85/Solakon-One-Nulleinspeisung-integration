"""Minimale Home-Assistant-Attrappen für die Charakterisierungstests.

Bildet nur die Schnittstellen nach, die die Integration importiert. Service-Aufrufe,
Tracker-Registrierungen, Store-Zugriffe und erzeugte Tasks landen im Protokoll des
jeweiligen FakeHass (siehe harness.py).
"""
from __future__ import annotations

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


class Event:
    def __init__(self, data=None):
        self.data = data or {}


def callback(func):
    return func


# ── helpers.event ────────────────────────────────────────────────────────────

def async_track_state_change_event(hass, entity_ids, action):
    return hass.log_tracker("state", list(entity_ids))


def async_track_time_interval(hass, action, interval):
    return hass.log_tracker("interval", interval.total_seconds())


# ── helpers.state ────────────────────────────────────────────────────────────

_ONE = ("on", "locked", "above_horizon", "open", "home")
_ZERO = ("off", "unlocked", "unknown", "below_horizon", "closed", "not_home")


def state_as_number(state) -> float:
    """Nachbau von homeassistant.helpers.state.state_as_number."""
    if state.state in _ONE:
        return 1
    if state.state in _ZERO:
        return 0
    return float(state.state)


# ── helpers.storage ──────────────────────────────────────────────────────────

class Store:
    def __init__(self, hass, version, key, *args, **kwargs):
        self.hass = hass
        self.version = version
        self.key = key

    async def async_load(self):
        data = self.hass.storage.get(self.key)
        return None if data is None else dict(data)

    async def async_save(self, data):
        self.hass.log_store("store_save", self.key, data)
        self.hass.storage[self.key] = data

    def async_delay_save(self, data_func, delay=0):
        self.hass.log_store("store_delay_save", self.key, data_func(), delay)

    async def async_remove(self):
        self.hass.log("store_remove", self.key)
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


class SensorEntity(Entity):
    pass


class BinarySensorEntity(Entity):
    pass


class SwitchEntity(Entity):
    pass


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


class _Description:
    def __init__(self, key, **kwargs):
        self.key = key
        for k, v in kwargs.items():
            setattr(self, k, v)


class SensorEntityDescription(_Description):
    pass


class BinarySensorEntityDescription(_Description):
    pass


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


class TextSelector(_Selector):
    pass


class EntitySelectorConfig(dict):
    def __repr__(self):
        return "EntitySelectorConfig(" + ", ".join(f"{k}={v!r}" for k, v in sorted(self.items())) + ")"


class ConfigEntryNotReady(Exception):
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


def install() -> None:
    _module("homeassistant.core", HomeAssistant=HomeAssistant, Event=Event, callback=callback)
    _module("homeassistant.helpers.event",
            async_track_state_change_event=async_track_state_change_event,
            async_track_time_interval=async_track_time_interval)
    _module("homeassistant.helpers.state", state_as_number=state_as_number)
    _module("homeassistant.helpers.storage", Store=Store)
    _module("homeassistant.util.dt", now=dt_now, utc_from_timestamp=utc_from_timestamp)
    _module("homeassistant.helpers.entity", Entity=Entity)
    _module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
    _module("homeassistant.components.sensor", SensorEntity=SensorEntity,
            SensorDeviceClass=SensorDeviceClass, SensorStateClass=SensorStateClass,
            SensorEntityDescription=SensorEntityDescription)
    _module("homeassistant.components.binary_sensor", BinarySensorEntity=BinarySensorEntity,
            BinarySensorEntityDescription=BinarySensorEntityDescription)
    _module("homeassistant.components.switch", SwitchEntity=SwitchEntity)
    _module("homeassistant.const", EntityCategory=EntityCategory, UnitOfPower=UnitOfPower)
    _module("homeassistant.config_entries", ConfigFlow=ConfigFlow, OptionsFlow=OptionsFlow,
            ConfigEntry=ConfigEntry)
    _module("homeassistant.data_entry_flow", FlowResult=dict)
    _module("homeassistant.helpers.selector", EntitySelector=EntitySelector,
            EntitySelectorConfig=EntitySelectorConfig, TextSelector=TextSelector)
    _module("homeassistant.exceptions", ConfigEntryNotReady=ConfigEntryNotReady)
    _module("homeassistant.components.http", StaticPathConfig=StaticPathConfig)
    _module("homeassistant.components.websocket_api", websocket_command=websocket_command,
            async_response=async_response, require_admin=require_admin,
            async_register_command=async_register_command, ActiveConnection=ActiveConnection)
    _module("homeassistant.components.panel_custom", async_register_panel=async_register_panel)
    _module("homeassistant.components.frontend", async_remove_panel=async_remove_panel)
