"""Gespeicherter Zustand der Netzgruppen: Verteilungseinstellungen, `soc_switch`-Zustand und Gruppennummer je Netzsensor."""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import CONF_GRID_SENSOR, DIST_DEFAULTS, DIST_INST_FIELDS, DIST_SCHEMA, DOMAIN
from .grid_group import NetGroup
from .i18n import translate
from .migrations import SolakonDistStore, SolakonSocSwitchStore
from .schema import check, notify_reset, sanitize

STORAGE_VERSION_DIST = 2
STORAGE_KEY_DIST     = f"{DOMAIN}_distribution"

STORAGE_VERSION_SOC_SWITCH = 2
STORAGE_KEY_SOC_SWITCH     = f"{DOMAIN}_soc_switch_state"

STORAGE_VERSION_NUMBERS = 1
STORAGE_KEY_NUMBERS     = f"{DOMAIN}_group_numbers"

# `hass.data`-Schlüssel dieses Moduls (ohne DOMAIN-Präfix), entfernt mit der letzten Instanz.
DATA_KEYS = ("group_store", "group_store_loaded", "groups")


def _soc_switch_group_state(stored: dict) -> dict:
    """Laufzeitzustand einer Netzgruppe im Modus `soc_switch` aus dem gespeicherten Stand."""
    return {
        "active_id": stored.get("active_id"),
        "start_soc": stored.get("start_soc"),
        "was_zone0": bool(stored.get("was_zone0", False)),
    }


def configured_members(hass: Any, grid_sensor: str) -> int:
    """Anzahl der Config-Entries am Netzsensor, geladen oder nicht."""
    return sum(1 for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_GRID_SENSOR, "") == grid_sensor)


def store_for(hass: Any) -> GroupStore | None:
    """Geladener Speicher aus `hass.data`, sonst None; nur für Aufrufer, die „nicht bereit“ selbst behandeln."""
    return hass.data.get(f"{DOMAIN}_group_store")


def require_store(hass: Any) -> GroupStore:
    """Geladener Speicher aus `hass.data`; RuntimeError, wenn er fehlt.

    Der Speicher lebt, solange mindestens eine Instanz geladen ist (`async_load` im Setup,
    Abräumen mit der letzten entladenen Instanz). Aufrufer außerhalb dieser Spanne laden ihn selbst.
    """
    store = store_for(hass)
    if store is None:
        raise RuntimeError("Solakon: Gruppenspeicher nicht geladen")
    return store


def group_for(hass: Any, grid_sensor: str) -> NetGroup:
    """Netzgruppe zum Netzsensor aus dem Register, bei Bedarf mit ihrem gespeicherten Zustand angelegt."""
    groups = hass.data.setdefault(f"{DOMAIN}_groups", {})
    group = groups.get(grid_sensor)
    if group is None:
        store = require_store(hass)
        group = groups[grid_sensor] = NetGroup(
            hass, grid_sensor,
            dist=lambda: store.dist_view(grid_sensor),
            soc_switch=store.soc_switch.get(grid_sensor),
            on_soc_switch_change=lambda state: store.soc_switch_changed(grid_sensor, state),
            dist_rev=lambda: store.dist_rev(grid_sensor),
        )
    return group


class GroupStore:
    """Verteilung, `soc_switch`-Zustand und Gruppennummer je Netzsensor, auch für Gruppen ohne laufende Instanz.

    Führende Stelle der Verteilung: Netzgruppen lesen sie hier über `dist_view` und `dist_rev`.
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

    def dist_view(self, grid_sensor: str) -> dict:
        """Verteilung einer Gruppe, mit Defaults aufgefüllt."""
        return {**DIST_DEFAULTS, **self.dist.get(grid_sensor, {})}

    def dist_rev(self, grid_sensor: str) -> int:
        """Revision der Verteilung einer Gruppe: Zahl der Speicherungen seit dem Laden."""
        return self._dist_revs.get(grid_sensor, 0)

    async def save_dist(self, grid_sensor: str, changes: dict) -> list[dict]:
        """Geänderte Verteilungsfelder einer Gruppe prüfen und in ihre Verteilung übernehmen; Befunde statt Speichern.

        Danach steigt die Revision, die Mitglieder der Netzgruppe melden ihre Trigger neu an
        und stoßen einen Regelzyklus an, angemeldete Beobachter werden benachrichtigt.
        """
        if findings := check(changes, DIST_SCHEMA, DIST_INST_FIELDS):
            return findings
        self.dist[grid_sensor] = {**self.dist.get(grid_sensor, {}), **changes}
        if self._dist_store is not None:
            await self._dist_store.async_save(self.dist)
        self._dist_revs[grid_sensor] = self.dist_rev(grid_sensor) + 1
        for coord in group_for(self.hass, grid_sensor).members().values():
            coord.apply_group_change()
        for listener in list(self._dist_listeners.get(grid_sensor, ())):
            listener()
        return []

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



async def async_load(hass: HomeAssistant) -> GroupStore:
    """Speicher einmalig anlegen und alle Stores laden; weitere Aufrufer warten auf dasselbe Laden."""
    if (loaded := hass.data.get(f"{DOMAIN}_group_store_loaded")) is not None:
        await loaded.wait()
        return hass.data[f"{DOMAIN}_group_store"]
    loaded = hass.data[f"{DOMAIN}_group_store_loaded"] = asyncio.Event()
    dist_store = SolakonDistStore(hass, STORAGE_VERSION_DIST, STORAGE_KEY_DIST)
    soc_switch_store = SolakonSocSwitchStore(hass, STORAGE_VERSION_SOC_SWITCH, STORAGE_KEY_SOC_SWITCH)
    numbers_store = Store(hass, STORAGE_VERSION_NUMBERS, STORAGE_KEY_NUMBERS)
    store = hass.data[f"{DOMAIN}_group_store"] = GroupStore(
        hass, dist_store, soc_switch_store, numbers_store=numbers_store,
    )
    try:
        store.dist = store._sanitize_dist(await dist_store.async_load() or {})
        stored = await soc_switch_store.async_load() or {}
        store.soc_switch = {gk: _soc_switch_group_state(st) for gk, st in stored.items()}
        store.numbers = dict(await numbers_store.async_load() or {})
    finally:
        loaded.set()
    return store


async def async_remove(hass: HomeAssistant) -> None:
    """Alle Stores der Netzgruppen löschen."""
    await SolakonDistStore(hass, STORAGE_VERSION_DIST, STORAGE_KEY_DIST).async_remove()
    await Store(hass, STORAGE_VERSION_SOC_SWITCH, STORAGE_KEY_SOC_SWITCH).async_remove()
    await Store(hass, STORAGE_VERSION_NUMBERS, STORAGE_KEY_NUMBERS).async_remove()
