"""Dynamic Offset: σ-Puffer der Netzgruppe, Offset-Formel und wirksamer Offset je Zone."""
from __future__ import annotations

from collections import deque
from typing import Any

from .const import (
    S_STDDEV_WINDOW, S_STDDEV_TRIM_COUNT, S_OFFSET_1, S_OFFSET_2, S_AC_OFFSET,
    S_DYN_Z1_ENABLED, S_DYN_Z1_MIN, S_DYN_Z1_MAX, S_DYN_Z1_NOISE, S_DYN_Z1_FACTOR, S_DYN_Z1_NEGATIVE,
    S_DYN_Z2_ENABLED, S_DYN_Z2_MIN, S_DYN_Z2_MAX, S_DYN_Z2_NOISE, S_DYN_Z2_FACTOR, S_DYN_Z2_NEGATIVE,
    S_DYN_AC_ENABLED, S_DYN_AC_MIN, S_DYN_AC_MAX, S_DYN_AC_NOISE, S_DYN_AC_FACTOR, S_DYN_AC_NEGATIVE,
)
from .pi import clamp as _clamp

# Offset-Parameter je Zone: (Min, Max, Rauschen, Faktor, Negativ) und ihre Casts.
DYN_OFFSETS = {
    "z1": (S_DYN_Z1_MIN, S_DYN_Z1_MAX, S_DYN_Z1_NOISE, S_DYN_Z1_FACTOR, S_DYN_Z1_NEGATIVE),
    "z2": (S_DYN_Z2_MIN, S_DYN_Z2_MAX, S_DYN_Z2_NOISE, S_DYN_Z2_FACTOR, S_DYN_Z2_NEGATIVE),
    "ac": (S_DYN_AC_MIN, S_DYN_AC_MAX, S_DYN_AC_NOISE, S_DYN_AC_FACTOR, S_DYN_AC_NEGATIVE),
}
DYN_CASTS = (int, int, float, float, bool)

# Offset je Anzeigezone: (Enable-Setting, statisches Setting).
OFFSET_SOURCES = {
    "ac": (S_DYN_AC_ENABLED, S_AC_OFFSET),
    "z1": (S_DYN_Z1_ENABLED, S_OFFSET_1),
    "z2": (S_DYN_Z2_ENABLED, S_OFFSET_2),
}


def _stddev_of(values: list[float]) -> float:
    """Populations-Standardabweichung einer Werteliste."""
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return round(variance ** 0.5, 1)


def dynamic_offset(
    stddev: float, min_off: int, max_off: int, noise: float, factor: float, negative: bool,
) -> float:
    """Offset = clamp(min + max(0, (StdDev − Rausch) × Faktor), min, max), mit `negative` negiert.

    Bei `min_off >= max_off` oder negativer StdDev gilt `min_off`.
    """
    if min_off >= max_off:
        result = min_off
    elif stddev < 0:
        result = min_off
    else:
        buf = max(0.0, (stddev - noise) * factor)
        result = _clamp(round(min_off + buf), min_off, max_off)
    return float(result * (-1 if negative else 1))


class Sigma:
    """σ-Puffer einer Netzgruppe: Netzwerte (timestamp, value) im Fenster, σ roh und getrimmt."""

    def __init__(self) -> None:
        self.samples: deque[tuple[float, float]] = deque()
        self.stddev: float = 0.0
        self.stddev_raw: float = 0.0

    def record(self, grid_value: float, now: float, settings: dict) -> None:
        """Netzwert aufnehmen, Werte außerhalb des Fensters verwerfen, σ neu berechnen."""
        cutoff = now - int(settings[S_STDDEV_WINDOW])

        self.samples.append((now, grid_value))

        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()

        n = len(self.samples)
        if n < 2:
            self.stddev = 0.0
            self.stddev_raw = 0.0
            return

        values = [s[1] for s in self.samples]
        self.stddev_raw = _stddev_of(values)

        # Getrimmte StdDev: die `trim` größten und kleinsten Samples im Fenster
        # ausschließen, bevor die Streuung berechnet wird.
        trim = int(settings[S_STDDEV_TRIM_COUNT])
        if trim > 0 and n - 2 * trim >= 2:  # Fallback: mind. 2 Kernwerte nötig, sonst ungetrimmt
            core = sorted(values)[trim: n - trim]
            self.stddev = _stddev_of(core)
        else:
            self.stddev = self.stddev_raw


class DynamicOffset:
    """Dynamic Offset einer Instanz: Kopie von σ aus der Netzgruppe und berechnete Offsets je Zone."""

    def __init__(self) -> None:
        self.stddev: float = 0.0
        self.stddev_raw: float = 0.0
        self.z1: float = 0.0
        self.z2: float = 0.0
        self.ac: float = 0.0

    def update(self, sigma: Sigma, settings: dict) -> None:
        """σ aus der Netzgruppe übernehmen; Offsets aller Zonen neu berechnen, wenn eine Zone dynamisch ist."""
        self.stddev = sigma.stddev
        self.stddev_raw = sigma.stddev_raw
        if not any(settings[enabled_key] for enabled_key, _ in OFFSET_SOURCES.values()):
            return
        for zone, keys in DYN_OFFSETS.items():
            args = (cast(settings[key]) for key, cast in zip(keys, DYN_CASTS))
            setattr(self, zone, dynamic_offset(self.stddev, *args))

    def offset(self, zone: str, settings: dict) -> tuple[bool, Any, float]:
        """(dynamisch, statischer Settings-Wert, wirksamer Offset) der Zone aus OFFSET_SOURCES."""
        enabled_key, static_key = OFFSET_SOURCES[zone]
        dynamic = bool(settings.get(enabled_key, False))
        static = settings.get(static_key)
        return dynamic, static, getattr(self, zone) if dynamic else static

    def value(self, zone: str, settings: dict) -> float:
        """Wirksamer Offset der Zone in W."""
        return float(self.offset(zone, settings)[2])

    @staticmethod
    def zone_of(ac_charge: bool, cycle: bool) -> str:
        """Offsetzone des Regelzustands: AC-Laden `ac`, sonst Zyklus `z1`, sonst `z2`."""
        return "ac" if ac_charge else "z1" if cycle else "z2"
