"""PI-Regler ohne Coordinator: Gates, Abklingen, Anti-Windup."""
from __future__ import annotations

import importlib

import pytest

from tests import harness as h

pi = importlib.import_module(h.PKG + ".pi")
STEP, HOLD, SATURATED = pi.STEP, pi.HOLD, pi.SATURATED


def _ctrl(integral: float = 0.0):
    c = pi.PIController()
    c.integral = integral
    return c


# grid, current, offset, limit, tolerance, erwartet
@pytest.mark.parametrize("args, expected", [
    ((30, 400, 30, 800, 25), HOLD),         # Fehler 0 in der Toleranz
    ((80, 400, 30, 800, 25), STEP),         # Fehler über Toleranz, nach oben
    ((-20, 400, 30, 800, 25), STEP),        # Fehler über Toleranz, nach unten
    ((35, 900, 30, 800, 25), STEP),         # über dem Limit, Fehler in der Toleranz
    ((200, 800, 30, 800, 25), SATURATED),   # am Limit, Netz will mehr
    ((-200, 800, 30, 800, 25), STEP),       # am Limit, Netz will weniger
    ((35, 800, 30, 800, 25), SATURATED),    # am Limit, kleiner positiver Fehler
    ((-200, 0, 30, 800, 25), HOLD),         # bei 0 W, Netz will weniger
    ((200, 0, 30, 800, 25), STEP),          # bei 0 W, Netz will mehr
    ((30, 0, 30, 0, 25), HOLD),             # Limit 0, Fehler 0
])
def test_gate_discharge(args, expected):
    assert _ctrl().gate_discharge(*args) == expected


@pytest.mark.parametrize("args, expected", [
    ((-500, -500, 25), HOLD),
    ((-470, -500, 25), STEP),
    ((-530, -500, 25), STEP),
    ((-525, -500, 25), HOLD),               # genau auf der Toleranz
])
def test_gate_ac_nur_toleranz(args, expected):
    assert _ctrl().gate_ac(*args) == expected


@pytest.mark.parametrize("gate, args", [
    ("gate_discharge", (30, 400, 30, 800, 25)),
    ("gate_discharge", (200, 800, 30, 800, 25)),
    ("gate_ac", (-500, -500, 25)),
])
def test_ohne_schritt_klingt_integral_ab(gate, args):
    c = _ctrl(100.0)
    getattr(c, gate)(*args)
    assert c.integral == pytest.approx(95.0)


def test_mit_schritt_bleibt_integral():
    c = _ctrl(100.0)
    assert c.gate_discharge(80, 400, 30, 800, 25) == STEP
    assert c.integral == 100.0


@pytest.mark.parametrize("start, expected", [
    (10.0, 10.0), (-10.0, -10.0), (11.0, 10.45), (-20.0, -19.0),
])
def test_decay_erst_ueber_10(start, expected):
    c = _ctrl(start)
    c.decay()
    assert c.integral == pytest.approx(expected)


def test_reset():
    c = _ctrl(123.0)
    c.reset()
    assert c.integral == 0.0


def test_schritt_ohne_begrenzung():
    c = _ctrl(0.0)
    out = c.calculate(130, 400, 30, 800, 1.0, 0.1)
    # Fehler 100: P 100 + I 10
    assert out == 510.0
    assert c.integral == pytest.approx(100.0)


def test_back_calculation_bei_begrenzung():
    c = _ctrl(0.0)
    out = c.calculate(1000, 700, 0, 800, 1.0, 0.1)
    # Fehler auf 100 bis zum Limit begrenzt, Ergebnis geklemmt auf 800
    assert out == 800.0
    assert c.integral == pytest.approx((800 - 700 - 100 * 1.0) / 0.1)


def test_ohne_i_faktor_keine_back_calculation():
    c = _ctrl(50.0)
    c.calculate(1000, 700, 0, 800, 1.0, 0.0)
    assert c.integral == pytest.approx(150.0)


def test_limit_auf_geraetemaximum_gedeckelt():
    c = _ctrl(0.0)
    out = c.calculate(5000, 0, 0, 5000, 1.0, 0.0)
    assert out == pi.DEVICE_MAX_POWER
    assert abs(c.integral) <= pi.DEVICE_MAX_POWER


def test_ac_fehlerrichtung_invertiert():
    entladen = _ctrl().calculate(-100, 400, 0, 800, 1.0, 0.0)
    laden = _ctrl().calculate(-100, 400, 0, 800, 1.0, 0.0, ac_charge_mode=True)
    assert entladen == 300.0
    assert laden == 500.0


def test_anteil_skaliert_fehler():
    out = _ctrl().calculate(130, 400, 30, 800, 1.0, 0.0, error_share=0.5)
    assert out == 450.0
