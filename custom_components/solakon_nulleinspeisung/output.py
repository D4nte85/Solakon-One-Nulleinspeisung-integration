"""Ausgangsleistung: Schreiben, Warten auf die Ist-Leistung, Nullbestätigung, Stillstandserkennung."""
from __future__ import annotations

import asyncio
import enum
import logging
import time
from typing import Any, Awaitable, Callable, NamedTuple

from .const import (
    DEVICE_MAX_POWER, OUTPUT_STALL_SECONDS, OUTPUT_STALL_DEVIATION,
    S_WAIT_TIME, S_SELF_ADJUST, S_SELF_ADJUST_TOL,
)
from .pi import clamp as _clamp

_LOGGER = logging.getLogger(__name__)


class Actual(NamedTuple):
    """Schnappschuss des Ist-Sensors.

    `power`: Ist-Leistung in W, 0 ohne Zahl. `ok`: State vorhanden und nicht
    unknown/unavailable. `updated`: `last_updated` als Unix-Zeit, None ohne State.
    """

    power: float
    ok: bool
    updated: float | None


class Stall(enum.Enum):
    """Urteil der Stillstandserkennung."""

    REWRITTEN = "rewritten"
    RECOVERY = "recovery"


class Output:
    """Ausgangsleistung eines Geräts mit Schreibzeitpunkt und Stillstandszählern.

    `write` schreibt den Sollwert (Guard beim Aufrufer), `read_actual` liefert einen
    frischen `Actual`, `settings` die aktuellen Einstellungen, `warn(key, params)`
    meldet eine Schreibwarnung in die Fehlerkette.
    """

    def __init__(
        self,
        write: Callable[[float], Awaitable[Any]],
        read_actual: Callable[[], Actual],
        settings: Callable[[], dict],
        warn: Callable[[str, dict], None],
    ) -> None:
        self._write = write
        self._read = read_actual
        self._settings = settings
        self._warn = warn
        self.last_ts: float = time.time()
        self.stall_actions: int = 0
        self.stall_last_ts: float = 0.0

    # ── Lesen: Ist-Leistung ──────────────────────────────────────────────────

    def _vs(self, target: float, ac_charge_mode: bool = False) -> tuple[float, float]:
        """(Ist-Leistung in W, Betrag ihrer Abweichung vom Sollwert).

        Im AC-Lademodus meldet der Ist-Sensor negativ; verglichen wird dann gegen `-target`.
        """
        actual = self._read().power
        return actual, abs(actual - (-target if ac_charge_mode else target))

    def _polled_since_write(self) -> bool:
        """True, wenn der Ist-Sensor seit dem letzten Schreibbefehl neu gepollt hat."""
        updated = self._read().updated
        return updated is not None and updated >= self.last_ts

    # ── Schreiben: Ausgangsleistung ──────────────────────────────────────────

    async def set(self, value: float) -> None:
        """Ausgangsleistung setzen, geklemmt auf 0 bis DEVICE_MAX_POWER.

        `last_ts` wird auch gesetzt, wenn der Guard den Schreibbefehl unterdrückt.
        """
        await self._write(_clamp(round(value), 0, DEVICE_MAX_POWER))
        self.last_ts = time.time()

    async def set_and_wait(self, value: float, ac_charge_mode: bool = False) -> None:
        """Ausgangsleistung setzen und auf reale Konvergenz warten (_wait_for_target).

        `number.set_value` läuft ohne `blocking=True`: der Aufruf kehrt zurück,
        sobald der Service-Call eingereiht ist, nicht wenn CONF_ACTIVE_POWER den
        neuen Wert zeigt. Ein unmittelbar folgender Reread im selben Zyklus sieht
        ohne diesen Wait noch den alten Wert.

        Nullung (`value == 0`) gilt als sicherheitskritisch und wird zusätzlich
        über `_confirm_zero()` verifiziert und bei Bedarf erneut geschrieben.
        """
        value = _clamp(value, 0, DEVICE_MAX_POWER)
        await self.set(value)
        await self._wait_for_target(value, ac_charge_mode=ac_charge_mode)
        if value == 0:
            await self._confirm_zero(ac_charge_mode)

    async def _wait_for_target(self, target: float, ac_charge_mode: bool = False) -> None:
        """Wartet, bis die Ist-Leistung den Zielwert erreicht, höchstens `S_WAIT_TIME` Sekunden.

        Ohne `S_SELF_ADJUST` wird die volle Wartezeit abgewartet.
        """
        settings = self._settings()
        wait_max = float(settings[S_WAIT_TIME])

        if not settings[S_SELF_ADJUST]:
            await asyncio.sleep(wait_max)
            return

        tolerance = float(settings[S_SELF_ADJUST_TOL])
        compare_target = -target if ac_charge_mode else target

        await asyncio.sleep(1.0)

        start = time.monotonic()
        remaining = wait_max - 1.0

        while remaining > 0:
            actual, deviation = self._vs(target, ac_charge_mode)
            if deviation <= tolerance:
                _LOGGER.debug(
                    "Solakon: Zielwert erreicht (actual=%.0f, target=%.0f) nach %.1fs",
                    actual, compare_target, time.monotonic() - start,
                )
                return
            await asyncio.sleep(min(1.0, remaining))
            remaining = wait_max - (time.monotonic() - start)

        _LOGGER.debug(
            "Solakon: Max-Wartezeit (%.0fs), actual=%.0f, target=%.0f",
            wait_max, self._read().power, compare_target,
        )

    async def _confirm_zero(self, ac_charge_mode: bool, max_retries: int = 2) -> None:
        """Bestätigt, dass die Ausgangsleistung real auf 0 gefallen ist, auch ohne S_SELF_ADJUST.

        Schreibt bei fehlender Konvergenz bis zu `max_retries`-mal erneut und meldet
        danach eine Schreibwarnung in der Fehlerkette. CONF_ACTUAL_SENSOR pollt in einem
        fremden Intervall (1–300 s): ein Wert, der älter ist als der letzte Schreibbefehl,
        belegt weder Erfolg noch Fehlschlag; dann unterbleibt nur die Warnung, Schreib-
        und Retry-Verhalten bleibt gleich.
        """
        if not self._read().ok:
            return  # kein Sensor zur Verifikation verfügbar — nichts zu prüfen

        tolerance = float(self._settings()[S_SELF_ADJUST_TOL])

        for attempt in range(max_retries):
            actual, deviation = self._vs(0)
            if deviation <= tolerance:
                return
            if self._polled_since_write():
                _LOGGER.warning(
                    "Solakon: Output-Nullung nicht bestätigt (Ist: %.0f W) — erneuter Schreibversuch %d/%d",
                    actual, attempt + 1, max_retries,
                )
            await self.set(0)
            await self._wait_for_target(0, ac_charge_mode=ac_charge_mode)

        actual, deviation = self._vs(0)
        if deviation > tolerance and self._polled_since_write():
            self._warn("warn_output_zero_unconfirmed", {"attempts": max_retries, "actual": actual})

    # ── Schreiben: Stillstand ────────────────────────────────────────────────

    def reset_stall(self) -> None:
        """Stillstandszähler zurücksetzen: der Ausgang folgt dem Limit oder ist nicht prüfbar."""
        self.stall_actions = 0
        self.stall_last_ts = 0.0

    async def check_stall(self, limit: float) -> tuple[Stall, float] | None:
        """Erkennt einen Wechselrichter, der dem Limit nicht folgt; (Urteil, Ist-Leistung) oder None.

        Kriterium: Abweichung über `OUTPUT_STALL_DEVIATION` bei einem Ist-Wert, dessen
        `last_updated` seit `OUTPUT_STALL_SECONDS` nicht vorrückt. Erster Treffer schreibt
        den Sollwert neu (`REWRITTEN`), jeder weitere liefert `RECOVERY`. Mindestabstand
        zweier Urteile: `OUTPUT_STALL_SECONDS`.
        """
        actual = self._read()
        if limit <= 0 or not actual.ok:
            self.reset_stall()
            return None

        if abs(actual.power - limit) <= limit * OUTPUT_STALL_DEVIATION:
            self.reset_stall()
            return None

        if actual.updated is None:
            self.reset_stall()
            return None

        now = time.time()
        if now - actual.updated < OUTPUT_STALL_SECONDS:
            return None
        if self.stall_last_ts and now - self.stall_last_ts < OUTPUT_STALL_SECONDS:
            return None

        self.stall_last_ts = now
        self.stall_actions += 1

        if self.stall_actions == 1:
            _LOGGER.warning(
                "Solakon: Ausgang %.0f W folgt Limit %.0f W nicht (unverändert seit %.0f s) "
                "— Sollwert wird neu geschrieben",
                actual.power, limit, now - actual.updated,
            )
            await self.set(limit)
            return Stall.REWRITTEN, actual.power
        return Stall.RECOVERY, actual.power
