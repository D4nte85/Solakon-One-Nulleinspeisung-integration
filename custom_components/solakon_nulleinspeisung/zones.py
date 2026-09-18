"""Zonenentscheidung: welcher Fall in diesem Zyklus greift, ohne ihn auszuführen."""
from __future__ import annotations

from dataclasses import dataclass, field

from .const import MODE_AC_CHARGE, MODE_DISABLED, MODE_DISCHARGE
from .tariff import TariffState


@dataclass(frozen=True)
class ZoneInputs:
    """Messwerte, Einstellungen, Preislage und Zustandsflags eines Zyklus."""

    soc: float
    grid: float
    actual: float
    total_actual: float
    mode: str
    zone1_limit: int
    zone3_limit: int
    surplus_enabled: bool
    new_surplus: bool
    ac_enabled: bool
    ac_soc_target: float
    ac_hysteresis: float
    ac_offset: float
    tariff: TariffState
    tariff_soc: float
    tariff_power: float
    is_night: bool
    zone1_forced: bool
    self_adjust_tol: float
    surplus_active: bool
    ac_charge_active: bool
    tariff_charge_active: bool
    cycle_active: bool
    at_rest: bool


@dataclass(frozen=True)
class FallDecision:
    """Getroffener Fall: Übergang (Argumente für `_transition`) und Aktionstext."""

    name: str
    transition: dict = field(default_factory=dict)
    action: str = ""
    params: dict = field(default_factory=dict)


def _end_charge(name: str, flag: str, action_key: str, cycle_active: bool) -> FallDecision:
    """Lade-Session beenden: Integral, Flag, Output 0, Rückkehrmodus, Aktionstext."""
    return FallDecision(name, {
        "reset_integral": True, "flags": {flag: False}, "output": 0,
        "mode": MODE_DISCHARGE, "rest": not cycle_active,
    }, action_key)


def decide(inp: ZoneInputs) -> FallDecision | None:
    """Prüft alle Falls in Reihenfolge; der erste Treffer gewinnt, sonst None."""
    soc = inp.soc
    mode = inp.mode
    zone1 = inp.zone1_limit
    zone3 = inp.zone3_limit

    # ── Fall 0A: Surplus Entry ───────────────────────────────────────────────
    if (
        inp.surplus_enabled
        and inp.new_surplus
        and not inp.surplus_active
        and not inp.ac_charge_active
        and not inp.tariff_charge_active
    ):
        # Zone 0 setzt immer auf einem aktiven Zone-1-Zyklus auf
        switch = mode != MODE_DISCHARGE or inp.at_rest
        return FallDecision("0A", {
            "flags": {"surplus_active": True, "cycle_active": True},
            "timer": switch, "mode": MODE_DISCHARGE if switch else None,
        }, "act_surplus_on")

    # ── Fall 0B: Surplus Exit ────────────────────────────────────────────────
    # Austritt bei erfüllter Austritts-Bedingung oder deaktivierter Überschuss-Option.
    if inp.surplus_active and (not inp.surplus_enabled or not inp.new_surplus):
        # Zone nach Overlay-Ende aus dem SOC ableiten
        return FallDecision("0B", {
            "reset_integral": True,
            "flags": {"surplus_active": False, "cycle_active": soc > zone1},
            "output": 0, "timer": False,
        }, "act_surplus_off")

    # ── Fall A: Zone 1 Start ─────────────────────────────────────────────────
    # zone1_forced erlaubt den Eintritt auch unter dem normalen
    # Zone-1-Limit, wenn der morgige PV-Ertrag die Nacht ohnehin wieder
    # auffüllt. Reiner Einweg-Trigger für den Eintritt — der Austritt läuft
    # unabhängig davon ausschließlich über Fall B (soc < zone3).
    zone1_forced = inp.zone1_forced
    if (
        not inp.ac_charge_active
        and inp.tariff.allows_discharge
        and not inp.tariff_charge_active
        and (soc > zone1 or zone1_forced)
        and not inp.cycle_active
    ):
        action = "act_fall_a_forced" if zone1_forced and soc <= zone1 else "act_fall_a"
        return FallDecision("A", {
            "reset_integral": True,
            "flags": {"cycle_active": True, "surplus_active": False,
                      "ac_charge_active": False, "tariff_charge_active": False},
            "mode": MODE_DISCHARGE,
        }, action, {"soc": soc})

    # ── Fall B: Zone 3 Stop (Zyklus on) ──────────────────────────────────────
    if (
        not inp.ac_charge_active
        and not inp.tariff_charge_active
        and soc <= zone3
        and inp.cycle_active
    ):
        return FallDecision("B", {
            "reset_integral": True,
            "flags": {"cycle_active": False, "surplus_active": False,
                      "ac_charge_active": False, "tariff_charge_active": False},
            "output": 0, "rest": True,
        }, "act_fall_b", {"soc": soc})

    # ── Fall C: Zone 3 Absicherung ───────────────────────────────────────────
    if (
        not inp.ac_charge_active
        and not inp.tariff_charge_active
        and soc <= zone3
        and not inp.cycle_active
        and not inp.at_rest
    ):
        return FallDecision("C", {
            "flags": {"surplus_active": False, "ac_charge_active": False,
                      "tariff_charge_active": False},
            "output": 0, "rest": True,
        }, "act_fall_c")

    # ── Fall D: Recovery ─────────────────────────────────────────────────────
    # Tarif-Lock blockiert Recovery für normalen Discharge (ac/tariff_charge_active-Recovery bleibt erlaubt)
    # Recovery einer aktiven Lade-Session ignoriert die Zone-3-Schwelle — Laden bleibt bei jedem SOC möglich
    charging_session_active = inp.ac_charge_active or inp.tariff_charge_active
    tariff_lock_active = inp.tariff.discharge_locked(charging_session_active, inp.surplus_active)
    if (
        (inp.cycle_active or charging_session_active)
        and (mode not in (MODE_DISCHARGE, MODE_AC_CHARGE) or inp.at_rest)
        and (charging_session_active or soc > zone3)
        and not tariff_lock_active
    ):
        return FallDecision("D", {
            "mode": MODE_AC_CHARGE if charging_session_active else MODE_DISCHARGE,
        }, "act_fall_d")

    # ── Fall GT: Tarif-Laden Start ───────────────────────────────────────────
    # Überschuss-Einspeisung hat Vorrang — kein Tarif-Laden während Zone 0 aktiv
    if (
        inp.tariff.below_cheap
        and soc < inp.tariff_soc
        and not inp.tariff_charge_active
        and not inp.surplus_active
        and mode != MODE_AC_CHARGE
    ):
        return FallDecision("GT", {
            "flags": {"tariff_charge_active": True}, "output": inp.tariff_power,
            "ac_charge_mode": True, "timer_first": True, "mode": MODE_AC_CHARGE,
        }, "act_fall_gt", {"price": inp.tariff.price})

    # ── Fall HT: Tarif-Laden Ende ────────────────────────────────────────────
    if (
        inp.tariff_charge_active
        and (
            soc >= inp.tariff_soc
            or inp.tariff.at_least_cheap
        )
    ):
        return _end_charge("HT", "tariff_charge_active", "act_fall_ht", inp.cycle_active)

    # ── Discharge-Lock (Preis < Teuer-Schwelle) ──────────────────────────────
    # Sperrt Zone 1 und Zone 2 solange Preis < teuer (günstig UND mittel).
    if (
        tariff_lock_active
        and mode == MODE_DISCHARGE
        and not inp.at_rest
    ):
        return FallDecision("TM", {
            "reset_integral": True, "flags": {"cycle_active": False}, "output": 0, "rest": True,
        }, "act_fall_tm", {"price": inp.tariff.price})

    # ── Fall G: AC Laden Start ───────────────────────────────────────────────
    # Überschuss-Einspeisung hat Vorrang — kein AC Laden während Zone 0 aktiv
    # total_actual summiert über alle entladenden Instanzen (Einzelbetrieb: eigener Wert)
    if (
        inp.ac_enabled
        and not inp.ac_charge_active
        and not inp.tariff_charge_active
        and not inp.surplus_active
        and soc < inp.ac_soc_target
        and mode != MODE_AC_CHARGE
        and (inp.grid + inp.total_actual) < -inp.ac_hysteresis
    ):
        return FallDecision("G", {
            "flags": {"ac_charge_active": True}, "output": 0,
            "ac_charge_mode": True, "timer_first": True, "mode": MODE_AC_CHARGE,
        }, "act_fall_g")

    # ── Fall H: AC Laden Ende ────────────────────────────────────────────────
    if (
        mode == MODE_AC_CHARGE
        and inp.ac_charge_active
        and not inp.tariff_charge_active
        and (
            soc >= inp.ac_soc_target
            or (
                inp.grid >= (inp.ac_offset + inp.ac_hysteresis)
                and abs(inp.actual) <= inp.self_adjust_tol
            )
        )
    ):
        return _end_charge("H", "ac_charge_active", "act_fall_h", inp.cycle_active)

    # ── Fall I: Safety — Modus '3' ohne aktive Lade-Session ──────────────────
    if (
        mode == MODE_AC_CHARGE
        and not inp.ac_charge_active
        and not inp.tariff_charge_active
    ):
        return FallDecision("I", {
            "reset_integral": True, "output": 0,
            "mode": MODE_DISCHARGE, "rest": not inp.cycle_active,
        }, "act_fall_i")

    # ── Fall E: Zone 2 Start ─────────────────────────────────────────────────
    if (
        not inp.ac_charge_active
        and not inp.tariff_charge_active
        and inp.tariff.allows_discharge
        and zone3 < soc <= zone1
        and not inp.cycle_active
        and (mode == MODE_DISABLED or inp.at_rest)
        and not inp.is_night
    ):
        return FallDecision("E", {"reset_integral": True, "mode": MODE_DISCHARGE}, "act_fall_e")

    # ── Fall F: Nachtabschaltung ─────────────────────────────────────────────
    if (
        not inp.ac_charge_active
        and not inp.tariff_charge_active
        and inp.is_night
        and not inp.cycle_active
        and not inp.at_rest
    ):
        return FallDecision("F", {"reset_integral": True, "output": 0, "rest": True}, "act_fall_f")

    return None
