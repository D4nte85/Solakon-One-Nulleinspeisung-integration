"""Binärsensor-Plattform: Zustandsflags der Instanz als Diagnose-Entitäten (read-only)."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SolakonCoordinator
from .entity_base import SolakonEntity
from .status_view import status_value


class DiagBoolSensor(SolakonEntity, BinarySensorEntity):
    """Zeigt einen Statuswert der Instanz als read-only Binärsensor an.

    `key` ist Suffix der unique_id, `translation_key` und Name in `status_view.STATUS`.
    """

    def __init__(self, coord: SolakonCoordinator, key: str, icon: str) -> None:
        super().__init__(coord, key, translation_key=key, icon=icon, entity_category=EntityCategory.DIAGNOSTIC)
        self._key = key

    @property
    def is_on(self) -> bool:
        """Wahrheitswert des Statuswerts."""
        return bool(status_value(self._coordinator, self._key))


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    """Diagnose-Binärsensoren der Instanz anlegen."""
    coord: SolakonCoordinator = hass.data[DOMAIN][entry.entry_id]
    add([
        DiagBoolSensor(coord, "cycle_active",               "mdi:battery-arrow-up"),
        DiagBoolSensor(coord, "surplus_active",             "mdi:solar-power"),
        DiagBoolSensor(coord, "is_night",                   "mdi:weather-night"),
        DiagBoolSensor(coord, "forecast_tariff_suppressed", "mdi:weather-sunny"),
        DiagBoolSensor(coord, "forecast_surplus_forced",    "mdi:weather-sunny-alert"),
        DiagBoolSensor(coord, "forecast_exit_lock",         "mdi:weather-cloudy-clock"),
        DiagBoolSensor(coord, "forecast_zone1_forced",      "mdi:weather-night-partly-cloudy"),
    ])
