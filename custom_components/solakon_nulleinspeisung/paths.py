"""Pfadwahl der PI-Phase: welcher Pfad in diesem Zyklus schreibt, ohne ihn auszuführen."""
from __future__ import annotations

from dataclasses import dataclass

from . import setpoint
from .const import MODE_DISCHARGE, SESSION_AC, SESSION_GRID, SESSION_TARIFF
from .limits import PowerLimits
from .pi import SATURATED, STEP, PiStep, gate_discharge
from .schema import CycleSettings

# Arten der Pfadentscheidung.
FIXED = "fixed"              # Festwert schreiben
SETPOINT = "setpoint"        # Stellwert der Stellwertrechnung schreiben
PI_STEP = "pi_step"          # PI-Schritt ausführen
STALL_CHECK = "stall_check"  # Stillstand prüfen
STALL_RESET = "stall_reset"  # Stillstandszähler zurücksetzen
IDLE = "idle"                # nichts tun


@dataclass(frozen=True)
class PathInputs:
    """Schnappschuss, Grenzen, Zustand, Messwerte, Offsets und Anteile der PI-Phase.

    `cap_reason` ist der Grund des PV-Deckels laut `limits.pv_cap_reason`, leer ohne Deckel;
    `decide` schaltet ihn auf Zyklus und Modus '1'.
    """

    cs: CycleSettings
    limits: PowerLimits
    mode: str
    cycle_active: bool
    surplus_active: bool
    session: str
    cap_reason: str
    grid: float
    solar: float
    current_power: float
    ac_offset: float
    target_offset: float
    ac_share: float
    share: float
    ac_charge: float
    ac_pool_charge: float
    discharge: float
    discharge_pool: float
    discharge_base: float


@dataclass(frozen=True)
class PathDecision:
    """Gewählter Pfad: Art, Festwert oder Stellwert, PI-Schritt, Grenze der Stillstandsprüfung,
    Abklingen des Integrals, Aktionsschlüssel des Hinweises auf den PV-Deckel."""

    kind: str
    value: float = 0.0
    action: str = ""
    ac_charge_mode: bool = False
    step: PiStep | None = None
    decay: bool = False
    cap_action: str = ""
    limit: float = 0.0


def decide(inp: PathInputs) -> PathDecision:
    """Pfad nach Regelzustand: Zone-0-Festwert, AC-Stellwert, Tarif- oder Netz-Lade-Festwert oder Entladen.

    Entladen schreibt nach dem Gate einen PI-Schritt, bei ausgeschaltetem `pi_enabled`
    stattdessen den Stellwert auf Ist-Basis (Bedarf Netz − Offset, ohne Mindestleistung).
    Obergrenze ist `limits.pi_max`. Der PV-Deckel gilt im Zyklus in Modus '1' und wählt
    über seinen Grund (`sister_charging`, `house_priority`) den Aktionstext.
    """
    cs, limits = inp.cs, inp.limits
    if inp.surplus_active:
        return PathDecision(FIXED, limits.zone0, "act_zone0_output")

    if inp.session == SESSION_AC:
        value = setpoint.ac(inp.grid, inp.ac_charge, inp.ac_pool_charge, inp.current_power,
                            inp.ac_offset, limits.ac, cs.ac_min_power, inp.ac_share,
                            cs.tolerance)
        if value is None:
            return PathDecision(IDLE)
        return PathDecision(SETPOINT, value, "act_ac_setpoint", ac_charge_mode=True)

    if inp.session == SESSION_TARIFF:
        return PathDecision(FIXED, cs.tariff_power, "act_tariff_power", ac_charge_mode=True)

    if inp.session == SESSION_GRID:
        return PathDecision(FIXED, cs.grid_charge_power, "act_grid_charge_power", ac_charge_mode=True)

    capped = inp.cap_reason if inp.cycle_active and inp.mode == MODE_DISCHARGE else ""
    dynamic_max = limits.pi_max(inp.cycle_active, inp.solar, bool(inp.cap_reason))
    gate = gate_discharge(inp.grid, inp.current_power, inp.target_offset, dynamic_max, cs.tolerance)
    if gate == STEP and not cs.pi_enabled:
        value = setpoint.value(inp.grid - inp.target_offset, inp.discharge, inp.discharge_pool,
                               inp.current_power, dynamic_max, 0.0, inp.share)
        if value is None:
            return PathDecision(IDLE)
        action = f"act_discharge_setpoint_{capped}" if capped else "act_discharge_setpoint"
        return PathDecision(SETPOINT, value, action)
    if gate == STEP:
        return PathDecision(PI_STEP, step=PiStep(
            inp.discharge_base, inp.target_offset, dynamic_max, cs.p_factor, cs.i_factor,
            inp.share, f"act_pi_{capped}" if capped else "act_pi",
        ))
    kind = STALL_CHECK if gate == SATURATED else STALL_RESET
    return PathDecision(kind, limit=inp.current_power, decay=True,
                        cap_action=f"act_zone1_{capped}" if capped else "")
