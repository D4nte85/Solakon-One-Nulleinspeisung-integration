"""Switch platform — Regelung ein/aus."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, S_REGULATION_ENABLED
from .coordinator import SolakonCoordinator
from .entity_base import SolakonEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coord: SolakonCoordinator = hass.data[DOMAIN][entry.entry_id]
    add([RegulationSwitch(coord)])


class RegulationSwitch(SolakonEntity, SwitchEntity):
    """Hauptschalter — aktiviert/deaktiviert den Schreibteil der Regelung."""
    _attr_name = "Regelung aktiv"
    _attr_icon = "mdi:power"

    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "regulation_enabled")

    @property
    def is_on(self) -> bool:
        return bool(self._coordinator.settings.get(S_REGULATION_ENABLED, False))

    async def async_turn_on(self, **kwargs: object) -> None:
        await self._coordinator.async_update_settings({S_REGULATION_ENABLED: True})

    async def async_turn_off(self, **kwargs: object) -> None:
        await self._coordinator.async_update_settings({S_REGULATION_ENABLED: False})
