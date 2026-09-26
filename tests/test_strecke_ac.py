"""AC-Laden im rückgekoppelten Streckensimulator: früherer AC-PI und Stellwertrechnung am gemessenen Gerät."""
from __future__ import annotations

import importlib

import pytest

from tests import harness as h
from tests.strecke_ac import Geraet, bewertung, simulieren, stufen

pi = importlib.import_module(h.PKG + ".pi")
ac = importlib.import_module(h.PKG + ".ac_charge")

OFFSET = -50.0
TOLERANZ = 15.0
LIMIT = 800.0
# Hauslast je Abschnitt (ab Sekunde, W); nötige Ladeleistung = Offset − Hauslast
HAUSLAST = ((0, -600.0), (60, -300.0), (120, -800.0), (180, -150.0), (240, -500.0))


def _ac_pi(p_factor: float, i_factor: float = 0.0):
    """Früherer AC-PI: Sollwert-Basis, Fehler Offset − Netz, Gate nur Toleranz."""
    c = pi.PIController()

    def regler(netz, ist, sollwert):
        if abs(netz - OFFSET) <= TOLERANZ:
            c.decay()
            return None
        return c.calculate(-netz, sollwert, -OFFSET, LIMIT, p_factor, i_factor)
    return regler


def _stellwert(netz, ist, sollwert):
    return ac.setpoint(netz, ist, ist, sollwert, OFFSET, LIMIT, 50.0, 1.0, TOLERANZ)


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


def test_stellwertrechnung_trifft_ohne_ueberschwingen():
    ergebnis = _abschnitte(_stellwert)
    assert max(e["ueberschwingen"] for e in ergebnis) <= 12      # nur Totzone des Geräts
    assert all(e["schreibvorgaenge"] <= 1 for e in ergebnis[1:])  # ein Schreibbefehl je Laständerung


@pytest.mark.parametrize("abschnitt, grenze", [
    (0, 17.0),   # 0 → 550 W: Totzeit 2 s + schneller Anlauf + Rampe ≈ 15,6 s
    (2, 18.0),   # 250 → 750 W: Totzeit + 500 W / 34 W/s ≈ 16,7 s
    (1, 3.0),    # Senken: nach der Totzeit
    (3, 3.0),
])
def test_stellwertrechnung_so_schnell_wie_das_geraet(abschnitt, grenze):
    assert _abschnitte(_stellwert)[abschnitt]["einschwingzeit"] <= grenze


@pytest.mark.parametrize("netz_takt", [1.0, 2.0, 3.0])
def test_stellwertrechnung_laststufe_waehrend_der_rampe(netz_takt):
    # Lastsprung mitten im Anstieg: gesenkt wird sofort, Überschwingen nur aus der Totzeit
    last = stufen((0, -750.0), (8.3, -450.0))
    verlauf = simulieren(_stellwert, last, 60, netz_takt=netz_takt)
    e = bewertung(verlauf, 400.0, 8.3, 60)
    assert e["ueberschwingen"] <= 34.0 * 3.5
    assert e["einschwingzeit"] <= 8.0
