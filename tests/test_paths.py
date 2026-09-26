"""Pfadwahl der PI-Phase ohne Coordinator: Pfad je Regelzustand, Abklingen, Schwester-Hinweis."""
from __future__ import annotations

import importlib

import pytest

from tests import harness as h

paths = importlib.import_module(h.PKG + ".paths")

BASE = dict(
    grid=30.0, current_power=400.0, tolerance=25.0,
    surplus_active=False, ac_charge_active=False, tariff_charge_active=False, capped=False,
    zone0_power=1200.0, tariff_power=800.0,
    ac_offset=-50.0, ac_limit=800.0, ac_p=0.3, ac_i=0.0, ac_share=1.0, ac_base=300.0,
    target_offset=30.0, dynamic_max=800.0, p_factor=1.3, i_factor=0.05, share=1.0,
    discharge_base=400.0,
)


def _decide(**over):
    return paths.decide(paths.PathInputs(**{**BASE, **over}))


def test_surplus_schreibt_zone0_festwert():
    d = _decide(surplus_active=True, ac_charge_active=True)
    assert (d.kind, d.value, d.action, d.ac_charge_mode) == (paths.FIXED, 1200.0, "act_zone0_output", False)


def test_tarif_schreibt_festwert_im_lademodus():
    d = _decide(tariff_charge_active=True)
    assert (d.kind, d.value, d.action, d.ac_charge_mode) == (paths.FIXED, 800.0, "act_tariff_power", True)


def test_ac_in_toleranz_nichts_und_abklingen():
    d = _decide(ac_charge_active=True, grid=-50.0)
    assert (d.kind, d.decay) == (paths.IDLE, True)


def test_ac_schritt_mit_ac_parametern():
    d = _decide(ac_charge_active=True, grid=-200.0)
    assert d.kind == paths.PI_STEP and not d.decay
    assert d.step == paths.PiStep(300.0, -50.0, 800.0, 0.3, 0.0, 1.0, "act_ac_pi", ac_charge_mode=True)


@pytest.mark.parametrize("capped, action", [(False, "act_pi"), (True, "act_pi_sister_charging")])
def test_entladen_schritt(capped, action):
    d = _decide(grid=200.0, capped=capped)
    assert d.kind == paths.PI_STEP and not d.decay and not d.sister_note
    assert d.step == paths.PiStep(400.0, 30.0, 800.0, 1.3, 0.05, 1.0, action)


@pytest.mark.parametrize("over, kind", [
    (dict(grid=30.0), "stall_reset"),
    (dict(grid=200.0, current_power=800.0), "stall_check"),
])
def test_entladen_ohne_schritt_klingt_ab(over, kind):
    d = _decide(**over, capped=True)
    assert (d.kind, d.value, d.decay, d.sister_note) == (kind, 800.0, True, True)
