"""Number platform — PI integral (diagnostisch, read-only)."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
    add([IntegralNumber(hass.data[DOMAIN][entry.entry_id])])


class IntegralNumber(SolakonEntity, NumberEntity):
    _attr_name = "PI Integral"
    _attr_icon = "mdi:chart-bell-curve"
    _attr_native_min_value = -1000
    _attr_native_max_value = 1000
    _attr_native_step = 0.01
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "integral")

    @property
    def native_value(self) -> float:
        return round(self._coordinator.integral, 2)

    async def async_set_native_value(self, value: float) -> None:
        pass  # read-only — Steuerung erfolgt intern über Coordinator
