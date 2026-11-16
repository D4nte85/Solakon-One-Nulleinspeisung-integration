"""Spielt alle Reproduktionsszenarien unter tests/repro/ ab.

Ein Szenario mit `offen: true` beschreibt einen noch nicht behobenen Fehler und muss
rot sein (strikt erwarteter Fehlschlag); wird es grün, ist `offen` zu entfernen.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests import repro

SZENARIEN = sorted((Path(__file__).resolve().parent / "repro").glob("*.yaml"))


@pytest.mark.parametrize("pfad", SZENARIEN, ids=[p.stem for p in SZENARIEN])
def test_repro(pfad):
    szenario = repro.lade(pfad)
    _, ergebnisse = repro.spiele(szenario)
    fehlend = [text for ok, text in ergebnisse if not ok]
    if szenario.get("offen"):
        assert fehlend, "als offen markiert, aber alle Erwartungen erfüllt — `offen` entfernen"
        pytest.xfail("offener Fehler: " + "; ".join(fehlend))
    assert not fehlend, "\n".join(fehlend)


def test_unbekanntes_flag_ist_ein_szenariofehler():
    szenario = {"titel": "x", "bezug": "x", "instanzen": [{"prefix": "a", "flags": {"cycle_activ": True}}],
                "schritte": [{"nach": 0}], "erwartet": []}
    with pytest.raises(repro.SzenarioFehler, match="cycle_activ"):
        repro.spec_aus(szenario)
