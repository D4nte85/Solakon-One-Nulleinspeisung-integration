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
    return sorted(hass.data[DOMAIN][f"entry_{prefix}"]._tracker_unsubs)


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
