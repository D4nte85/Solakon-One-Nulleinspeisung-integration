"""Speichermigrationen: Kapazitätssensor aus den Settings in die Verteilung (Settings 2.1 → 2.2)."""
from __future__ import annotations

import asyncio
import importlib

from tests import harness as h

mig = importlib.import_module(h.PKG + ".migrations")
DOMAIN = h.const.DOMAIN
DIST_KEY = f"{DOMAIN}_distribution"
CAP_KEY = "inst_entry_a_capacity_sensor"


def _setup(dist=None):
    """Hass mit einem Eintrag `entry_a` am Netzsensor `sensor.grid` und geladenem Verteilungsspeicher."""
    hass = h.FakeHass("de")
    hass.config_entries.entries = [h.FakeEntry("entry_a", h.entry_data("a"))]
    if dist is not None:
        hass.storage[DIST_KEY] = dist
    asyncio.run(h.group_store_mod.async_load(hass))
    return hass, mig.SolakonSettingsStore(hass, 2, f"{DOMAIN}_entry_a", minor_version=2)


def _migrate(store, major, minor, data):
    return asyncio.run(store._async_migrate_func(major, minor, dict(data)))


def test_kapazitaetssensor_wandert_in_die_verteilung():
    hass, store = _setup()
    out = _migrate(store, 2, 1, {"zone1_limit": 50, mig.OLD_CAPACITY_SENSOR: "sensor.cap_a"})
    assert out == {"zone1_limit": 50}
    assert hass.storage[DIST_KEY]["sensor.grid"][CAP_KEY] == "sensor.cap_a"


def test_vorhandener_sensor_in_der_verteilung_bleibt():
    hass, store = _setup({"sensor.grid": {CAP_KEY: "sensor.neu"}})
    out = _migrate(store, 2, 1, {mig.OLD_CAPACITY_SENSOR: "sensor.alt"})
    assert mig.OLD_CAPACITY_SENSOR not in out
    assert hass.storage[DIST_KEY]["sensor.grid"][CAP_KEY] == "sensor.neu"


def test_leerer_altschluessel_wird_nur_entfernt():
    hass, store = _setup()
    out = _migrate(store, 2, 1, {mig.OLD_CAPACITY_SENSOR: ""})
    assert out == {}
    assert DIST_KEY not in hass.storage


def test_version_1_durchlaeuft_beide_schritte():
    hass, store = _setup()
    out = _migrate(store, 1, 1, {"hard_limit": 650, mig.OLD_CAPACITY_SENSOR: "sensor.cap_a"})
    assert out == {"hard_limit_z0": 650, "hard_limit_z1": 650}
    assert hass.storage[DIST_KEY]["sensor.grid"][CAP_KEY] == "sensor.cap_a"


def test_neuere_nebenversion_bleibt_unveraendert():
    _, store = _setup()
    data = {"zone1_limit": 50, mig.OLD_CAPACITY_SENSOR: "sensor.cap_a", "charge_session": "none"}
    assert _migrate(store, 2, 3, data) == data


def test_ohne_verteilungsspeicher_bleiben_die_settings():
    hass = h.FakeHass("de")
    store = mig.SolakonSettingsStore(hass, 2, f"{DOMAIN}_entry_a", minor_version=2)
    data = {mig.OLD_CAPACITY_SENSOR: "sensor.cap_a"}
    assert _migrate(store, 2, 1, data) == data
