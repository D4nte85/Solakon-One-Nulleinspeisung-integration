"""Number platform — exposes PI integral value."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
    async_add_entities([SolakonIntegralNumber(coordinator)])


class SolakonIntegralNumber(SolakonEntity, NumberEntity):
    """Read-only number showing the PI integral value."""

    _attr_name          = "PI Integral"
    _attr_icon          = "mdi:chart-line"
    _attr_native_min_value  = -1000
    _attr_native_max_value  = 1000
    _attr_native_step   = 0.01
    _attr_mode          = NumberMode.BOX
    _attr_entity_category = None

    def __init__(self, coordinator: SolakonCoordinator) -> None:
        super().__init__(coordinator, "integral")

    @property
    def native_value(self) -> float:
        return round(self._coordinator.integral, 2)

    # Read-only — coordinator manages the integral exclusively
    async def async_set_native_value(self, value: float) -> None:
        pass
