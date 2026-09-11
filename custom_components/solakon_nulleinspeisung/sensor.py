"""Sensor platform — Betriebszustand, zone, mode label, last action, StdDev."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, OPERATING_STATES
from .coordinator import SolakonCoordinator
from .entity_base import SolakonEntity

_ZONE_ICONS = {
    0: "mdi:solar-power",
    1: "mdi:battery-high",
    2: "mdi:battery-medium",
    3: "mdi:battery-off-outline",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coord: SolakonCoordinator = hass.data[DOMAIN][entry.entry_id]
    add([
        OperatingStateSensor(coord),
        ZoneSensor(coord),
        ModeTextSensor(coord),
        LastActionSensor(coord),
        GridStdDevSensor(coord),
        ActiveFallSensor(coord),
        IntegralSensor(coord),
        SurplusPowerSensor(coord),
    ])


_STATE_ICONS = {
    "disabled":         "mdi:power-off",
    "blocked":          "mdi:alert-circle-outline",
    "exporting":        "mdi:transmission-tower-export",
    "tariff_charging":  "mdi:currency-eur",
    "ac_charging":      "mdi:lightning-bolt",
    "discharge_locked": "mdi:lock-clock",
    "night_off":        "mdi:weather-night",
    "discharging":      "mdi:battery-arrow-up",
    "safety_stop":      "mdi:battery-off-outline",
    "idle":             "mdi:sleep",
}


class OperatingStateSensor(SolakonEntity, SensorEntity):
    """Was die Instanz gerade tut — ein Zustand aus OPERATING_STATES.

    Abgegrenzt zu `ActiveFallSensor`: der haelt den zuletzt ausgefuehrten
    Uebergang, dieser den aktuell geltenden Zustand.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = OPERATING_STATES
    _attr_translation_key = "operating_state"

    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "operating_state")

    @property
    def native_value(self) -> str | None:
        return self._coordinator.operating_state or None

    @property
    def icon(self) -> str:
        return _STATE_ICONS.get(self._coordinator.operating_state, "mdi:state-machine")

    @property
    def extra_state_attributes(self) -> dict:
        coord = self._coordinator
        return {
            "zone": coord.current_zone,
            "zone_label": coord.zone_label,
            "device_mode": coord.mode_label,
            "last_fall": coord.active_fall,
            "last_action": coord.last_action,
            "last_error": coord.last_error,
            "changed_at": dt_util.utc_from_timestamp(coord.operating_state_ts).isoformat(),
        }


class ZoneSensor(SolakonEntity, SensorEntity):
    _attr_name = "Aktuelle Zone"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "zone")

    @property
    def native_value(self) -> int:
        return self._coordinator.current_zone

    @property
    def icon(self) -> str:
        return _ZONE_ICONS.get(self._coordinator.current_zone, "mdi:layers")

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "zone_label": self._coordinator.zone_label,
            "last_action": self._coordinator.last_action,
            "last_error": self._coordinator.last_error,
            "integral": round(self._coordinator.integral, 2),
            "regulation_enabled": self._coordinator.settings.get("regulation_enabled", False),
        }
_FALL_LABELS: dict[str, str] = {
    "0A": "Zone 0: Überschuss Start",
    "0B": "Zone 0: Überschuss Ende",
    "A":  "Zone 1: Entladezyklus Start",
    "B":  "Zone 3: Stopp (Zyklus aktiv)",
    "C":  "Zone 3: Stopp",
    "D":  "Recovery: Modus wiederhergestellt",
    "E":  "Zone 2: Regelung aktiv",
    "F":  "Nacht: Abschaltung",
    "G":  "AC Laden: Start",
    "H":  "AC Laden: Ende",
    "I":  "Safety: Modus-Korrektur",
    "GT": "Tarif-Laden: Start",
    "HT": "Tarif-Laden: Ende",
    "TM": "Discharge-Lock: Preis zu hoch",
}


class ActiveFallSensor(SolakonEntity, SensorEntity):
    _attr_name = "Aktiver Fall"
    _attr_icon = "mdi:state-machine"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "active_fall")

    @property
    def native_value(self) -> str:
        return _FALL_LABELS.get(self._coordinator.active_fall, self._coordinator.active_fall)

    @property
    def extra_state_attributes(self) -> dict:
        return {"fall_id": self._coordinator.active_fall}


class ModeTextSensor(SolakonEntity, SensorEntity):
    _attr_name = "Betriebsmodus"
    _attr_icon = "mdi:information-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "mode_label")

    @property
    def native_value(self) -> str:
        return self._coordinator.mode_label


class LastActionSensor(SolakonEntity, SensorEntity):
    _attr_name = "Letzte Aktion"
    _attr_icon = "mdi:history"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "last_action")

    @property
    def native_value(self) -> str:
        return self._coordinator.last_action


class GridStdDevSensor(SolakonEntity, SensorEntity):
    """Netz-Standardabweichung — intern berechnet aus Grid-Messwert-Stream."""
    _attr_name = "Netz-Standardabweichung"
    _attr_icon = "mdi:chart-bell-curve-cumulative"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 1

    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "grid_stddev")

    @property
    def native_value(self) -> float:
        return self._coordinator.grid_stddev

    @property
    def extra_state_attributes(self) -> dict:
        s = self._coordinator.settings
        dyn = any(s.get(k, False) for k in ("dyn_z1_enabled", "dyn_z2_enabled", "dyn_ac_enabled"))
        attrs = {
            "window_seconds": s.get("stddev_window", 60),
            "sample_count": len(self._coordinator._grid_samples),
            "trim_count": s.get("stddev_trim_count", 0),
            "stddev_raw": self._coordinator.grid_stddev_raw,
            "dynamic_offset_active": dyn,
        }
        if dyn:
            attrs["dyn_offset_z1"] = self._coordinator.dyn_offset_z1
            attrs["dyn_offset_z2"] = self._coordinator.dyn_offset_z2
            attrs["dyn_offset_ac"] = self._coordinator.dyn_offset_ac
        return attrs


class IntegralSensor(SolakonEntity, SensorEntity):
    _attr_name = "PI Integral"
    _attr_icon = "mdi:chart-bell-curve"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "integral")

    @property
    def native_value(self) -> float:
        return round(self._coordinator.integral, 1)


class SurplusPowerSensor(SolakonEntity, SensorEntity):
    """Verwertbarer PV-Überschuss — Luft zwischen aktuellem Output und dem
    Minimum aus Hard-Limit und aktueller PV-Leistung. Für Automationen gedacht
    (z. B. Zusatzverbraucher schalten), daher bewusst keine Diagnose-Entität."""
    _attr_name = "Überschussleistung"
    _attr_icon = "mdi:transmission-tower-export"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "surplus_power")

    @property
    def native_value(self) -> float:
        return round(self._coordinator.surplus_power, 0)
