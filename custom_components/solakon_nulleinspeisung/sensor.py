"""Sensor platform — current zone and last action."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SolakonCoordinator
from .entity_base import SolakonEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SolakonCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        SolakonZoneSensor(coordinator),
        SolakonLastActionSensor(coordinator),
    ])


class SolakonZoneSensor(SolakonEntity, SensorEntity):
    """Current active zone (0–3)."""

    _attr_name        = "Aktuelle Zone"
    _attr_icon        = "mdi:layers"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _ZONE_ICONS = {0: "mdi:solar-power", 1: "mdi:battery-high", 2: "mdi:battery-medium", 3: "mdi:battery-off"}

    def __init__(self, coordinator: SolakonCoordinator) -> None:
        super().__init__(coordinator, "zone")

    @property
    def native_value(self) -> int:
        return self._coordinator.current_zone

    @property
    def icon(self) -> str:
        return self._ZONE_ICONS.get(self._coordinator.current_zone, "mdi:layers")

    @property
    def extra_state_attributes(self) -> dict:
        zone = self._coordinator.current_zone
        labels = {
            0: "Zone 0 — Überschuss-Einspeisung",
            1: "Zone 1 — Aggressive Entladung",
            2: "Zone 2 — Batterieschonend",
            3: "Zone 3 — Sicherheitsstopp",
        }
        return {"zone_label": labels.get(zone, "Unbekannt")}


class SolakonLastActionSensor(SolakonEntity, SensorEntity):
    """Last executed fall / action."""

    _attr_name = "Letzte Aktion"
    _attr_icon = "mdi:information-outline"

    def __init__(self, coordinator: SolakonCoordinator) -> None:
        super().__init__(coordinator, "last_action")

    @property
    def native_value(self) -> str:
        return self._coordinator.last_action
