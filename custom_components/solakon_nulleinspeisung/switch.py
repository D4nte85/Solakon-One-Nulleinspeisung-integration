"""Switch platform — exposes internal boolean states."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
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
    async_add_entities([
        SolakonBoolSwitch(coordinator, "cycle_active",        "Entladezyklus aktiv",   "mdi:battery-arrow-up"),
        SolakonBoolSwitch(coordinator, "surplus_active",      "Zone 0 Überschuss",     "mdi:solar-power"),
        SolakonBoolSwitch(coordinator, "ac_charge_active",    "AC Laden aktiv",        "mdi:lightning-bolt"),
        SolakonBoolSwitch(coordinator, "tariff_charge_active","Tarif-Laden aktiv",     "mdi:currency-eur"),
    ])


class SolakonBoolSwitch(SolakonEntity, SwitchEntity):
    """Read-only status switch — reflects coordinator internal boolean."""

    def __init__(
        self,
        coordinator: SolakonCoordinator,
        attr: str,
        name: str,
        icon: str,
    ) -> None:
        super().__init__(coordinator, attr)
        self._attr_name = name
        self._attr_icon = icon
        self._attr_entity_category = None
        self._bool_attr = attr

    @property
    def is_on(self) -> bool:
        return bool(getattr(self._coordinator, self._bool_attr, False))

    # Read-only — turning on/off from HA UI has no effect
    async def async_turn_on(self, **kwargs) -> None:
        pass

    async def async_turn_off(self, **kwargs) -> None:
        pass
