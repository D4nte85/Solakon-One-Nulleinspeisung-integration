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

    actual = output_mod.Actual(power=500.0, ok=True, updated=h.CLOCK.now, reported=h.CLOCK.now)
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


class Ist:
    """Veränderlicher Ist-Sensor für `Output`."""

    def __init__(self, power: float, ok: bool = True, updated: float | None = None,
                 reported: float | None = None):
        self.power, self.ok, self.updated = power, ok, updated
        self.reported = updated if reported is None else reported

    def __call__(self):
        return output_mod.Actual(self.power, self.ok, self.updated, self.reported)


def _output_mit(ist: Ist, written: list[float], warnings: list | None = None):
    async def write(value):
        written.append(value)

    return output_mod.Output(write, ist, lambda key, params: (warnings if warnings is not None else []).append(key))


STALL_S = h.const.OUTPUT_STALL_SECONDS


@pytest.mark.parametrize("limit, power, ok, alter", [
    (10.0, 500.0, True, STALL_S),        # Limit unter OUTPUT_STALL_MIN_LIMIT
    (400.0, 410.0, True, STALL_S),       # Abweichung bis OUTPUT_STALL_DEVIATION
    (400.0, 100.0, False, STALL_S),      # Ist-Sensor nicht verfügbar
])
def test_stillstand_nicht_pruefbar_setzt_zaehler_zurueck(limit, power, ok, alter):
    written: list[float] = []
    out = _output_mit(Ist(power, ok, h.CLOCK.now - alter), written)
    out.stall_actions, out.stall_last_ts = 3, 1.0
    assert asyncio.run(out.check_stall(limit)) is None
    assert (out.stall_actions, out.stall_last_ts, written) == (0, 0.0, [])


def test_stillstand_erst_nach_der_frist_dann_neu_schreiben_dann_ruhezustand():
    written: list[float] = []
    ist = Ist(100.0, True, h.CLOCK.now - STALL_S + 1)
    out = _output_mit(ist, written)
    assert asyncio.run(out.check_stall(400.0)) is None and written == []
    ist.updated = h.CLOCK.now - STALL_S
    assert asyncio.run(out.check_stall(400.0)) == (output_mod.Stall.REWRITTEN, 100.0)
    assert written == [400]
    h.CLOCK.now += STALL_S - 1
    assert asyncio.run(out.check_stall(400.0)) is None
    h.CLOCK.now += 1
    assert asyncio.run(out.check_stall(400.0)) == (output_mod.Stall.RECOVERY, 100.0)
    assert written == [400] and out.stall_actions == 2


def test_nullung_bestaetigt_ohne_neues_schreiben():
    written: list[float] = []
    out = _output_mit(Ist(0.0, True, h.CLOCK.now + 1), written)
    out.begin_cycle(0, False, 2)
    asyncio.run(out.set_and_wait(0))
    assert written == [0]


def test_nullung_ohne_ist_sensor_wird_nicht_geprueft():
    written: list[float] = []
    out = _output_mit(Ist(300.0, False, None), written)
    out.begin_cycle(0, False, 2)
    asyncio.run(out.set_and_wait(0))
    assert written == [0]


@pytest.mark.parametrize("frisch, warnung", [(True, ["warn_output_zero_unconfirmed"]), (False, [])])
def test_nullung_nicht_bestaetigt_schreibt_zweimal_neu(frisch, warnung):
    """Frisch ist eine Meldung nach dem Schreibbefehl (`last_reported`), auch wenn der Wert seit langem steht."""
    written: list[float] = []
    warnings: list = []
    ist = Ist(300.0, True, h.CLOCK.now - 1000)
    out = _output_mit(ist, written, warnings)
    out.begin_cycle(0, False, 2)
    ist.reported = h.CLOCK.now + (1 if frisch else -1000)
    asyncio.run(out.set_and_wait(0))
    assert written == [0, 0, 0]
    assert warnings == warnung
