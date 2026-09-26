"""Pfadwahl der PI-Phase: welcher Pfad in diesem Zyklus schreibt, ohne ihn auszuführen."""
from __future__ import annotations

from dataclasses import dataclass

from .ac_charge import setpoint as ac_setpoint
from .pi import SATURATED, STEP, gate_discharge

# Arten der Pfadentscheidung.
FIXED = "fixed"              # Festwert schreiben
AC_SET = "ac_set"            # Stellwert des AC-Ladens schreiben
PI_STEP = "pi_step"          # PI-Schritt ausführen
STALL_CHECK = "stall_check"  # Stillstand prüfen
STALL_RESET = "stall_reset"  # Stillstandszähler zurücksetzen
IDLE = "idle"                # nichts tun


@dataclass(frozen=True)
class PathInputs:
    """Messwerte, Grenzen, Faktoren und Zustandsflags der PI-Phase."""

    grid: float
    current_power: float
    tolerance: float
    surplus_active: bool
    ac_charge_active: bool
    tariff_charge_active: bool
    capped: bool
    zone0_power: float
    tariff_power: float
    ac_offset: float
    ac_limit: float
    ac_min_charge: float
    ac_share: float
    ac_charge: float
    ac_pool_charge: float
    target_offset: float
    dynamic_max: float
    p_factor: float
    i_factor: float
    share: float
    discharge_base: float


@dataclass(frozen=True)
class PiStep:
    """Argumente eines PI-Schritts für `_pi_step`."""

    base: float
    offset: float
    limit: float
    p_factor: float
    i_factor: float
    share: float
    action: str


@dataclass(frozen=True)
class PathDecision:
    """Gewählter Pfad: Art, Festwert oder PI-Schritt, Abklingen des Integrals, Schwester-Hinweis."""

    kind: str
    value: float = 0.0
    action: str = ""
    ac_charge_mode: bool = False
    step: PiStep | None = None
    decay: bool = False
    sister_note: bool = False


def decide(inp: PathInputs) -> PathDecision:
    """Pfad nach Regelzustand: Zone-0-Festwert, AC-Stellwert, Tarif-Festwert oder Entlade-PI."""
    if inp.surplus_active:
        return PathDecision(FIXED, inp.zone0_power, "act_zone0_output")

    if inp.ac_charge_active:
        value = ac_setpoint(inp.grid, inp.ac_charge, inp.ac_pool_charge, inp.current_power,
                            inp.ac_offset, inp.ac_limit, inp.ac_min_charge, inp.ac_share,
                            inp.tolerance)
        if value is None:
            return PathDecision(IDLE)
        return PathDecision(AC_SET, value, "act_ac_setpoint", ac_charge_mode=True)

    if inp.tariff_charge_active:
        return PathDecision(FIXED, inp.tariff_power, "act_tariff_power", ac_charge_mode=True)

    gate = gate_discharge(inp.grid, inp.current_power, inp.target_offset, inp.dynamic_max, inp.tolerance)
    if gate == STEP:
        return PathDecision(PI_STEP, step=PiStep(
            inp.discharge_base, inp.target_offset, inp.dynamic_max, inp.p_factor, inp.i_factor,
            inp.share, "act_pi_sister_charging" if inp.capped else "act_pi",
        ))
    kind = STALL_CHECK if gate == SATURATED else STALL_RESET
    return PathDecision(kind, inp.dynamic_max, decay=True, sister_note=inp.capped)
