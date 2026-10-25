"""Statusansicht einer Instanz für Panel und Sensoren: Anzeigezustand unter internen Namen."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .const import S_DYN_AC_ENABLED, S_DYN_Z1_ENABLED, S_DYN_Z2_ENABLED, S_REGULATION_ENABLED

if TYPE_CHECKING:
    from .coordinator import SolakonCoordinator


def snapshot(coord: SolakonCoordinator) -> dict[str, Any]:
    """Anzeigezustand unter internen Namen, ohne Live-Sensorwerte.

    Offsetzone: AC-Laden, sonst Zone 1 bei aktivem Zyklus (bei Dunkelheit Nacht-Offset), sonst Zone 2.
    Kapazität in kWh aus dem Verteilungs-Sensor der Instanz, None ohne gültigen Wert.
    """
    offset_zone = coord.offset_zone()
    offset_dynamic, offset_static, offset_value = coord.dyn.offset(offset_zone, coord.settings)
    cap_sensor = str(coord.group.dist_cfg().get(f"inst_{coord.entry.entry_id}_capacity_sensor", ""))
    return {
        "offset_zone": offset_zone,
        "offset_dynamic": offset_dynamic,
        "offset_static": offset_static,
        "offset_value": offset_value,
        "capacity_kwh": coord.capacity_kwh(cap_sensor) if cap_sensor else None,
        "current_zone": coord.display.zone,
        "zone_label": coord.display.zone_label,
        "mode_key": coord.display.mode_key,
        "mode_label": coord.display.mode_label,
        "last_action": coord.last_action,
        "last_action_ts": coord.last_action_ts,
        "last_output_ts": coord.out.last_ts,
        "mode_label_ts": coord.display.mode_ts,
        "last_error": coord.last_error,
        "integral": round(coord.integral, 2),
        "cycle_active": coord.cycle_active,
        "surplus_active": coord.surplus_active,
        "ac_charge_active": coord.ac_charge_active,
        "tariff_charge_active": coord.tariff_charge_active,
        "grid_charge_active": coord.grid_charge_active,
        "regulation_enabled": coord.settings.get(S_REGULATION_ENABLED, False),
        "grid_stddev": coord.dyn.stddev,
        "grid_stddev_raw": coord.dyn.stddev_raw,
        "dyn_z1_enabled": coord.settings.get(S_DYN_Z1_ENABLED, False),
        "dyn_z2_enabled": coord.settings.get(S_DYN_Z2_ENABLED, False),
        "dyn_ac_enabled": coord.settings.get(S_DYN_AC_ENABLED, False),
        "dyn_offset_z1": coord.dyn.z1,
        "dyn_offset_z1_night": coord.dyn.z1_night,
        "dyn_offset_z2": coord.dyn.z2,
        "dyn_offset_ac": coord.dyn.ac,
        "active_fall": coord.active_fall,
        "operating_state": coord.display.operating_state,
        "operating_state_ts": coord.display.operating_state_ts,
        "discharge_locked": coord.discharge_locked,
        "dist_mode_effective": coord.dist_mode_effective,
        "is_night": coord.is_night,
        "forecast_tariff_suppressed": coord.forecast_tariff_suppressed,
        "forecast_surplus_forced": coord.forecast_surplus_forced,
        "forecast_exit_lock": coord.forecast_exit_lock,
        "allocated_power": coord.allocated_power,
    }


def snapshot_view(coord: SolakonCoordinator, names: tuple[str | tuple[str, str], ...]) -> dict[str, Any]:
    """Auswahl aus `snapshot`; ein Paar (außen, innen) benennt den Schlüssel um."""
    snap = snapshot(coord)
    pairs = (n if isinstance(n, tuple) else (n, n) for n in names)
    return {outer: snap[inner] for outer, inner in pairs}
