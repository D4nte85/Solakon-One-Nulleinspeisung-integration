"""Settings-Änderung unter dem Lock: ein laufender Regelzyklus sieht keine neuen Settings."""
from __future__ import annotations

import asyncio

from tests import harness as h
from tests.test_status_texts import _coord

C = h.const


def test_aenderung_wartet_auf_laufenden_regelzyklus():
    _, coord = _coord("de")

    async def run():
        await coord._lock.acquire()
        task = asyncio.ensure_future(coord.async_update_settings({C.S_TOLERANCE: 42}))
        await asyncio.sleep(0)
        waehrend = coord.settings[C.S_TOLERANCE]
        coord._lock.release()
        await task
        return waehrend, coord.settings[C.S_TOLERANCE]

    waehrend, danach = asyncio.run(run())
    assert waehrend == C.SETTINGS_DEFAULTS[C.S_TOLERANCE]
    assert danach == 42


def test_ruhe_endet_nur_bei_geaendertem_ruhemodus():
    _, coord = _coord("de")
    coord.resting = True
    asyncio.run(coord.async_update_settings({C.S_REST_IN_DISCHARGE: False}))
    assert coord.resting is True
    asyncio.run(coord.async_update_settings({C.S_REST_IN_DISCHARGE: True}))
    assert coord.resting is False


def test_integral_nur_bei_umgeschaltetem_entlade_pi_auf_null():
    _, coord = _coord("de")
    an = C.SETTINGS_DEFAULTS[C.S_PI_ENABLED]
    coord.pi.integral = 12.5
    asyncio.run(coord.async_update_settings({C.S_PI_ENABLED: an}))
    assert coord.pi.integral == 12.5
    asyncio.run(coord.async_update_settings({C.S_PI_ENABLED: not an}))
    assert coord.pi.integral == 0
