"""Ausgangsleistung: Warten auf die Ist-Leistung nach einem Schreibbefehl."""
from __future__ import annotations

import asyncio
import importlib

import pytest

from tests import harness as h

output_mod = importlib.import_module(h.PKG + ".output")


def _output(written: list[float]):
    async def write(value):
        written.append(value)

    actual = output_mod.Actual(power=500.0, ok=True, updated=h.CLOCK.now)
    return output_mod.Output(write, lambda: actual, lambda key, params: None)


@pytest.mark.parametrize("self_adjust", [True, False])
def test_wartezeit_null_wartet_nicht(self_adjust):
    written: list[float] = []
    out = _output(written)
    out.begin_cycle(0, self_adjust, 2)
    start = h.CLOCK.now
    asyncio.run(out.set_and_wait(100))
    assert written == [100]
    assert h.CLOCK.now == start



def test_adaptive_wartezeit_wartet_hoechstens_die_wartezeit():
    written: list[float] = []
    out = _output(written)
    out.begin_cycle(3, True, 2)
    start = h.CLOCK.now
    asyncio.run(out.set_and_wait(100))
    assert h.CLOCK.now - start == pytest.approx(3.0)
