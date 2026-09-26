"""PI-Regler: Integral, Gate, Schritt mit Anti-Windup und Abklingen."""
from __future__ import annotations

from .const import DEVICE_MAX_POWER

# Ergebnisse der Gates.
STEP = "step"            # PI-Schritt ausführen
HOLD = "hold"            # nichts schreiben
SATURATED = "saturated"  # wie HOLD, Ausgang steht am Limit und könnte höher


def clamp(value, lo, hi):
    """`value` auf [lo, hi] begrenzen."""
    return max(lo, min(hi, value))


def gate_discharge(grid: float, current: float, offset: float, limit: float, tolerance: float) -> str:
    """Gate des Entlade-PI: Toleranz, Sättigung oben, Überschreitung des Limits, Untergrenze.

    Über `limit` gibt es auch bei Netzfehler in der Toleranz einen Schritt.
    """
    error = grid - offset
    above_limit = current > limit
    saturated_high = current >= limit and not above_limit and error > 0
    if ((abs(error) > tolerance or above_limit)
            and not saturated_high and not (current <= 0 and error < 0)):
        return STEP
    return SATURATED if saturated_high else HOLD


def gate_ac(grid: float, offset: float, tolerance: float) -> str:
    """Gate des AC-Lade-PI: nur Toleranz, keine Guards an den Grenzen."""
    return STEP if abs(grid - offset) > tolerance else HOLD


class PIController:
    """Integral, Rechenschritt und Abklingen."""

    def __init__(self) -> None:
        self.integral: float = 0.0

    def reset(self) -> None:
        """Integral nullen."""
        self.integral = 0.0

    def decay(self) -> None:
        """Integral über 10 um 5 % abklingen lassen."""
        if abs(self.integral) > 10:
            self.integral *= 0.95

    def calculate(
        self,
        grid_power: float,
        current_power: float,
        target_offset: float,
        max_power: float,
        p_factor: float,
        i_factor: float,
        ac_charge_mode: bool = False,
        error_share: float = 1.0,
    ) -> float:
        """PI-Schritt mit modusabhängiger Fehlerrichtung und Anti-Windup via Back-Calculation.

        max_power wird auf DEVICE_MAX_POWER gedeckelt, damit Klemmung und
        Back-Calculation gegen die real erreichbare Grenze rechnen.
        """
        max_power = min(max_power, DEVICE_MAX_POWER)

        if ac_charge_mode:
            raw_error = (target_offset - grid_power) * error_share
        else:
            raw_error = (grid_power - target_offset) * error_share

        if raw_error > 0:
            error = min(raw_error, max(0.0, max_power - current_power))
        else:
            error = max(raw_error, 0 - current_power)

        integral_candidate = self.integral + error
        correction = error * p_factor + integral_candidate * i_factor
        new_power = current_power + correction
        final = clamp(new_power, 0, max_power)

        if i_factor != 0:
            integral_candidate = (final - current_power - error * p_factor) / i_factor
        self.integral = clamp(integral_candidate, -max_power, max_power)

        return round(final, 1)
