"""Number platform — Settings-Zahlenwerte der Instanz und Gesamtlimit der Netzgruppe."""
from __future__ import annotations

from typing import Any, Callable

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import group_store
from .const import (
    DIST_SCHEMA, DOMAIN, S_HARD_LIMIT_Z0, S_HARD_LIMIT_Z1, S_TARGET_GRID_POWER, S_TARGET_SOC,
    SETTINGS_SCHEMA, VERSION,
)
from .coordinator import SolakonCoordinator
from .entity_base import SolakonEntity
from .schema import InvalidSettings

GROUP_LIMIT_KEY = "global_max_power"
# `hass.data`-Schlüssel (ohne DOMAIN-Präfix) der Träger-Verwaltung, entfernt mit der letzten Instanz.
DATA_KEY = "group_limit"


class SettingNumber(SolakonEntity, NumberEntity):
    """Setzt einen ganzzahligen Settings-Eintrag der Instanz; Bereich und Schritt aus dem Panelfeld."""

    def __init__(self, coord: SolakonCoordinator, key: str, unit: str, icon: str) -> None:
        lo, hi, step = SETTINGS_SCHEMA[key].ui
        super().__init__(
            coord, key, translation_key=key, icon=icon, native_unit_of_measurement=unit,
            native_min_value=lo, native_max_value=hi, native_step=step,
            mode=NumberMode.BOX, entity_category=EntityCategory.CONFIG,
        )
        self._key = key

    @property
    def native_value(self) -> int:
        """Wert des Settings-Eintrags."""
        return int(self._coordinator.settings.get(self._key, SETTINGS_SCHEMA[self._key].default))

    async def async_set_native_value(self, value: float) -> None:
        """Settings-Eintrag setzen."""
        await self._coordinator.async_update_settings({self._key: int(value)})


class GroupLimitNumber(NumberEntity):
    """Gesamtlimit einer Netzgruppe an ihrem eigenen Gerät (Gruppennummer im Namen); `carrier` ist der Config-Entry, der sie führt."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = GROUP_LIMIT_KEY
    _attr_icon = "mdi:transmission-tower-export"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, store: group_store.GroupStore, grid_sensor: str, number: int, carrier: str) -> None:
        self._store = store
        self.grid_sensor = grid_sensor
        self.carrier = carrier
        self._unsub: Callable[[], None] | None = None
        lo, hi, step = DIST_SCHEMA[GROUP_LIMIT_KEY].ui
        self._attr_native_min_value, self._attr_native_max_value, self._attr_native_step = lo, hi, step
        self._attr_unique_id = f"group_{number}_{GROUP_LIMIT_KEY}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"group_{number}")},
            "translation_key": "net_group",
            "translation_placeholders": {"number": str(number)},
            "manufacturer": "D4nte",
            "model": "Netzgruppe",
            "sw_version": VERSION,
        }

    @property
    def native_value(self) -> int:
        """Gesamtlimit der Netzgruppe."""
        return int(self._store.dist_view(self.grid_sensor)[GROUP_LIMIT_KEY])

    async def async_set_native_value(self, value: float) -> None:
        """Gesamtlimit der Netzgruppe speichern; InvalidSettings bei verletztem Schema."""
        if findings := await self._store.save_dist(self.grid_sensor, {GROUP_LIMIT_KEY: int(value)}):
            raise InvalidSettings(findings)

    async def async_added_to_hass(self) -> None:
        """Für gespeicherte Verteilungen der Gruppe anmelden."""
        self._unsub = self._store.listen_dist(self.grid_sensor, self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Abmelden."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None


def _carriers(hass: Any) -> dict[str, Any]:
    """Träger-Verwaltung aus `hass.data`: `adders` je geladenem Eintrag, `entities` je Netzsensor."""
    return hass.data.setdefault(f"{DOMAIN}_{DATA_KEY}", {"adders": {}, "entities": {}})


def _drop_group_limit(hass: Any, grid_sensor: str) -> None:
    """Gesamtlimit-Entität und Gerät der Netzgruppe aus Entitäts- und Geräteregistrierung entfernen."""
    store = group_store.store_for(hass)
    if store is None or (number := store.numbers.get(grid_sensor)) is None:
        return
    entities = er.async_get(hass)
    if entity_id := entities.async_get_entity_id("number", DOMAIN, f"group_{number}_{GROUP_LIMIT_KEY}"):
        entities.async_remove(entity_id)
    devices = dr.async_get(hass)
    if device := devices.async_get_device(identifiers={(DOMAIN, f"group_{number}")}):
        devices.async_remove_device(device.id)


async def assign_carrier(hass: Any, grid_sensor: str) -> None:
    """Gesamtlimit-Entität der Gruppe an die geladene Mitgliedsinstanz mit der kleinsten entry_id geben.

    Haben weniger als zwei Config-Entries diesen Netzsensor, gibt es keine Netzgruppe: Entität und
    Gerät werden entfernt. Trägt schon die richtige Instanz, bleibt alles, wie es ist. Sonst entfernt
    sie die Entität des bisherigen noch geladenen Trägers und legt sie mit derselben unique_id beim
    neuen Träger an.
    """
    reg = _carriers(hass)
    members = sorted(eid for eid, (_, coord) in reg["adders"].items() if coord.grid_sensor == grid_sensor)
    current = reg["entities"].get(grid_sensor)
    if group_store.configured_members(hass, grid_sensor) < 2:
        if current is not None and current.carrier in reg["adders"]:
            await current.async_remove()
        reg["entities"].pop(grid_sensor, None)
        _drop_group_limit(hass, grid_sensor)
        return
    if not members:
        reg["entities"].pop(grid_sensor, None)
        return
    carrier = members[0]
    if current is not None and current.carrier == carrier:
        return
    if current is not None and current.carrier in reg["adders"]:
        await current.async_remove()
    store = group_store.store_for(hass)
    entity = GroupLimitNumber(store, grid_sensor, await store.group_number(grid_sensor), carrier)
    reg["entities"][grid_sensor] = entity
    reg["adders"][carrier][0]([entity])


async def release_carrier(hass: Any, entry_id: str) -> None:
    """Entladenen Eintrag austragen; trug er ein Gesamtlimit, übernimmt die nächste Mitgliedsinstanz."""
    reg = _carriers(hass)
    if (gone := reg["adders"].pop(entry_id, None)) is None:
        return
    grid_sensor = gone[1].grid_sensor
    current = reg["entities"].get(grid_sensor)
    if current is not None and current.carrier == entry_id:
        reg["entities"].pop(grid_sensor)
    await assign_carrier(hass, grid_sensor)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    """Zahlenwerte der Instanz anlegen und die Instanz als möglichen Träger des Gesamtlimits eintragen."""
    coord: SolakonCoordinator = hass.data[DOMAIN][entry.entry_id]
    add([
        SettingNumber(coord, S_TARGET_SOC,        PERCENTAGE,      "mdi:battery-charging-high"),
        SettingNumber(coord, S_TARGET_GRID_POWER, UnitOfPower.WATT, "mdi:transmission-tower-import"),
        SettingNumber(coord, S_HARD_LIMIT_Z0,     UnitOfPower.WATT, "mdi:solar-power"),
        SettingNumber(coord, S_HARD_LIMIT_Z1,     UnitOfPower.WATT, "mdi:battery-arrow-down"),
    ])
    _carriers(hass)["adders"][entry.entry_id] = (add, coord)
    await assign_carrier(hass, coord.grid_sensor)
