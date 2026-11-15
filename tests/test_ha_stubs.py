"""Attrappen gegen das Verhalten von Home Assistant (helpers/storage.py, async_create_task)."""
from __future__ import annotations

import asyncio

import pytest

from tests import harness as h
from tests.ha_stubs import Store, UnsupportedStorageVersionError


class _V2(Store):
    """Store in Version 2.1, der Version 1 durch Verschachteln hebt."""

    async def _async_migrate_func(self, old_major, old_minor, old_data):
        return {"alt": old_data}


def test_laden_in_aktueller_version_liefert_kopie():
    hass = h.FakeHass()
    h.put_store(hass, "k", {"a": {"b": 1}}, version=2)
    data = asyncio.run(_V2(hass, 2, "k").async_load())
    data["a"]["b"] = 9
    assert h.stored(hass, "k") == {"a": {"b": 1}}


def test_aeltere_version_wird_migriert_und_gespeichert():
    hass = h.FakeHass()
    h.put_store(hass, "k", {"x": 1}, version=1)
    assert asyncio.run(_V2(hass, 2, "k").async_load()) == {"alt": {"x": 1}}
    assert hass.storage["k"]["version"] == 2 and h.stored(hass, "k") == {"alt": {"x": 1}}
    assert [e[0] for e in hass.events] == ["store_save"]


def test_neuere_hauptversion_bricht_ab():
    hass = h.FakeHass()
    h.put_store(hass, "k", {}, version=3)
    with pytest.raises(UnsupportedStorageVersionError):
        asyncio.run(_V2(hass, 2, "k").async_load())


def test_andere_nebenversion_ohne_migration_bleibt():
    hass = h.FakeHass()
    h.put_store(hass, "k", {"x": 1}, version=1, minor_version=2)
    assert asyncio.run(Store(hass, 1, "k").async_load()) == {"x": 1}


def test_verzoegertes_speichern_schreibt_nach_frist_den_stand_beim_schreiben(monkeypatch):
    monkeypatch.setattr(h.CLOCK, "now", h.CLOCK.now)
    hass = h.FakeHass()
    store = Store(hass, 1, "k")
    werte = {"n": 1}
    store.async_delay_save(lambda: dict(werte), 5)
    werte["n"] = 2
    asyncio.run(hass.async_block_till_done())
    assert "k" not in hass.storage
    h.CLOCK.now += 5
    asyncio.run(hass.async_block_till_done())
    assert h.stored(hass, "k") == {"n": 2}


def test_laden_sieht_vorgemerkten_stand_derselben_instanz():
    hass = h.FakeHass()
    store = Store(hass, 1, "k")
    store.async_delay_save(lambda: {"n": 1}, 5)
    assert asyncio.run(store.async_load()) == {"n": 1}
    assert asyncio.run(Store(hass, 1, "k").async_load()) is None


def test_entfernen_verwirft_nur_den_eigenen_auftrag():
    hass = h.FakeHass()
    a, b = Store(hass, 1, "k"), Store(hass, 1, "k")
    a.async_delay_save(lambda: {"von": "a"}, 0)
    asyncio.run(b.async_remove())
    asyncio.run(hass.async_block_till_done())
    assert h.stored(hass, "k") == {"von": "a"}
    asyncio.run(a.async_remove())
    asyncio.run(hass.async_block_till_done())
    assert "k" not in hass.storage


def test_task_laeuft_erst_in_block_till_done_auch_nachgeschobene():
    hass = h.FakeHass()
    lauf = []

    async def zweiter():
        lauf.append(2)

    async def erster():
        lauf.append(1)
        hass.async_create_task(zweiter())

    hass.async_create_task(erster())
    assert lauf == []
    asyncio.run(hass.async_block_till_done())
    assert lauf == [1, 2]
    assert [e[1] for e in hass.events if e[0] == "task"] == [
        "test_task_laeuft_erst_in_block_till_done_auch_nachgeschobene.<locals>.erster",
        "test_task_laeuft_erst_in_block_till_done_auch_nachgeschobene.<locals>.zweiter"]
