"""Settings-Schema: Prüfung beim Speichern, Rücksetzen beim Laden, WebSocket-Antworten."""
from __future__ import annotations

import asyncio
import importlib
import json

import pytest

from tests import harness as h
from tests.ha_stubs import ActiveConnection

schema = importlib.import_module(h.PKG + ".schema")
C = h.const
S = C.SETTINGS_SCHEMA
DIST = (C.DIST_SCHEMA, C.DIST_INST_FIELDS)


@pytest.mark.parametrize("key, value, reason", [
    (C.S_HARD_LIMIT_Z0, 0, None),
    (C.S_HARD_LIMIT_Z0, 50, None),
    (C.S_HARD_LIMIT_Z0, 1200, None),
    (C.S_HARD_LIMIT_Z0, 1201, "range"),
    (C.S_HARD_LIMIT_Z0, -1, "range"),
    (C.S_HARD_LIMIT_Z0, 810, None),
    (C.S_DISCHARGE_MAX, 40, None),
    (C.S_DISCHARGE_MAX, 41, "range"),
    (C.S_ZONE1_LIMIT, 101, "range"),
    (C.S_SURPLUS_PV_HYST, 0, None),
    (C.S_SURPLUS_PV_HYST, 5000, None),
    (C.S_SURPLUS_PV_HYST, -10, "range"),
    (C.S_PERIODIC_INTERVAL, 3, None),
    (C.S_PERIODIC_INTERVAL, 0, "range"),
    (C.S_OFFSET_1, -10000, None),
    (C.S_TARIFF_CHEAP_THRESHOLD, -5.0, None),
    (C.S_P_FACTOR, -0.1, "range"),
    (C.S_ZONE1_LIMIT, 50.0, None),
    (C.S_ZONE1_LIMIT, 50.5, "integer"),
    (C.S_P_FACTOR, 1.35, None),
    (C.S_P_FACTOR, 2, None),
    (C.S_P_FACTOR, None, "type"),
    (C.S_TOLERANCE, "15", "type"),
    (C.S_TOLERANCE, True, "type"),
    (C.S_AC_OFFSET, -501, None),
    (C.S_SURPLUS_ENABLED, True, None),
    (C.S_SURPLUS_ENABLED, 1, "type"),
    (C.S_TARIFF_PRICE_SENSOR, "sensor.preis", None),
    (C.S_TARIFF_PRICE_SENSOR, None, "type"),
    ("gibt_es_nicht", 1, "unknown"),
])
def test_check_settings(key, value, reason):
    findings = schema.check({key: value}, S)
    assert [f["reason"] for f in findings] == ([reason] if reason else [])
    if reason == "range":
        assert (findings[0]["min"], findings[0]["max"]) == (S[key].min, S[key].max)


@pytest.mark.parametrize("key, value, reason", [
    ("distribution_mode", "soc_switch", None),
    ("distribution_mode", "weighted", "type"),
    ("global_max_power", 20000, None),
    ("global_max_power", -1, "range"),
    ("soc_switch_divergence", 0, None),
    ("soc_switch_divergence", 101, "range"),
    ("inst_entry_a_capacity_sensor", "sensor.a_capacity", None),
    ("inst_entry_a_capacity_sensor", 5, "type"),
    ("inst_entry_a_soc_sensor", "sensor.a_soc", "unknown"),
])
def test_check_dist(key, value, reason):
    assert [f["reason"] for f in schema.check({key: value}, *DIST)] == ([reason] if reason else [])


def test_standardwerte_im_bereich():
    for s in (S, C.DIST_SCHEMA):
        assert schema.check({k: f.default for k, f in s.items()}, s) == []


def test_sanitize_setzt_standard_und_behaelt_fremde_schluessel():
    stored = {C.S_TARIFF_POWER: 2000, C.S_TOLERANCE: 20, "cycle_active": True}
    clean, reset = schema.sanitize(stored, S)
    assert clean == {C.S_TARIFF_POWER: 800, C.S_TOLERANCE: 20, "cycle_active": True}
    assert reset == [(C.S_TARIFF_POWER, 2000, 800)]
    assert stored[C.S_TARIFF_POWER] == 2000


def test_sanitize_schneidet_kommazahl_in_ganzzahlfeld_ab():
    clean, reset = schema.sanitize({C.S_HARD_LIMIT_Z0: 805.7, C.S_HARD_LIMIT_Z1: 1500.5}, S)
    assert clean == {C.S_HARD_LIMIT_Z0: 805, C.S_HARD_LIMIT_Z1: 800}
    assert reset == [(C.S_HARD_LIMIT_Z1, 1500.5, 800)]


def _coord(hass, stored=None):
    entry = h.FakeEntry("entry_a", h.entry_data("a"))
    if stored is not None:
        hass.storage[f"{C.DOMAIN}_entry_a"] = stored
    coord = h.coordinator_mod.SolakonCoordinator(hass, entry)
    hass.data.setdefault(C.DOMAIN, {})["entry_a"] = coord
    return coord


def test_laden_setzt_zurueck_meldet_und_speichert():
    hass = h.FakeHass("de")
    coord = _coord(hass, {C.S_AC_POWER_LIMIT: 1500, C.S_ZONE1_LIMIT: 60, "cycle_active": True})
    asyncio.run(coord.async_setup())
    assert coord.settings[C.S_AC_POWER_LIMIT] == 800
    assert coord.settings[C.S_ZONE1_LIMIT] == 60
    assert coord.cycle_active is True
    kinds = [e[0] for e in hass.events]
    assert kinds.count("notify") == 1 and kinds.count("store_save") == 1
    notify = next(e for e in hass.events if e[0] == "notify")
    assert notify[1] == f"{C.DOMAIN}_settings_reset_entry_a"
    assert "ac_power_limit (1500 → 800)" in notify[3]


def test_laden_ohne_befund_ohne_meldung():
    hass = h.FakeHass("de")
    coord = _coord(hass, {C.S_ZONE1_LIMIT: 60})
    asyncio.run(coord.async_setup())
    assert [e for e in hass.events if e[0] in ("notify", "store_save")] == []


def test_speichern_weist_ganze_menge_ab():
    hass = h.FakeHass("de")
    coord = _coord(hass, {C.S_REGULATION_ENABLED: True})
    asyncio.run(coord.async_setup())
    before = dict(coord.settings)
    hass.events = []
    changes = {C.S_REGULATION_ENABLED: False, C.S_ZONE1_LIMIT: 60, C.S_HARD_LIMIT_Z0: 5000}
    with pytest.raises(schema.InvalidSettings) as err:
        asyncio.run(coord.async_update_settings(changes))
    assert err.value.findings == [{"key": C.S_HARD_LIMIT_Z0, "reason": "range", "min": 0, "max": 1200}]
    assert coord.settings == before
    assert hass.events == []


def _ws(handler, hass, **msg):
    conn = ActiveConnection()
    asyncio.run(handler(hass, conn, {"id": 1, **msg}))
    return conn.sent


def test_ws_save_config_antwortet_mit_befunden():
    hass = h.FakeHass("de")
    coord = _coord(hass)
    asyncio.run(coord.async_setup())
    sent = _ws(h.integration._ws_save_config, hass, entry_id="entry_a", changes={"x": 1})
    assert sent[0][:3] == ("error", 1, "invalid_settings")
    assert json.loads(sent[0][3]) == [{"key": "x", "reason": "unknown", "min": None, "max": None}]


def test_ws_save_distribution_config_weist_ab():
    hass = h.FakeHass("de")
    h.install_groups(hass, dist_store=h.ha_stubs.Store(hass, 2, "dist"))
    sent = _ws(h.integration._ws_save_distribution_config, hass,
               grid_sensor="sensor.grid", distribution={"distribution_mode": "weighted"})
    assert sent[0][:3] == ("error", 1, "invalid_settings")
    assert "dist" not in hass.storage


def test_verteilung_beim_laden_zurueckgesetzt():
    hass = h.FakeHass("en")
    store = h.install_groups(hass, dist_store=h.ha_stubs.Store(hass, 2, "dist"))
    stored = {"sensor.grid": {"global_max_power": -5, "inst_entry_a_capacity_sensor": "sensor.a"},
              "sensor.other": {"global_max_power": 1000}}
    groups = store._sanitize_dist(stored)
    assert groups["sensor.grid"] == {"global_max_power": 800, "inst_entry_a_capacity_sensor": "sensor.a"}
    assert groups["sensor.other"] == stored["sensor.other"]
    notify = [e for e in hass.events if e[0] == "notify"]
    assert [n[1] for n in notify] == [f"{C.DOMAIN}_dist_reset_sensor.grid"]
    assert "distribution sensor.grid" in notify[0][2]
    assert [e[0] for e in hass.events].count("store_delay_save") == 1


def test_get_schema_liefert_jeden_schluessel():
    sent = _ws(h.integration._ws_get_schema, h.FakeHass("de"))
    result = sent[0][2]
    assert set(result["settings"]) == set(C.SETTINGS_DEFAULTS)
    assert set(result["distribution"]) == set(C.DIST_DEFAULTS)
    assert result["settings"][C.S_HARD_LIMIT_Z0]["max"] == 1200
    assert list(result["settings"][C.S_HARD_LIMIT_Z0]["ui"]) == [100, 1200, 50]
