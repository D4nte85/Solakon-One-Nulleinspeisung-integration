"""Pfadwahl der PI-Phase ohne Coordinator: Pfad je Regelzustand, Abklingen, Schwester-Hinweis."""
from __future__ import annotations

import importlib

import pytest

from tests import harness as h

paths = importlib.import_module(h.PKG + ".paths")
limits = importlib.import_module(h.PKG + ".limits")
schema = importlib.import_module(h.PKG + ".schema")

# Zyklus in Modus '1' mit viel PV: Obergrenze ist das Zone-1-Limit, auch mit PV-Deckel.
CS = schema.cycle_settings(h.const.SETTINGS_DEFAULTS)._replace(
    tolerance=25, tariff_power=800, grid_charge_power=800, ac_min_power=50,
    pi_enabled=True, p_factor=1.3, i_factor=0.05,
)
LIMITS = limits.PowerLimits(zone0=1200, zone12=800, ac=800, export=1200, pv_reserve=50)
BASE = dict(
    cs=CS, limits=LIMITS, mode="1", cycle_active=True, surplus_active=False, session="none", cap_reason="",
    grid=30.0, solar=5000.0, current_power=400.0,
    ac_offset=-50.0, target_offset=30.0, ac_share=1.0, share=1.0,
    ac_charge=300.0, ac_pool_charge=300.0, discharge=390.0, discharge_pool=390.0, discharge_base=400.0,
)


def _decide(**over):
    cs = CS._replace(**{k: over.pop(k) for k in CS._fields if k in over})
    if "capped" in over:
        over["cap_reason"] = over.pop("capped")
    return paths.decide(paths.PathInputs(**{**BASE, "cs": cs, **over}))


def test_deckel_nur_im_zyklus_in_modus_1():
    for over in (dict(cycle_active=False), dict(mode="3")):
        d = _decide(grid=200.0, cap_reason="sister_charging", **over)
        assert d.kind == paths.PI_STEP and d.step.action == "act_pi"


def test_deckel_begrenzt_auf_pv_minus_reserve():
    d = _decide(grid=200.0, cap_reason="house_priority", solar=450.0, current_power=300.0)
    assert (d.step.limit, d.step.action) == (400.0, "act_pi_house_priority")


def test_surplus_schreibt_zone0_festwert():
    d = _decide(surplus_active=True, session="ac_charge")
    assert (d.kind, d.value, d.action, d.ac_charge_mode) == (paths.FIXED, 1200.0, "act_zone0_output", False)


def test_tarif_schreibt_festwert_im_lademodus():
    d = _decide(session="tariff_charge")
    assert (d.kind, d.value, d.action, d.ac_charge_mode) == (paths.FIXED, 800.0, "act_tariff_power", True)


def test_netz_laden_schreibt_festwert_im_lademodus():
    d = _decide(session="grid_charge", grid_charge_power=1000.0)
    assert (d.kind, d.value, d.action, d.ac_charge_mode) == (paths.FIXED, 1000.0, "act_grid_charge_power", True)


def test_ac_in_toleranz_nichts():
    d = _decide(session="ac_charge", grid=-50.0, current_power=300.0)
    assert (d.kind, d.decay) == (paths.IDLE, False)


def test_ac_stellwert_aus_ist_leistung():
    d = _decide(session="ac_charge", grid=-200.0, current_power=300.0)
    assert (d.kind, d.value, d.action, d.ac_charge_mode, d.decay) == (
        paths.SETPOINT, 450.0, "act_ac_setpoint", True, False)


@pytest.mark.parametrize("capped, action", [
    ("", "act_pi"), ("sister_charging", "act_pi_sister_charging"), ("house_priority", "act_pi_house_priority"),
])
def test_entladen_schritt(capped, action):
    d = _decide(grid=200.0, capped=capped)
    assert d.kind == paths.PI_STEP and not d.decay and not d.cap_note
    assert d.step == paths.PiStep(400.0, 30.0, 800.0, 1.3, 0.05, 1.0, action)


@pytest.mark.parametrize("over, kind", [
    (dict(grid=30.0, current_power=400.0), "stall_reset"),
    (dict(grid=200.0, current_power=800.0), "stall_check"),
    (dict(grid=200.0, current_power=790.0), "stall_check"),
])
def test_entladen_ohne_schritt_klingt_ab(over, kind):
    d = _decide(**over, capped="sister_charging")
    assert (d.kind, d.value, d.decay, d.cap_note) == (kind, over["current_power"], True, "sister_charging")


@pytest.mark.parametrize("capped, action", [
    ("", "act_discharge_setpoint"), ("sister_charging", "act_discharge_setpoint_sister_charging"),
    ("house_priority", "act_discharge_setpoint_house_priority"),
])
def test_entladen_stellwert_ohne_pi(capped, action):
    # Ist 390 W + (200 − 30) = 560 W, geschrieben im Entlademodus
    d = _decide(grid=200.0, capped=capped, pi_enabled=False)
    assert (d.kind, d.value, d.action, d.ac_charge_mode, d.decay, d.step) == (
        paths.SETPOINT, 560.0, action, False, False, None)


def test_entladen_stellwert_aus_dem_pool():
    d = _decide(grid=200.0, pi_enabled=False, discharge_pool=780.0, share=0.5)
    assert d.value == 475.0


@pytest.mark.parametrize("over, kind", [
    (dict(grid=30.0, current_power=400.0), "stall_reset"),
    (dict(grid=200.0, current_power=800.0), "stall_check"),
    (dict(grid=200.0, current_power=790.0), "stall_check"),
])
def test_entladen_stellwert_gate_bleibt(over, kind):
    d = _decide(**over, pi_enabled=False)
    assert (d.kind, d.value, d.decay) == (kind, over["current_power"], True)


def test_entladen_stellwert_rampe_nichts():
    # Ist 200 W unter der Ausgangsleistung 400 W, Stellwert höher: nichts schreiben
    d = _decide(grid=400.0, pi_enabled=False, discharge=200.0, discharge_pool=200.0)
    assert d.kind == paths.IDLE
