"""Timeout-Reset: Timer-Wechsel T ↔ T − 1 bei Countdown unter 120 oder fremdem Wert, höchstens einmal je Regelzyklus."""
from __future__ import annotations

import asyncio
import importlib

import pytest

from tests import harness as h

timeout_mod = importlib.import_module(h.PKG + ".timeout")


def _timeout(written: list[float], gesetzt: float = 3599.0, countdown_ok: bool = True, dauer: int = 3599):
    async def write(value):
        written.append(value)

    return timeout_mod.Timeout(write, lambda: gesetzt, lambda: countdown_ok, lambda: dauer)


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


@pytest.mark.parametrize("gesetzt, neu", [(300.0, 299.0), (299.0, 300.0)])
def test_timer_wechsel_zwischen_dauer_und_dauer_minus_eins(gesetzt, neu):
    written: list[float] = []
    asyncio.run(_timeout(written, gesetzt, dauer=300).reset_if_due(119))
    assert written == [neu]


@pytest.mark.parametrize("timer", [3000, None])
def test_fremder_timer_wert_wird_im_naechsten_zyklus_die_dauer(timer):
    written: list[float] = []
    t = _timeout(written, 3599.0, dauer=300)
    asyncio.run(t.reset_if_due(timer))
    asyncio.run(t.reset_if_due(timer))
    assert written == [300.0]


def test_eingestellter_timer_wert_ohne_faelligen_reset_bleibt():
    written: list[float] = []
    asyncio.run(_timeout(written, 299.0, dauer=300).reset_if_due(None))
    assert written == []
