"""Fernsteuerungs-Timeout des Geräts: Timer-Toggle T ↔ T − 1 und Timeout-Reset im Regelzyklus."""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from .const import TIMEOUT_RESET_BELOW


class Timeout:
    """Timer-Toggle mit Merker, ob im laufenden Regelzyklus schon getoggelt wurde.

    `write` schreibt den Timer-Wert, `read_set` liest den gesetzten Timer,
    `countdown_ok` meldet, ob der Countdown-Sensor verfügbar ist, `duration` liefert die
    eingestellte Dauer T.
    """

    def __init__(
        self, write: Callable[[float], Awaitable[Any]], read_set: Callable[[], float],
        countdown_ok: Callable[[], bool], duration: Callable[[], int],
    ) -> None:
        self._write = write
        self._read_set = read_set
        self._countdown_ok = countdown_ok
        self._duration = duration
        self.toggled_in_cycle: bool = False

    def start_cycle(self) -> None:
        """Merker zu Beginn des Regelzyklus zurücksetzen."""
        self.toggled_in_cycle = False

    def _pair(self) -> tuple[float, float]:
        """Die zwei Werte des Timer-Toggles: T und T − 1."""
        high = float(self._duration())
        return high, high - 1

    async def toggle(self) -> None:
        """Timer-Wechsel T ↔ T − 1 — erzwingt sichere Modus-Übernahme; ein fremder Wert wird T."""
        high, low = self._pair()
        new_val = low if self._read_set() == high else high
        await self._write(new_val)
        self.toggled_in_cycle = True
        await asyncio.sleep(1)

    async def reset_if_due(self, timer_val: float | None) -> None:
        """Timeout-Reset, wenn in diesem Regelzyklus noch nicht getoggelt: bei Countdown unter
        TIMEOUT_RESET_BELOW oder wenn der gesetzte Timer weder T noch T − 1 ist. Ohne Countdown-Zahl
        (`timer_val` None) nur der zweite Grund."""
        if self.toggled_in_cycle:
            return
        due = timer_val is not None and timer_val < TIMEOUT_RESET_BELOW and self._countdown_ok()
        if due or self._read_set() not in self._pair():
            await self.toggle()
