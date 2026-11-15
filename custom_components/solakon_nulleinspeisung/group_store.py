"""Gespeicherter Zustand der Netzgruppen: Verteilungseinstellungen, `soc_switch`-Zustand und Gruppennummer je Netzsensor."""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from . import runtime
from .const import CAPACITY_KEY, CONF_GRID_SENSOR, DIST_DEFAULTS, DIST_INST_FIELDS, DIST_SCHEMA, DOMAIN
from .grid_group import NetGroup
from .i18n import translate
from .migrations import SolakonDistStore, SolakonSocSwitchStore
from .schema import InvalidSettings, check, notify_reset, sanitize

STORAGE_VERSION_DIST = 2
STORAGE_KEY_DIST     = f"{DOMAIN}_distribution"

STORAGE_VERSION_SOC_SWITCH = 2
STORAGE_KEY_SOC_SWITCH     = f"{DOMAIN}_soc_switch_state"

STORAGE_VERSION_NUMBERS = 1
STORAGE_KEY_NUMBERS     = f"{DOMAIN}_group_numbers"

def _soc_switch_group_state(stored: dict) -> dict:
    """Laufzeitzustand einer Netzgruppe im Modus `soc_switch` aus dem gespeicherten Stand."""
    return {
        "active_id": stored.get("active_id"),
        "start_soc": stored.get("start_soc"),
        "was_zone0": bool(stored.get("was_zone0", False)),
    }


class StoredGroup:
    """Zustand der Netzgruppe `grid_sensor` im Gruppenspeicher, gelesen bei jedem Aufruf (`GroupState`)."""

    def __init__(self, store: GroupStore, grid_sensor: str) -> None:
        self._store = store
        self._grid_sensor = grid_sensor
        self._fresh = _soc_switch_group_state({})

    def dist(self) -> dict:
        """Verteilung der Gruppe mit Defaults."""
        return self._store.dist_view(self._grid_sensor)

    def dist_rev(self) -> int:
        """Revision der Verteilung der Gruppe."""
        return self._store.dist_rev(self._grid_sensor)

    def soc_switch(self) -> dict:
        """Gespeicherter `soc_switch`-Zustand; ohne Stand ein neuer, den erst `soc_switch_changed` übernimmt."""
        return self._store.soc_switch.get(self._grid_sensor, self._fresh)

    def soc_switch_changed(self, state: dict) -> None:
        """Geänderten `soc_switch`-Zustand in den Gruppenspeicher übernehmen."""
        self._store.soc_switch_changed(self._grid_sensor, state)


def configured_members(hass: Any, grid_sensor: str) -> int:
    """Anzahl der Config-Entries am Netzsensor, geladen oder nicht."""
    return sum(1 for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_GRID_SENSOR, "") == grid_sensor)


def store_for(hass: Any) -> GroupStore | None:
    """Geladener Speicher aus dem Laufzeitzustand, sonst None; nur für Aufrufer, die „nicht bereit“ selbst behandeln."""
    rt = runtime.peek(hass)
    return None if rt is None else rt.store


def require_store(hass: Any) -> GroupStore:
    """Geladener Speicher aus dem Laufzeitzustand; RuntimeError, wenn er fehlt.

    Der Speicher lebt, solange mindestens eine Instanz geladen ist (`async_load` im Setup,
    Abräumen mit der letzten entladenen Instanz). Aufrufer außerhalb dieser Spanne laden ihn selbst.
    """
    store = store_for(hass)
    if store is None:
        raise RuntimeError("Solakon: Gruppenspeicher nicht geladen")
    return store


class GroupStore:
    """Verteilung, `soc_switch`-Zustand und Gruppennummer je Netzsensor, auch für Gruppen ohne laufende Instanz,
    dazu das Register der Netzgruppen.

    Führende Stelle der Verteilung: Netzgruppen lesen sie und den `soc_switch`-Zustand über `StoredGroup`.
    Ohne HA-Store (`None`) wird nur gehalten, nicht gespeichert.
    """

    def __init__(
        self, hass: Any, dist_store: Store | None = None, soc_switch_store: Store | None = None,
        dist: dict[str, dict] | None = None, soc_switch: dict[str, dict] | None = None,
        numbers_store: Store | None = None, numbers: dict[str, int] | None = None,
    ) -> None:
        self.hass = hass
        self._dist_store = dist_store
        self._soc_switch_store = soc_switch_store
        self._numbers_store = numbers_store
        self.dist: dict[str, dict] = {} if dist is None else dist
        self.soc_switch: dict[str, dict] = {} if soc_switch is None else soc_switch
        self.numbers: dict[str, int] = {} if numbers is None else numbers
        self._dist_revs: dict[str, int] = {}
        self._dist_listeners: dict[str, list[Callable[[], None]]] = {}
        self._groups: dict[str, NetGroup] = {}

    def group(self, grid_sensor: str) -> NetGroup:
        """Netzgruppe zum Netzsensor aus dem Register, bei Bedarf mit ihrem gespeicherten Zustand angelegt."""
        if (group := self._groups.get(grid_sensor)) is None:
            group = self._groups[grid_sensor] = NetGroup(self.hass, grid_sensor, StoredGroup(self, grid_sensor))
        return group

    def dist_view(self, grid_sensor: str) -> dict:
        """Verteilung einer Gruppe, mit Defaults aufgefüllt."""
        return {**DIST_DEFAULTS, **self.dist.get(grid_sensor, {})}

    def dist_rev(self, grid_sensor: str) -> int:
        """Revision der Verteilung einer Gruppe: Zahl der Speicherungen seit dem Laden."""
        return self._dist_revs.get(grid_sensor, 0)

    async def save_dist(self, grid_sensor: str, changes: dict) -> None:
        """Geänderte Verteilungsfelder einer Gruppe prüfen und in ihre Verteilung übernehmen.

        Danach steigt die Revision und angemeldete Beobachter werden benachrichtigt.
        InvalidSettings, wenn eine Änderung das Schema verletzt; dann bleibt alles unverändert.
        """
        if findings := check(changes, DIST_SCHEMA, DIST_INST_FIELDS):
            raise InvalidSettings(findings)
        self.dist[grid_sensor] = {**self.dist.get(grid_sensor, {}), **changes}
        await self._commit_dist({grid_sensor})

    async def tidy_capacity(self) -> None:
        """Kapazitätssensoren der Verteilung den Config-Entries nachführen.

        Ein Schlüssel ohne Config-Entry entfällt. Liegt er in einer anderen Netzgruppe als der
        seines Eintrags, wandert er dorthin, sofern dort keiner gesetzt ist; sonst entfällt er.
        """
        owners = {e.entry_id: e.data.get(CONF_GRID_SENSOR, "") for e in self.hass.config_entries.async_entries(DOMAIN)}
        changed: set[str] = set()
        moved: dict[str, dict] = {}
        for grid_sensor, cfg in self.dist.items():
            for key in list(cfg):
                if (match := CAPACITY_KEY.fullmatch(key)) is None or owners.get(match[1]) == grid_sensor:
                    continue
                value = cfg.pop(key)
                changed.add(grid_sensor)
                if (target := owners.get(match[1])) is not None:
                    moved.setdefault(target, {})[key] = value
        for grid_sensor, values in moved.items():
            cfg = self.dist.setdefault(grid_sensor, {})
            for key, value in values.items():
                if not cfg.get(key):
                    cfg[key] = value
                    changed.add(grid_sensor)
        if changed:
            await self._commit_dist(changed)

    async def _commit_dist(self, grid_sensors: set[str]) -> None:
        """Verteilung speichern; je Gruppe Revision erhöhen und Beobachter benachrichtigen."""
        if self._dist_store is not None:
            await self._dist_store.async_save(self.dist)
        for grid_sensor in sorted(grid_sensors):
            self._dist_revs[grid_sensor] = self.dist_rev(grid_sensor) + 1
            for listener in list(self._dist_listeners.get(grid_sensor, ())):
                listener()

    def listen_dist(self, grid_sensor: str, listener: Callable[[], None]) -> Callable[[], None]:
        """`listener` nach jeder gespeicherten Verteilung der Gruppe aufrufen; gibt die Abmeldung zurück."""
        listeners = self._dist_listeners.setdefault(grid_sensor, [])
        listeners.append(listener)
        return lambda: listeners.remove(listener)

    async def group_number(self, grid_sensor: str) -> int:
        """Gruppennummer des Netzsensors; beim ersten Auftreten die nächste freie vergeben und speichern."""
        if grid_sensor not in self.numbers:
            self.numbers[grid_sensor] = max(self.numbers.values(), default=0) + 1
            if self._numbers_store is not None:
                await self._numbers_store.async_save(self.numbers)
        return self.numbers[grid_sensor]

    def soc_switch_changed(self, grid_sensor: str, state: dict) -> None:
        """`soc_switch`-Zustand einer Gruppe übernehmen, alle Gruppen nach 2 s speichern."""
        self.soc_switch[grid_sensor] = state
        if self._soc_switch_store is not None:
            snapshot = {gk: dict(st) for gk, st in self.soc_switch.items()}
            self._soc_switch_store.async_delay_save(lambda: snapshot, 2)

    async def async_write_pending(self) -> None:
        """Ausstehendes Speichern von Verteilung und `soc_switch`-Zustand sofort schreiben."""
        for store in (self._dist_store, self._soc_switch_store):
            if store is not None:
                await store.async_write_pending()

    def _sanitize_dist(self, stored: dict) -> dict:
        """Verteilung je Gruppe gegen DIST_SCHEMA prüfen; Zurückgesetztes melden und speichern."""
        groups = {}
        for grid, cfg in stored.items():
            groups[grid], reset = sanitize(cfg, DIST_SCHEMA, DIST_INST_FIELDS)
            if reset:
                scope = translate(self.hass.config.language, "dist_scope", grid=grid)
                notify_reset(self.hass, f"{DOMAIN}_dist_reset_{grid}", scope, reset)
        if groups != stored:
            self._dist_store.async_delay_save(lambda: groups, 0)
        return groups



async def _load_stores(hass: HomeAssistant) -> GroupStore:
    """Speicher mit den drei HA-Stores anlegen und laden; die Verteilung gegen DIST_SCHEMA bereinigt."""
    dist_store = SolakonDistStore(hass, STORAGE_VERSION_DIST, STORAGE_KEY_DIST)
    soc_switch_store = SolakonSocSwitchStore(hass, STORAGE_VERSION_SOC_SWITCH, STORAGE_KEY_SOC_SWITCH)
    numbers_store = Store(hass, STORAGE_VERSION_NUMBERS, STORAGE_KEY_NUMBERS)
    store = GroupStore(hass, dist_store, soc_switch_store, numbers_store=numbers_store)
    store.dist = store._sanitize_dist(await dist_store.async_load() or {})
    stored = await soc_switch_store.async_load() or {}
    store.soc_switch = {gk: _soc_switch_group_state(st) for gk, st in stored.items()}
    store.numbers = dict(await numbers_store.async_load() or {})
    return store


async def async_load(hass: HomeAssistant) -> GroupStore:
    """Speicher einmalig anlegen und alle Stores laden; weitere Aufrufer warten auf dasselbe Laden.

    Sichtbar über `store_for` erst nach erfolgreichem Laden. Scheitert es, erhalten alle
    Wartenden den Fehler, und der nächste Aufruf lädt neu.
    """
    rt = runtime.runtime(hass)
    if rt.store is not None:
        return rt.store
    if rt.loading is not None:
        return await rt.loading
    loading = rt.loading = asyncio.get_running_loop().create_future()
    try:
        store = await _load_stores(hass)
    except Exception as err:
        rt.loading = None
        loading.set_exception(err)
        loading.exception()
        raise
    rt.store, rt.loading = store, None
    loading.set_result(store)
    return store


async def async_remove(hass: HomeAssistant) -> None:
    """Alle Stores der Netzgruppen löschen."""
    await SolakonDistStore(hass, STORAGE_VERSION_DIST, STORAGE_KEY_DIST).async_remove()
    await Store(hass, STORAGE_VERSION_SOC_SWITCH, STORAGE_KEY_SOC_SWITCH).async_remove()
    await Store(hass, STORAGE_VERSION_NUMBERS, STORAGE_KEY_NUMBERS).async_remove()
