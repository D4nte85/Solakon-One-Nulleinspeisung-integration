"""Switch platform — Settings-Schalter der Instanz."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, S_REGULATION_ENABLED, S_TARIFF_ENABLED
from .coordinator import SolakonCoordinator
from .entity_base import SolakonEntity


class SettingSwitch(SolakonEntity, SwitchEntity):
    """Schaltet einen booleschen Settings-Eintrag der Instanz."""

    def __init__(self, coord: SolakonCoordinator, key: str, icon: str) -> None:
        super().__init__(coord, key, translation_key=key, icon=icon)
        self._key = key

    @property
    def is_on(self) -> bool:
        """Wahrheitswert des Settings-Eintrags."""
        return bool(self._coordinator.settings.get(self._key, False))

    async def async_turn_on(self, **kwargs: object) -> None:
        """Settings-Eintrag setzen."""
        await self._coordinator.async_update_settings({self._key: True})

    async def async_turn_off(self, **kwargs: object) -> None:
        """Settings-Eintrag löschen."""
        await self._coordinator.async_update_settings({self._key: False})


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    """Schalter der Instanz anlegen."""
    coord: SolakonCoordinator = hass.data[DOMAIN][entry.entry_id]
    add([
        SettingSwitch(coord, S_REGULATION_ENABLED, "mdi:power"),
        SettingSwitch(coord, S_TARIFF_ENABLED,     "mdi:currency-eur"),
    ])
