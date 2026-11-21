"""Number platform — Settings-Zahlenwerte der Instanz und Gesamtlimit der Netzgruppe."""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import group_store, runtime
from .const import (
    DIST_GLOBAL_MAX, DIST_SCHEMA, DOMAIN, S_HARD_LIMIT_Z0, S_HARD_LIMIT_Z1, S_TARGET_GRID_POWER, S_TARGET_SOC,
    SETTINGS_SCHEMA,
)
from .coordinator import SolakonCoordinator
from .entity_base import SolakonEntity, device_info


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
        return int(self._coordinator.settings[self._key])

    async def async_set_native_value(self, value: float) -> None:
        """Settings-Eintrag setzen."""
        await self._coordinator.async_update_settings({self._key: int(value)})


def _group_device(number: int) -> str:
    """Kennung des Geräts der Netzgruppe `number`."""
    return f"group_{number}"


def _group_limit_uid(number: int) -> str:
    """unique_id der Gesamtlimit-Entität der Netzgruppe `number`."""
    return f"{_group_device(number)}_{DIST_GLOBAL_MAX}"


class GroupLimitNumber(NumberEntity):
    """Gesamtlimit einer Netzgruppe an ihrem eigenen Gerät (Gruppennummer im Namen); `carrier` ist der Config-Entry, der sie führt."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = DIST_GLOBAL_MAX
    _attr_icon = "mdi:transmission-tower-export"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, store: group_store.GroupStore, grid_sensor: str, number: int, carrier: str) -> None:
        self._store = store
        self.grid_sensor = grid_sensor
        self.carrier = carrier
        self._unsub: Callable[[], None] | None = None
        lo, hi, step = DIST_SCHEMA[DIST_GLOBAL_MAX].ui
        self._attr_native_min_value, self._attr_native_max_value, self._attr_native_step = lo, hi, step
        self._attr_unique_id = _group_limit_uid(number)
        self._attr_device_info = device_info(
            _group_device(number), "Netzgruppe",
            translation_key="net_group", translation_placeholders={"number": str(number)},
        )

    @property
    def native_value(self) -> int:
        """Gesamtlimit der Netzgruppe."""
        return int(self._store.dist_view(self.grid_sensor)[DIST_GLOBAL_MAX])

    async def async_set_native_value(self, value: float) -> None:
        """Gesamtlimit der Netzgruppe speichern; InvalidSettings bei verletztem Schema."""
        await self._store.save_dist(self.grid_sensor, {DIST_GLOBAL_MAX: int(value)})

    async def async_added_to_hass(self) -> None:
        """Für gespeicherte Verteilungen der Gruppe anmelden."""
        self._unsub = self._store.listen_dist(self.grid_sensor, self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Abmelden."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None


def _drop_group_limit(hass: Any, grid_sensor: str) -> None:
    """Gesamtlimit-Entität und Gerät der Netzgruppe aus Entitäts- und Geräteregistrierung entfernen."""
    if (number := group_store.require_store(hass).numbers.get(grid_sensor)) is None:
        return
    entities = er.async_get(hass)
    if entity_id := entities.async_get_entity_id("number", DOMAIN, _group_limit_uid(number)):
        entities.async_remove(entity_id)
    devices = dr.async_get(hass)
    identifiers = {(DOMAIN, _group_device(number))}
    # Ab HA 2026.8 async_get_devices; async_get_device ist dort veraltet (bricht in 2027.8).
    if hasattr(devices, "async_get_devices"):
        found = devices.async_get_devices(identifiers=identifiers)
    else:
        found = [device] if (device := devices.async_get_device(identifiers=identifiers)) else []
    for device in found:
        devices.async_remove_device(device.id)


class Carriers:
    """Träger der Gesamtlimit-Entitäten: Hinzufüge-Funktion und Netzsensor je geladenem Eintrag, Entität je Netzsensor.

    Kandidaten sind die Mitglieder der Netzgruppe, deren number-Plattform geladen ist. Zuordnungen
    laufen nacheinander: Zwischen dem Prüfen des Trägers und dem Eintragen der Entität liegen
    Wartepunkte (Entfernen, Vergabe der Gruppennummer).
    """

    def __init__(self, hass: Any) -> None:
        self.hass = hass
        self._adders: dict[str, AddEntitiesCallback] = {}
        self._grid_sensors: dict[str, str] = {}
        self._entities: dict[str, GroupLimitNumber] = {}
        self._lock = asyncio.Lock()

    async def add(self, entry_id: str, add: AddEntitiesCallback, grid_sensor: str) -> None:
        """Geladenen Eintrag mit dem Netzsensor, mit dem er geladen wurde, als möglichen Träger eintragen und den Träger seiner Gruppe bestimmen."""
        self._adders[entry_id] = add
        self._grid_sensors[entry_id] = grid_sensor
        await self.assign(grid_sensor)

    async def assign(self, grid_sensor: str) -> None:
        """Gesamtlimit-Entität der Gruppe an die geladene Mitgliedsinstanz mit der kleinsten entry_id geben.

        Haben weniger als zwei Config-Entries diesen Netzsensor, gibt es keine Netzgruppe: Entität und
        Gerät werden entfernt. Trägt schon die richtige Instanz, bleibt alles, wie es ist. Sonst entfernt
        sie die Entität des bisherigen Trägers und legt sie mit derselben unique_id beim neuen an.
        """
        async with self._lock:
            await self._assign(grid_sensor)

    async def _assign(self, grid_sensor: str) -> None:
        """Zuordnung aus `assign`, nur unter dem Lock aufrufen."""
        store = group_store.require_store(self.hass)
        members = sorted(eid for eid in store.group(grid_sensor).members() if eid in self._adders)
        current = self._entities.get(grid_sensor)
        lone = group_store.configured_members(self.hass, grid_sensor) < 2
        carrier = None if lone or not members else members[0]
        if current is not None and current.carrier == carrier:
            return
        if current is not None:
            await current.async_remove()
        self._entities.pop(grid_sensor, None)
        if lone:
            _drop_group_limit(self.hass, grid_sensor)
        if carrier is None:
            return
        entity = GroupLimitNumber(store, grid_sensor, await store.group_number(grid_sensor), carrier)
        self._entities[grid_sensor] = entity
        self._adders[carrier]([entity])

    async def release(self, entry_id: str) -> None:
        """Entladenen Eintrag austragen und die Netzgruppe, mit der er geladen wurde, neu bewerten.

        Trug er ein Gesamtlimit, übernimmt die nächste Mitgliedsinstanz. Seine Entität entfernt HA
        mit der Plattform; sie wird nur ausgetragen. Beim Löschen der vorletzten Instanz zieht die
        Entität kurz zur Schwester um, bis `async_remove_entry` sie entfernt; das Entladen
        unterscheidet Löschen nicht von Neuladen.
        """
        if self._adders.pop(entry_id, None) is None:
            return
        grid_sensor = self._grid_sensors.pop(entry_id)
        current = self._entities.get(grid_sensor)
        if current is not None and current.carrier == entry_id:
            self._entities.pop(grid_sensor)
        await self.assign(grid_sensor)


def carriers(hass: Any) -> Carriers:
    """Träger-Verwaltung aus dem Laufzeitzustand, bei Bedarf angelegt."""
    rt = runtime.runtime(hass)
    if rt.carriers is None:
        rt.carriers = Carriers(hass)
    return rt.carriers


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
    await carriers(hass).add(entry.entry_id, add, coord.grid_sensor)
