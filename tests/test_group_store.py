"""Speicher der Netzgruppen: Laden, Speichern, Register und Entfernen."""
from __future__ import annotations

import asyncio

from tests import harness as h

gs = h.group_store_mod
DOMAIN = h.const.DOMAIN
DIST_KEY = f"{DOMAIN}_distribution"
SWITCH_KEY = f"{DOMAIN}_soc_switch_state"
SWITCH = {"distribution_mode": "soc_switch", "soc_switch_divergence": 5}


class M:
    """Minimales Mitglied für Pools und `soc_switch`."""

    surplus_active = False
    ac_charge_active = False

    def __init__(self, member_id, grid_sensor="sensor.grid", soc=50.0):
        self.member_id, self.grid_sensor, self.soc = member_id, grid_sensor, soc
        self.regulating = True

    def soc_reading(self):
        return self.soc


def _hass(*members):
    hass = h.FakeHass("de")
    hass.data[DOMAIN] = {m.member_id: m for m in members}
    return hass


def _load(hass):
    return asyncio.run(gs.async_load(hass))


def test_register_eine_gruppe_je_netzsensor():
    hass = _hass()
    assert gs.group_for(hass, "sensor.grid") is gs.group_for(hass, "sensor.grid")
    assert gs.group_for(hass, "sensor.grid") is not gs.group_for(hass, "sensor.other")


def test_gruppe_bekommt_gespeicherten_zustand():
    hass = _hass()
    hass.storage[DIST_KEY] = {"sensor.grid": SWITCH}
    hass.storage[SWITCH_KEY] = {"sensor.grid": {"active_id": "a", "start_soc": 60}}
    _load(hass)
    g = gs.group_for(hass, "sensor.grid")
    assert g.dist_cfg()["distribution_mode"] == "soc_switch"
    assert g.soc_switch_state() == {"active_id": "a", "start_soc": 60, "was_zone0": False}


def test_paralleles_laden_einmal_und_alle_warten():
    hass = _hass()
    hass.storage[DIST_KEY] = {"sensor.grid": SWITCH}
    loads = []
    load = h.ha_stubs.Store.async_load

    async def yielding_load(self):
        loads.append(self.key)
        for _ in range(3):
            await asyncio.sleep(0)
        return await load(self)

    async def run():
        h.ha_stubs.Store.async_load = yielding_load
        try:
            return await asyncio.gather(gs.async_load(hass), gs.async_load(hass))
        finally:
            h.ha_stubs.Store.async_load = load

    first, second = asyncio.run(run())
    assert first is second
    assert second.dist == {"sensor.grid": SWITCH}
    assert loads == [DIST_KEY, SWITCH_KEY]


def test_soc_switch_zustand_je_gruppe_und_gespeichert():
    a, b, x = M("a"), M("b", soc=70.0), M("x", grid_sensor="sensor.other", soc=90.0)
    hass = _hass(a, b, x)
    hass.storage[DIST_KEY] = {"sensor.grid": SWITCH, "sensor.other": SWITCH}
    _load(hass)
    gs.group_for(hass, "sensor.grid").soc_switch_shares({"a": a, "b": b}, a, 50)
    gs.group_for(hass, "sensor.other").soc_switch_shares({"x": x}, x, 90.0)
    saves = [e for e in hass.events if e[0] == "store_delay_save" and e[1] == SWITCH_KEY]
    assert {g: st["active_id"] for g, st in saves[-1][2]["rest"].items()} == {
        "sensor.grid": "b", "sensor.other": "x"}


def test_speichern_erreicht_gruppe_und_behaelt_gruppe_ohne_instanz():
    hass = _hass()
    hass.storage[DIST_KEY] = {"sensor.frei": {"distribution_mode": "soc"}}
    store = _load(hass)
    g = gs.group_for(hass, "sensor.grid")
    assert asyncio.run(store.save_dist("sensor.grid", {"distribution_mode": "capacity"})) == []
    assert g.dist_cfg()["distribution_mode"] == "capacity"
    assert hass.storage[DIST_KEY] == {
        "sensor.frei": {"distribution_mode": "soc"}, "sensor.grid": {"distribution_mode": "capacity"}}
    assert store.dist_view("sensor.frei")["distribution_mode"] == "soc"


def test_speichern_mit_befund_aendert_nichts():
    hass = _hass()
    store = _load(hass)
    g = gs.group_for(hass, "sensor.grid")
    assert asyncio.run(store.save_dist("sensor.grid", {"distribution_mode": "weighted"}))
    assert g.dist is None and DIST_KEY not in hass.storage


def test_entfernen_loescht_beide_stores():
    hass = _hass()
    hass.storage[DIST_KEY] = {"sensor.grid": SWITCH}
    hass.storage[SWITCH_KEY] = {"sensor.grid": {"active_id": "a"}}
    asyncio.run(gs.async_remove(hass))
    assert DIST_KEY not in hass.storage and SWITCH_KEY not in hass.storage
