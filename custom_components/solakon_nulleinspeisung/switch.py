"""Switch platform — internal boolean states (read-only)."""
from __future__ import annotations
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
from .coordinator import SolakonCoordinator
from .entity_base import SolakonEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    coord: SolakonCoordinator = hass.data[DOMAIN][entry.entry_id]
    add([
        BoolSwitch(coord, "cycle_active",         "Entladezyklus aktiv",  "mdi:battery-arrow-up"),
        BoolSwitch(coord, "surplus_active",        "Überschuss-Modus",     "mdi:solar-power"),
        BoolSwitch(coord, "ac_charge_active",      "AC Laden aktiv",       "mdi:lightning-bolt"),
        BoolSwitch(coord, "tariff_charge_active",  "Tarif-Laden aktiv",    "mdi:currency-eur"),
    ])


class BoolSwitch(SolakonEntity, SwitchEntity):
    def __init__(self, coord: SolakonCoordinator, attr: str, name: str, icon: str) -> None:
        super().__init__(coord, attr)
        self._attr_name = name
        self._attr_icon = icon
        self._attr = attr

    @property
    def is_on(self) -> bool:
        return bool(getattr(self._coordinator, self._attr, False))

    async def async_turn_on(self, **_: object) -> None:
        pass

    async def async_turn_off(self, **_: object) -> None:
        pass
