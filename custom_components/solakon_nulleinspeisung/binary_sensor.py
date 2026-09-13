"""Binary sensor platform — diagnostische Zustandsanzeigen (read-only)."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SolakonCoordinator
from .entity_base import SolakonEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coord: SolakonCoordinator = hass.data[DOMAIN][entry.entry_id]
    add([
        DiagBoolSensor(coord, "cycle_active",               "mdi:battery-arrow-up"),
        DiagBoolSensor(coord, "surplus_active",             "mdi:solar-power"),
        DiagBoolSensor(coord, "ac_charge_active",           "mdi:lightning-bolt"),
        DiagBoolSensor(coord, "tariff_charge_active",       "mdi:currency-eur"),
        DiagBoolSensor(coord, "is_night",                   "mdi:weather-night"),
        DiagBoolSensor(coord, "forecast_tariff_suppressed", "mdi:weather-sunny"),
        DiagBoolSensor(coord, "forecast_surplus_forced",    "mdi:weather-sunny-alert"),
        DiagBoolSensor(coord, "forecast_exit_lock",         "mdi:weather-cloudy-clock"),
        DiagBoolSensor(coord, "zone1_forced",               "mdi:weather-night-partly-cloudy"),
    ])


class DiagBoolSensor(SolakonEntity, BinarySensorEntity):
    """Zeigt internen Coordinator-Zustand als read-only Binärsensor an."""

    def __init__(self, coord: SolakonCoordinator, attr: str, icon: str) -> None:
        super().__init__(coord, attr, translation_key=attr, icon=icon)
        self._attr = attr

    @property
    def is_on(self) -> bool:
        return bool(getattr(self._coordinator, self._attr, False))
