"""Speichermigrationen: Kapazitätssensor in die Verteilung (2.2), Lade-Flags zur Lade-Session (2.3), Binärsensoren (Entry 1.2)."""
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
    return hass, mig.SolakonSettingsStore(hass, 2, f"{DOMAIN}_entry_a", minor_version=3)


def _migrate(store, major, minor, data):
    return asyncio.run(store._async_migrate_func(major, minor, dict(data)))


def test_kapazitaetssensor_wandert_in_die_verteilung():
    hass, store = _setup()
    out = _migrate(store, 2, 1, {"zone1_limit": 50, mig.OLD_CAPACITY_SENSOR: "sensor.cap_a"})
    assert out == {"zone1_limit": 50, "charge_session": "none"}
    assert hass.storage[DIST_KEY]["sensor.grid"][CAP_KEY] == "sensor.cap_a"


def test_vorhandener_sensor_in_der_verteilung_bleibt():
    hass, store = _setup({"sensor.grid": {CAP_KEY: "sensor.neu"}})
    out = _migrate(store, 2, 1, {mig.OLD_CAPACITY_SENSOR: "sensor.alt"})
    assert mig.OLD_CAPACITY_SENSOR not in out
    assert hass.storage[DIST_KEY]["sensor.grid"][CAP_KEY] == "sensor.neu"


def test_leerer_altschluessel_wird_nur_entfernt():
    hass, store = _setup()
    out = _migrate(store, 2, 1, {mig.OLD_CAPACITY_SENSOR: ""})
    assert out == {"charge_session": "none"}
    assert DIST_KEY not in hass.storage


def test_version_1_durchlaeuft_beide_schritte():
    hass, store = _setup()
    out = _migrate(store, 1, 1, {"hard_limit": 650, mig.OLD_CAPACITY_SENSOR: "sensor.cap_a"})
    assert out == {"hard_limit_z0": 650, "hard_limit_z1": 650, "charge_session": "none"}
    assert hass.storage[DIST_KEY]["sensor.grid"][CAP_KEY] == "sensor.cap_a"


def test_neuere_nebenversion_bleibt_unveraendert():
    _, store = _setup()
    data = {"zone1_limit": 50, mig.OLD_CAPACITY_SENSOR: "sensor.cap_a", "ac_charge_active": True}
    assert _migrate(store, 2, 4, data) == data


def test_ohne_gruppenspeicher_bricht_die_migration_ab():
    """Der Schritt 2.1 → 2.2 wird nicht still übersprungen: HA höbe die Version sonst trotzdem an."""
    hass = h.FakeHass("de")
    store = mig.SolakonSettingsStore(hass, 2, f"{DOMAIN}_entry_a", minor_version=3)
    try:
        _migrate(store, 2, 1, {mig.OLD_CAPACITY_SENSOR: "sensor.cap_a"})
    except RuntimeError as err:
        assert "Gruppenspeicher" in str(err)
    else:
        raise AssertionError("Migration ohne Gruppenspeicher lief durch")


def test_ohne_alten_kapazitaetssensor_braucht_die_migration_keinen_gruppenspeicher():
    hass = h.FakeHass("de")
    store = mig.SolakonSettingsStore(hass, 2, f"{DOMAIN}_entry_a", minor_version=3)
    assert _migrate(store, 2, 1, {"zone1_limit": 50}) == {"zone1_limit": 50, "charge_session": "none"}


def test_ein_lade_flag_wird_zur_art():
    _, store = _setup()
    out = _migrate(store, 2, 2, {"cycle_active": True, "ac_charge_active": False,
                                 "tariff_charge_active": True, "grid_charge_active": False})
    assert out == {"cycle_active": True, "charge_session": "tariff_charge"}


def test_mehrere_lade_flags_ergeben_keine_session():
    _, store = _setup()
    out = _migrate(store, 2, 2, {"ac_charge_active": True, "tariff_charge_active": True})
    assert out == {"charge_session": "none"}


def test_entry_migration_entfernt_die_binaersensoren_der_lade_flags():
    hass = h.FakeHass("de")
    entry = h.FakeEntry("entry_a", h.entry_data("a"))
    entry.version, entry.minor_version = 1, 1
    hass.config_entries.entries = [entry]
    reg = h.ha_stubs.entity_registry_get(hass)
    for key in ("ac_charge_active", "tariff_charge_active", "grid_charge_active", "cycle_active"):
        reg.entities[f"binary_sensor.a_{key}"] = ("binary_sensor", DOMAIN, f"entry_a_{key}")
    assert asyncio.run(mig.async_migrate_entry(hass, entry)) is True
    assert list(reg.entities) == ["binary_sensor.a_cycle_active"]
    assert entry.minor_version == 2
    assert asyncio.run(mig.async_migrate_entry(hass, entry)) is True
    assert list(reg.entities) == ["binary_sensor.a_cycle_active"]
