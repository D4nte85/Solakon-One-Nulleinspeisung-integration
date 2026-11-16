"""Timeout-Reset: Timer-Wechsel bei Countdown unter 120, höchstens einmal je Regelzyklus."""
from __future__ import annotations

import asyncio
import importlib

import pytest

from tests import harness as h

timeout_mod = importlib.import_module(h.PKG + ".timeout")


def _timeout(written: list[float], gesetzt: float = 3599.0, countdown_ok: bool = True):
    async def write(value):
        written.append(value)

    return timeout_mod.Timeout(write, lambda: gesetzt, lambda: countdown_ok)


@pytest.mark.parametrize("gesetzt, neu", [(3599.0, 3598.0), (3598.0, 3599.0)])
def test_countdown_unter_120_wechselt_den_timer_einmal_je_zyklus(gesetzt, neu):
    written: list[float] = []
    t = _timeout(written, gesetzt)
    asyncio.run(t.reset_if_due(119))
    asyncio.run(t.reset_if_due(119))
    assert written == [neu] and t.toggled_in_cycle
    t.start_cycle()
    asyncio.run(t.reset_if_due(119))
    assert written == [neu, neu]


@pytest.mark.parametrize("timer, countdown_ok", [(120, True), (50, False)])
def test_kein_timer_wechsel(timer, countdown_ok):
    written: list[float] = []
    asyncio.run(_timeout(written, countdown_ok=countdown_ok).reset_if_due(timer))
    assert written == []


def test_countdown_ohne_zahl_ist_none():
    hass = h.FakeHass("de")
    cfg = h.entry_data("a")
    for key, _, _, _ in h.coordinator_mod.CORE_SENSORS:
        hass.states.set(cfg[key], "100")
    hass.states.set(cfg[h.const.CONF_TIMEOUT_COUNTDOWN], "abc")
    core = h.coordinator_mod.read_core(hass, cfg)
    assert not isinstance(core, str) and core.timer is None
