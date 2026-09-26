"""Stellwertrechnung des AC-Ladens: Ladesollwert auf Ist-Basis in einem Schritt."""
from __future__ import annotations

from .pi import clamp

# Die Rampe läuft, solange die eigene Ist-Ladeleistung mehr als diesen Betrag unter der
# Ausgangsleistung liegt.
RAMP_BAND = 15.0


def setpoint(
    grid: float, own_charge: float, pool_charge: float, output: float,
    offset: float, limit: float, min_charge: float, share: float, tolerance: float,
) -> float | None:
    """Neuer Ladesollwert oder None, wenn nichts zu schreiben ist.

    Stellwert = Anteil × (Ist-Ladeleistung des AC-Pools + Offset − Netz), geklemmt auf
    0 … `limit`; unter der Mindestladeleistung `min_charge` 0, höchstens aber unter `limit`.
    Geschrieben wird bei Netzfehler über der Toleranz oder Ausgangsleistung über `limit`.
    Während die Rampe läuft, wird nur gesenkt.
    """
    if abs(offset - grid) <= tolerance and output <= limit:
        return None
    value = round(clamp((pool_charge + offset - grid) * share, 0, limit))
    if value < min(min_charge, limit):
        value = 0.0
    if own_charge < output - RAMP_BAND and value > output:
        return None
    if abs(value - output) < 0.5:
        return None
    return float(value)
