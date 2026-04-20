"""Base entity for Solakon ONE."""
from __future__ import annotations

from homeassistant.helpers.entity import Entity

from .const import DOMAIN, CONF_INSTANCE_NAME
from .coordinator import SolakonCoordinator


class SolakonEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: SolakonCoordinator, suffix: str) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{suffix}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": coordinator.entry.data.get(CONF_INSTANCE_NAME, "Solakon ONE"),
            "manufacturer": "D4nte",
            "model": "Nulleinspeisung v2.0.1",
        }

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_entity_listener(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_entity_listener(self._on_update)

    def _on_update(self) -> None:
        self.async_write_ha_state()
