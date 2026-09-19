"""Gespeicherter Zustand der Netzgruppen: Verteilungseinstellungen und `soc_switch`-Zustand je Netzsensor."""
from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import CONF_GRID_SENSOR, DIST_DEFAULTS, DIST_INST_FIELDS, DIST_SCHEMA, DOMAIN
from .group import NetGroup
from .i18n import translate
from .schema import check, notify_reset, sanitize

STORAGE_VERSION_DIST = 2
STORAGE_KEY_DIST     = f"{DOMAIN}_distribution"

STORAGE_VERSION_SOC_SWITCH = 2
STORAGE_KEY_SOC_SWITCH     = f"{DOMAIN}_soc_switch_state"

# `hass.data`-Schlüssel dieses Moduls (ohne DOMAIN-Präfix), entfernt mit der letzten Instanz.
DATA_KEYS = ("group_store", "group_store_loaded", "groups")


class SolakonDistStore(Store):
    """Verteilungs-Store mit Schemamigration."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict
    ) -> dict:
        """Hebt Version 1 auf 2: flache Form verschachteln, Zwei-Feld-Modus auflösen."""
        if old_major_version >= 2 or not old_data:
            return old_data

        if "distribution_mode" in old_data or "global_max_power" in old_data:
            flat = _migrate_dist_mode(old_data)
            return {gk: dict(flat) for gk in _grid_groups(self.hass)}
        return {gk: _migrate_dist_mode(cfg) for gk, cfg in old_data.items()}


class SolakonSocSwitchStore(Store):
    """SOC-Switch-Store mit Schemamigration."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict
    ) -> dict:
        """Hebt Version 1 auf 2: der flache Zustand gilt für jede vorhandene Netzgruppe."""
        if old_major_version >= 2 or not old_data:
            return old_data
        return {gk: dict(old_data) for gk in _grid_groups(self.hass)}


def _grid_groups(hass: HomeAssistant) -> set[str]:
    """Netzsensoren aller Einträge, einer je Netzgruppe."""
    return {e.data.get(CONF_GRID_SENSOR, "") for e in hass.config_entries.async_entries(DOMAIN)}


def _soc_switch_group_state(stored: dict) -> dict:
    """Laufzeitzustand einer Netzgruppe im Modus `soc_switch` aus dem gespeicherten Stand."""
    return {
        "active_id": stored.get("active_id"),
        "start_soc": stored.get("start_soc"),
        "was_zone0": bool(stored.get("was_zone0", False)),
    }


def _migrate_dist_mode(cfg: dict) -> dict:
    """Bildet das alte `capacity_weighting`-Bool auf den Drei-Wert-`distribution_mode` ab."""
    if "capacity_weighting" not in cfg:
        return cfg
    migrated = dict(cfg)
    if migrated.pop("capacity_weighting", False):
        migrated["distribution_mode"] = "capacity"
    elif migrated.get("distribution_mode") == "weighted":
        migrated["distribution_mode"] = "soc"
    return migrated


class GroupStore:
    """Verteilung und `soc_switch`-Zustand je Netzsensor, auch für Gruppen ohne laufende Instanz.

    Ohne HA-Store (`None`) wird nur gehalten, nicht gespeichert.
    """

    def __init__(
        self, hass: Any, dist_store: Store | None = None, soc_switch_store: Store | None = None,
        dist: dict[str, dict] | None = None, soc_switch: dict[str, dict] | None = None,
    ) -> None:
        self.hass = hass
        self._dist_store = dist_store
        self._soc_switch_store = soc_switch_store
        self.dist: dict[str, dict] = {} if dist is None else dist
        self.soc_switch: dict[str, dict] = {} if soc_switch is None else soc_switch

    def dist_view(self, grid_sensor: str) -> dict:
        """Verteilung einer Gruppe, mit Defaults aufgefüllt."""
        return {**DIST_DEFAULTS, **self.dist.get(grid_sensor, {})}

    async def save_dist(self, grid_sensor: str, cfg: dict) -> list[dict]:
        """Verteilung einer Gruppe prüfen, speichern und der Netzgruppe übergeben; Befunde statt Speichern."""
        if findings := check(cfg, DIST_SCHEMA, DIST_INST_FIELDS):
            return findings
        self.dist[grid_sensor] = cfg
        await self._dist_store.async_save(self.dist)
        if (group := self.hass.data.get(f"{DOMAIN}_groups", {}).get(grid_sensor)) is not None:
            group.dist = cfg
        return []

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


def store_for(hass: Any) -> GroupStore | None:
    """Geladener Speicher aus `hass.data`, sonst None."""
    return hass.data.get(f"{DOMAIN}_group_store")


async def async_load(hass: HomeAssistant) -> GroupStore:
    """Speicher einmalig anlegen und beide Stores laden; weitere Aufrufer warten auf dasselbe Laden."""
    if (loaded := hass.data.get(f"{DOMAIN}_group_store_loaded")) is not None:
        await loaded.wait()
        return hass.data[f"{DOMAIN}_group_store"]
    loaded = hass.data[f"{DOMAIN}_group_store_loaded"] = asyncio.Event()
    dist_store = SolakonDistStore(hass, STORAGE_VERSION_DIST, STORAGE_KEY_DIST)
    soc_switch_store = SolakonSocSwitchStore(hass, STORAGE_VERSION_SOC_SWITCH, STORAGE_KEY_SOC_SWITCH)
    store = hass.data[f"{DOMAIN}_group_store"] = GroupStore(hass, dist_store, soc_switch_store)
    try:
        store.dist = store._sanitize_dist(await dist_store.async_load() or {})
        stored = await soc_switch_store.async_load() or {}
        store.soc_switch = {gk: _soc_switch_group_state(st) for gk, st in stored.items()}
    finally:
        loaded.set()
    return store


async def async_remove(hass: HomeAssistant) -> None:
    """Beide Stores der Netzgruppen löschen."""
    await SolakonDistStore(hass, STORAGE_VERSION_DIST, STORAGE_KEY_DIST).async_remove()
    await Store(hass, STORAGE_VERSION_SOC_SWITCH, STORAGE_KEY_SOC_SWITCH).async_remove()


def group_for(hass: Any, grid_sensor: str) -> NetGroup:
    """Netzgruppe zum Netzsensor aus dem Register, bei Bedarf mit ihrem gespeicherten Zustand angelegt."""
    groups = hass.data.setdefault(f"{DOMAIN}_groups", {})
    group = groups.get(grid_sensor)
    if group is None:
        store = store_for(hass)
        group = groups[grid_sensor] = NetGroup(hass, grid_sensor) if store is None else NetGroup(
            hass, grid_sensor,
            dist=store.dist.get(grid_sensor),
            soc_switch=store.soc_switch.get(grid_sensor),
            on_soc_switch_change=lambda state: store.soc_switch_changed(grid_sensor, state),
        )
    return group
