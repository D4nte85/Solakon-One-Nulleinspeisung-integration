"""AC-Laden im rückgekoppelten Streckensimulator: Verhalten des AC-PI gegen das gemessene Gerät."""
from __future__ import annotations

import importlib

import pytest

from tests import harness as h
from tests.strecke_ac import Geraet, bewertung, simulieren, stufen

pi = importlib.import_module(h.PKG + ".pi")

OFFSET = -50.0
TOLERANZ = 15.0
LIMIT = 800.0
# Hauslast je Abschnitt (ab Sekunde, W); nötige Ladeleistung = Offset − Hauslast
HAUSLAST = ((0, -600.0), (60, -300.0), (120, -800.0), (180, -150.0), (240, -500.0))


def _ac_pi(p_factor: float, i_factor: float = 0.0):
    c = pi.PIController()

    def regler(netz, ist, sollwert):
        if pi.gate_ac(netz, OFFSET, TOLERANZ) != pi.STEP:
            c.decay()
            return None
        return c.calculate(netz, sollwert, OFFSET, LIMIT, p_factor, i_factor, ac_charge_mode=True)
    return regler


def _abschnitte(regler):
    verlauf = simulieren(regler, stufen(*HAUSLAST), HAUSLAST[-1][0] + 60)
    return [bewertung(verlauf, OFFSET - last, ab, ab + 60) for ab, last in HAUSLAST]


def test_geraet_rampe_und_schneller_anlauf():
    g = Geraet(seed=0, totzone=0.0)
    g.schreiben(0.0, 600.0)
    punkte = {}
    for n in range(300):
        t = round(n * 0.1, 3)
        g.schritt(t)
        punkte[t] = g.leistung
    assert punkte[1.9] == 0.0                              # Totzeit
    assert punkte[4.2] == pytest.approx(165.0, abs=8)      # schneller Anlauf bis ~160 W
    assert punkte[14.2] - punkte[9.2] == pytest.approx(170.0, abs=5)  # danach 34 W/s


def test_geraet_senken_als_sprung():
    g = Geraet(seed=0, totzone=0.0)
    g.leistung = 500.0
    g._ziel = 500.0
    g.schreiben(0.0, 200.0)
    for n in range(25):
        g.schritt(round(n * 0.1, 3))
    assert g.leistung == pytest.approx(200.0 - 15.0 + 34.0 * 0.4, abs=4)


def test_ac_pi_klein_ueberschwingt_nicht_ist_aber_langsam():
    ergebnis = _abschnitte(_ac_pi(0.3))
    assert max(e["ueberschwingen"] for e in ergebnis) < 40
    assert ergebnis[0]["einschwingzeit"] > 30


def test_ac_pi_mit_p_1_ueberschwingt():
    ergebnis = _abschnitte(_ac_pi(1.0))
    assert ergebnis[0]["ueberschwingen"] > 150
