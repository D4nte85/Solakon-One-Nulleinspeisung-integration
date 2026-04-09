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
        DiagBoolSensor(coord, "cycle_active",         "Entladezyklus aktiv", "mdi:battery-arrow-up"),
        DiagBoolSensor(coord, "surplus_active",       "Überschuss-Modus",    "mdi:solar-power"),
        DiagBoolSensor(coord, "ac_charge_active",     "AC Laden aktiv",      "mdi:lightning-bolt"),
        DiagBoolSensor(coord, "tariff_charge_active", "Tarif-Laden aktiv",   "mdi:currency-eur"),
        DiagBoolSensor(coord, "is_night",             "Nachtabschaltung",    "mdi:weather-night"),
        DiagBoolSensor(coord, "forecast_tariff_suppressed", "PV-Vorhersage: Tarif gesperrt", "mdi:weather-sunny"),
    ])


class DiagBoolSensor(SolakonEntity, BinarySensorEntity):
    """Zeigt internen Coordinator-Zustand als read-only Binärsensor an."""
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coord: SolakonCoordinator, attr: str, name: str, icon: str
    ) -> None:
        super().__init__(coord, attr)
        self._attr_name = name
        self._attr_icon = icon
        self._attr = attr

    @property
    def is_on(self) -> bool:
        return bool(getattr(self._coordinator, self._attr, False))
