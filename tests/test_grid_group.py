"""Netzgruppe ohne Coordinator: Mitglieder, Pools, Anteile je Modus, soc_switch, Zuteilung."""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests import harness as h

group = importlib.import_module(h.PKG + ".grid_group")
DOMAIN = h.const.DOMAIN


@dataclass(eq=False)
class M:
    """Attrappe für group.Member; zählt SOC-Lesungen."""

    member_id: str
    grid_sensor: str = "sensor.grid"
    regulating: bool = True
    discharge: bool = True
    surplus_active: bool = False
    ac_charge_active: bool = False
    allocated_power: float | None = None
    soc: float | None = 50.0
    limit: float = 800.0
    zone3: float = 20.0
    ac_target: float = 90.0
    capacity: dict = field(default_factory=dict)
    actual: float = 0.0
    setpoint: float = 0.0
    soc_reads: int = 0

    def in_discharge_pool(self):
        return self.regulating and self.discharge

    def soc_reading(self):
        self.soc_reads += 1
        return self.soc

    def hard_limit(self):
        return self.limit

    def zone3_limit(self):
        return self.zone3

    def ac_soc_target(self):
        return self.ac_target

    def capacity_kwh(self, entity_id):
        return self.capacity.get(entity_id)

    def actual_power(self):
        return self.actual

    def output_setpoint(self):
        return self.setpoint


class Hass:
    def __init__(self, *members):
        self.data = {DOMAIN: {m.member_id: m for m in members}}


def _group(*members, dist=None, soc_switch=None, on_change=None):
    hass = Hass(*members)
    return hass, group.NetGroup(hass, "sensor.grid", dist=dist, soc_switch=soc_switch,
                                on_soc_switch_change=on_change)


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
    b = M("b", discharge=False, ac_charge_active=True)
    c = M("c", regulating=False, ac_charge_active=True)
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


def test_ac_actual_summiert_ac_pool():
    a, b = M("a", actual=999), M("b", actual=100)
    c = M("c", actual=-50, discharge=False, ac_charge_active=True)
    _, g = _group(a, b, c)
    assert g.ac_actual(a, -10) == -60


def test_pi_base_pool_mal_anteil():
    a, b = M("a", setpoint=999), M("b", setpoint=100)
    c = M("c", setpoint=50, discharge=False, ac_charge_active=True)
    _, g = _group(a, b, c)
    assert g.pi_base(a, 10, 0.5) == (10 + 100) * 0.5


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
    _, g = _group(a, b, dist=SWITCH)
    s = g.all_shares({"a": a, "b": b}, a, 80, ac=True)
    assert s.mode == "soc"
    assert s.values == pytest.approx({"a": 10 / 70, "b": 60 / 70})
    assert g._soc_switch is None


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
    changes = []
    a, b = M("a"), M("b", soc=70.0)
    _, g = _group(a, b, dist=SWITCH, on_change=lambda st: changes.append(dict(st)))
    assert g.all_shares({"a": a, "b": b}, a, 50).values == {"a": 0.0, "b": 1.0}
    assert g.soc_switch_state() == {"active_id": "b", "start_soc": 70.0, "was_zone0": False}
    assert changes == [{"active_id": "b", "start_soc": 70.0, "was_zone0": False}]


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
    _, g = _group(a, b, dist=SWITCH, soc_switch=_switch_state(active_id="a", start_soc=80.0))
    assert g.soc_switch_shares({"a": a, "b": b}, a, 50) == {"a": 0.0, "b": 1.0}
    state = g.soc_switch_state()
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


def test_zuteilung_einzeln_und_ausserhalb():
    a, b = M("a"), M("b", discharge=False)
    _, g = _group(a, b)
    assert g.distribution(a, 50) == (1.0, None, None)
    assert g.distribution(b, 50) == (0.0, None, None)


def test_zuteilung_steigt_nur_bis_zur_freien_leistung():
    a, b = M("a"), M("b", allocated_power=700)
    _, g = _group(a, b, dist={"distribution_mode": "equal", "global_max_power": 800})
    share, alloc, shares = g.distribution(a, 50)
    assert (share, alloc) == (0.5, 100) and shares.mode == "equal"
    b.allocated_power = 900
    assert g.distribution(a, 50)[1] == 0
    b.allocated_power = None
    assert g.distribution(a, 50)[1] == 400


def test_ac_anteil():
    a, b = M("a", ac_charge_active=True), M("b", ac_charge_active=True)
    _, g = _group(a, b, dist={"distribution_mode": "equal"})
    assert g.ac_share(a, 50) == (0.5, group.Shares({"a": 0.5, "b": 0.5}, "equal"))
    a.ac_charge_active = False
    assert g.ac_share(a, 50) == (0.0, None)
