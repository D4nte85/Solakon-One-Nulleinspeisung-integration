"""Base entity for Solakon ONE."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import Entity

from .const import DOMAIN, VERSION
from .coordinator import SolakonCoordinator


def device_info(identifier: str, model: str, **fields: Any) -> dict[str, Any]:
    """Geräteinfo eines Geräts der Integration: Kennung, Hersteller, Modell, Softwarestand und `fields`."""
    return {
        "identifiers": {(DOMAIN, identifier)},
        "manufacturer": "D4nte",
        "model": model,
        "sw_version": VERSION,
        **fields,
    }


class SolakonEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: SolakonCoordinator, suffix: str, **attrs: Any) -> None:
        """`suffix` ergänzt die unique_id; `attrs` setzt `_attr_<name>`."""
        self._coordinator = coordinator
        for name, value in attrs.items():
            setattr(self, f"_attr_{name}", value)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{suffix}"
        self._attr_device_info = device_info(
            coordinator.entry.entry_id, "Nulleinspeisung",
            name=coordinator.instance_name,
        )

    async def async_added_to_hass(self) -> None:
        """Beim Coordinator als Listener anmelden."""
        self._coordinator.register_entity_listener(self._on_update)

    async def async_will_remove_from_hass(self) -> None:
        """Beim Coordinator abmelden."""
        self._coordinator.unregister_entity_listener(self._on_update)

    def _on_update(self) -> None:
        """Zustand nach HA schreiben."""
        self.async_write_ha_state()
