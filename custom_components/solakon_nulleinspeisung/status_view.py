"""Statusansicht einer Instanz für Panel und Entitäten: ein Leser je Statusschlüssel."""
from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Any, Callable

from .const import S_Z1_NIGHT_ENABLED, capacity_key
from .dynamic_offset import offset_params

if TYPE_CHECKING:
    from .coordinator import SolakonCoordinator


# Leser je Statusschlüssel (interner Name), ohne Live-Sensorwerte.
STATUS: dict[str, Callable[["_Reading"], Any]] = {
    "offset_zone": lambda r: r.offset[0],
    "offset_dynamic": lambda r: r.offset[1],
    "offset_static": lambda r: r.offset[2],
    "offset_value": lambda r: r.offset[3],
    "capacity_kwh": lambda r: r.capacity_kwh(),
    "current_zone": lambda r: r.c.display.zone,
    "zone_label": lambda r: r.c.display.zone_label,
    "mode_key": lambda r: r.c.display.mode_key,
    "mode_label": lambda r: r.c.display.mode_label,
    "last_action": lambda r: r.c.last_action,
    "last_output_ts": lambda r: r.c.out.last_ts,
    "mode_label_ts": lambda r: r.c.display.mode_ts,
    "last_error": lambda r: r.c.last_error,
    "integral": lambda r: round(r.c.integral, 2),
    "cycle_active": lambda r: r.c.cycle_active,
    "surplus_active": lambda r: r.c.surplus_active,
    "charge_session": lambda r: r.c.charge_session,
    "regulation_enabled": lambda r: r.c.regulating,
    "settings_rev": lambda r: r.c.settings_rev,
    "dist_rev": lambda r: r.c.group.dist_rev,
    "grid_stddev": lambda r: r.c.dyn.stddev,
    "grid_stddev_raw": lambda r: r.c.dyn.stddev_raw,
    "active_fall": lambda r: r.c.active_fall,
    "operating_state": lambda r: r.c.display.operating_state,
    "operating_state_ts": lambda r: r.c.display.operating_state_ts,
    "dist_mode_effective": lambda r: r.c.dist_mode_effective,
    "is_night": lambda r: r.c.is_night,
    "forecast_tariff_suppressed": lambda r: r.c.tariff.suppressed,
    "forecast_surplus_forced": lambda r: r.c.forecast.surplus_forced,
    "forecast_exit_lock": lambda r: r.c.forecast.exit_lock,
    "forecast_zone1_forced": lambda r: r.c.forecast.zone1_forced,
    "allocated_power": lambda r: r.c.allocated_power,
}

# Schlüssel des WS-Status: Name im Panel oder Paar (Panel, interner Name).
WS_STATUS_KEYS = (
    ("zone", "current_zone"), "mode_key", "mode_label", "last_action",
    "last_output_ts", "mode_label_ts", "last_error", "integral",
    "cycle_active", "surplus_active", "charge_session", "regulation_enabled",
    ("stddev", "grid_stddev"), ("stddev_raw", "grid_stddev_raw"),
    "active_fall", "operating_state", "dist_mode_effective", "is_night",
    "forecast_tariff_suppressed", "forecast_surplus_forced", "forecast_exit_lock", "forecast_zone1_forced",
    "allocated_power",
    "offset_zone", "offset_dynamic", "offset_static", "offset_value", "capacity_kwh",
    "settings_rev", "dist_rev",
)


class _Reading:
    """Ein Abruf der Statusansicht; die Offsetlage wird höchstens einmal gerechnet."""

    def __init__(self, coord: SolakonCoordinator) -> None:
        self.c = coord

    @cached_property
    def offset(self) -> tuple[str, bool, Any, float]:
        """(Offsetzone, dynamisch, statischer Wert, wirksamer Offset).

        Offsetzone: AC-Laden, sonst Zone 1 bei aktivem Zyklus (bei Dunkelheit Nacht-Offset), sonst Zone 2.
        """
        zone = self.c.offset_zone(self.c.settings[S_Z1_NIGHT_ENABLED])
        return (zone, *self.c.dyn.offset(zone, offset_params(self.c.settings)))

    def capacity_kwh(self) -> float | None:
        """Kapazität in kWh aus dem Verteilungs-Sensor der Instanz, None ohne gültigen Wert."""
        sensor = str(self.c.group.dist_cfg().get(capacity_key(self.c.entry.entry_id), ""))
        return self.c.capacity_kwh(sensor) if sensor else None


def status_value(coord: SolakonCoordinator, name: str) -> Any:
    """Ein Statuswert unter seinem internen Namen."""
    return STATUS[name](_Reading(coord))


def snapshot_view(coord: SolakonCoordinator, names: tuple[str | tuple[str, str], ...]) -> dict[str, Any]:
    """Statuswerte zu `names`; ein Paar (außen, innen) benennt den Schlüssel um."""
    reading = _Reading(coord)
    pairs = (n if isinstance(n, tuple) else (n, n) for n in names)
    return {outer: STATUS[inner](reading) for outer, inner in pairs}
