"""Integrationsweiter Laufzeitzustand: ein Objekt unter `hass.data`, entfernt mit der letzten Instanz."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .const import DOMAIN

if TYPE_CHECKING:
    from .group_store import GroupStore
    from .number import Carriers

RUNTIME_KEY = f"{DOMAIN}_runtime"


@dataclass
class Runtime:
    """Gruppenspeicher und sein laufendes Laden, Träger-Verwaltung des Gesamtlimits, Panel-Merker.

    `store` ist erst nach erfolgreichem Laden gesetzt; `loading` nur, solange es läuft.
    """

    store: GroupStore | None = None
    loading: asyncio.Future | None = None
    carriers: Carriers | None = None
    panel_registered: bool = False


def runtime(hass: Any) -> Runtime:
    """Laufzeitzustand aus `hass.data`, bei Bedarf angelegt."""
    return hass.data.setdefault(RUNTIME_KEY, Runtime())


def peek(hass: Any) -> Runtime | None:
    """Laufzeitzustand aus `hass.data`, ohne ihn anzulegen."""
    return hass.data.get(RUNTIME_KEY)


def drop(hass: Any) -> None:
    """Laufzeitzustand aus `hass.data` entfernen."""
    hass.data.pop(RUNTIME_KEY, None)
