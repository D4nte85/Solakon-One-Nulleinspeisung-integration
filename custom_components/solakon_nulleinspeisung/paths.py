"""Pfadwahl der PI-Phase: welcher Pfad in diesem Zyklus schreibt, ohne ihn auszuführen."""
from __future__ import annotations

from dataclasses import dataclass

from .pi import SATURATED, STEP, gate_ac, gate_discharge

# Arten der Pfadentscheidung.
FIXED = "fixed"              # Festwert schreiben
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
    ac_p: float
    ac_i: float
    ac_share: float
    ac_base: float
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
    ac_charge_mode: bool = False


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
    """Pfad nach Regelzustand: Zone-0-Festwert, AC-PI, Tarif-Festwert oder Entlade-PI."""
    if inp.surplus_active:
        return PathDecision(FIXED, inp.zone0_power, "act_zone0_output")

    if inp.ac_charge_active:
        if gate_ac(inp.grid, inp.ac_offset, inp.tolerance) != STEP:
            return PathDecision(IDLE, decay=True)
        return PathDecision(PI_STEP, step=PiStep(
            inp.ac_base, inp.ac_offset, inp.ac_limit, inp.ac_p, inp.ac_i, inp.ac_share,
            "act_ac_pi", ac_charge_mode=True,
        ))

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
