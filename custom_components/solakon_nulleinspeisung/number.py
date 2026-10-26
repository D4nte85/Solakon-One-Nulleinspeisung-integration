"""Number platform — Settings-Zahlenwerte der Instanz."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, S_TARGET_GRID_POWER, S_TARGET_SOC, SETTINGS_SCHEMA
from .coordinator import SolakonCoordinator
from .entity_base import SolakonEntity


class SettingNumber(SolakonEntity, NumberEntity):
    """Setzt einen ganzzahligen Settings-Eintrag der Instanz; Bereich und Schritt aus dem Panelfeld."""

    def __init__(self, coord: SolakonCoordinator, key: str, unit: str, icon: str) -> None:
        lo, hi, step = SETTINGS_SCHEMA[key].ui
        super().__init__(
            coord, key, translation_key=key, icon=icon, native_unit_of_measurement=unit,
            native_min_value=lo, native_max_value=hi, native_step=step,
            mode=NumberMode.BOX, entity_category=EntityCategory.CONFIG,
        )
        self._key = key

    @property
    def native_value(self) -> int:
        """Wert des Settings-Eintrags."""
        return int(self._coordinator.settings.get(self._key, SETTINGS_SCHEMA[self._key].default))

    async def async_set_native_value(self, value: float) -> None:
        """Settings-Eintrag setzen."""
        await self._coordinator.async_update_settings({self._key: int(value)})


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    """Zahlenwerte der Instanz anlegen."""
    coord: SolakonCoordinator = hass.data[DOMAIN][entry.entry_id]
    add([
        SettingNumber(coord, S_TARGET_SOC,        PERCENTAGE,      "mdi:battery-charging-high"),
        SettingNumber(coord, S_TARGET_GRID_POWER, UnitOfPower.WATT, "mdi:transmission-tower-import"),
    ])
