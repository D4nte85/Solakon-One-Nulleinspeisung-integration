"""Zonenentscheidung: welcher Fall in diesem Zyklus greift, ohne ihn auszuführen."""
from __future__ import annotations

from dataclasses import dataclass, field

from .const import MODE_AC_CHARGE, MODE_DISABLED, MODE_DISCHARGE
from .tariff import TariffState

# Entladestrom in A je Regelzustand; der Zyklus nutzt den eingestellten Maximalstrom.
DISCHARGE_BY_STATE = {"surplus": 2.0, "tariff_charge": 0.0, "ac_charge": 0.0, "pv": 0.0}


def control_state(surplus: bool, tariff_charge: bool, ac_charge: bool, cycle: bool) -> str:
    """Regelzustand aus den Flags; es gilt surplus → tariff_charge → ac_charge → cycle → pv."""
    if surplus:
        return "surplus"
    if tariff_charge:
        return "tariff_charge"
    if ac_charge:
        return "ac_charge"
    if cycle:
        return "cycle"
    return "pv"


def rest_mode(rest_in_discharge: bool) -> str:
    """Modus des Ruhezustands: '1' mit `rest_in_discharge`, sonst '0'."""
    return MODE_DISCHARGE if rest_in_discharge else MODE_DISABLED


def at_rest(mode: str, rest_in_discharge: bool, resting: bool) -> bool:
    """True, wenn `mode` der Ruhemodus ist und die Instanz darin ruht.

    Modus '0' wird nur vom Ruhezustand geschrieben und gilt stets als Ruhe;
    in Modus '1' entscheidet `resting`.
    """
    return mode == rest_mode(rest_in_discharge) and (mode == MODE_DISABLED or resting)


def required_discharge(state: str, mode: str, discharge_max: int) -> float:
    """Entladestrom für den Regelzustand `state` laut DISCHARGE_BY_STATE.

    Ohne Zyklus und Lade-Session gilt 0 A nur in Modus '1' (Zone 2, Ruhe in Modus 1);
    in jedem anderen Modus `discharge_max`.
    """
    if state == "pv" and mode != MODE_DISCHARGE:
        return float(discharge_max)
    return DISCHARGE_BY_STATE.get(state, float(discharge_max))


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
    tariff_soc_hyst: float
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
    """Getroffener Fall: Übergang (Argumente für `_transition`), Aktionstext, Warnung."""

    name: str
    transition: dict = field(default_factory=dict)
    action: str = ""
    params: dict = field(default_factory=dict)
    warn: tuple[str, dict] | None = None


def _end_charge(name: str, flag: str, action_key: str, cycle_active: bool) -> FallDecision:
    """Lade-Session beenden: Integral, Flag, Output 0, Rückkehrmodus, Aktionstext."""
    return FallDecision(name, {
        "reset_integral": True, "flags": {flag: False}, "output": 0,
        "mode": MODE_DISCHARGE, "rest": not cycle_active,
    }, action_key)


@dataclass(frozen=True)
class ForecastFlags:
    """Prognoselage eines Zyklus: Zone-0-Forcierung, Austritts-Sperre, Zone-1-Nacht-Forcierung."""

    surplus_forced: bool
    exit_lock: bool
    zone1_forced: bool


def forecast_flags(
    *, surplus_forecast: float | None, surplus_lock: float | None, zone1_force: float | None,
    solar: float, soc: float, surplus_forecast_threshold: float, hard_limit_z0: float,
    zone3_limit: float, surplus_lock_factor: float, zone1_force_threshold: float,
    pv_reserve: float, zone1_force_min_soc: float,
) -> ForecastFlags:
    """Prognoseflags aus den Prognosewerten; ein fehlender Wert (None) setzt sein Flag nicht."""
    # Forcierung nur solange die PV das Ausgangslimit übersteigt und der
    # SOC über der Zone-3-Schutzgrenze liegt.
    surplus_forced = surplus_forecast is not None and (
        surplus_forecast >= surplus_forecast_threshold
        and solar > hard_limit_z0
        and soc > zone3_limit
    )

    # Sperrt nur den PV-Austritt aus Zone 0, solange die Vorhersage über
    # dem Ausgabelimit liegt. Der SOC-Austritt bleibt ungesperrt.
    exit_lock = surplus_lock is not None and (
        surplus_lock >= surplus_lock_factor * hard_limit_z0
        and soc > zone3_limit
    )

    # Zone-1-Nacht-Forcierung: erlaubt Entladung unter das normale
    # Zone-1-Limit, wenn der morgige PV-Ertrag die Nacht ohnehin wieder auffüllt.
    zone1_forced = zone1_force is not None and (
        zone1_force >= zone1_force_threshold
        and solar < pv_reserve         # "gerade dunkel", ohne Nacht-Hysterese
        and soc > zone1_force_min_soc  # eigener Floor, unabhängig von zone3_limit (Exit-Schwelle)
    )
    return ForecastFlags(surplus_forced, exit_lock, zone1_forced)


@dataclass(frozen=True)
class SurplusState:
    """Hysteresezustand zwischen Zyklen: PV-0-Eintritt scharf, Dunkelheit."""

    armed: bool
    dark: bool


@dataclass(frozen=True)
class SurplusNight:
    """Ergebnis der Vorstufe: Zone 0 in diesem Zyklus, Nacht, neuer Hysteresezustand."""

    new_surplus: bool
    is_night: bool
    state: SurplusState


def surplus_and_night(
    *, state: SurplusState, surplus_enabled: bool, surplus_active: bool, cycle_active: bool,
    forced: bool, exit_lock: bool, solar: float, soc: float, actual: float, prev_actual: float,
    total_actual: float, grid: float, error_share: float, surplus_threshold: float,
    surplus_soc_hyst: float, surplus_pv_hyst: float, pv_reserve: float,
    night_hysteresis: float, night_enabled: bool,
) -> SurplusNight:
    """Überschuss-Ein- und -Austritt und Nacht-Hysterese aus Messwerten und bisherigem Zustand."""
    armed = state.armed
    if surplus_enabled:
        if solar > 0:
            armed = True

        # Lastanteil dieser Instanz für Ein- und Austritt: (Σactual + grid) × error_share.
        consumption_share = (total_actual + grid) * error_share
        pv_hyst_share = surplus_pv_hyst * error_share

        normal_entry = (
            soc >= surplus_threshold
            and (
                solar > (consumption_share + pv_hyst_share)
                or (
                    solar == 0
                    and actual == 0
                    and prev_actual == 0
                    and armed
                )
            )
        )
        # Forcierung ist bereits an solar > hard_limit_z0 gekoppelt → SOC-unabhängiger Eintritt.
        surplus_entry = normal_entry or forced

        # Austritt: bei aktiver Forcierung gesperrt (SOC- und Verbrauchsterm ausgeklammert),
        # sonst normal über SOC- oder Verbrauchsschwelle. Der Exit-Lock sperrt nur den
        # Verbrauchsterm — der SOC-Austritt greift immer.
        soc_exit = soc < (surplus_threshold - surplus_soc_hyst)
        power_exit = solar <= (consumption_share - pv_hyst_share) and not exit_lock
        surplus_exit = not forced and (soc_exit or power_exit)
        if surplus_active:
            new_surplus = not surplus_exit
            if surplus_exit and solar == 0:
                armed = False
        else:
            new_surplus = surplus_entry
    else:
        new_surplus = False

    dark = state.dark
    if solar < pv_reserve:
        dark = True
    elif solar >= pv_reserve + night_hysteresis:
        dark = False
    is_night = night_enabled and dark and not cycle_active
    return SurplusNight(new_surplus, is_night, SurplusState(armed, dark))


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
    # Recovery folgt einer Lade-Session nur, solange deren Ladegrund noch gilt
    recovery_session = (
        (inp.ac_charge_active and inp.ac_enabled)
        or (inp.tariff_charge_active and inp.tariff.below_cheap)
    )
    if (
        (inp.cycle_active or recovery_session)
        and (mode not in (MODE_DISCHARGE, MODE_AC_CHARGE) or inp.at_rest)
        and (recovery_session or soc > zone3)
        and not tariff_lock_active
    ):
        return FallDecision("D", {
            "mode": MODE_AC_CHARGE if recovery_session else MODE_DISCHARGE,
        }, "act_fall_d")

    # ── Fall GT: Tarif-Laden Start ───────────────────────────────────────────
    # Überschuss-Einspeisung hat Vorrang — kein Tarif-Laden während Zone 0 aktiv
    if (
        inp.tariff.below_cheap
        and soc < inp.tariff_soc - inp.tariff_soc_hyst
        and not inp.tariff_charge_active
        and not inp.ac_charge_active
        and not inp.surplus_active
        and mode != MODE_AC_CHARGE
    ):
        return FallDecision("GT", {
            "flags": {"tariff_charge_active": True}, "output": inp.tariff_power,
            "ac_charge_mode": True, "timer_first": True, "mode": MODE_AC_CHARGE,
        }, "act_fall_gt", {"price": inp.tariff.price})

    # ── Fall HT: Tarif-Laden Ende ────────────────────────────────────────────
    # Kein günstiger Preis mehr ausgewiesen — auch bei abgeschaltetem, unterdrücktem
    # oder unlesbarem Tarif — oder Ladeziel erreicht.
    if (
        inp.tariff_charge_active
        and (
            not inp.tariff.below_cheap
            or soc >= inp.tariff_soc
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
            not inp.ac_enabled
            or soc >= inp.ac_soc_target
            or (
                inp.grid >= (inp.ac_offset + inp.ac_hysteresis)
                and abs(inp.actual) <= inp.self_adjust_tol
            )
        )
    ):
        return _end_charge("H", "ac_charge_active", "act_fall_h", inp.cycle_active)

    # ── Fall I: Safety — Modus und Lade-Session widersprechen sich ───────────
    # Zwei Richtungen: Modus '3' ohne Session, und Session ohne Modus '3' bzw.
    # beide Lade-Flags zugleich. Im zweiten Zweig fällt das Flag, der Modus bleibt.
    both_sessions = inp.ac_charge_active and inp.tariff_charge_active
    session = inp.ac_charge_active or inp.tariff_charge_active
    if both_sessions or (session and mode != MODE_AC_CHARGE):
        return FallDecision("I", {
            "reset_integral": True,
            "flags": {"ac_charge_active": False, "tariff_charge_active": False},
        }, "act_fall_i_session", warn=("warn_double_session", {}) if both_sessions else None)
    if mode == MODE_AC_CHARGE and not session:
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
