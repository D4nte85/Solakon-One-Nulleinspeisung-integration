"""Stellwertrechnung: Sollwert auf Ist-Basis in einem Schritt, für AC-Laden und Entladen."""
from __future__ import annotations

from .pi import clamp

# Die Rampe läuft, solange die eigene Ist-Leistung mehr als diesen Betrag unter der
# Ausgangsleistung liegt.
RAMP_BAND = 15.0


def value(
    demand: float, own: float, pool: float, output: float,
    limit: float, min_power: float, share: float,
) -> float | None:
    """Neuer Sollwert oder None, wenn nichts zu schreiben ist.

    Stellwert = Anteil × (Ist-Leistung des Pools + Bedarf), geklemmt auf 0 … `limit`;
    unter `min_power` 0, höchstens aber unter `limit`. Während die Rampe läuft, wird nur gesenkt.
    """
    result = round(clamp((pool + demand) * share, 0, limit))
    if result < min(min_power, limit):
        result = 0.0
    if own < output - RAMP_BAND and result > output:
        return None
    if abs(result - output) < 0.5:
        return None
    return float(result)


def ac(
    grid: float, own_charge: float, pool_charge: float, output: float,
    offset: float, limit: float, min_charge: float, share: float, tolerance: float,
) -> float | None:
    """Ladesollwert des AC-Ladens oder None, wenn nichts zu schreiben ist.

    Bedarf = Offset − Netz, Basis ist die Ist-Ladeleistung des AC-Pools, Schwelle die
    Mindestladeleistung `min_charge`. Geschrieben wird bei Netzfehler über der Toleranz
    oder Ausgangsleistung über `limit`.
    """
    if abs(offset - grid) <= tolerance and output <= limit:
        return None
    return value(offset - grid, own_charge, pool_charge, output, limit, min_charge, share)
