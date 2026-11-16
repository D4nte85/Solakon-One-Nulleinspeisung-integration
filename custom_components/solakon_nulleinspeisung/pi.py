"""PI-Regler: Integral, Gate, Schritt mit Anti-Windup und Abklingen."""
from __future__ import annotations

from dataclasses import dataclass

from .const import DEVICE_MAX_POWER

# Ergebnisse der Gates.
STEP = "step"            # PI-Schritt ausführen
HOLD = "hold"            # nichts schreiben
SATURATED = "saturated"  # wie HOLD, Ausgang steht am Limit und könnte höher


def clamp(value: float, lo: float, hi: float) -> float:
    """`value` auf [lo, hi] begrenzen."""
    return max(lo, min(hi, value))


def gate_discharge(grid: float, current: float, offset: float, limit: float, tolerance: float) -> str:
    """Gate der Entladeregelung: Totband, Sättigung am Limit, Überschreitung des Limits, Untergrenze.

    Gilt für PI-Schritt und Stellwertrechnung. Über `limit` gibt es auch bei Netzfehler im
    Totband einen Schritt. Bei positivem Netzfehler gilt ein Ausgang über 0 im Totband
    unter `limit` als gesättigt.
    """
    error = grid - offset
    above_limit = current > limit
    near_limit = current >= limit or (current > 0 and current >= limit - tolerance)
    saturated_high = near_limit and not above_limit and error > 0
    if ((abs(error) > tolerance or above_limit)
            and not saturated_high and not (current <= 0 and error < 0)):
        return STEP
    return SATURATED if saturated_high else HOLD


@dataclass(frozen=True)
class PiStep:
    """Eingaben eines PI-Schritts außer dem Netzwert.

    `base` ist die Ausgangsleistung, von der der Schritt ausgeht, `offset` der Ziel-Offset,
    `limit` die Obergrenze, `share` der Poolanteil am Netzfehler, `action` der Aktionstext.
    """

    base: float
    offset: float
    limit: float
    p_factor: float
    i_factor: float
    share: float = 1.0
    action: str = ""


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

    def calculate(self, step: PiStep, grid: float) -> float:
        """PI-Schritt des Entladens mit Anti-Windup via Back-Calculation.

        Die Grenze wird auf DEVICE_MAX_POWER gedeckelt, damit Klemmung und
        Back-Calculation gegen die real erreichbare Grenze rechnen.
        Mit I-Faktor 0 bleibt das Integral 0.
        """
        max_power = min(step.limit, DEVICE_MAX_POWER)
        base, p_factor, i_factor = step.base, step.p_factor, step.i_factor

        raw_error = (grid - step.offset) * step.share

        if raw_error > 0:
            error = min(raw_error, max(0.0, max_power - base))
        else:
            error = max(raw_error, 0 - base)

        integral_candidate = self.integral + error
        correction = error * p_factor + integral_candidate * i_factor
        new_power = base + correction
        final = clamp(new_power, 0, max_power)

        if i_factor != 0:
            integral_candidate = (final - base - error * p_factor) / i_factor
        else:
            integral_candidate = 0.0
        self.integral = clamp(integral_candidate, -max_power, max_power)

        return round(final, 1)
