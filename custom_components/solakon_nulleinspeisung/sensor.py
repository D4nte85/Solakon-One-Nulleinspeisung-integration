"""Sensor platform — zone, mode label, last action (diagnostisch)."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SolakonCoordinator
from .entity_base import SolakonEntity

_ZONE_ICONS = {
    0: "mdi:solar-power",
    1: "mdi:battery-high",
    2: "mdi:battery-medium",
    3: "mdi:battery-off-outline",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coord: SolakonCoordinator = hass.data[DOMAIN][entry.entry_id]
    add([
        ZoneSensor(coord),
        ModeTextSensor(coord),
        LastActionSensor(coord),
    ])


class ZoneSensor(SolakonEntity, SensorEntity):
    _attr_name = "Aktuelle Zone"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "zone")

    @property
    def native_value(self) -> int:
        return self._coordinator.current_zone

    @property
    def icon(self) -> str:
        return _ZONE_ICONS.get(self._coordinator.current_zone, "mdi:layers")

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "zone_label": self._coordinator.zone_label,
            "last_action": self._coordinator.last_action,
            "last_error": self._coordinator.last_error,
            "integral": round(self._coordinator.integral, 2),
            "regulation_enabled": self._coordinator.settings.get("regulation_enabled", False),
        }


class ModeTextSensor(SolakonEntity, SensorEntity):
    _attr_name = "Betriebsmodus"
    _attr_icon = "mdi:information-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "mode_label")

    @property
    def native_value(self) -> str:
        return self._coordinator.mode_label


class LastActionSensor(SolakonEntity, SensorEntity):
    _attr_name = "Letzte Aktion"
    _attr_icon = "mdi:history"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "last_action")

    @property
    def native_value(self) -> str:
        return self._coordinator.last_action
