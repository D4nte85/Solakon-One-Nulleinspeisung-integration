"""PI-Regler ohne Coordinator: Gate, Abklingen, Anti-Windup."""
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
    assert pi.gate_discharge(*args) == expected


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


def test_anteil_skaliert_fehler():
    out = _ctrl().calculate(130, 400, 30, 800, 1.0, 0.0, error_share=0.5)
    assert out == 450.0
