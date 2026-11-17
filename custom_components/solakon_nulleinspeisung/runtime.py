"""Integrationsweiter Laufzeitzustand: ein Objekt unter `hass.data`, entfernt mit dem letzten Halter.

Halter sind geladene Instanzen und das laufende Löschen eines Eintrags. `acquire` lädt den
Gruppenspeicher und trägt den Halter ein, `release` trägt ihn aus und räumt mit dem letzten
Halter Panel, Instanzliste und Laufzeitzustand ab.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .const import DOMAIN

if TYPE_CHECKING:
    from .group_store import GroupStore
    from .number import Carriers

RUNTIME_KEY = f"{DOMAIN}_runtime"


@dataclass
class Runtime:
    """Gruppenspeicher und sein laufendes Laden, Träger-Verwaltung des Gesamtlimits, Panel-Merker, Halter.

    `store` ist erst nach erfolgreichem Laden gesetzt; `loading` nur, solange es läuft.
    """

    store: GroupStore | None = None
    loading: asyncio.Future | None = None
    carriers: Carriers | None = None
    panel_registered: bool = False
    holders: set[str] = field(default_factory=set)


def runtime(hass: Any) -> Runtime:
    """Laufzeitzustand aus `hass.data`, bei Bedarf angelegt."""
    return hass.data.setdefault(RUNTIME_KEY, Runtime())


def peek(hass: Any) -> Runtime | None:
    """Laufzeitzustand aus `hass.data`, ohne ihn anzulegen."""
    return hass.data.get(RUNTIME_KEY)


def drop(hass: Any) -> None:
    """Laufzeitzustand aus `hass.data` entfernen."""
    hass.data.pop(RUNTIME_KEY, None)


async def acquire(hass: Any, holder: str) -> GroupStore:
    """Gruppenspeicher laden und `holder` eintragen; scheitert das Laden, wird nichts eingetragen."""
    from .group_store import async_load

    store = await async_load(hass)
    runtime(hass).holders.add(holder)
    return store


async def release(hass: Any, holder: str) -> None:
    """`holder` austragen und seine Träger abgeben; mit dem letzten Halter alles abräumen.

    Abräumen: ausstehendes Speichern schreiben, Panel entfernen, Instanzliste und Laufzeitzustand
    aus `hass.data` nehmen. Eine Instanz steht beim Aufruf nicht mehr in `hass.data[DOMAIN]`,
    weil die Netzgruppe ihre Mitglieder dort liest.
    """
    if (rt := peek(hass)) is None:
        return
    rt.holders.discard(holder)
    if rt.carriers is not None:
        await rt.carriers.release(holder)
    if rt.holders:
        return
    if rt.store is not None:
        await rt.store.async_write_pending()
    if rt.panel_registered:
        from homeassistant.components.frontend import async_remove_panel

        async_remove_panel(hass, DOMAIN)
    hass.data.pop(DOMAIN, None)
    drop(hass)
