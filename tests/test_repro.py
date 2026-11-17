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


@pytest.mark.parametrize("szenario, falsch", [
    ({"titel": "x", "erwatet": []}, "erwatet"),
    ({"titel": "x", "instanzen": [{"prefix": "a", "folgt": 0}]}, "folgt"),
    ({"titel": "x", "verteilung": {"distributon_mode": "equal"}}, "distributon_mode"),
    ({"titel": "x", "verteilung_netz": {"sensor.grid_other": {"inst_a_kapazitaet": 2}}}, "inst_a_kapazitaet"),
    ({"titel": "x", "schritte": [{"nach": 0, "wer": "b"}]}, "'b'"),
])
def test_unbekanntes_feld_im_szenario_ist_ein_szenariofehler(szenario, falsch):
    with pytest.raises(repro.SzenarioFehler, match=falsch):
        repro.spec_aus(szenario)


@pytest.mark.parametrize("erwartung, falsch", [
    ({"schritt": 1, "zustant": {"cycle_active": True}}, "zustant"),
    ({"schritt": 1, "aufruf": {"entity": "a.leistung", "wer": 0}}, "wer"),
    ({"schritt": 1, "instanz": "z", "zustand": {"cycle_active": True}}, "'z'"),
])
def test_unbekanntes_feld_in_erwartung_ist_ein_szenariofehler(erwartung, falsch):
    rec, _ = repro.spiele({"titel": "x", "schritte": [{"nach": 0}], "erwartet": []})
    with pytest.raises(repro.SzenarioFehler, match=falsch):
        repro.pruefe(erwartung, rec)
