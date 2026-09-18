"""Zonenentscheidung ohne Coordinator: je Fall ein Treffer, Reihenfolge, kein Treffer."""
from __future__ import annotations

import dataclasses
import importlib

import pytest

from tests import harness as h

zones = importlib.import_module(h.PKG + ".zones")
tariff = importlib.import_module(h.PKG + ".tariff")

# Ruhe in Modus '0' bei SOC in Zone 2, Nacht, keine Session: kein Fall greift.
BASE = zones.ZoneInputs(
    soc=40, grid=0, actual=0, total_actual=0, mode="0",
    zone1_limit=60, zone3_limit=20,
    surplus_enabled=False, new_surplus=False,
    ac_enabled=False, ac_soc_target=90, ac_hysteresis=50, ac_offset=-50,
    tariff=tariff.TariffState(price=0.30, cheap=0.20, exp=0.40, below_exp=False,
                              below_cheap=False, at_least_cheap=True),
    tariff_soc=80, tariff_power=800,
    is_night=True, zone1_forced=False, self_adjust_tol=3,
    surplus_active=False, ac_charge_active=False, tariff_charge_active=False,
    cycle_active=False, at_rest=True,
)


_TARIFF_KEYS = ("below_exp", "below_cheap", "at_least_cheap")


def _decide(**kw):
    t = {k: kw.pop(k) for k in _TARIFF_KEYS if k in kw}
    return zones.decide(dataclasses.replace(BASE, tariff=dataclasses.replace(BASE.tariff, **t), **kw))


def test_base_trifft_keinen_fall():
    assert zones.decide(BASE) is None


@pytest.mark.parametrize("kw, name", [
    (dict(surplus_enabled=True, new_surplus=True), "0A"),
    (dict(surplus_active=True, cycle_active=True, mode="1", at_rest=False), "0B"),
    (dict(soc=70), "A"),
    (dict(zone1_forced=True), "A"),
    (dict(soc=15, cycle_active=True, mode="1", at_rest=False), "B"),
    (dict(soc=15, mode="1", at_rest=False), "C"),
    (dict(cycle_active=True), "D"),
    (dict(below_cheap=True, below_exp=True), "GT"),
    (dict(tariff_charge_active=True, mode="3", at_rest=False), "HT"),
    (dict(below_exp=True, at_least_cheap=False, mode="1", at_rest=False), "TM"),
    (dict(ac_enabled=True, grid=-200, mode="1", at_rest=True, below_exp=True), "G"),
    (dict(ac_charge_active=True, mode="3", at_rest=False, soc=95), "H"),
    (dict(ac_charge_active=True, mode="3", at_rest=False, grid=10, actual=3), "H"),
    (dict(mode="3", at_rest=False), "I"),
    (dict(is_night=False), "E"),
    (dict(mode="1", at_rest=False), "F"),
])
def test_je_fall_ein_treffer(kw, name):
    assert _decide(**kw).name == name


@pytest.mark.parametrize("kw, name", [
    # 0A vor A: Überschuss-Eintritt und Zone-1-SOC zugleich
    (dict(surplus_enabled=True, new_surplus=True, soc=70), "0A"),
    # B vor C: nur der aktive Zyklus trennt die beiden
    (dict(soc=15, cycle_active=True, mode="1", at_rest=False), "B"),
    # GT vor G: Tarif-Laden hat Vorrang vor AC-Laden
    (dict(below_cheap=True, below_exp=True, ac_enabled=True, grid=-200,
          mode="1"), "GT"),
    # E vor F: tagsüber Zone 2, nicht Nachtabschaltung
    (dict(is_night=False, mode="0", at_rest=True), "E"),
])
def test_reihenfolge(kw, name):
    assert _decide(**kw).name == name


def test_0a_ohne_moduswechsel_in_laufendem_modus_1():
    d = _decide(surplus_enabled=True, new_surplus=True, mode="1", at_rest=False)
    assert d.transition == {"flags": {"surplus_active": True, "cycle_active": True},
                            "timer": False, "mode": None}


def test_0b_leitet_zyklus_aus_soc_ab():
    d = _decide(surplus_active=True, soc=70)
    assert d.transition["flags"] == {"surplus_active": False, "cycle_active": True}


def test_a_erzwungen_unter_zone1():
    d = _decide(zone1_forced=True)
    assert (d.action, d.params) == ("act_fall_a_forced", {"soc": 40})


def test_d_session_kehrt_unter_zone3_in_modus_3_zurueck():
    d = _decide(ac_charge_active=True, soc=15)
    assert (d.name, d.transition) == ("D", {"mode": "3"})


def test_d_durch_tarif_lock_gesperrt():
    assert _decide(cycle_active=True, below_exp=True) is None


@pytest.mark.parametrize("cycle_active, rest", [(False, True), (True, False)])
def test_end_charge_ruhe_nur_ohne_zyklus(cycle_active, rest):
    d = _decide(ac_charge_active=True, mode="3", at_rest=False, soc=95, cycle_active=cycle_active)
    assert d.transition == {"reset_integral": True, "flags": {"ac_charge_active": False},
                            "output": 0, "mode": "1", "rest": rest}
    assert d.action == "act_fall_h"


def test_h_bleibt_bei_selbstregelung_ausserhalb_der_toleranz():
    assert _decide(ac_charge_active=True, mode="3", at_rest=False, grid=10, actual=5) is None
