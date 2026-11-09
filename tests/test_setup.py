"""Setup über async_setup_entry: Trigger auf globale Sensoren der Netzgruppe."""
from __future__ import annotations

import asyncio

from tests import harness as h

DOMAIN = h.const.DOMAIN


def _hass(prefixes: str) -> tuple[h.FakeHass, list[h.FakeEntry]]:
    """Instanzen mit Tarif ohne lokalen Preissensor, globaler Preissensor im Verteilungs-Store."""
    hass = h.FakeHass("de")
    entries = [h.FakeEntry(f"entry_{p}", h.entry_data(p)) for p in prefixes]
    hass.config_entries.entries = entries
    hass.storage[f"{DOMAIN}_distribution"] = {
        "sensor.grid": {"global_tariff_price_sensor": "sensor.preis"}}
    for p in prefixes:
        hass.storage[f"{DOMAIN}_entry_{p}"] = {"tariff_enabled": True}
    return hass, entries


def _triggers(hass: h.FakeHass, prefix: str) -> list[str]:
    return hass.data[DOMAIN][f"entry_{prefix}"].trackers.active()


def test_globaler_sensor_trigger_nach_setup():
    hass, entries = _hass("a")

    async def run():
        await h.integration.async_setup(hass, {})
        await h.integration.async_setup_entry(hass, entries[0])

    asyncio.run(run())
    assert _triggers(hass, "a") == ["tariff"]


def test_globaler_sensor_trigger_bei_parallelem_setup(monkeypatch):
    hass, entries = _hass("ab")
    load = h.ha_stubs.Store.async_load

    async def yielding_load(self):
        # Verteilungs-Store lädt langsamer als die Settings der Instanz.
        for _ in range(5 if self.key.endswith("_distribution") else 1):
            await asyncio.sleep(0)
        return await load(self)

    monkeypatch.setattr(h.ha_stubs.Store, "async_load", yielding_load)

    async def run():
        await h.integration.async_setup(hass, {})
        await asyncio.gather(*(h.integration.async_setup_entry(hass, e) for e in entries))

    asyncio.run(run())
    assert {p: _triggers(hass, p) for p in "ab"} == {"a": ["tariff"], "b": ["tariff"]}


def test_config_schema_nur_ueber_config_entry():
    """async_setup verlangt ein CONFIG_SCHEMA (hassfest config_schema)."""
    assert hasattr(h.integration, "CONFIG_SCHEMA")


def test_number_entitaeten_setzen_settings():
    hass = h.FakeHass("de")
    entry = h.FakeEntry("entry_a", h.entry_data("a"))
    hass.config_entries.entries = [entry]

    async def run():
        await h.integration.async_setup(hass, {})
        await h.integration.async_setup_entry(hass, entry)
        coord = hass.data[DOMAIN]["entry_a"]
        numbers = {e.translation_key: e for e in h.build_entities(hass, coord)
                   if isinstance(e, h.number_mod.SettingNumber)}
        assert set(numbers) == {"target_soc", "target_grid_power", "hard_limit_z0", "hard_limit_z1"}
        assert (numbers["target_soc"].native_value, numbers["target_grid_power"].native_value) == (70, 800)
        assert (numbers["target_grid_power"].native_min_value,
                numbers["target_grid_power"].native_max_value,
                numbers["target_grid_power"].native_step) == (100, 1200, 50)
        await numbers["target_soc"].async_set_native_value(100.0)
        await numbers["target_grid_power"].async_set_native_value(600.0)
        await numbers["hard_limit_z1"].async_set_native_value(400.0)
        await numbers["hard_limit_z0"].async_set_native_value(1000.0)
        return coord

    coord = asyncio.run(run())
    assert (coord.settings["target_soc"], coord.settings["target_grid_power"]) == (100, 600)
    assert (coord.settings["hard_limit_z1"], coord.settings["hard_limit_z0"]) == (400, 1000)
    assert coord.settings_rev == 4
    assert coord.settings["target_charge_enabled"] is False


def _group_setup(entries: list[h.FakeEntry]) -> tuple[h.FakeHass, dict[str, list]]:
    """Instanzen anlegen und ihre number-Plattform in Reihenfolge von `entries` laden; Entitäten je Eintrag."""
    hass = h.FakeHass("de")
    hass.config_entries.entries = list(entries)
    added: dict[str, list] = {e.entry_id: [] for e in entries}

    async def run():
        await h.integration.async_setup(hass, {})
        for entry in entries:
            await h.integration.async_setup_entry(hass, entry)
        for entry in entries:
            await h.number_mod.async_setup_entry(hass, entry, added[entry.entry_id].extend)

    asyncio.run(run())
    return hass, added


def _group_limits(added: dict[str, list]) -> dict[str, list]:
    return {eid: [e for e in ents if isinstance(e, h.number_mod.GroupLimitNumber)] for eid, ents in added.items()}


def test_gesamtlimit_traegt_kleinste_entry_id_und_wechselt_beim_laden():
    hass, added = _group_setup([h.FakeEntry("entry_b", h.entry_data("b")),
                                h.FakeEntry("entry_a", h.entry_data("a"))])
    limits = _group_limits(added)
    first, second = limits["entry_b"][0], limits["entry_a"][0]
    assert first.__dict__.get("removed") is True
    assert second.carrier == "entry_a" and "removed" not in second.__dict__
    assert first.unique_id == second.unique_id == "group_1_global_max_power"
    assert second.device_info["translation_placeholders"] == {"number": "1"}
    assert (second.native_min_value, second.native_max_value, second.native_step) == (0, 9600, 10)


def test_gesamtlimit_setzen_speichert_nur_das_feld_und_stoesst_regelung_an():
    hass, added = _group_setup([h.FakeEntry("entry_a", h.entry_data("a")),
                                h.FakeEntry("entry_b", h.entry_data("b"))])
    entity = _group_limits(added)["entry_a"][0]
    writes = []
    entity.async_write_ha_state = lambda: writes.append(entity.native_value)
    asyncio.run(entity.async_added_to_hass())
    hass.events.clear()
    asyncio.run(entity.async_set_native_value(400.0))
    assert hass.storage[f"{DOMAIN}_distribution"]["sensor.grid"] == {"global_max_power": 400}
    group = h.group_store_mod.group_for(hass, "sensor.grid")
    assert group.dist_cfg()["global_max_power"] == 400 and group.dist_rev == 1
    assert writes == [400]
    assert [e for e in hass.events if e[0] == "task"] == [["task", "SolakonCoordinator._async_regulate"]] * 2
    try:
        asyncio.run(entity.async_set_native_value(-10.0))
    except h.number_mod.InvalidSettings:
        pass
    else:
        raise AssertionError("Wert unter der harten Grenze angenommen")


def test_gesamtlimit_geht_beim_entladen_an_die_naechste_instanz():
    hass, added = _group_setup([h.FakeEntry("entry_a", h.entry_data("a")),
                                h.FakeEntry("entry_b", h.entry_data("b"))])
    entry_a = hass.config_entries.entries[0]
    asyncio.run(h.integration.async_unload_entry(hass, entry_a))
    limits = _group_limits(added)
    assert [e.carrier for e in limits["entry_b"]] == ["entry_b"]
    assert limits["entry_b"][0].unique_id == "group_1_global_max_power"


def test_gruppennummer_fest_je_netzsensor_und_gespeichert():
    other = "sensor.grid_other"
    hass, added = _group_setup([h.FakeEntry("entry_a", h.entry_data("a")),
                                h.FakeEntry("entry_b", h.entry_data("b")),
                                h.FakeEntry("entry_c", h.entry_data("c", grid_sensor=other)),
                                h.FakeEntry("entry_d", h.entry_data("d", grid_sensor=other))])
    limits = _group_limits(added)
    assert limits["entry_a"][0].unique_id == "group_1_global_max_power"
    assert limits["entry_c"][0].unique_id == "group_2_global_max_power"
    assert hass.storage[f"{DOMAIN}_group_numbers"] == {"sensor.grid": 1, "sensor.grid_other": 2}


def _register_group_limit(hass: h.FakeHass, number: int) -> tuple:
    """Gesamtlimit-Entität und Gruppengerät wie aus einem früheren Lauf in den Registrierungen."""
    ents, devs = h.ha_stubs.entity_registry_get(hass), h.ha_stubs.device_registry_get(hass)
    ents.entities[f"number.netzgruppe_{number}"] = ("number", DOMAIN, f"group_{number}_global_max_power")
    devs.devices[f"dev_{number}"] = h.ha_stubs.DeviceEntry(f"dev_{number}", {(DOMAIN, f"group_{number}")})
    return ents, devs


def test_einzelinstanz_bekommt_kein_gesamtlimit():
    hass, added = _group_setup([h.FakeEntry("entry_a", h.entry_data("a")),
                                h.FakeEntry("entry_c", h.entry_data("c", grid_sensor="sensor.grid_other"))])
    assert _group_limits(added) == {"entry_a": [], "entry_c": []}
    assert "sensor.grid" not in hass.storage.get(f"{DOMAIN}_group_numbers", {})


def test_einzelinstanz_raeumt_gesamtlimit_frueherer_laeufe_ab():
    hass = h.FakeHass("de")
    hass.storage[f"{DOMAIN}_group_numbers"] = {"sensor.grid": 1, "sensor.grid_other": 2}
    ents, devs = _register_group_limit(hass, 1)
    _register_group_limit(hass, 2)
    entries = [h.FakeEntry("entry_a", h.entry_data("a")),
               h.FakeEntry("entry_c", h.entry_data("c", grid_sensor="sensor.grid_other")),
               h.FakeEntry("entry_d", h.entry_data("d", grid_sensor="sensor.grid_other"))]
    hass.config_entries.entries = entries

    async def run():
        await h.integration.async_setup(hass, {})
        for entry in entries:
            await h.integration.async_setup_entry(hass, entry)
            await h.number_mod.async_setup_entry(hass, entry, lambda ents: None)

    asyncio.run(run())
    assert list(ents.entities) == ["number.netzgruppe_2"]
    assert list(devs.devices) == ["dev_2"]


def test_loeschen_der_zweiten_instanz_entfernt_gesamtlimit_und_geraet():
    hass, added = _group_setup([h.FakeEntry("entry_a", h.entry_data("a")),
                                h.FakeEntry("entry_b", h.entry_data("b"))])
    ents, devs = _register_group_limit(hass, 1)
    entry_b = hass.config_entries.entries[1]

    async def run():
        await h.integration.async_unload_entry(hass, entry_b)
        hass.config_entries.entries.remove(entry_b)
        await h.integration.async_remove_entry(hass, entry_b)

    asyncio.run(run())
    assert _group_limits(added)["entry_a"][0].__dict__.get("removed") is True
    assert ents.entities == {} and devs.devices == {}
    assert hass.storage[f"{DOMAIN}_group_numbers"] == {"sensor.grid": 1}


def test_gesamtlimit_bei_zwei_eintraegen_auch_wenn_nur_einer_geladen():
    entries = [h.FakeEntry("entry_a", h.entry_data("a")), h.FakeEntry("entry_b", h.entry_data("b"))]
    hass, added = _group_setup(entries[:1])
    hass.config_entries.entries = entries
    asyncio.run(h.number_mod.assign_carrier(hass, "sensor.grid"))
    assert [e.carrier for e in _group_limits(added)["entry_a"]] == ["entry_a"]
