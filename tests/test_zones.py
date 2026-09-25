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
    tariff_soc=80, tariff_soc_hyst=3, tariff_power=800,
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
    (dict(ac_enabled=True, ac_charge_active=True, mode="3", at_rest=False, soc=95), "H"),
    (dict(ac_enabled=True, ac_charge_active=True, mode="3", at_rest=False, grid=10, actual=3), "H"),
    # Options-Austritt: abgeschaltete Option beendet die Session unabhängig vom Wert
    (dict(ac_charge_active=True, mode="3", at_rest=False), "H"),
    (dict(tariff_charge_active=True, mode="3", at_rest=False, at_least_cheap=False), "HT"),
    (dict(mode="3", at_rest=False), "I"),
    # Fall I beidseitig: Session ohne Modus '3' und beide Lade-Flags zugleich
    (dict(ac_charge_active=True, ac_enabled=True, mode="1", at_rest=False), "I"),
    (dict(ac_charge_active=True, tariff_charge_active=True, mode="3", at_rest=False,
          below_cheap=True, at_least_cheap=False), "I"),
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
    d = _decide(ac_enabled=True, ac_charge_active=True, soc=15)
    assert (d.name, d.transition) == ("D", {"mode": "3"})


@pytest.mark.parametrize("soc, hyst, gt", [
    (76, 3, True), (77, 3, False), (79, 3, False), (79, 0, True), (80, 0, False),
])
def test_gt_erst_unter_ladeziel_minus_hysterese(soc, hyst, gt):
    d = _decide(below_cheap=True, below_exp=True, soc=soc, tariff_soc_hyst=hyst)
    assert (d is not None and d.name == "GT") == gt


def test_d_durch_tarif_lock_gesperrt():
    assert _decide(cycle_active=True, below_exp=True) is None


@pytest.mark.parametrize("cycle_active, rest", [(False, True), (True, False)])
def test_end_charge_ruhe_nur_ohne_zyklus(cycle_active, rest):
    d = _decide(ac_enabled=True, ac_charge_active=True, mode="3", at_rest=False, soc=95,
                cycle_active=cycle_active)
    assert d.transition == {"reset_integral": True, "flags": {"ac_charge_active": False},
                            "output": 0, "mode": "1", "rest": rest}
    assert d.action == "act_fall_h"


def test_h_bleibt_bei_selbstregelung_ausserhalb_der_toleranz():
    assert _decide(ac_enabled=True, ac_charge_active=True, mode="3", at_rest=False,
                   grid=10, actual=5) is None


def test_d_folgt_session_mit_abgeschalteter_option_nicht():
    d = _decide(tariff_charge_active=True, cycle_active=True, soc=70)
    assert (d.name, d.transition) == ("D", {"mode": "1"})


def test_gt_startet_nicht_neben_laufender_ac_session():
    assert _decide(ac_enabled=True, ac_charge_active=True, mode="1", at_rest=False,
                   below_cheap=True, below_exp=True).name == "I"


def test_i_loescht_flags_und_laesst_modus_stehen():
    d = _decide(ac_enabled=True, ac_charge_active=True, mode="1", at_rest=False)
    assert d.transition == {"reset_integral": True,
                            "flags": {"ac_charge_active": False, "tariff_charge_active": False}}
    assert (d.action, d.warn) == ("act_fall_i_session", None)


def test_i_meldet_nur_die_doppelsession():
    d = _decide(ac_charge_active=True, tariff_charge_active=True, mode="3", at_rest=False,
                below_cheap=True, at_least_cheap=False)
    assert d.warn == ("warn_double_session", {})


# ── Vorstufe: Prognoseflags ──────────────────────────────────────────────────

FC = dict(
    surplus_forecast=None, surplus_lock=None, zone1_force=None, solar=0, soc=50,
    surplus_forecast_threshold=15, hard_limit_z0=800, zone3_limit=20, surplus_lock_factor=1.5,
    zone1_force_threshold=10, pv_reserve=50, zone1_force_min_soc=30,
)


def _flags(**kw):
    return zones.forecast_flags(**{**FC, **kw})


def test_prognoseflags_ohne_werte_aus():
    assert _flags() == zones.ForecastFlags(False, False, False)


@pytest.mark.parametrize("kw, erwartet", [
    (dict(surplus_forecast=15, solar=801, soc=21), True),
    (dict(surplus_forecast=14.9, solar=801, soc=21), False),
    (dict(surplus_forecast=15, solar=800, soc=21), False),
    (dict(surplus_forecast=15, solar=801, soc=20), False),
])
def test_zone0_forcierung_grenzen(kw, erwartet):
    assert _flags(**kw).surplus_forced is erwartet


@pytest.mark.parametrize("kw, erwartet", [
    (dict(surplus_lock=1200, soc=21), True),
    (dict(surplus_lock=1199, soc=21), False),
    (dict(surplus_lock=1200, soc=20), False),
])
def test_austritts_sperre_grenzen(kw, erwartet):
    assert _flags(**kw).exit_lock is erwartet


@pytest.mark.parametrize("kw, erwartet", [
    (dict(zone1_force=10, solar=49, soc=31), True),
    (dict(zone1_force=9.9, solar=49, soc=31), False),
    (dict(zone1_force=10, solar=50, soc=31), False),
    (dict(zone1_force=10, solar=49, soc=30), False),
])
def test_zone1_forcierung_grenzen(kw, erwartet):
    assert _flags(**kw).zone1_forced is erwartet


# ── Vorstufe: Überschuss und Nacht ───────────────────────────────────────────

# Nicht in Zone 0, PV 0, PV-0-Eintritt scharf, hell, Lastanteil 0.
SN = dict(
    state=zones.SurplusState(armed=True, dark=False), surplus_enabled=True,
    surplus_active=False, cycle_active=False, forced=False, exit_lock=False,
    solar=0, soc=95, actual=0, prev_actual=0, total_actual=0, grid=0, error_share=1.0,
    surplus_threshold=90, surplus_soc_hyst=2, surplus_pv_hyst=50,
    pv_reserve=50, night_hysteresis=20, night_enabled=True,
)


def _sn(**kw):
    return zones.surplus_and_night(**{**SN, **kw})


@pytest.mark.parametrize("kw, erwartet", [
    # Eintritt über Lastanteil + PV-Hysterese: 200 + 100 + 50 = 350
    (dict(solar=351, total_actual=200, grid=100), True),
    (dict(solar=350, total_actual=200, grid=100), False),
    (dict(solar=351, total_actual=200, grid=100, soc=89), False),
    # Eintritt bei PV 0 nur scharf und ohne Ausgang in diesem und dem vorigen Zyklus
    (dict(), True),
    (dict(state=zones.SurplusState(armed=False, dark=False)), False),
    (dict(actual=5), False),
    (dict(prev_actual=5), False),
    # Forcierung tritt SOC-unabhängig ein
    (dict(forced=True, soc=30), True),
    (dict(surplus_enabled=False), False),
])
def test_ueberschuss_eintritt(kw, erwartet):
    assert _sn(**kw).new_surplus is erwartet


@pytest.mark.parametrize("kw, erwartet", [
    # SOC-Austritt unter Schwelle − Hysterese (88)
    (dict(soc=87, solar=1000), False),
    (dict(soc=88, solar=1000), True),
    # Verbrauchsaustritt: PV ≤ Lastanteil − PV-Hysterese (300 − 50)
    (dict(solar=250, total_actual=200, grid=100), False),
    (dict(solar=251, total_actual=200, grid=100), True),
    # Exit-Lock sperrt nur den Verbrauchsterm (Issue #7)
    (dict(solar=250, total_actual=200, grid=100, exit_lock=True), True),
    (dict(soc=87, solar=1000, exit_lock=True), False),
    # Forcierung sperrt den ganzen Austritt
    (dict(soc=50, forced=True), True),
])
def test_ueberschuss_austritt(kw, erwartet):
    assert _sn(surplus_active=True, **kw).new_surplus is erwartet


def test_pv0_eintritt_erst_nach_pv_wieder_scharf():
    """Issue #17: nach dem Austritt bei PV 0 kein Wiedereintritt, bis PV > 0 war."""
    r = _sn(surplus_active=True, soc=87)
    assert (r.new_surplus, r.state.armed) == (False, False)
    r = _sn(state=r.state)
    assert (r.new_surplus, r.state.armed) == (False, False)
    r = _sn(state=r.state, solar=10)
    assert (r.new_surplus, r.state.armed) == (False, True)
    assert _sn(state=r.state).new_surplus is True


def test_austritt_mit_pv_laesst_eintritt_scharf():
    r = _sn(surplus_active=True, soc=87, solar=10)
    assert (r.new_surplus, r.state.armed) == (False, True)


def test_ohne_ueberschuss_bleibt_scharf_unveraendert():
    assert _sn(surplus_enabled=False, solar=10, state=zones.SurplusState(False, False)).state.armed is False


def test_nacht_hysterese_band():
    r = _sn(solar=49)
    assert (r.state.dark, r.is_night) == (True, True)
    r = _sn(state=r.state, solar=69)
    assert (r.state.dark, r.is_night) == (True, True)
    r = _sn(state=r.state, solar=70)
    assert (r.state.dark, r.is_night) == (False, False)
    r = _sn(state=r.state, solar=50)
    assert (r.state.dark, r.is_night) == (False, False)


@pytest.mark.parametrize("kw", [dict(cycle_active=True), dict(night_enabled=False)])
def test_nacht_unterdrueckt(kw):
    r = _sn(solar=0, **kw)
    assert (r.state.dark, r.is_night) == (True, False)
