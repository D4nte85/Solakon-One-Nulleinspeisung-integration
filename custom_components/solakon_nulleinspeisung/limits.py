"""Leistungsgrenzen einer Instanz: Zonen, PI-Phase, AC-Laden, Export-Limit."""
from __future__ import annotations

from dataclasses import dataclass

from .const import DEVICE_MAX_POWER, MODE_AC_CHARGE


@dataclass(frozen=True)
class PowerLimits:
    """Grenzen eines Zyklus in W.

    `zone0` und `zone12` sind die Hard-Limits, gedeckelt auf Gerätegrenze und
    zugeteilte Leistung. `ac` ist die AC-Ladegrenze auf Gerätegrenze, `export` der
    Sollwert des Export-Limits aus den Panel-Werten.
    """

    zone0: int
    zone12: int
    ac: int
    export: int
    pv_reserve: int

    def zone_max(self, surplus_active: bool) -> int:
        """Hard-Limit der aktuellen Zone: Zone 0 bei Überschuss, sonst Zone 1/2."""
        return self.zone0 if surplus_active else self.zone12

    def pi_max(self, mode: str, cycle_active: bool, solar: float) -> float:
        """Obergrenze des PI: AC-Grenze in Modus '3', Zone-1/2-Limit mit Zyklus, sonst zusätzlich PV minus Reserve."""
        if mode == MODE_AC_CHARGE:
            return self.ac
        if cycle_active:
            return self.zone12
        return min(self.zone12, max(0, solar - self.pv_reserve))


def power_limits(
    *, hard_limit_z0: int, hard_limit_z1: int, ac_power_limit: int, pv_reserve: int,
    allocated: float | None,
) -> PowerLimits:
    """Grenzen aus den Panel-Werten und der zugeteilten Leistung; `None` ohne Zuteilung."""
    def cap(limit: int) -> int:
        """`limit` gedeckelt auf Gerätemaximum und, falls vorhanden, auf die Zuteilung."""
        if allocated is None:
            return int(min(limit, DEVICE_MAX_POWER))
        return int(min(int(allocated), limit, DEVICE_MAX_POWER))

    return PowerLimits(
        zone0=cap(hard_limit_z0),
        zone12=cap(hard_limit_z1),
        ac=int(min(ac_power_limit, DEVICE_MAX_POWER)),
        export=max(hard_limit_z0, hard_limit_z1),
        pv_reserve=pv_reserve,
    )
