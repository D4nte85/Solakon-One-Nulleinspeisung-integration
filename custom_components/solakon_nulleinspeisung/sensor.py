"""Sensor platform — Betriebszustand, zone, mode label, last action, StdDev."""
from __future__ import annotations

from typing import Any, Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, FALL_KEYS, MODE_KEYS, OPERATING_STATES
from .coordinator import SolakonCoordinator
from .entity_base import SolakonEntity

# Attribute aus dem Coordinator-Schnappschuss: Name oder Paar (Attribut, Schnappschuss).
OPERATING_STATE_ATTRS = (
    ("zone", "current_zone"), "zone_label", ("device_mode", "mode_label"),
    ("last_fall", "active_fall"), "last_action", "last_error", ("changed_at", "operating_state_ts"),
)
ZONE_ATTRS = ("zone_label", "last_action", "last_error", "integral", "regulation_enabled")

_ZONE_ICONS = {
    0: "mdi:solar-power",
    1: "mdi:battery-high",
    2: "mdi:battery-medium",
    3: "mdi:battery-off-outline",
}

_STATE_ICONS = {
    "disabled":         "mdi:power-off",
    "blocked":          "mdi:alert-circle-outline",
    "exporting":        "mdi:transmission-tower-export",
    "tariff_charging":  "mdi:currency-eur",
    "ac_charging":      "mdi:lightning-bolt",
    "discharge_locked": "mdi:lock-clock",
    "night_off":        "mdi:weather-night",
    "battery_supply":   "mdi:battery-arrow-up",
    "safety_stop":      "mdi:battery-off-outline",
    "pv_direct":        "mdi:solar-power-variant",
}

# Gemeinsame Entity-Attribute der Sensortabelle.
DIAG = {"entity_category": EntityCategory.DIAGNOSTIC}
POWER = {"native_unit_of_measurement": UnitOfPower.WATT, "state_class": SensorStateClass.MEASUREMENT}


def _enum(options: list[str]) -> dict:
    """Attribute eines ENUM-Sensors mit den erlaubten Zuständen `options`."""
    return {"device_class": SensorDeviceClass.ENUM, "options": options}


class CoordinatorSensor(SolakonEntity, SensorEntity):
    """Sensor mit Wert `value_fn(coordinator)`; `key` ist unique_id-Suffix und translation_key."""

    def __init__(
        self, coord: SolakonCoordinator, key: str,
        value_fn: Callable[[SolakonCoordinator], Any], **attrs: Any,
    ) -> None:
        super().__init__(coord, key, translation_key=key, **attrs)
        self._value_fn = value_fn

    @property
    def native_value(self) -> Any:
        """Wert aus `value_fn`."""
        return self._value_fn(self._coordinator)


class OperatingStateSensor(CoordinatorSensor):
    """Was die Instanz gerade tut — ein Zustand aus OPERATING_STATES.

    Abgegrenzt zu `active_fall`: der haelt den zuletzt ausgefuehrten
    Uebergang, dieser den aktuell geltenden Zustand.
    """

    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "operating_state", lambda c: c.operating_state or None,
                         **_enum(OPERATING_STATES))

    @property
    def icon(self) -> str:
        return _STATE_ICONS.get(self._coordinator.operating_state, "mdi:state-machine")

    @property
    def extra_state_attributes(self) -> dict:
        attrs = self._coordinator.snapshot_view(OPERATING_STATE_ATTRS)
        attrs["changed_at"] = dt_util.utc_from_timestamp(attrs["changed_at"]).isoformat()
        return attrs


class ZoneSensor(CoordinatorSensor):
    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "zone", lambda c: c.current_zone,
                         state_class=SensorStateClass.MEASUREMENT, **DIAG)

    @property
    def icon(self) -> str:
        return _ZONE_ICONS.get(self._coordinator.current_zone, "mdi:layers")

    @property
    def extra_state_attributes(self) -> dict:
        return self._coordinator.snapshot_view(ZONE_ATTRS)


class LastActionSensor(CoordinatorSensor):
    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "last_action", lambda c: c.last_action, icon="mdi:history", **DIAG)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "action_key": self._coordinator.last_action_key,
            **self._coordinator.last_action_params,
        }


class GridStdDevSensor(CoordinatorSensor):
    """Netz-Standardabweichung — intern berechnet aus Grid-Messwert-Stream."""

    def __init__(self, coord: SolakonCoordinator) -> None:
        super().__init__(coord, "grid_stddev", lambda c: c.grid_stddev,
                         icon="mdi:chart-bell-curve-cumulative", suggested_display_precision=1,
                         **POWER, **DIAG)

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


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    coord: SolakonCoordinator = hass.data[DOMAIN][entry.entry_id]
    add([
        OperatingStateSensor(coord),
        ZoneSensor(coord),
        CoordinatorSensor(coord, "mode_label", lambda c: c.mode_key,
                          icon="mdi:information-outline", **_enum(MODE_KEYS), **DIAG),
        LastActionSensor(coord),
        GridStdDevSensor(coord),
        CoordinatorSensor(coord, "active_fall", lambda c: c.active_fall or None,
                          icon="mdi:state-machine", **_enum(FALL_KEYS), **DIAG),
        CoordinatorSensor(coord, "integral", lambda c: round(c.integral, 1),
                          icon="mdi:chart-bell-curve", suggested_display_precision=1, **POWER, **DIAG),
        # Für Automationen gedacht (z. B. Zusatzverbraucher schalten), daher keine Diagnose-Entität.
        CoordinatorSensor(coord, "surplus_power", lambda c: round(c.surplus_power, 0),
                          icon="mdi:transmission-tower-export", suggested_display_precision=0, **POWER),
    ])
