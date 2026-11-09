"""Speichermigrationen: je Speicher eine Store-Klasse, je Version ein Schritt."""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er

from .const import (
    CHARGE_SESSION_KEY, CONF_GRID_SENSOR, DOMAIN, S_HARD_LIMIT_Z0, S_HARD_LIMIT_Z1, S_PV_FORECAST_SENSOR,
    SESSION_AC, SESSION_GRID, SESSION_NONE, SESSION_TARIFF,
)

_LOGGER = logging.getLogger(__name__)

# Settings-Schlüssel des Kapazitätssensors bis v2.1.6; seither je Instanz in der Verteilung.
OLD_CAPACITY_SENSOR = "battery_capacity_sensor"

# Lade-Flags bis Settings 2.2 je Art der Lade-Session; zugleich Unique-ID-Suffix ihrer Binärsensoren.
OLD_SESSION_FLAGS = {
    SESSION_AC: "ac_charge_active",
    SESSION_TARIFF: "tariff_charge_active",
    SESSION_GRID: "grid_charge_active",
}


def _grid_groups(hass: HomeAssistant) -> set[str]:
    """Netzsensoren aller Einträge, einer je Netzgruppe."""
    return {e.data.get(CONF_GRID_SENSOR, "") for e in hass.config_entries.async_entries(DOMAIN)}


def _migrate_dist_mode(cfg: dict) -> dict:
    """Bildet das alte `capacity_weighting`-Bool auf den Drei-Wert-`distribution_mode` ab."""
    if "capacity_weighting" not in cfg:
        return cfg
    migrated = dict(cfg)
    if migrated.pop("capacity_weighting", False):
        migrated["distribution_mode"] = "capacity"
    elif migrated.get("distribution_mode") == "weighted":
        migrated["distribution_mode"] = "soc"
    return migrated


def _settings_v2(data: dict) -> dict:
    """Settings 1 → 2: Hard-Limit auf Zone 0 und Zone 1 aufgeteilt, Forecast-Sensor umbenannt."""
    old_limit = data.pop("hard_limit", 800)
    data.setdefault(S_HARD_LIMIT_Z0, old_limit)
    data.setdefault(S_HARD_LIMIT_Z1, old_limit)

    old_forecast = data.pop("surplus_forecast_sensor", "")
    if old_forecast and not data.get(S_PV_FORECAST_SENSOR):
        data[S_PV_FORECAST_SENSOR] = old_forecast
    return data


async def _capacity_to_dist(hass: HomeAssistant, entry_id: str, data: dict) -> dict:
    """Settings 2.1 → 2.2: Kapazitätssensor der Instanz in die Verteilung ihrer Netzgruppe übernehmen.

    Ein dort schon eingetragener Sensor bleibt. Ohne geladenen Verteilungsspeicher oder
    ohne Eintrag bleiben die Settings unverändert.
    """
    if OLD_CAPACITY_SENSOR not in data:
        return data
    from .group_store import store_for

    store = store_for(hass)
    entry = next((e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id == entry_id), None)
    if store is None or entry is None:
        return data
    migrated = dict(data)
    sensor = migrated.pop(OLD_CAPACITY_SENSOR)
    grid_sensor = entry.data.get(CONF_GRID_SENSOR, "")
    key = f"inst_{entry_id}_capacity_sensor"
    if sensor and not store.dist_view(grid_sensor).get(key):
        await store.save_dist(grid_sensor, {key: sensor})
    return migrated


def _session_from_flags(data: dict) -> dict:
    """Settings 2.2 → 2.3: Lade-Flags zur Art der Lade-Session; mehrere gesetzte Flags ergeben keine."""
    migrated = dict(data)
    kinds = [kind for kind, key in OLD_SESSION_FLAGS.items() if migrated.pop(key, False)]
    if len(kinds) > 1:
        _LOGGER.warning("Solakon: mehrere Lade-Sessions gespeichert (%s), keine übernommen", ", ".join(kinds))
    migrated.setdefault(CHARGE_SESSION_KEY, kinds[0] if len(kinds) == 1 else SESSION_NONE)
    return migrated


class SolakonSettingsStore(Store):
    """Settings-Speicher einer Instanz unter `<DOMAIN>_<entry_id>`."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict
    ) -> dict:
        """Schritte von der gespeicherten Version bis 2.3; neuere Stände bleiben unverändert."""
        if old_major_version < 2:
            old_data = _settings_v2(old_data)
        if (old_major_version, old_minor_version) < (2, 2):
            old_data = await _capacity_to_dist(self.hass, self.key.removeprefix(f"{DOMAIN}_"), old_data)
        if (old_major_version, old_minor_version) < (2, 3):
            old_data = _session_from_flags(old_data)
        return old_data


class SolakonDistStore(Store):
    """Verteilungsspeicher aller Netzgruppen."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict
    ) -> dict:
        """Hebt Version 1 auf 2: flache Form verschachteln, Zwei-Feld-Modus auflösen."""
        if old_major_version >= 2 or not old_data:
            return old_data

        if "distribution_mode" in old_data or "global_max_power" in old_data:
            flat = _migrate_dist_mode(old_data)
            return {gk: dict(flat) for gk in _grid_groups(self.hass)}
        return {gk: _migrate_dist_mode(cfg) for gk, cfg in old_data.items()}


class SolakonSocSwitchStore(Store):
    """Speicher des `soc_switch`-Zustands aller Netzgruppen."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict
    ) -> dict:
        """Hebt Version 1 auf 2: der flache Zustand gilt für jede vorhandene Netzgruppe."""
        if old_major_version >= 2 or not old_data:
            return old_data
        return {gk: dict(old_data) for gk in _grid_groups(self.hass)}


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Config-Entry 1.1 → 1.2: Binärsensoren der Lade-Flags aus der Entitätsregistrierung entfernen."""
    if entry.version == 1 and entry.minor_version < 2:
        registry = er.async_get(hass)
        for key in OLD_SESSION_FLAGS.values():
            if entity_id := registry.async_get_entity_id("binary_sensor", DOMAIN, f"{entry.entry_id}_{key}"):
                registry.async_remove(entity_id)
        hass.config_entries.async_update_entry(entry, minor_version=2)
    return True
