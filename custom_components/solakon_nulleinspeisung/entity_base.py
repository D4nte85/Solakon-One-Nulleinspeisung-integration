"""Base entity class for Solakon ONE entities."""
from __future__ import annotations

from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import SolakonCoordinator


class SolakonEntity(Entity):
    """Base class — wired to coordinator, updates on state change."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: SolakonCoordinator, unique_suffix: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{unique_suffix}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": "Solakon ONE",
            "manufacturer": "D4nte",
            "model": "Nulleinspeisung",
            "sw_version": "1.0.0",
        }

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_entity_listener(self._on_coordinator_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator._entity_listeners = [
            cb for cb in self._coordinator._entity_listeners if cb is not self._on_coordinator_update
        ]

    def _on_coordinator_update(self) -> None:
        self.async_write_ha_state()
