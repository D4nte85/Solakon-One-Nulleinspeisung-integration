"""Netzgruppe ohne Coordinator: Mitglieder, Pools, Anteile je Modus, soc_switch, Zuteilung."""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from tests import harness as h

group = importlib.import_module(h.PKG + ".grid_group")
DOMAIN = h.const.DOMAIN


M = h.FakeMember


def _group(*members, dist=None, soc_switch=None):
    """Netzgruppe `sensor.grid` mit Gruppenspeicher ohne HA-Store; `soc_switch` als gespeicherter Zustand."""
    hass = h.hass_with_members(*members)
    store = h.install_groups(hass, {"sensor.grid": dict(dist or {})},
                             None if soc_switch is None else {"sensor.grid": soc_switch})
    return hass, group.NetGroup(hass, "sensor.grid", h.group_store_mod.StoredGroup(store, "sensor.grid"))


def _stored_switch(hass):
    """Im Gruppenspeicher übernommener `soc_switch`-Zustand von `sensor.grid`, sonst None."""
    return h.group_store_mod.require_store(hass).soc_switch.get("sensor.grid")


def test_kein_modul_group_im_paket():
    """Issue #42: Home Assistant lädt ein Modul `group` als Plattform der Group-Integration."""
    assert not (Path(group.__file__).parent / "group.py").exists()


def test_mitglieder_nur_am_eigenen_netzsensor():
    a, b, x = M("a"), M("b"), M("x", grid_sensor="sensor.other")
    _, g = _group(a, b, x)
    assert list(g.members()) == ["a", "b"]


def test_leader_kleinste_id_unter_regelnden_sonst_unter_allen():
    a, b, c = M("a", regulating=False), M("c"), M("b")
    _, g = _group(a, b, c)
    assert g.leader() is c
    for m in (b, c):
        m.regulating = False
    assert g.leader() is a


def test_pools():
    a = M("a")
    b = M("b", discharge=False, charge_session="ac_charge")
    c = M("c", regulating=False, charge_session="ac_charge")
    _, g = _group(a, b, c)
    assert list(g.discharge_pool()) == ["a"]
    assert list(g.ac_pool()) == ["b"]


def test_pool_sum_eigener_wert_immer_fremde_ueber_reader():
    a, b, c = M("a", actual=999), M("b", actual=100), M("c", actual=50)
    _, g = _group(a, b, c)
    assert group.pool_sum({"b": b, "c": c}, a, 10, lambda m: m.actual_power()) == 160
    assert group.pool_sum({"a": a, "b": b}, a, 10, lambda m: m.actual_power()) == 110



def test_discharge_actual_summiert_entlade_pool():
    a, b = M("a", actual=999), M("b", actual=100)
    c = M("c", actual=50, discharge=False)
    _, g = _group(a, b, c)
    assert g.discharge_actual(a, 10) == 110


def test_discharge_output_im_surplus_nur_ist_leistung():
    # b im Surplus zählt mit der Ist-Leistung statt mit dem festen Zone-0-Sollwert
    a, b = M("a", actual=100, setpoint=300), M("b", actual=300, setpoint=800, surplus_active=True)
    c = M("c", actual=200, setpoint=500)
    _, g = _group(a, b, c)
    assert g.discharge_output(b, 300, 800) == 300 + 300 + 500
    assert g.discharge_output(a, 100, 300) == 300 + 300 + 500
    # Eine negative Ist-Leistung im Surplus ist ein veralteter Ladewert, dann zählt der Sollwert
    b.actual = -1200
    assert g.discharge_output(a, 100, 300) == 300 + 800 + 500


def test_ac_actual_summiert_ac_pool():
    a, b = M("a", actual=999), M("b", actual=100)
    c = M("c", actual=-50, discharge=False, charge_session="ac_charge")
    _, g = _group(a, b, c)
    assert g.ac_actual(a, -10) == -60


def test_pi_base_pool_mal_anteil():
    a, b = M("a", setpoint=999), M("b", setpoint=100)
    c = M("c", setpoint=50, discharge=False, charge_session="ac_charge")
    _, g = _group(a, b, c)
    assert g.pi_base(a, 10, 0.5, 0.0) == (10 + 100) * 0.5


def test_config_mit_defaults():
    _, g = _group(dist={"global_max_power": 500})
    cfg = g.dist_cfg()
    assert cfg["global_max_power"] == 500 and cfg["distribution_mode"] == "equal"


def test_anteile_leerer_pool_und_einzeln():
    a = M("a")
    _, g = _group(a, dist={"distribution_mode": "soc"})
    assert g.all_shares({}, a, 50) == group.Shares({})
    assert g.all_shares({"a": a}, a, 50) == group.Shares({"a": 1.0}, "soc")


def test_anteile_gleich():
    a, b = M("a"), M("b")
    _, g = _group(a, b, dist={"distribution_mode": "equal"})
    assert g.all_shares({"a": a, "b": b}, a, 50) == group.Shares({"a": 0.5, "b": 0.5}, "equal")


def test_anteile_soc_ueber_zone3():
    a, b = M("a"), M("b", soc=40.0, zone3=10.0)
    _, g = _group(a, b, dist={"distribution_mode": "soc"})
    s = g.all_shares({"a": a, "b": b}, a, 50)
    assert s.mode == "soc" and s.warning == ""
    assert s.values == pytest.approx({"a": 30 / 60, "b": 30 / 60})


def test_anteile_soc_ohne_nutzbaren_soc_gleich():
    a, b = M("a"), M("b", soc=10.0)
    _, g = _group(a, b, dist={"distribution_mode": "soc"})
    assert g.all_shares({"a": a, "b": b}, a, 15) == group.Shares({"a": 0.5, "b": 0.5}, "equal")


def test_fremd_soc_fehlt_gleich_mit_warnung_und_abbruch():
    a, b, c = M("a"), M("b", soc=None), M("c")
    _, g = _group(a, b, c, dist={"distribution_mode": "soc"})
    s = g.all_shares({"a": a, "b": b, "c": c}, a, 50)
    assert s == group.Shares({"a": 1 / 3, "b": 1 / 3, "c": 1 / 3}, "equal", "warn_dist_soc_sensor")
    assert (a.soc_reads, b.soc_reads, c.soc_reads) == (0, 1, 0)


def test_anteile_kapazitaet():
    dist = {"distribution_mode": "capacity",
            "inst_a_capacity_sensor": "sensor.ka", "inst_b_capacity_sensor": "sensor.kb"}
    a = M("a", capacity={"sensor.ka": 2.0})
    b = M("b", soc=50.0, capacity={"sensor.kb": 6.0})
    _, g = _group(a, b, dist=dist)
    s = g.all_shares({"a": a, "b": b}, a, 50)
    assert s.mode == "capacity" and s.values == pytest.approx({"a": 0.25, "b": 0.75})


def test_kapazitaet_fehlt_soc_gewichtung_mit_warnung():
    dist = {"distribution_mode": "capacity", "inst_a_capacity_sensor": "sensor.ka"}
    a, b = M("a", capacity={"sensor.ka": 2.0}), M("b", soc=80.0)
    _, g = _group(a, b, dist=dist)
    s = g.all_shares({"a": a, "b": b}, a, 50)
    assert (s.mode, s.warning) == ("soc", "warn_dist_capacity_sensor")
    assert s.values == pytest.approx({"a": 30 / 90, "b": 60 / 90})


@pytest.mark.parametrize("dist, soc_b, warnungen", [
    ({"distribution_mode": "capacity", "inst_a_capacity_sensor": "sensor.ka"}, 80.0,
     ("warn_dist_capacity_sensor", "warn_ac_dist_capacity_sensor")),
    ({"distribution_mode": "soc"}, None, ("warn_dist_soc_sensor", "warn_ac_dist_soc_sensor")),
    ({"distribution_mode": "soc_switch"}, None,
     ("warn_dist_soc_switch_sensor", "warn_ac_dist_soc_sensor")),
])
def test_warnschluessel_je_pool(dist, soc_b, warnungen):
    a, b = M("a", capacity={"sensor.ka": 2.0}), M("b", soc=soc_b)
    _, g = _group(a, b, dist=dist)
    assert tuple(g.all_shares({"a": a, "b": b}, a, 50, ac=ac).warning for ac in (False, True)) == warnungen


def test_ac_pool_gewichtet_nach_platz_bis_ladeziel():
    a, b = M("a", ac_target=90.0), M("b", soc=30.0, ac_target=80.0)
    _, g = _group(a, b, dist={"distribution_mode": "soc"})
    s = g.all_shares({"a": a, "b": b}, a, 80, ac=True)
    assert s.values == pytest.approx({"a": 10 / 60, "b": 50 / 60})


def test_ac_pool_kapazitaet_gewichtet_fehlende_kwh():
    dist = {"distribution_mode": "capacity",
            "inst_a_capacity_sensor": "sensor.ka", "inst_b_capacity_sensor": "sensor.kb"}
    a, b = M("a", capacity={"sensor.ka": 4.0}), M("b", soc=50.0, capacity={"sensor.kb": 2.0})
    _, g = _group(a, b, dist=dist)
    s = g.all_shares({"a": a, "b": b}, a, 70, ac=True)
    assert s.values == pytest.approx({"a": 0.8 / 1.6, "b": 0.8 / 1.6})


def test_ac_pool_soc_switch_wirkt_wie_soc_ohne_rotationszustand():
    a, b = M("a"), M("b", soc=30.0)
    hass, g = _group(a, b, dist=SWITCH)
    s = g.all_shares({"a": a, "b": b}, a, 80, ac=True)
    assert s.mode == "soc_switch" and s.warning == ""
    assert s.values == pytest.approx({"a": 10 / 70, "b": 60 / 70})
    assert _stored_switch(hass) is None


def test_ac_pool_ueber_ladeziel_ohne_gewicht():
    a, b = M("a"), M("b", soc=95.0)
    _, g = _group(a, b, dist={"distribution_mode": "soc"})
    assert g.all_shares({"a": a, "b": b}, a, 60, ac=True).values == pytest.approx({"a": 1.0, "b": 0.0})


def test_kapazitaet_fehlt_und_soc_ohne_gewicht_behaelt_warnung():
    dist = {"distribution_mode": "capacity"}
    a, b = M("a"), M("b", soc=5.0)
    _, g = _group(a, b, dist=dist)
    assert g.all_shares({"a": a, "b": b}, a, 5) == group.Shares(
        {"a": 0.5, "b": 0.5}, "equal", "warn_dist_capacity_sensor")


SWITCH = {"distribution_mode": "soc_switch", "soc_switch_divergence": 5}


def test_soc_switch_start_beim_hoechsten_soc_und_speichert():
    a, b = M("a"), M("b", soc=70.0)
    hass, g = _group(a, b, dist=SWITCH)
    assert _stored_switch(hass) is None
    assert g.all_shares({"a": a, "b": b}, a, 50).values == {"a": 0.0, "b": 1.0}
    assert _stored_switch(hass) == {"active_id": "b", "start_soc": 70.0, "was_zone0": False}


def _switch_state(**state):
    return {"was_zone0": False, **state}


@pytest.mark.parametrize("soc_b, aktiv", [(66.0, "b"), (65.0, "c"), (64.0, "c")])
def test_soc_switch_divergenz_grenze_und_rotation_zum_hoechsten(soc_b, aktiv):
    a, b, c = M("a", soc=30.0), M("b", soc=soc_b), M("c", soc=60.0)
    _, g = _group(a, b, c, dist=SWITCH, soc_switch=_switch_state(active_id="b", start_soc=70.0))
    shares = g.soc_switch_shares({"a": a, "b": b, "c": c}, a, 30.0)
    assert shares == {k: (1.0 if k == aktiv else 0.0) for k in "abc"}


def test_soc_switch_mehrere_zone0_gleichmaessig():
    a, b, c = M("a", surplus_active=True), M("b", surplus_active=True), M("c")
    _, g = _group(a, b, c, dist=SWITCH)
    assert g.soc_switch_shares({"a": a, "b": b, "c": c}, a, 50) == {"a": 0.5, "b": 0.5, "c": 0.0}


def test_soc_switch_zone0_uebernimmt_und_verlassen_verankert_neu():
    a, b = M("a"), M("b", soc=90.0, surplus_active=True)
    hass, g = _group(a, b, dist=SWITCH, soc_switch=_switch_state(active_id="a", start_soc=80.0))
    assert g.soc_switch_shares({"a": a, "b": b}, a, 50) == {"a": 0.0, "b": 1.0}
    state = _stored_switch(hass)
    assert state == {"active_id": "b", "start_soc": 90.0, "was_zone0": True}
    b.surplus_active, b.soc = False, 88.0
    assert g.soc_switch_shares({"a": a, "b": b}, a, 50) == {"a": 0.0, "b": 1.0}
    assert state == {"active_id": "b", "start_soc": 88.0, "was_zone0": False}


def test_soc_switch_fremd_soc_fehlt():
    a, b = M("a"), M("b", soc=None)
    _, g = _group(a, b, dist=SWITCH)
    assert g.all_shares({"a": a, "b": b}, a, 50) == group.Shares(
        {"a": 0.5, "b": 0.5}, "equal", "warn_dist_soc_switch_sensor")


def test_wasserfuellung_abgerundet():
    ms = {k: M(k) for k in "abc"}
    _, g = _group(*ms.values())
    assert group.waterfill(ms, {k: 1 / 3 for k in ms}, 800) == {"a": 266, "b": 266, "c": 266}


def test_wasserfuellung_reicht_rest_weiter():
    a, b = M("a", limit=200), M("b")
    _, g = _group(a, b)
    assert group.waterfill({"a": a, "b": b}, {"a": 0.5, "b": 0.5}, 800) == {"a": 200, "b": 600}


def test_wasserfuellung_ohne_anteile_null():
    a, b = M("a"), M("b")
    _, g = _group(a, b)
    assert group.waterfill({"a": a, "b": b}, {"a": 0.0, "b": 0.0}, 800) == {"a": 0.0, "b": 0.0}


def test_zuteilung_einzelbetrieb_ohne_gesamtlimit():
    a = M("a")
    _, g = _group(a, dist={"global_max_power": 500})
    assert g.distribution(a, 50, g.discharge_pool()) == (1.0, None, None)


@pytest.mark.parametrize("limit, erwartet", [(1200, 800), (600, 600)])
def test_zuteilung_allein_im_pool_einer_netzgruppe(limit, erwartet):
    a, b = M("a", limit=limit), M("b", discharge=False)
    _, g = _group(a, b, dist={"global_max_power": 800})
    assert g.distribution(a, 50, g.discharge_pool()) == (1.0, erwartet, None)
    assert g.distribution(b, 50, g.discharge_pool()) == (0.0, None, None)


def test_zuteilung_steigt_nur_bis_zur_freien_leistung():
    a, b = M("a"), M("b", allocated_power=700)
    _, g = _group(a, b, dist={"distribution_mode": "equal", "global_max_power": 800})
    share, alloc, shares = g.distribution(a, 50, g.discharge_pool())
    assert (share, alloc) == (0.5, 100) and shares.mode == "equal"
    b.allocated_power = 900
    assert g.distribution(a, 50, g.discharge_pool())[1] == 0
    b.allocated_power = None
    assert g.distribution(a, 50, g.discharge_pool())[1] == 400


def test_zuteilung_ohne_limit_von_mitgliedern_ausserhalb_des_pools():
    """Das letzte Limit einer abgeschalteten Instanz kappt die übrigen nicht."""
    a, b = M("a"), M("b", allocated_power=400)
    c = M("c", regulating=False, allocated_power=266)
    _, g = _group(a, b, c, dist={"distribution_mode": "equal", "global_max_power": 800})
    assert g.distribution(a, 50, g.discharge_pool())[1] == 400


def test_ac_anteil():
    a, b = M("a", charge_session="ac_charge"), M("b", charge_session="ac_charge")
    _, g = _group(a, b, dist={"distribution_mode": "equal"})
    assert g.ac_share(a, 50, g.ac_pool()) == (0.5, group.Shares({"a": 0.5, "b": 0.5}, "equal"))
    a.charge_session = "none"
    assert g.ac_share(a, 50, g.ac_pool()) == (0.0, None)


def test_verteilungslage_aus_dem_pool_der_instanz():
    a, b = M("a"), M("b")
    _, g = _group(a, b, dist={"distribution_mode": "equal"})
    pos = g.position(a, 50)
    assert (pos.pools, pos.share, pos.ac_share, pos.mode, pos.warning) == ((True, False), 0.5, 0.0, "equal", "")
    a.charge_session = b.charge_session = "ac_charge"
    pos = g.position(a, 50)
    assert (pos.pools, pos.share, pos.ac_share, pos.mode) == ((True, True), 0.5, 0.5, "equal")
    a.charge_session = "none"
    a_aus = M("a", discharge=False)
    _, g = _group(a_aus, b, dist={"distribution_mode": "equal"})
    pos = g.position(a_aus, 50)
    assert (pos.pools, pos.share, pos.ac_share, pos.mode, pos.warning) == ((False, False), 0.0, 0.0, "", "")


def test_verteilungslage_veraltet_bei_poolwechsel_oder_surplus_flag():
    """Die Zuteilung hängt an Pool-Zugehörigkeit und Surplus-Flag (über das Hard-Limit der Zone)."""
    a, b = M("a"), M("b")
    _, g = _group(a, b)
    pos = g.position(a, 50)
    assert (pos.pools, pos.surplus, pos.stale(a)) == ((True, False), False, False)
    a.surplus_active = True
    assert pos.stale(a)
    a.surplus_active, a.discharge = False, False
    assert pos.stale(a)
    a.discharge, a.charge_session = True, "ac_charge"
    assert pos.stale(a)
    a.charge_session = "none"
    assert not pos.stale(a)


def test_zuteilung_allein_im_pool_folgt_dem_hard_limit_der_zone():
    a = M("a", limit=300.0)
    b = M("b", discharge=False)
    _, g = _group(a, b, dist={"global_max_power": 800})
    assert g.position(a, 50).allocated == 300
    a.limit = 800.0
    assert g.position(a, 50).allocated == 800


def test_schwester_laedt_bei_jeder_art_der_lade_session():
    for kind in ("ac_charge", "tariff_charge", "grid_charge"):
        a, b = M("a"), M("b", charge_session=kind)
        _, g = _group(a, b)
        assert g.sister_charging(a) is True
        assert g.sister_charging(b) is False
    b.regulating = False
    assert g.sister_charging(a) is False
