"""Testumgebung: FakeHass mit Zustandsspeicher, Uhr und Aufrufprotokoll.

Jeder Szenariolauf baut eine frische Umgebung und liefert ein JSON-fähiges Protokoll.
Uhr, `asyncio.sleep` und `dt_util.now` sind virtuell, damit Warte- und
Stillstandspfade deterministisch und ohne Echtzeit durchlaufen.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from tests import ha_stubs  # noqa: E402

ha_stubs.install()

PKG = "custom_components.solakon_nulleinspeisung"
integration = importlib.import_module(PKG)
coordinator_mod = importlib.import_module(PKG + ".coordinator")
const = importlib.import_module(PKG + ".const")
sensor_mod = importlib.import_module(PKG + ".sensor")
binary_mod = importlib.import_module(PKG + ".binary_sensor")
switch_mod = importlib.import_module(PKG + ".switch")
config_flow_mod = importlib.import_module(PKG + ".config_flow")

DOMAIN = const.DOMAIN


# ── Uhr ──────────────────────────────────────────────────────────────────────

class Clock:
    START = 1_800_000_000.0

    def __init__(self):
        self.now = self.START
        self.hass = None

    def time(self):
        return self.now

    def monotonic(self):
        return self.now - self.START

    async def sleep(self, seconds):
        if self.hass is not None:
            self.hass.log("sleep", round(float(seconds), 3))
        self.now += float(seconds)


CLOCK = Clock()


class _TimeProxy:
    def time(self):
        return CLOCK.time()

    def monotonic(self):
        return CLOCK.monotonic()


class _AsyncioProxy:
    Lock = asyncio.Lock

    def __getattr__(self, name):
        return getattr(asyncio, name)

    async def sleep(self, seconds):
        await CLOCK.sleep(seconds)


def _patch_modules() -> None:
    for name, mod in list(sys.modules.items()):
        if not name.startswith(PKG):
            continue
        if getattr(mod, "time", None) is not None and hasattr(mod.time, "monotonic"):
            mod.time = _TimeProxy()
        if getattr(mod, "asyncio", None) is not None and hasattr(mod.asyncio, "sleep"):
            mod.asyncio = _AsyncioProxy()


_patch_modules()


# ── Zustände und Services ────────────────────────────────────────────────────

class FakeState:
    def __init__(self, entity_id, state, attributes=None, last_updated=None):
        self.entity_id = entity_id
        self.state = str(state)
        self.attributes = dict(attributes or {})
        ts = CLOCK.now if last_updated is None else last_updated
        self.last_updated = datetime.fromtimestamp(ts, tz=timezone.utc)


class FakeStates:
    def __init__(self):
        self._states: dict[str, FakeState] = {}

    def get(self, entity_id):
        return self._states.get(entity_id)

    def set(self, entity_id, state, attributes=None, last_updated=None):
        if state is None:
            self._states.pop(entity_id, None)
            return
        self._states[entity_id] = FakeState(entity_id, state, attributes, last_updated)


class FakeServices:
    def __init__(self, hass):
        self.hass = hass

    async def async_call(self, domain, service, data, *args, **kwargs):
        eid = data.get("entity_id")
        value = data.get("value", data.get("option"))
        self.hass.log("call", domain, service, eid, value)
        old = self.hass.states.get(eid)
        attrs = old.attributes if old else {}
        if domain == "number" and service == "set_value":
            self.hass.states.set(eid, _num(value), attrs)
            for follower, sign in self.hass.followers.get(eid, ()):
                # sign 0: Sensor meldet frisch, bleibt aber auf seinem Wert stehen
                prev = self.hass.states.get(follower)
                new = prev.state if sign == 0 and prev else _num(sign * float(value))
                self.hass.states.set(follower, new, prev.attributes if prev else {})
        elif domain == "select" and service == "select_option":
            self.hass.states.set(eid, value, attrs)


def _num(value):
    f = float(value)
    return str(int(f)) if f == int(f) else repr(f)


class FakeConfig:
    def __init__(self, language):
        self.language = language


class FakeConfigEntries:
    def __init__(self, hass):
        self.hass = hass
        self.entries = []

    def async_entries(self, domain=None):
        return list(self.entries)

    def async_update_entry(self, entry, data=None, **kwargs):
        self.hass.log("entry_update", entry.entry_id, data)
        if data is not None:
            entry.data = data

    async def async_forward_entry_setups(self, entry, platforms):
        self.hass.log("forward_setups", entry.entry_id, list(platforms))

    async def async_unload_platforms(self, entry, platforms):
        self.hass.log("unload_platforms", entry.entry_id, list(platforms))
        return True

    async def async_reload(self, entry_id):
        self.hass.log("reload", entry_id)


class FakeHttp:
    def __init__(self, hass):
        self.hass = hass

    async def async_register_static_paths(self, paths):
        self.hass.log("static_paths", [[url, str(Path(path).relative_to(ROOT)), cache]
                                       for url, path, cache in paths])


class FakeHass:
    def __init__(self, language="de"):
        self.states = FakeStates()
        self.services = FakeServices(self)
        self.data: dict = {}
        self.storage: dict = {}
        self.config = FakeConfig(language)
        self.config_entries = FakeConfigEntries(self)
        self.http = FakeHttp(self)
        self.events: list = []
        self.followers: dict[str, list[tuple[str, float]]] = {}
        self._tracker_seq = 0
        CLOCK.hass = self

    def log(self, *event):
        self.events.append(list(event))

    def log_store(self, kind, key, data, *extra):
        """Store-Inhalt als Hash der Settings plus alle übrigen Schlüssel im Klartext."""
        data = jsonable(data)
        settings = {k: v for k, v in data.items() if k in const.SETTINGS_DEFAULTS}
        rest = {k: v for k, v in data.items() if k not in const.SETTINGS_DEFAULTS}
        digest = hashlib.sha1(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:12]
        self.log(kind, key, {"settings_sha": digest, "rest": rest}, *extra)

    def log_tracker(self, kind, target):
        self._tracker_seq += 1
        handle = self._tracker_seq
        self.log("track", kind, target, handle)

        def unsub():
            self.log("untrack", handle)
        return unsub

    def async_create_task(self, coro, *args, **kwargs):
        self.log("task", getattr(coro, "__qualname__", str(coro)))
        coro.close()


class FakeEntry:
    def __init__(self, entry_id, data, title="Solakon"):
        self.entry_id = entry_id
        self.data = data
        self.title = title
        self.options = {}
        self.unloads = []

    def async_on_unload(self, func):
        self.unloads.append(func)

    def add_update_listener(self, listener):
        return lambda: None


def entry_data(prefix: str, grid_sensor: str = "sensor.grid", export_limit: bool = True) -> dict:
    data = {
        const.CONF_INSTANCE_NAME: f"Speicher {prefix}",
        const.CONF_GRID_SENSOR: grid_sensor,
        const.CONF_ACTUAL_SENSOR: f"sensor.{prefix}_actual",
        const.CONF_SOLAR_SENSOR: f"sensor.{prefix}_solar",
        const.CONF_SOC_SENSOR: f"sensor.{prefix}_soc",
        const.CONF_TIMEOUT_COUNTDOWN: f"sensor.{prefix}_countdown",
        const.CONF_ACTIVE_POWER: f"number.{prefix}_power",
        const.CONF_DISCHARGE_CURRENT: f"number.{prefix}_discharge",
        const.CONF_TIMEOUT_SET: f"number.{prefix}_timeout",
        const.CONF_MODE_SELECT: f"select.{prefix}_mode",
    }
    if export_limit:
        data[const.CONF_EXPORT_LIMIT] = f"number.{prefix}_export"
    return data


# ── Aufzeichnung ─────────────────────────────────────────────────────────────

COORD_ATTRS = (
    "current_zone", "zone_label", "mode_key", "mode_label",
    "last_action", "last_action_key", "last_action_params", "last_action_ts",
    "last_error", "integral", "active_fall",
    "cycle_active", "surplus_active", "ac_charge_active", "tariff_charge_active", "resting",
    "is_night", "discharge_locked", "operating_state", "operating_state_ts",
    "_cycle_blocked", "last_output_ts", "mode_label_ts",
    "grid_stddev", "grid_stddev_raw", "dyn_offset_z1", "dyn_offset_z2", "dyn_offset_ac",
    "allocated_power", "surplus_power", "_dist_warning", "_output_warning",
    "_output_stall_actions", "_output_stall_last_ts", "_tariff_unit_suspect_since",
    "dist_mode_effective", "_prev_actual", "_solar_zero_entry_armed",
    "_timer_toggled_in_cycle",
    "forecast_tariff_suppressed", "forecast_surplus_forced", "forecast_exit_lock",
    "zone1_forced",
)

_MISSING = "<fehlt>"


def jsonable(value):
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        items = [jsonable(v) for v in value]
        return sorted(items, key=repr) if isinstance(value, set) else items
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if hasattr(value, "value") and not callable(value.value):
        return jsonable(value.value)
    return repr(value)


def coord_state(coord) -> dict:
    return {name: jsonable(getattr(coord, name, _MISSING)) for name in COORD_ATTRS}


class LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.records: list = []

    def emit(self, record):
        entry = [record.levelname, record.getMessage()]
        if record.exc_info:
            entry.append(f"{record.exc_info[0].__name__}: {record.exc_info[1]}")
        self.records.append(entry)


def capture_logs() -> LogCapture:
    handler = LogCapture()
    logger = logging.getLogger(PKG)
    for old in [h for h in logger.handlers if isinstance(h, LogCapture)]:
        logger.removeHandler(old)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return handler


def build_entities(hass, coord) -> list:
    entities: list = []
    for mod in (sensor_mod, binary_mod, switch_mod):
        _run_sync(mod.async_setup_entry(hass, coord.entry, entities.extend))
    return entities


def _run_sync(coro):
    """Treibt eine Coroutine ohne Event-Loop, sofern sie nicht wirklich suspendiert."""
    try:
        coro.send(None)
    except StopIteration as stop:
        return stop.value
    raise RuntimeError("Coroutine suspendiert unerwartet")


STATIC_ENTITY_ATTRS = (
    "unique_id", "translation_key", "entity_category", "device_class", "state_class",
    "native_unit_of_measurement", "suggested_display_precision", "options",
    "has_entity_name", "should_poll", "device_info",
)


def entity_state(entity, static=False) -> dict:
    rec = {"unique_id": entity.unique_id, "icon": jsonable(entity.icon)}
    if static:
        for name in STATIC_ENTITY_ATTRS:
            rec[name] = jsonable(getattr(entity, name))
    for name in ("native_value", "is_on", "extra_state_attributes"):
        try:
            value = getattr(type(entity), name, None)
            if value is None:
                continue
            rec[name] = jsonable(getattr(entity, name))
        except Exception as exc:  # pragma: no cover — Befund, nicht Absturz
            rec[name] = f"<{type(exc).__name__}: {exc}>"
    return rec


async def ws_status(hass, entry_id) -> list:
    conn = ha_stubs.ActiveConnection()
    await integration._ws_get_status(hass, conn, {"id": 1, "entry_id": entry_id})
    return jsonable(conn.sent)
