"""Stellwertrechnung des AC-Ladens: Ladesollwert auf Ist-Basis in einem Schritt."""
from __future__ import annotations

from .pi import clamp

# Kleinste Ladeleistung, die das Gerät ruhig hält; darunter wird 0 geschrieben.
MIN_CHARGE = 50.0
# Die Rampe läuft, solange die eigene Ist-Ladeleistung mehr als diesen Betrag unter der
# Ausgangsleistung liegt.
RAMP_BAND = 15.0


def setpoint(
    grid: float, own_charge: float, pool_charge: float, output: float,
    offset: float, limit: float, share: float, tolerance: float,
) -> float | None:
    """Neuer Ladesollwert oder None, wenn nichts zu schreiben ist.

    Stellwert = Anteil × (Ist-Ladeleistung des AC-Pools + Offset − Netz), geklemmt auf
    0 … `limit`; unter MIN_CHARGE 0. Geschrieben wird bei Netzfehler über der Toleranz
    oder Ausgangsleistung über `limit`. Während die Rampe läuft, wird nur gesenkt.
    """
    if abs(offset - grid) <= tolerance and output <= limit:
        return None
    value = round(clamp((pool_charge + offset - grid) * share, 0, limit))
    if value < MIN_CHARGE:
        value = 0.0
    if own_charge < output - RAMP_BAND and value > output:
        return None
    if abs(value - output) < 0.5:
        return None
    return float(value)
