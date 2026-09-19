"""Netzgruppe: Instanzen am selben Netzsensor, ihr geteilter Zustand und die Leistungsverteilung."""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .const import DIST_DEFAULTS, DOMAIN

# Warnschlüssel bei Rückfall des Verteilungsmodus, je Grund: (Entlade-Pool, AC-Pool).
# soc_switch kommt nur im Entlade-Pool vor.
DIST_WARNINGS = {
    "soc_switch": ("warn_dist_soc_switch_sensor", ""),
    "capacity": ("warn_dist_capacity_sensor", "warn_ac_dist_capacity_sensor"),
    "soc": ("warn_dist_soc_sensor", "warn_ac_dist_soc_sensor"),
}


class Member(Protocol):
    """Lesefläche einer Instanz für ihre Netzgruppe; Sensoren werden erst beim Aufruf gelesen."""

    surplus_active: bool
    ac_charge_active: bool
    allocated_power: float | None

    @property
    def member_id(self) -> str: ...
    @property
    def grid_sensor(self) -> str: ...
    @property
    def regulating(self) -> bool: ...
    def in_discharge_pool(self) -> bool: ...
    def soc_reading(self) -> float | None: ...
    def hard_limit(self) -> float: ...
    def zone3_limit(self) -> float: ...
    def ac_soc_target(self) -> float: ...
    def capacity_kwh(self, entity_id: str) -> float | None: ...
    def actual_power(self) -> float: ...
    def output_setpoint(self) -> float: ...


@dataclass(frozen=True)
class Shares:
    """Anteile je Instanz, dazu der angewandte Verteilungsmodus (None: keiner) und ein Warnschlüssel."""

    values: dict[str, float]
    mode: str | None = None
    warning: str = ""


def pool_sum(
    pool: dict[str, Member], me: Member, own_value: float, reader: Callable[[Member], float],
) -> float:
    """`own_value` plus `reader(m)` aller übrigen Mitglieder in `pool`; der eigene Wert zählt immer."""
    return own_value + sum(reader(m) for m in pool.values() if m is not me)


def _socs(active: dict[str, Member], me: Member, own_soc: float) -> dict[str, float] | None:
    """SOC je Mitglied in `active`, eigener Wert `own_soc`; `None` beim ersten nicht verfügbaren."""
    socs: dict[str, float] = {}
    for eid, m in active.items():
        if m is me:
            socs[eid] = own_soc
            continue
        soc = m.soc_reading()
        if soc is None:
            return None
        socs[eid] = soc
    return socs


def waterfill(active: dict[str, Member], shares: dict[str, float], global_max: float) -> dict[str, float]:
    """Verteilt `global_max` nach `shares`, gekappt am Hard-Limit jedes Mitglieds.

    Der Rest gekappter Mitglieder geht iterativ an die übrigen; terminiert, weil jede Runde
    mindestens ein Mitglied endgültig zuteilt. Abgerundet, damit die Summe `global_max`
    nicht übersteigt.
    """
    caps = {eid: m.hard_limit() for eid, m in active.items()}

    remaining_ids = set(shares.keys())
    allocations: dict[str, float] = {}
    remaining_power = global_max

    while remaining_ids:
        share_sum = sum(shares[eid] for eid in remaining_ids)
        if share_sum <= 0:
            for eid in remaining_ids:
                allocations[eid] = 0.0
            break

        portion = {eid: remaining_power * (shares[eid] / share_sum) for eid in remaining_ids}
        newly_capped = [eid for eid in remaining_ids if portion[eid] >= caps[eid] - 0.01]

        if not newly_capped:
            allocations.update(portion)
            break

        for eid in newly_capped:
            allocations[eid] = caps[eid]
            remaining_power -= caps[eid]
        remaining_ids -= set(newly_capped)

    return {eid: math.floor(v) for eid, v in allocations.items()}


class NetGroup:
    """Alle Instanzen an einem Netzsensor. Mitglieder werden bei jedem Aufruf neu bestimmt,
    Anteile je Aufruf neu gerechnet; gehalten werden StdDev-Puffer, gespeicherte Verteilung
    und `soc_switch`-Zustand. Änderungen am `soc_switch`-Zustand gehen an `on_soc_switch_change`."""

    def __init__(
        self, hass: Any, grid_sensor: str, dist: dict | None = None, soc_switch: dict | None = None,
        on_soc_switch_change: Callable[[dict], None] | None = None,
    ) -> None:
        self.hass = hass
        self.grid_sensor = grid_sensor
        self.samples: deque[tuple[float, float]] = deque()
        self.dist = dist
        self._soc_switch = soc_switch
        self._on_soc_switch_change = on_soc_switch_change

    # ── Lesen: Mitglieder, Pools, Verteilungs-Config ─────────────────────────

    def members(self) -> dict[str, Member]:
        """Instanzen mit diesem Netzsensor, in Reihenfolge der Registrierung."""
        return {
            eid: m for eid, m in self.hass.data.get(DOMAIN, {}).items()
            if m.grid_sensor == self.grid_sensor
        }

    def pool(self, pred: Callable[[Member], bool]) -> dict[str, Member]:
        """Mitglieder, für die `pred` gilt."""
        return {eid: m for eid, m in self.members().items() if pred(m)}

    def leader(self) -> Member:
        """Kleinste entry_id unter den regelnden Mitgliedern, sonst unter allen."""
        active = self.pool(lambda m: m.regulating) or self.members()
        return active[min(active)]

    def discharge_pool(self) -> dict[str, Member]:
        """Regelnde Mitglieder in Modus '1', die nicht darin ruhen."""
        return self.pool(lambda m: m.in_discharge_pool())

    def ac_pool(self) -> dict[str, Member]:
        """Regelnde Mitglieder mit aktivem AC-Laden."""
        return self.pool(lambda m: m.regulating and m.ac_charge_active)

    def dist_cfg(self) -> dict:
        """Verteilungs-Config dieser Gruppe, mit Defaults aufgefüllt."""
        return {**DIST_DEFAULTS, **(self.dist or {})}

    # ── Ableiten: Verteilung ─────────────────────────────────────────────────

    def all_shares(self, active: dict[str, Member], me: Member, own_soc: float, ac: bool = False) -> Shares:
        """Anteile aller Mitglieder in `active` nach Verteilungsmodus.

        Gewicht im Entlade-Pool ist der SOC über der Zone-3-Grenze, mit `ac` der Platz bis
        zum Ladeziel; `soc_switch` wirkt im AC-Pool wie `soc`. Fehlt ein Fremdsensor (SOC
        oder Kapazität), weicht der Modus aus: capacity → soc, soc/soc_switch → equal;
        `Shares.mode` und `Shares.warning` tragen das. Der Warnschlüssel kommt aus
        DIST_WARNINGS, mit `ac` der des AC-Pools.
        """
        n = len(active)
        if n == 0:
            return Shares({})
        dist = self.dist_cfg()
        mode = effective = dist["distribution_mode"]
        if ac and mode == "soc_switch":
            mode = effective = "soc"
        warning = ""

        if n <= 1:
            return Shares({eid: 1.0 for eid in active}, effective)

        equal = {eid: 1.0 / n for eid in active}

        def to_equal(reason: str) -> Shares:
            """Rückfall auf Gleichverteilung mit dem Warnschlüssel des Grundes."""
            return Shares(equal, "equal", DIST_WARNINGS[reason][ac])

        if mode == "equal":
            return Shares(equal, effective)

        if mode == "soc_switch":
            shares = self.soc_switch_shares(active, me, own_soc)
            return Shares(shares, effective) if shares is not None else to_equal("soc_switch")

        # Modus "soc" und unbekannte Modi: reine SOC-Prozentpunkt-Gewichtung.
        caps = {eid: 1.0 for eid in active}
        if mode == "capacity":
            def _cap_kwh(eid: str, m: Member) -> float | None:
                """Kapazität der Instanz in kWh; None ohne Sensor oder ohne gültigen Wert."""
                cap_s = str(dist.get(f"inst_{eid}_capacity_sensor", ""))
                if not cap_s:
                    return None
                return m.capacity_kwh(cap_s)

            # Sobald eine Kapazität fehlt, zählen alle neutral 1.0 (reine SOC-Gewichtung).
            measured = {eid: _cap_kwh(eid, m) for eid, m in active.items()}
            if any(cap is None for cap in measured.values()):
                effective, warning = "soc", DIST_WARNINGS["capacity"][ac]
            else:
                caps = measured

        socs = _socs(active, me, own_soc)
        if socs is None:
            return to_equal("soc")

        # SOC-Gewichte: nutzbare bzw. fehlende kWh (mode "capacity"), sonst SOC-Punkte
        def headroom(eid: str, m: Member) -> float:
            """Gewichtungsbasis in SOC-Punkten: Abstand zum AC-Ziel bzw. zur Zone-3-Grenze."""
            if ac:
                return m.ac_soc_target() - socs[eid]
            return socs[eid] - m.zone3_limit()

        soc_weights = {
            eid: max(0.0, headroom(eid, m) / 100.0 * caps[eid])
            for eid, m in active.items()
        }
        total_soc = sum(soc_weights.values())
        if total_soc <= 0:
            return Shares(equal, "equal", warning)
        return Shares({eid: w / total_soc for eid, w in soc_weights.items()}, effective, warning)

    def soc_switch_state(self) -> dict:
        """Laufzeitzustand des Modus `soc_switch` dieser Gruppe, bei Bedarf angelegt."""
        if self._soc_switch is None:
            self._soc_switch = {"active_id": None, "start_soc": None, "was_zone0": False}
        return self._soc_switch

    def soc_switch_shares(self, active: dict[str, Member], me: Member, own_soc: float) -> dict[str, float] | None:
        """Anteile für Modus `soc_switch`; `None`, wenn ein Fremd-SOC unsicher ist.

        Genau ein Mitglied erhält vollen Anteil, bis sein SOC seit Übernahme um
        `soc_switch_divergence` Punkte gefallen ist; dann das mit dem höchsten SOC.
        Zone 0 übernimmt bedingungslos, mehrere Zone-0-Mitglieder gleichmäßig; beim
        Rückgang in die Rotation wird `start_soc` neu verankert.
        """
        socs = _socs(active, me, own_soc)
        if socs is None:
            return None

        zone0 = {eid for eid, m in active.items() if m.surplus_active}

        state = self.soc_switch_state()

        was_zone0 = bool(state.get("was_zone0", False))
        active_id = state.get("active_id")
        changed = False
        rebase = False

        if len(zone0) > 1:
            result = {eid: (1.0 / len(zone0) if eid in zone0 else 0.0) for eid in socs}
        else:
            divergence = float(self.dist_cfg()["soc_switch_divergence"])

            if zone0:
                z0_leader = next(iter(zone0))
                if active_id != z0_leader:
                    active_id, rebase = z0_leader, True
            elif was_zone0 and active_id in socs:
                # Zone 0 gerade verlassen — Baseline für die Rotation neu setzen
                rebase = True
            elif active_id not in socs:
                active_id = max(socs, key=socs.get)
                rebase = True
            elif state.get("start_soc") is None:
                rebase = True
            elif state["start_soc"] - socs[active_id] >= divergence:
                remaining = {eid: s for eid, s in socs.items() if eid != active_id}
                active_id = max(remaining, key=remaining.get) if remaining else active_id
                rebase = True

            if rebase:
                state["start_soc"] = socs[active_id]
                changed = True

            result = {eid: (1.0 if eid == active_id else 0.0) for eid in socs}

        if bool(zone0) != was_zone0:
            state["was_zone0"] = bool(zone0)
            changed = True

        if changed:
            state["active_id"] = active_id
            if self._on_soc_switch_change is not None:
                self._on_soc_switch_change(state)

        return result

    def distribution(self, me: Member, own_soc: float) -> tuple[float, float | None, Shares | None]:
        """Fehler-Anteil, zugeteilte Leistung und Anteile von `me` im Entlade-Pool (Modus '1').

        Einzelbetrieb oder `me` nicht im Pool: (1.0 bzw. 0.0, None, None). Angehoben wird
        höchstens bis zu dem, was die veröffentlichten Limits der übrigen Mitglieder von
        `global_max_power` freilassen; Senken wirkt sofort.
        """
        active = self.discharge_pool()
        if me.member_id not in active or len(active) <= 1:
            return (1.0 if me.member_id in active else 0.0), None, None

        shares = self.all_shares(active, me, own_soc)
        global_max = float(self.dist_cfg()["global_max_power"])
        allocations = waterfill(active, shares.values, global_max)
        others = sum(m.allocated_power or 0 for m in self.members().values() if m is not me)
        own = allocations.get(me.member_id)
        if own is not None:
            own = min(own, max(0, math.floor(global_max - others)))
        return shares.values.get(me.member_id, 0.0), own, shares

    def ac_share(self, me: Member, own_soc: float) -> tuple[float, Shares | None]:
        """Fehler-Anteil von `me` unter den AC-ladenden Mitgliedern; 0.0 ohne Anteile, wenn nicht im Pool."""
        active = self.ac_pool()
        if me.member_id not in active:
            return 0.0, None
        shares = self.all_shares(active, me, own_soc, ac=True)
        return shares.values.get(me.member_id, 0.0), shares
