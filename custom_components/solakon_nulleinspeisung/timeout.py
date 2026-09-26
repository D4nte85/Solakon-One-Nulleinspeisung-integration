"""Timeout des Geräts: Timer-Toggle 3598↔3599 und Timeout-Reset im Regelzyklus."""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable


class Timeout:
    """Timer-Toggle mit Merker, ob im laufenden Regelzyklus schon getoggelt wurde.

    `write` schreibt den Timer-Wert, `read_set` liest den gesetzten Timer (Default 3599),
    `countdown_ok` meldet, ob der Countdown-Sensor verfügbar ist.
    """

    def __init__(
        self, write: Callable[[float], Awaitable[Any]], read_set: Callable[[], float],
        countdown_ok: Callable[[], bool],
    ) -> None:
        self._write = write
        self._read_set = read_set
        self._countdown_ok = countdown_ok
        self.toggled_in_cycle: bool = False

    def start_cycle(self) -> None:
        """Merker zu Beginn des Regelzyklus zurücksetzen."""
        self.toggled_in_cycle = False

    async def toggle(self) -> None:
        """Timer-Wechsel 3598↔3599 — erzwingt sichere Modus-Übernahme."""
        current = self._read_set()
        new_val = 3598.0 if current >= 3599 else 3599.0
        await self._write(new_val)
        self.toggled_in_cycle = True
        await asyncio.sleep(1)

    async def reset_if_due(self, timer_val: float) -> None:
        """Timeout-Reset: toggeln bei Countdown unter 120, wenn in diesem Zyklus noch nicht getoggelt."""
        if timer_val < 120 and not self.toggled_in_cycle and self._countdown_ok():
            await self.toggle()
