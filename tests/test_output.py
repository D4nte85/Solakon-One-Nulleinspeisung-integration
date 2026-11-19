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
    return output_mod.Output(write, lambda: actual, lambda: 0.0, lambda key, params: None)


@pytest.mark.parametrize("self_adjust", [True, False])
def test_wartezeit_null_wartet_nicht(self_adjust):
    written: list[float] = []
    out = _output(written)
    out.begin_cycle(0, self_adjust, 2)
    start = h.CLOCK.now
    asyncio.run(out.set_and_wait(100))
    assert written == [100]
    assert h.CLOCK.now == pytest.approx(start, abs=1e-3)



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

    return output_mod.Output(write, ist, lambda: 0.0, lambda key, params: (warnings if warnings is not None else []).append(key))


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


def test_bewegter_ist_wert_beendet_die_episode():
    """Rückt der Ist-Wert nach dem Neuschreiben vor, beginnt das nächste Einfrieren wieder mit REWRITTEN."""
    written: list[float] = []
    ist = Ist(100.0, True, h.CLOCK.now - STALL_S)
    out = _output_mit(ist, written)
    assert asyncio.run(out.check_stall(400.0)) == (output_mod.Stall.REWRITTEN, 100.0)
    h.CLOCK.now += 60
    ist.power, ist.updated = 150.0, h.CLOCK.now
    assert asyncio.run(out.check_stall(400.0)) is None
    assert (out.stall_actions, out.stall_last_ts) == (0, 0.0)
    h.CLOCK.now += STALL_S
    assert asyncio.run(out.check_stall(400.0)) == (output_mod.Stall.REWRITTEN, 150.0)
    assert written == [400, 400] and out.stall_actions == 1

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


@pytest.mark.parametrize("beleg, geschrieben, warnung", [
    (True, [0, 0, 0], ["warn_output_zero_unconfirmed"]),
    (False, [0], []),
])
def test_nullung_nicht_bestaetigt_schreibt_nur_mit_beleg_neu(beleg, geschrieben, warnung):
    """Beleg ist eine Meldung ab `OUTPUT_ZERO_REACTION` nach dem Schreibbefehl (`last_reported`), auch wenn der Wert seit langem steht."""
    written: list[float] = []
    warnings: list = []
    ist = Ist(300.0, True, h.CLOCK.now - 1000)
    out = _output_mit(ist, written, warnings)
    out.begin_cycle(0, False, 2)
    ist.reported = h.CLOCK.now + (1000 if beleg else -1000)
    asyncio.run(out.set_and_wait(0))
    assert written == geschrieben
    assert warnings == warnung


def test_nullung_meldung_vor_der_reaktionszeit_ist_kein_beleg():
    """Die Meldung aus dem Refresh direkt nach dem Schreiben zeigt den alten Wert, der Poll 6 s danach 0 W."""
    written: list[float] = []
    warnings: list = []
    start = h.CLOCK.now

    def ist():
        if h.CLOCK.now >= start + 6:
            return output_mod.Actual(0.0, True, start + 6, start + 6)
        return output_mod.Actual(300.0, True, start - 1000, start + 0.5)

    out = output_mod.Output(lambda v: _schreibe(written, v), ist, lambda: 0.0,
                            lambda key, params: warnings.append(key))
    out.begin_cycle(4, True, 2)
    asyncio.run(out.set_and_wait(0))
    assert written == [0]
    assert warnings == []
    assert h.CLOCK.now - start == pytest.approx(6.0, abs=1.0)


async def _schreibe(written: list[float], value: float) -> None:
    written.append(value)


def test_nullung_verlorener_schreibbefehl_wird_nachgeschrieben():
    """Zeigt der Sollwert nach der Reaktionszeit nicht 0, wird ohne Meldung des Ist-Sensors neu geschrieben."""
    written: list[float] = []
    warnings: list = []
    ist = Ist(300.0, True, h.CLOCK.now - 1000, h.CLOCK.now - 1000)

    async def write(value):
        written.append(value)

    out = output_mod.Output(write, ist, lambda: 300.0, lambda key, params: warnings.append(key))
    out.begin_cycle(0, False, 2)
    asyncio.run(out.set_and_wait(0))
    assert written == [0, 0, 0]
    assert warnings == ["warn_output_zero_unconfirmed"]


def test_nullung_unterdrueckter_schreibbefehl_ist_kein_verlust():
    written: list[float] = []
    ist = Ist(300.0, True, h.CLOCK.now - 1000, h.CLOCK.now - 1000)

    async def write(value):
        written.append(value)
        return False

    out = output_mod.Output(write, ist, lambda: 300.0, lambda key, params: None)
    out.begin_cycle(0, False, 2)
    asyncio.run(out.set_and_wait(0))
    assert written == [0]


def test_meldeintervall_erst_mit_voller_reihe_gemessen():
    ist = Ist(0.0, True, h.CLOCK.now, h.CLOCK.now)
    out = _output_mit(ist, [])
    assert out.report_interval() == output_mod.OUTPUT_REPORT_INTERVAL_MAX
    for abstand in [10.0, 10.0, 0.5, 9.5, 10.0, 10.0, 10.0, 10.0]:
        ist.reported += abstand
        out.begin_cycle(0, False, 2)
    assert out.report_interval() == pytest.approx(10.0)
    ist.reported += 120.0
    out.begin_cycle(0, False, 2)
    assert out.report_interval() == output_mod.OUTPUT_REPORT_INTERVAL_MAX


def test_sollwert_zum_zeitpunkt_vor_spaeterem_schreibbefehl():
    """Gilt der Sollwert vor dem ersten Schreibbefehl nach `ts`, ohne späteren Schreibbefehl der gesetzte."""
    gesetzt = {"wert": 100.0}

    async def write(value):
        gesetzt["wert"] = value

    out = output_mod.Output(write, lambda: output_mod.Actual(0.0, True, None, None), lambda: gesetzt["wert"],
                            lambda key, params: None)
    vorher = h.CLOCK.now
    asyncio.run(out.set(300))
    zwischen = h.CLOCK.now
    asyncio.run(out.set(500))
    assert out.setpoint_at(vorher) == 100.0
    assert out.setpoint_at(zwischen) == 300.0
    assert out.setpoint_at(out.last_ts) == 500.0
