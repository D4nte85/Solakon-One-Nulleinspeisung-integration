"""Binary sensor platform — diagnostische Zustandsanzeigen (read-only)."""
from __future__ import annotations

from operator import attrgetter

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SolakonCoordinator
from .entity_base import SolakonEntity


class DiagBoolSensor(SolakonEntity, BinarySensorEntity):
    """Zeigt internen Coordinator-Zustand als read-only Binärsensor an.

    `key` ist Suffix der unique_id und `translation_key`; `path` der Attributpfad am
    Coordinator, ohne Angabe gleich `key`.
    """

    def __init__(self, coord: SolakonCoordinator, key: str, icon: str, path: str | None = None) -> None:
        super().__init__(coord, key, translation_key=key, icon=icon)
        self._read = attrgetter(path or key)

    @property
    def is_on(self) -> bool:
        """Wahrheitswert des Coordinator-Attributs."""
        return bool(self._read(self._coordinator))


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    """Diagnose-Binärsensoren der Instanz anlegen."""
    coord: SolakonCoordinator = hass.data[DOMAIN][entry.entry_id]
    add([
        DiagBoolSensor(coord, "cycle_active",               "mdi:battery-arrow-up"),
        DiagBoolSensor(coord, "surplus_active",             "mdi:solar-power"),
        DiagBoolSensor(coord, "is_night",                   "mdi:weather-night"),
        DiagBoolSensor(coord, "forecast_tariff_suppressed", "mdi:weather-sunny", "tariff.suppressed"),
        DiagBoolSensor(coord, "forecast_surplus_forced",    "mdi:weather-sunny-alert", "forecast.surplus_forced"),
        DiagBoolSensor(coord, "forecast_exit_lock",         "mdi:weather-cloudy-clock", "forecast.exit_lock"),
        DiagBoolSensor(coord, "forecast_zone1_forced",      "mdi:weather-night-partly-cloudy", "forecast.zone1_forced"),
    ])
