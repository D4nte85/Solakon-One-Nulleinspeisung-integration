"""Stellwertrechnung des AC-Ladens ohne Coordinator: Ist-Basis, Gate, Schwelle, Rampe."""
from __future__ import annotations

import importlib

import pytest

from tests import harness as h

ac = importlib.import_module(h.PKG + ".ac_charge")


def _sp(grid, own=400.0, pool=None, output=400.0, offset=-50.0, limit=800.0, share=1.0, tolerance=15.0,
        min_charge=50.0):
    return ac.setpoint(grid, own, own if pool is None else pool, output, offset, limit, min_charge, share,
                       tolerance)


@pytest.mark.parametrize("grid, expected", [
    (-250.0, 600.0),   # 200 W zu viel Einspeisung: Ladeleistung + 200
    (150.0, 200.0),    # 200 W Bezug: Ladeleistung − 200
    (-60.0, None),     # Netzfehler in der Toleranz
])
def test_ist_basis_ein_schritt(grid, expected):
    assert _sp(grid) == expected


def test_ist_basis_statt_sollwert():
    # Gerät steht 10 W neben dem Sollwert; gerechnet wird von der Ist-Leistung
    assert _sp(-150.0, own=390.0, output=400.0) == 490.0


def test_klemmen_auf_limit():
    assert _sp(-900.0) == 800.0


def test_ueber_gesenktem_limit_auch_in_toleranz():
    assert _sp(-50.0, own=800.0, output=800.0, limit=500.0) == 500.0


@pytest.mark.parametrize("grid, output, expected", [
    (330.0, 400.0, 0.0),    # Stellwert 20 W → 0
    (-90.0, 0.0, None),     # aus 0 mit Stellwert 40 → bleibt bei 0
    (-110.0, 0.0, 60.0),    # aus 0 mit Stellwert 60 → startet
])
def test_mindestladeleistung(grid, output, expected):
    own = 400.0 if output else 0.0
    assert _sp(grid, own=own, output=output) == expected


@pytest.mark.parametrize("min_charge, expected", [
    (100.0, 0.0),    # Stellwert 80 W unter der eingestellten Mindestladeleistung → 0
    (0.0, 80.0),     # Mindestladeleistung 0: jeder Stellwert wird geschrieben
])
def test_mindestladeleistung_einstellbar(min_charge, expected):
    assert _sp(270.0, min_charge=min_charge) == expected


def test_mindestladeleistung_ueber_limit():
    # Mindestladeleistung 300 W über Max. Ladeleistung 200 W: das Limit gilt als Schwelle
    assert _sp(-900.0, own=0.0, output=0.0, limit=200.0, min_charge=300.0) == 200.0


@pytest.mark.parametrize("grid, expected", [
    (-600.0, None),    # Stellwert 750 über der Ausgangsleistung 600: gesperrt
    (-300.0, 450.0),   # Stellwert 450 unter der Ausgangsleistung: senken
])
def test_rampe_laeuft_nur_senken(grid, expected):
    # Ist 200 W, Ausgangsleistung 600 W: die Rampe läuft
    assert _sp(grid, own=200.0, output=600.0) == expected


def test_nach_der_rampe_wieder_erhoehen():
    assert _sp(-300.0, own=590.0, output=600.0) == 800.0   # 840, geklemmt aufs Limit


def test_anteil_im_ac_pool():
    # zwei Instanzen mit zusammen 800 W, 200 W Überschuss, Anteil 0,5
    assert _sp(-250.0, own=300.0, pool=800.0, output=300.0, share=0.5) == 500.0
