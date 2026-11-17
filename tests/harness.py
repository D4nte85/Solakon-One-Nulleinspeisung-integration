"""Testumgebung: FakeHass mit Zustandsspeicher, Uhr und Aufrufprotokoll.

Jeder Szenariolauf baut eine frische Umgebung und liefert ein JSON-fähiges Protokoll.
Uhr, `asyncio.sleep` und `dt_util.now` sind virtuell, damit Warte- und
Stillstandspfade deterministisch und ohne Echtzeit durchlaufen.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import itertools
import json
import logging
import sys
import weakref
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
dynamic_offset_mod = importlib.import_module(PKG + ".dynamic_offset")
zones_mod = importlib.import_module(PKG + ".zones")
pi_mod = importlib.import_module(PKG + ".pi")
const = importlib.import_module(PKG + ".const")
sensor_mod = importlib.import_module(PKG + ".sensor")
binary_mod = importlib.import_module(PKG + ".binary_sensor")
switch_mod = importlib.import_module(PKG + ".switch")
number_mod = importlib.import_module(PKG + ".number")
config_flow_mod = importlib.import_module(PKG + ".config_flow")
group_store_mod = importlib.import_module(PKG + ".group_store")
runtime_mod = importlib.import_module(PKG + ".runtime")
migrations_mod = importlib.import_module(PKG + ".migrations")

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

_REPORT_SEQ = itertools.count()


class FakeState:
    def __init__(self, entity_id, state, attributes=None, last_updated=None):
        self.entity_id = entity_id
        self.state = str(state)
        self.attributes = dict(attributes or {})
        ts = CLOCK.now if last_updated is None else last_updated
        self.last_updated = datetime.fromtimestamp(ts, tz=timezone.utc)
        # Eigener Meldezeitpunkt je Setzen, auch bei gleicher Uhrzeit.
        self.last_reported = self.last_updated + timedelta(microseconds=next(_REPORT_SEQ))


class FakeStates:
    def __init__(self):
        self._states: dict[str, FakeState] = {}
        self.defaults: dict[str, dict] = {}   # Standardattribute je Entity, s. tests/geraet.py

    def get(self, entity_id):
        return self._states.get(entity_id)

    def set(self, entity_id, state, attributes=None, last_updated=None):
        if state is None:
            self._states.pop(entity_id, None)
            return
        attrs = {**self.defaults.get(entity_id, {}), **(attributes or {})}
        new = FakeState(entity_id, state, attrs, last_updated)
        # Wie HA: Gleicher Zustand mit gleichen Attributen rückt nur `last_reported` vor.
        old = self._states.get(entity_id)
        if last_updated is None and old is not None and (old.state, old.attributes) == (new.state, new.attributes):
            new.last_updated = old.last_updated
        self._states[entity_id] = new


class FakeServices:
    def __init__(self, hass):
        self.hass = hass

    async def async_call(self, domain, service, data, *args, **kwargs):
        eid = data.get("entity_id")
        value = data.get("value", data.get("option"))
        self.hass.log("call", domain, service, eid, value)
        old = self.hass.states.get(eid)
        attrs = old.attributes if old else {}
        geraet = self.hass.geraet.get(eid)
        # HA weist Werte außerhalb des Bereichs ab; ohne blocking erreicht der Fehler den Aufrufer nicht
        if domain == "number" and service == "set_value":
            if not geraet or geraet.min <= float(value) <= geraet.max:
                # Geräte-Integration schreibt int(value) ins Register, Rückmeldung per Poll
                self.hass.states.set(eid, _num(int(float(value)) if geraet else value), attrs)
                for follower, sign in self.hass.followers.get(eid, ()):
                    # sign 0: Sensor meldet neu (last_reported), bleibt aber auf seinem Wert stehen
                    prev = self.hass.states.get(follower)
                    new = prev.state if sign == 0 and prev else _num(sign * float(value))
                    self.hass.states.set(follower, new, prev.attributes if prev else {})
        elif domain == "select" and service == "select_option":
            if not geraet or value in geraet.optionen:
                self.hass.states.set(eid, value, attrs)
        # Szenario-Schlüssel `nach_aufruf`: Zustände einmalig nach dem ersten Schreibbefehl auf `eid`
        # setzen, auch wenn HA ihn abweist
        for other, st in self.hass.on_call.pop(eid, {}).items():
            self.hass.states.set(other, st.get("state"), st.get("attrs"),
                                 last_updated=CLOCK.now - st.get("age", 0))


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
        for key, value in kwargs.items():
            setattr(entry, key, value)

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


_LIVE_HASS: weakref.WeakSet = weakref.WeakSet()


def close_open_tasks() -> None:
    """Nicht abgearbeitete Tasks aller FakeHass schließen.

    Szenarioläufe rufen `_async_regulate` je Schritt selbst auf; angestoßene Zyklen aus
    `request_regulation` laufen nur in Tests mit `async_block_till_done`.
    """
    for hass in list(_LIVE_HASS):
        hass.close_tasks()


def run(coro):
    """`asyncio.run` für einen Lauf; danach offene Tasks schließen."""
    try:
        return asyncio.run(coro)
    finally:
        close_open_tasks()


class FakeHass:
    def __init__(self, language="de"):
        _LIVE_HASS.add(self)
        self.states = FakeStates()
        self.services = FakeServices(self)
        self.data: dict = {}
        self.storage: dict = {}          # Schlüssel -> Umschlag wie in `.storage` (siehe ha_stubs.Store)
        self.pending_stores: set = set()  # Stores mit vorgemerktem `async_delay_save`
        self.tasks: list = []             # Koroutinen aus `async_create_task`, laufen in `async_block_till_done`
        self.config = FakeConfig(language)
        self.config_entries = FakeConfigEntries(self)
        self.http = FakeHttp(self)
        self.events: list = []
        self.followers: dict[str, list[tuple[str, float]]] = {}
        self.on_call: dict[str, dict] = {}   # entity_id -> Zustände, gesetzt nach dem ersten Schreibbefehl darauf
        self.geraet: dict = {}   # entity_id -> tests.geraet.Entity
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

    def clock_now(self) -> float:
        return CLOCK.now

    def async_create_task(self, coro, *args, **kwargs):
        """Wie HA: Koroutine einplanen, nicht im Aufrufer ausführen; sie läuft in `async_block_till_done`."""
        self.log("task", getattr(coro, "__qualname__", str(coro)))
        self.tasks.append(coro)
        return coro

    async def async_block_till_done(self) -> None:
        """Eingeplante Tasks abarbeiten, auch nachgeschobene, dann fällige Schreibaufträge der Stores."""
        while True:
            if self.tasks:
                await self.tasks.pop(0)
                continue
            due = sorted((s for s in self.pending_stores if s.due <= CLOCK.now), key=lambda s: s.due)
            if not due:
                return
            for store in due:
                store.write_pending()

    def close_tasks(self) -> None:
        """Nicht abgearbeitete Tasks schließen (Testende ohne `async_block_till_done`)."""
        for coro in self.tasks:
            coro.close()
        self.tasks = []


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

# Zustand am Coordinator für Aufzeichnungen; Schlüssel ist der Pfad (Teilobjekt.Attribut).
COORD_ATTRS = (
    "display.zone", "display.zone_label", "display.mode_key", "display.mode_label", "last_action",
    "last_action_key", "last_action_params", "last_error", "last_error_msgs",
    "integral", "active_fall", "cycle_active", "surplus_active", "charge_session", "resting",
    "is_night", "discharge_locked", "display.operating_state", "display.operating_state_ts",
    "_cycle_blocked", "out.last_ts", "display.mode_ts", "dyn.stddev", "dyn.stddev_raw",
    "dyn.offsets.z1", "dyn.offsets.z1_night", "dyn.offsets.z2", "dyn.offsets.ac",
    "allocated_power", "surplus_power", "_messages.hardware_msg", "out.stall_actions",
    "out.stall_last_ts", "tariff.unit_suspect_since", "dist_mode_effective", "surplus.prev_actual",
    "surplus.armed", "timeout.toggled_in_cycle", "tariff.suppressed", "forecast.surplus_forced",
    "forecast.exit_lock", "forecast.zone1_forced", "settings_rev",
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


def _store_version(key: str) -> tuple[int, int]:
    """Aktuelle (Haupt-, Neben-)Version des Stores unter `key`; Testschlüssel ohne Store: (1, 1)."""
    gs = group_store_mod
    versions = {gs.STORAGE_KEY_DIST: gs.STORAGE_VERSION_DIST, gs.STORAGE_KEY_SOC_SWITCH: gs.STORAGE_VERSION_SOC_SWITCH,
                gs.STORAGE_KEY_NUMBERS: gs.STORAGE_VERSION_NUMBERS}
    if key in versions:
        return versions[key], 1
    if key.startswith(f"{const.DOMAIN}_entry_"):
        return const.STORAGE_VERSION, const.STORAGE_MINOR_VERSION
    return 1, 1


def put_store(hass, key: str, data, version: int | None = None, minor_version: int | None = None) -> None:
    """Speicherstand wie eine Datei in `.storage` ablegen; ohne Version in der aktuellen des Stores."""
    major, minor = _store_version(key)
    if version is not None:
        major, minor = version, 1 if minor_version is None else minor_version
    hass.storage[key] = {"version": major, "minor_version": minor, "key": key, "data": data}


def stored(hass, key: str, default=None):
    """Gespeicherte Nutzdaten unter `key`, ohne Umschlag."""
    env = hass.storage.get(key)
    return default if env is None else env["data"]


def install_groups(hass, dist=None, soc_switch=None, dist_store=None, soc_switch_store=None):
    """Speicher der Netzgruppen ohne Setup in `hass.data` legen."""
    store = group_store_mod.GroupStore(hass, dist_store, soc_switch_store, dist, soc_switch)
    runtime_mod.runtime(hass).store = store
    return store


def groups_state(hass):
    """Gruppenzustand für Aufzeichnungen: {Netzsensor: {"dist": …, "soc_switch": …}}, ohne Speicher None."""
    store = group_store_mod.store_for(hass)
    if store is None:
        return None
    out: dict = {}
    for grid, cfg in store.dist.items():
        out.setdefault(grid, {})["dist"] = cfg
    for grid, state in store.soc_switch.items():
        out.setdefault(grid, {})["soc_switch"] = state
    return jsonable(out)


def _coord_attr(coord, name):
    obj = coord
    for part in name.split("."):
        obj = obj.get(part, _MISSING) if isinstance(obj, dict) else getattr(obj, part, _MISSING)
    return obj


def coord_state(coord) -> dict:
    return {name: jsonable(_coord_attr(coord, name)) for name in COORD_ATTRS}


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
    for mod in (sensor_mod, binary_mod, switch_mod, number_mod):
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
    "native_min_value", "native_max_value", "native_step", "mode",
)


def mask_version(rec: dict) -> dict:
    """Ersetzt die Integrationsversion im Protokoll durch einen Platzhalter."""
    return json.loads(json.dumps(rec, ensure_ascii=False).replace(const.VERSION, "<version>"))


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


async def ws_call(handler, hass, msg_id: int = 1, **msg) -> list:
    """WS-Handler mit einer frischen Verbindung aufrufen; liefert die gesendeten Nachrichten."""
    conn = ha_stubs.ActiveConnection()
    await handler(hass, conn, {"id": msg_id, **msg})
    return conn.sent


async def ws_status(hass, entry_id) -> list:
    return jsonable(await ws_call(integration._ws_get_status, hass, entry_id=entry_id))


def make_coord(hass, prefix: str = "a", stored: dict | None = None):
    """Coordinator für `entry_<prefix>` anlegen und in `hass.data` eintragen; `stored` als Speicherstand."""
    entry = FakeEntry(f"entry_{prefix}", entry_data(prefix))
    if stored is not None:
        put_store(hass, f"{const.DOMAIN}_{entry.entry_id}", stored)
    coord = coordinator_mod.SolakonCoordinator(hass, entry)
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = coord
    return coord


@dataclass(eq=False)
class FakeMember:
    """Attrappe für `grid_group.Member`; zählt SOC-Lesungen."""

    member_id: str
    grid_sensor: str = "sensor.grid"
    regulating: bool = True
    discharge: bool = True
    surplus_active: bool = False
    charge_session: str = "none"
    allocated_power: float | None = None
    soc: float | None = 50.0
    limit: float = 800.0
    zone3: float = 20.0
    ac_target: float = 90.0
    capacity: dict = field(default_factory=dict)
    actual: float = 0.0
    setpoint: float = 0.0
    soc_reads: int = 0

    def in_discharge_pool(self):
        return self.regulating and self.discharge

    def soc_reading(self):
        self.soc_reads += 1
        return self.soc

    def hard_limit(self):
        return self.limit

    def zone3_limit(self):
        return self.zone3

    def ac_soc_target(self):
        return self.ac_target

    def capacity_kwh(self, entity_id):
        return self.capacity.get(entity_id)

    def actual_power(self):
        return self.actual

    def output_setpoint(self):
        return self.setpoint


def hass_with_members(*members) -> FakeHass:
    """FakeHass, dessen `hass.data[DOMAIN]` die Mitglieder nach `member_id` hält."""
    hass = FakeHass("de")
    hass.data[const.DOMAIN] = {m.member_id: m for m in members}
    return hass
