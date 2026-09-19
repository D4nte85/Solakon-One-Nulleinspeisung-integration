"""Invarianten: Regeln für gewolltes Verhalten, geprüft über alle Charakterisierungsszenarien.

Die Regeln stammen aus der Verhaltensbeschreibung, nicht aus dem Code. Jede Regel ist eine
Funktion `(ctx) -> str | None`, die nach einem Regelzyklus einer Instanz einen Verstoß meldet.
`python tests/invarianten.py [regel ...]` zählt Verstöße je Regel mit Beispielszenarien.
"""
from __future__ import annotations

import asyncio
import copy
import sys
from collections import defaultdict
from dataclasses import dataclass, field

from tests import harness as h
from tests import scenarios

C = h.const
KINDS = ("cycle", "multi", "stall", "tariff", "domain", "rest")
NICHT_ZAHL = ("unavailable", "unknown", "None", "abc", "nan", "on", "off")


# ── Lesen ────────────────────────────────────────────────────────────────────

def zahl(snap: dict, eid: str, leistung: bool = False) -> float | None:
    """Zahlenwert eines Zustands aus dem Schnappschuss; Leistung in W normalisiert."""
    st = snap.get(eid)
    if st is None or st["state"] in NICHT_ZAHL:
        return None
    try:
        val = float(st["state"])
    except ValueError:
        return None
    if val != val:
        return None
    if leistung and st["attrs"].get("unit_of_measurement") == "kW":
        val *= 1000.0
    return val


def schnappschuss(hass) -> dict:
    return {eid: {"state": s.state, "attrs": dict(s.attributes)} for eid, s in hass.states._states.items()}


@dataclass
class Ctx:
    """Ein Regelzyklus einer Instanz: Eingänge davor, Aufrufe, Zustand danach."""
    kind: str
    spec_id: str
    schritt: int
    prefix: str
    cfg: dict
    settings: dict
    vorher: dict
    nachher: dict
    flags_vorher: dict
    flags: dict
    aufrufe: list
    alle: dict = field(default_factory=dict)       # prefix -> (cfg, flags, nachher-Schnappschuss)
    dist: dict | None = None
    aus_seit: int | None = None                    # Schritt, in dem die Regelung abgeschaltet wurde
    abgeschaltet_jetzt: bool = False
    runde_vollstaendig: bool = True                # alle Instanzen haben in dieser Runde geregelt
    geregelt: dict = field(default_factory=dict)   # prefix -> Regelung an, vor diesem Zyklus

    def e(self, key: str) -> str:
        return self.cfg[key]

    # Aufrufe dieser Instanz
    def schreibt(self, eid: str | None = None) -> list:
        return [a for a in self.aufrufe if eid is None or a[3] == eid]

    # Eingänge
    def soc(self) -> float | None:
        return zahl(self.vorher, self.e(C.CONF_SOC_SENSOR))

    def netz(self) -> float | None:
        return zahl(self.vorher, self.e(C.CONF_GRID_SENSOR), leistung=True)

    def pv(self) -> float | None:
        return zahl(self.vorher, self.e(C.CONF_SOLAR_SENSOR), leistung=True)

    def sensoren_gueltig(self) -> bool:
        """Netz, Ist-Leistung und SOC liefern Zahlen — der Geltungsbereich von C2."""
        return None not in (self.soc(), self.netz(), zahl(self.vorher, self.e(C.CONF_ACTUAL_SENSOR), True))

    def eingaenge_gueltig(self) -> bool:
        """Zusätzlich PV als Zahl und ein lesbarer Modus-Select."""
        modus = (self.vorher.get(self.e(C.CONF_MODE_SELECT)) or {}).get("state")
        return self.sensoren_gueltig() and self.pv() is not None and modus not in (None, "unavailable", "unknown")

    def konfig_gueltig(self) -> bool:
        s = self.settings
        if s[C.S_ZONE1_LIMIT] <= s[C.S_ZONE3_LIMIT]:
            return False
        if s[C.S_SURPLUS_ENABLED] and s[C.S_SURPLUS_SOC_THRESHOLD] <= s[C.S_ZONE1_LIMIT]:
            return False
        if s[C.S_ZONE1_FORCE_ENABLED] and not s[C.S_ZONE3_LIMIT] < s[C.S_ZONE1_FORCE_MIN_SOC] < s[C.S_ZONE1_LIMIT]:
            return False
        return True

    def normal(self) -> bool:
        """Regelung an, Konfiguration und Pflichtsensoren gültig — der Zyklus soll regeln."""
        return self.settings[C.S_REGULATION_ENABLED] and self.konfig_gueltig() and self.eingaenge_gueltig()

    # Zustand danach
    def modus(self) -> str | None:
        st = self.nachher.get(self.e(C.CONF_MODE_SELECT))
        return st["state"] if st else None

    def leistung(self) -> float | None:
        return zahl(self.nachher, self.e(C.CONF_ACTIVE_POWER))

    def entladestrom(self) -> float | None:
        return zahl(self.nachher, self.e(C.CONF_DISCHARGE_CURRENT))

    def ruhemodus(self) -> str:
        return C.MODE_DISCHARGE if self.settings.get(C.S_REST_IN_DISCHARGE) else C.MODE_DISABLED

    def lade_session(self) -> bool:
        return bool(self.flags["ac_charge_active"] or self.flags["tariff_charge_active"])

    def start_konsistent(self) -> bool:
        """Startzustand erfüllt selbst D1–D4 — sonst prüft die Regel das Heilen, nicht das Halten."""
        f = self.flags_vorher
        modus = (self.vorher.get(self.e(C.CONF_MODE_SELECT)) or {}).get("state")
        session = f.get("ac_charge_active") or f.get("tariff_charge_active")
        return not (
            (f.get("surplus_active") and (not f.get("cycle_active") or session))
            or (f.get("ac_charge_active") and f.get("tariff_charge_active"))
            or (modus == C.MODE_AC_CHARGE and not session)
            or (session and modus != C.MODE_AC_CHARGE)
        )

    def uebergang(self) -> bool:
        """Dieser Lauf hat einen Fall gewechselt oder den Modus geschrieben."""
        return self.flags["active_fall"] != self.flags_vorher.get("active_fall") or bool(self.schreibt(self.e(C.CONF_MODE_SELECT)))

    def geraete_max(self) -> float:
        st = self.vorher.get(self.e(C.CONF_ACTIVE_POWER)) or {"attrs": {}}
        attr = st["attrs"].get("max")
        return min(C.DEVICE_MAX_POWER, float(attr)) if attr is not None else C.DEVICE_MAX_POWER


# ── Regeln ───────────────────────────────────────────────────────────────────

def a1(c: Ctx):
    grenze = c.geraete_max()
    for a in c.schreibt(c.e(C.CONF_ACTIVE_POWER)):
        if not 0 <= float(a[4]) <= grenze:
            return f"Output {a[4]} W außerhalb [0, {grenze}]"


def a2(c: Ctx):
    for a in c.schreibt(c.e(C.CONF_MODE_SELECT)):
        if a[4] not in ("0", "1", "3"):
            return f"Modus {a[4]!r} geschrieben"


def a3(c: Ctx):
    s = c.settings
    if c.flags["ac_charge_active"]:
        grenze = s[C.S_AC_POWER_LIMIT]
    else:
        # In Zone 0 bleibt das Integral aus Zone 1 eingefroren (I4) — dort gilt dessen Limit.
        grenze = s[C.S_HARD_LIMIT_Z1]
    grenze = min(grenze, C.DEVICE_MAX_POWER)
    if abs(c.flags["integral"]) > grenze + 1e-6:
        return f"Integral {c.flags['integral']} außerhalb ±{grenze}"


def a4(c: Ctx):
    # Der Countdown der Testumgebung zählt nie herunter — die Regel gilt also immer.
    modus_eid, timer_eid = c.e(C.CONF_MODE_SELECT), c.e(C.CONF_TIMEOUT_SET)
    timer_gesehen = False
    alt = (c.vorher.get(modus_eid) or {}).get("state")
    for a in c.aufrufe:
        if a[3] == timer_eid:
            timer_gesehen = True
        elif a[3] == modus_eid:
            if a[4] != alt and not timer_gesehen:
                return f"Moduswechsel {alt!r}→{a[4]!r} ohne vorherigen Timer-Toggle"
            alt = a[4]


def b1(c: Ctx):
    if not c.normal() or c.aus_seit is not None:
        return None
    soc = c.soc()
    if soc > c.settings[C.S_ZONE3_LIMIT] or c.lade_session():
        return None
    fehler = []
    if c.modus() != c.ruhemodus():
        fehler.append(f"Modus {c.modus()!r} statt Ruhemodus {c.ruhemodus()!r}")
    if c.leistung() not in (0.0, None) and c.modus() == C.MODE_DISCHARGE:
        fehler.append(f"Output {c.leistung()} W")
    if c.flags["cycle_active"] or c.flags["surplus_active"]:
        fehler.append("cycle/surplus aktiv")
    return f"SOC {soc} ≤ Zone 3: " + ", ".join(fehler) if fehler else None


def b2(c: Ctx):
    if not c.normal() or c.aus_seit is not None:
        return None
    f = c.flags
    if f["cycle_active"] or f["surplus_active"] or c.lade_session() or f["resting"] or c.modus() != C.MODE_DISCHARGE:
        return None
    pv = c.pv()
    if pv is None:
        return None
    grenze = max(0.0, pv - c.settings[C.S_PV_RESERVE])
    if (c.leistung() or 0) > grenze + 1e-6:
        return f"Zone 2: Output {c.leistung()} W > PV {pv} − Reserve {c.settings[C.S_PV_RESERVE]}"


def b3(c: Ctx):
    strom = c.entladestrom()
    dmax = c.settings[C.S_DISCHARGE_MAX]
    if c.aus_seit is not None:
        soll, lage = dmax, "Regelung aus"
    elif not c.normal():
        return None
    elif c.lade_session():
        return None
    elif c.flags["surplus_active"]:
        soll, lage = 2, "Surplus"
    elif c.flags["resting"] and c.modus() == C.MODE_DISCHARGE:
        return None  # Ruhe in Modus 1: Gerät bleibt aktiv, 0 A wäre ebenso vertretbar
    elif c.flags["resting"] or c.modus() == C.MODE_DISABLED:
        soll, lage = dmax, "Ruhe in Modus 0"
    elif c.flags["cycle_active"]:
        soll, lage = dmax, "Zone 1"
    elif c.modus() == C.MODE_DISCHARGE:
        soll, lage = 0, "Zone 2"
    else:
        return None
    # Toleranz wie `_set_number(only_if_changed=True)`: Abweichungen bis 0,5 A schreibt der Zyklus nicht.
    if strom is None or abs(strom - soll) > 0.5:
        return f"{lage}: Entladestrom {strom} statt {soll}"


def c1(c: Ctx):
    if c.aus_seit is None:
        if c.settings[C.S_REGULATION_ENABLED] is False and c.schreibt():
            return f"Regelung von Anfang an aus, trotzdem {len(c.schreibt())} Schreibbefehle"
        return None
    if c.abgeschaltet_jetzt:
        erlaubt = {c.e(C.CONF_MODE_SELECT), c.e(C.CONF_TIMEOUT_SET), c.e(C.CONF_DISCHARGE_CURRENT)}
        fremd = [a for a in c.schreibt() if a[3] not in erlaubt
                 and not (a[3] == c.e(C.CONF_ACTIVE_POWER) and float(a[4]) == 0)]
        modi = [a[4] for a in c.schreibt(c.e(C.CONF_MODE_SELECT))]
        if fremd:
            return f"beim Abschalten zusätzlich geschrieben: {fremd}"
        if modi not in ([C.MODE_DISABLED], []) or c.modus() != C.MODE_DISABLED:
            return f"beim Abschalten Modi {modi}, Endmodus {c.modus()!r}"
        return None
    if c.schreibt():
        return f"nach dem Abschalten geschrieben: {c.schreibt()}"


def c2(c: Ctx):
    if not c.settings[C.S_REGULATION_ENABLED] or not c.konfig_gueltig() or c.sensoren_gueltig() or c.aus_seit is not None:
        return None
    fehler = []
    if c.schreibt():
        fehler.append(f"{len(c.schreibt())} Schreibbefehle")
    if not c.flags["last_error"]:
        fehler.append("keine Fehlermeldung")
    return "Sensor ungültig: " + ", ".join(fehler) if fehler else None


def c3(c: Ctx):
    if not c.settings[C.S_REGULATION_ENABLED] or c.konfig_gueltig() or not c.eingaenge_gueltig() or c.aus_seit is not None:
        return None
    fehler = []
    if c.schreibt():
        fehler.append(f"{len(c.schreibt())} Schreibbefehle")
    if not c.flags["last_error"]:
        fehler.append("keine Fehlermeldung")
    return "Konfiguration ungültig: " + ", ".join(fehler) if fehler else None


def d1(c: Ctx):
    if c.normal() and c.flags["surplus_active"] and not c.flags["cycle_active"]:
        return "surplus_active ohne cycle_active"


def d2(c: Ctx):
    if c.flags["ac_charge_active"] and c.flags["tariff_charge_active"]:
        return "AC- und Tarif-Laden gleichzeitig"


def d3(c: Ctx):
    f = c.flags
    if not c.normal() or not f["surplus_active"]:
        return None
    teile = [k for k in ("ac_charge_active", "tariff_charge_active", "discharge_locked", "is_night") if f[k]]
    if teile:
        return "surplus_active mit " + ", ".join(teile)


def d4(c: Ctx):
    if c.normal() and c.aus_seit is None and c.modus() == C.MODE_AC_CHARGE and not c.lade_session():
        return "Modus 3 ohne Lade-Session"


def _tarif_eingang(c: Ctx):
    """Preis und Schwellen, nur bei lokal konfiguriertem Preis und festen Schwellen."""
    s = c.settings
    if not s[C.S_TARIFF_ENABLED] or s[C.S_TARIFF_CHEAP_ENTITY] or s[C.S_TARIFF_EXP_ENTITY]:
        return None
    if c.dist and (c.dist.get("global_tariff_cheap_entity") or c.dist.get("global_tariff_exp_entity")):
        return None  # globale dynamische Schwellen
    sensor = s[C.S_TARIFF_PRICE_SENSOR]
    if not sensor:
        return None
    return zahl(c.vorher, sensor), s[C.S_TARIFF_CHEAP_THRESHOLD], s[C.S_TARIFF_EXP_THRESHOLD]


def e1(c: Ctx):
    if not c.normal() or c.aus_seit is not None:
        return None
    t = _tarif_eingang(c)
    if not t or t[0] is None:
        return None
    preis, guenstig, _ = t
    f = c.flags
    if preis >= guenstig or c.soc() >= c.settings[C.S_TARIFF_SOC_TARGET]:
        return None
    # Laufendes AC-Laden wird nicht abgelöst; eine Ablösung käme nur als Tarif-Schalter.
    if f["surplus_active"] or f["forecast_tariff_suppressed"] or c.flags_vorher.get("ac_charge_active"):
        return None
    if not f["tariff_charge_active"] or c.modus() != C.MODE_AC_CHARGE:
        return f"Preis {preis} < {guenstig}, SOC {c.soc()}: tariff_charge={f['tariff_charge_active']}, Modus {c.modus()!r}"


def e2(c: Ctx):
    if not c.normal() or c.aus_seit is not None:
        return None
    t = _tarif_eingang(c)
    if not t or t[0] is None:
        return None
    preis, guenstig, teuer = t
    if not guenstig <= preis < teuer or c.flags["surplus_active"] or c.lade_session() or c.flags["forecast_tariff_suppressed"]:
        return None
    if c.modus() == C.MODE_DISCHARGE and (c.leistung() or 0) > 0:
        return f"Preis {preis} im Sperrband [{guenstig}, {teuer}): Modus 1 mit {c.leistung()} W"


def f1(c: Ctx):
    if not c.normal() or c.flags_vorher.get("ac_charge_active") or not c.flags["ac_charge_active"]:
        return None
    # Ist-Leistung vorzeichenrichtig: Entladen positiv, Laden negativ. Die eigene Instanz
    # zählt immer, die übrigen nur am selben Netzsensor, mit Regelung und in Modus '1'.
    netz = c.netz()
    summe = 0.0
    for p, (cfg, _flags, _nach) in c.alle.items():
        if p == c.prefix or (
            cfg[C.CONF_GRID_SENSOR] == c.e(C.CONF_GRID_SENSOR) and c.geregelt.get(p)
            and (c.vorher.get(cfg[C.CONF_MODE_SELECT]) or {}).get("state") == C.MODE_DISCHARGE
        ):
            summe += zahl(c.vorher, cfg[C.CONF_ACTUAL_SENSOR], True) or 0.0
    hyst = c.settings[C.S_AC_HYSTERESIS]
    if not netz + summe < -hyst:
        return f"AC-Laden gestartet bei Netz {netz} + ΣOutput {summe} ≥ −{hyst}"


def f2(c: Ctx):
    if c.flags_vorher.get("cycle_active") and c.flags["active_fall"] == "F" and c.flags_vorher.get("active_fall") != "F":
        return "Nachtabschaltung bei laufendem Zone-1-Zyklus"


def f3(c: Ctx):
    if c.prefix != "a" or len(c.alle) < 2 or not c.dist or not c.runde_vollstaendig:
        return None
    gesamt = c.dist["global_max_power"]
    summe = sum((fl.get("allocated_power") or 0) for cfg, fl, nach in c.alle.values()
                if (nach.get(cfg[C.CONF_MODE_SELECT]) or {}).get("state") == C.MODE_DISCHARGE)
    if summe > gesamt + 1e-6:
        return f"Σ Limits {summe} > Gesamtleistung {gesamt}"


def f4(c: Ctx):
    s = c.settings
    if not c.normal() or not c.flags["surplus_active"] or c.flags["forecast_surplus_forced"]:
        return None
    grenze = s[C.S_SURPLUS_SOC_THRESHOLD] - s[C.S_SURPLUS_SOC_HYST]
    if c.soc() < grenze:
        return f"Surplus bleibt bei SOC {c.soc()} < {grenze}"


# ── Regeln aus der Funktionsbeschreibung (README) ────────────────────────────

def _fall_neu(c: Ctx, *faelle) -> bool:
    """Einer der Falls hat in diesem Regellauf gefeuert (Wechsel des zuletzt ausgeführten Falls)."""
    return c.flags["active_fall"] in faelle and c.flags_vorher.get("active_fall") != c.flags["active_fall"]


def _preis_gueltig(c: Ctx):
    t = _tarif_eingang(c)
    return t if t and t[0] is not None else None


def h1(c: Ctx):
    if not c.normal() or not c.flags["tariff_charge_active"] or c.modus() != C.MODE_AC_CHARGE:
        return None
    soll = min(c.settings[C.S_TARIFF_POWER], C.DEVICE_MAX_POWER)
    for a in c.schreibt(c.e(C.CONF_ACTIVE_POWER)):
        if abs(float(a[4]) - soll) > 1e-6:
            return f"Tarif-Laden schreibt {a[4]} W statt fest {soll} W"


def h2(c: Ctx):
    if not c.normal() or c.aus_seit is not None:
        return None
    t = _preis_gueltig(c)
    if not t:
        return None
    preis, guenstig, _ = t
    f = c.flags
    if preis >= guenstig or c.soc() < c.settings[C.S_TARIFF_SOC_TARGET]:
        return None
    if f["surplus_active"] or c.lade_session() or f["forecast_tariff_suppressed"]:
        return None
    if c.modus() == C.MODE_DISCHARGE and (c.leistung() or 0) > 0:
        return f"Preis {preis} < günstig, Ladeziel erreicht: Modus 1 mit {c.leistung()} W"


def h3(c: Ctx):
    if not c.normal() or not c.flags["tariff_charge_active"]:
        return None
    t = _preis_gueltig(c)
    if not t:
        return None
    preis, guenstig, _ = t
    ziel = c.settings[C.S_TARIFF_SOC_TARGET]
    if preis >= guenstig or c.soc() >= ziel:
        return f"Tarif-Laden läuft weiter bei Preis {preis} (günstig {guenstig}), SOC {c.soc()} (Ziel {ziel})"


def h4(c: Ctx):
    if not c.normal() or not c.flags["forecast_tariff_suppressed"]:
        return None
    if c.flags["tariff_charge_active"] and not c.flags_vorher.get("tariff_charge_active"):
        return "Tarif-Laden startet trotz PV-Vorhersage-Unterdrückung"
    if c.flags["discharge_locked"]:
        return "Entladesperre trotz PV-Vorhersage-Unterdrückung"


def h5(c: Ctx):
    if not c.normal():
        return None
    t = _preis_gueltig(c)
    if not t:
        return None
    preis, guenstig, _ = t
    einheit = str(c.vorher[c.settings[C.S_TARIFF_PRICE_SENSOR]]["attrs"].get("unit_of_measurement") or "").lower()
    if ("€" in einheit or "eur" in einheit) and 0 <= preis < 1 and guenstig >= 3 and not c.flags["last_error"]:
        return f"Preis {preis} {einheit} bei Günstig-Schwelle {guenstig}: keine Meldung"


def i1(c: Ctx):
    if c.normal() and not c.settings[C.S_SURPLUS_ENABLED] and c.flags["surplus_active"]:
        return "Überschuss-Option aus, surplus_active bleibt"


def i2(c: Ctx):
    if not c.normal() or c.flags_vorher.get("surplus_active") or not c.flags["surplus_active"]:
        return None
    schwelle = c.settings[C.S_SURPLUS_SOC_THRESHOLD]
    if c.soc() < schwelle and not c.flags["forecast_surplus_forced"]:
        return f"Zone-0-Eintritt bei SOC {c.soc()} < {schwelle} ohne Forcierung"


def i3(c: Ctx):
    if not c.normal() or not c.flags["forecast_surplus_forced"]:
        return None
    pv, hz0, z3 = c.pv(), c.settings[C.S_HARD_LIMIT_Z0], c.settings[C.S_ZONE3_LIMIT]
    if not (pv > hz0 and c.soc() > z3):
        return f"Forcierung aktiv bei PV {pv} (Z0 {hz0}), SOC {c.soc()} (Zone 3 {z3})"


def i4(c: Ctx):
    if not c.normal() or not (c.flags_vorher.get("surplus_active") and c.flags["surplus_active"]):
        return None
    if abs(c.flags["integral"] - c.flags_vorher.get("integral", 0)) > 1e-6:
        return f"Integral in Zone 0 verändert: {c.flags_vorher.get('integral')} → {c.flags['integral']}"


def i5(c: Ctx):
    if not c.normal() or not c.flags["surplus_active"]:
        return None
    soll = min(c.settings[C.S_HARD_LIMIT_Z0], C.DEVICE_MAX_POWER)
    if c.flags["allocated_power"] is not None:
        soll = min(soll, c.flags["allocated_power"])
    for a in c.schreibt(c.e(C.CONF_ACTIVE_POWER)):
        if abs(float(a[4]) - soll) > 1e-6:
            return f"Zone 0 schreibt {a[4]} W statt {soll} W"


def _tarif_sperre(c: Ctx) -> bool:
    t = _preis_gueltig(c)
    return bool(t) and t[0] < t[2] and not c.flags["forecast_tariff_suppressed"]


def j1(c: Ctx):
    if not c.normal() or c.flags_vorher.get("cycle_active") or not c.flags["cycle_active"]:
        return None
    if c.flags["surplus_active"] or c.lade_session():
        return None
    z1 = c.settings[C.S_ZONE1_LIMIT]
    if c.soc() <= z1 and not c.flags["zone1_forced"]:
        return f"Zyklusstart bei SOC {c.soc()} ≤ Zone 1 {z1} ohne Nacht-Forcierung"
    if _tarif_sperre(c):
        return f"Zyklusstart trotz Tarif-Sperre (Preis {_preis_gueltig(c)[0]})"


def j2(c: Ctx):
    if not c.normal() or not c.flags_vorher.get("cycle_active") or c.flags["cycle_active"]:
        return None
    if c.soc() <= c.settings[C.S_ZONE3_LIMIT] or c.flags_vorher.get("surplus_active"):
        return None
    if _tarif_sperre(c) or _fall_neu(c, "TM"):
        return None
    return f"Zyklus endet bei SOC {c.soc()} über Zone 3 ohne Sperre oder Zone-0-Austritt (Fall {c.flags['active_fall']!r})"


def j3(c: Ctx):
    if not c.normal() or not c.flags["zone1_forced"]:
        return None
    s = c.settings
    if not (c.pv() < s[C.S_PV_RESERVE] and c.soc() > s[C.S_ZONE1_FORCE_MIN_SOC]):
        return f"Nacht-Forcierung bei PV {c.pv()} (Reserve {s[C.S_PV_RESERVE]}), SOC {c.soc()} (Min {s[C.S_ZONE1_FORCE_MIN_SOC]})"


def j4(c: Ctx):
    if not c.normal() or not _fall_neu(c, "F"):
        return None
    s = c.settings
    grenze = s[C.S_PV_RESERVE] + s.get(C.S_NIGHT_HYSTERESIS, 0)
    if c.pv() >= grenze:
        return f"Nachtabschaltung bei PV {c.pv()} ≥ {grenze}"


def j5(c: Ctx):
    if c.normal() and _fall_neu(c, "B", "F", "TM") and abs(c.flags["integral"]) > 1e-6:
        return f"Fall {c.flags['active_fall']}: Integral {c.flags['integral']} statt 0"


def c4(c: Ctx):
    if not c.abgeschaltet_jetzt:
        return None
    for k in ("cycle_active", "tariff_charge_active"):
        if c.flags[k] != c.flags_vorher.get(k):
            return f"Abschalten ändert {k}: {c.flags_vorher.get(k)} → {c.flags[k]}"


def c5(c: Ctx):
    msgs = [repr(m) for m in c.flags["last_error_msgs"]]
    doppelt = sorted({m for m in msgs if msgs.count(m) > 1})
    if doppelt:
        return f"Meldung mehrfach in der Fehlerkette: {', '.join(doppelt)}"


def k1(c: Ctx):
    zug = c.flags["allocated_power"]
    if zug is None or not c.normal():
        return None
    # Zugeteilt wird zu Zyklusbeginn, also nach der Lage vor den Falls.
    schluessel = C.S_HARD_LIMIT_Z0 if c.flags_vorher.get("surplus_active") else C.S_HARD_LIMIT_Z1
    grenze = min(c.settings[schluessel], C.DEVICE_MAX_POWER)
    if zug > grenze + 1e-6:
        return f"zugeteilt {zug} W > Hard Limit {grenze} W"


def k2(c: Ctx):
    if not c.normal() or c.flags["allocated_power"] is None:
        return None
    modus = (c.vorher.get(c.e(C.CONF_MODE_SELECT)) or {}).get("state")
    if (modus == C.MODE_DISABLED or c.flags_vorher.get("resting")) and c.flags["allocated_power"] > 0:
        return f"Instanz in Modus {modus!r}/Ruhe mit zugeteilter Leistung {c.flags['allocated_power']}"


def k3(c: Ctx):
    """Nur die dokumentierte Degradation: SOC- oder Kapazitätssensor einer fremden Instanz ungültig."""
    if not c.normal() or not c.dist or len(c.alle) < 2:
        return None
    modus = c.dist.get("distribution_mode")
    if modus not in ("soc", "capacity", "soc_switch"):
        return None
    eigener = (c.vorher.get(c.e(C.CONF_MODE_SELECT)) or {}).get("state")
    fv = c.flags_vorher
    if eigener != C.MODE_DISCHARGE or fv.get("resting") or fv.get("ac_charge_active") or fv.get("tariff_charge_active"):
        return None  # nur Instanzen, die zu Zyklusbeginn im Entlade-Pool stehen
    for p, (cfg, _fl, _nach) in c.alle.items():
        if p == c.prefix or cfg[C.CONF_GRID_SENSOR] != c.e(C.CONF_GRID_SENSOR):
            continue  # andere Netzgruppe, eigener Pool
        if (c.vorher.get(cfg[C.CONF_MODE_SELECT]) or {}).get("state") != C.MODE_DISCHARGE:
            continue
        if _fl.get("operating_state") == "disabled":
            continue
        kap = c.dist.get(f"inst_entry_{p}_capacity_sensor")

        def fehlt(eid):  # nicht-numerische Zustände gehören zu C2, nicht zur Degradation
            st = c.vorher.get(eid)
            return st is None or st["state"] in ("unknown", "unavailable")
        ungueltig = fehlt(cfg[C.CONF_SOC_SENSOR]) or (modus == "capacity" and kap and fehlt(kap))
        if ungueltig and not c.flags["last_error"]:
            return f"Sensor der Instanz {p} ungültig bei Modus {modus}, keine Meldung"


def k4(c: Ctx):
    f = c.flags
    if not c.settings[C.S_REGULATION_ENABLED]:
        soll = "disabled"
    elif f["_cycle_blocked"]:
        soll = "blocked"
    elif f["surplus_active"]:
        soll = "exporting"
    elif f["tariff_charge_active"]:
        soll = "tariff_charging"
    elif f["ac_charge_active"]:
        soll = "ac_charging"
    elif f["discharge_locked"]:
        soll = "discharge_locked"
    elif f["is_night"]:
        soll = "night_off"
    elif f["cycle_active"]:
        soll = "battery_supply"
    elif f["current_zone"] == 3:
        soll = "safety_stop"
    else:
        soll = "pv_direct"
    if f["operating_state"] != soll:
        return f"Betriebszustand {f['operating_state']!r} statt {soll!r}"


def k5(c: Ctx):
    eid = c.cfg.get(C.CONF_EXPORT_LIMIT)
    if not eid or not c.normal():
        return None
    soll = max(c.settings[C.S_HARD_LIMIT_Z0], c.settings[C.S_HARD_LIMIT_Z1])
    ist = zahl(c.nachher, eid)
    if ist is None or abs(ist - soll) >= 1:
        return f"Export-Limit {ist} statt {soll}"


# Regeln, die erst nach dem Übergang gelten: der erste zutreffende Fall gewinnt, der
# gewollte Zustand stellt sich ein bis zwei Läufe später ein.
VERZOEGERT = {"b1", "d3", "e1", "h2"}


def verstoss(name: str, c: Ctx) -> str | None:
    """Verstoß gegen eine Regel; verzögerte Regeln nur in Läufen ohne Übergang."""
    if name in VERZOEGERT and c.uebergang():
        return None
    return REGELN[name](c)


REGELN = {n: f for n, f in globals().items() if len(n) == 2 and n[0] in "abcdefhijk" and n[1].isdigit() and callable(f)}


# ── Ablauf ───────────────────────────────────────────────────────────────────

async def _lauf(kind: str, spec: dict) -> list[Ctx]:
    hass, _logs, coords = scenarios._setup_env(spec)
    for inst in spec["instances"]:
        coord = coords[inst["prefix"]]
        await coord.async_setup()
        if not inst["stored"]:
            coord.settings.update(inst["settings"])
        coord.integral = inst["integral"]
        coord._prev_actual = inst["prev_actual"]
    flags = {p: h.coord_state(c) for p, c in coords.items()}
    aus_seit = {p: None for p in coords}
    out = []
    for idx, step in enumerate(spec["steps"]):
        h.CLOCK.now += step["advance"]
        scenarios._apply_states(hass, step["set"])
        hass.events = []
        abgeschaltet = set()
        aenderungen = [("a", step["changes"])] if "changes" in step else []
        aenderungen += list(step.get("changes_for", {}).items())
        for p, changes in aenderungen:
            war_an = coords[p].settings[C.S_REGULATION_ENABLED]
            await coords[p].async_update_settings(dict(changes))
            if war_an and not coords[p].settings[C.S_REGULATION_ENABLED]:
                aus_seit[p] = idx
                abgeschaltet.add(p)
            elif not war_an and coords[p].settings[C.S_REGULATION_ENABLED]:
                aus_seit[p] = None
        ereignisse_aenderung = [e for e in hass.events if e[0] == "call"]
        targets = list(coords) if step["who"] == "all" else ["a"]
        runde = []
        for p in targets:
            coord = coords[p]
            vorher = schnappschuss(hass)
            hass.events = []
            await coord._async_regulate()
            aufrufe = [e for e in hass.events if e[0] == "call"]
            if p in abgeschaltet:
                aufrufe = ereignisse_aenderung + aufrufe
            neu = h.coord_state(coord)
            runde.append(Ctx(kind, spec["id"], idx, p, coord.entry.data, dict(coord.settings), vorher,
                             schnappschuss(hass), flags[p], neu, aufrufe,
                             dist=spec["dist"] if spec.get("has_dist_config") else None,
                             aus_seit=aus_seit[p], abgeschaltet_jetzt=p in abgeschaltet,
                             geregelt={q: bool(c.settings[C.S_REGULATION_ENABLED]) for q, c in coords.items()}))
            flags[p] = neu
        nach = schnappschuss(hass)
        alle = {p: (coords[p].entry.data, flags[p], nach) for p in coords}
        for ctx in runde:
            ctx.alle = alle
            ctx.runde_vollstaendig = len(runde) == len(coords)
        out.extend(runde)
    return out


def kontexte(kind: str, spec: dict) -> list[Ctx]:
    return asyncio.run(_lauf(kind, spec))


def pruefen(kinds=KINDS, regeln=None) -> dict[str, list[tuple[str, int, str, str]]]:
    regeln = regeln or list(REGELN)
    befunde: dict[str, list] = defaultdict(list)
    for kind in kinds:
        for spec in scenarios.generate(kind):
            for ctx in kontexte(kind, copy.deepcopy(spec)):
                for name in regeln:
                    msg = verstoss(name, ctx)
                    if msg:
                        befunde[name].append((ctx.spec_id, ctx.schritt, ctx.prefix, msg, ctx.start_konsistent()))
    return befunde


def e3_befunde(kinds=("tariff",)) -> list[tuple[str, str]]:
    """E3: ungültiger Preis schreibt dasselbe wie Tarif aus (Vergleich zweier Läufe)."""
    out = []
    for kind in kinds:
        for spec in scenarios.generate(kind):
            s = spec["instances"][0]["settings"]
            sensor = s[C.S_TARIFF_PRICE_SENSOR]
            if not s[C.S_TARIFF_ENABLED] or not sensor:
                continue
            werte = [spec["shared"].get(sensor)] + [st["set"].get(sensor) for st in spec["steps"] if sensor in st["set"]]
            if any(w and zahl({sensor: {"state": str(w.get("state")), "attrs": w.get("attrs", {})}}, sensor) is not None
                   for w in werte):
                continue
            mit = [x.aufrufe for x in kontexte(kind, copy.deepcopy(spec))]
            ohne_spec = copy.deepcopy(spec)
            ohne_spec["instances"][0]["settings"][C.S_TARIFF_ENABLED] = False
            ohne = [x.aufrufe for x in kontexte(kind, ohne_spec)]
            if mit != ohne:
                out.append((spec["id"], "Schreibfolge mit ungültigem Preis weicht von Tarif aus ab"))
    return out


if __name__ == "__main__":
    auswahl = [a for a in sys.argv[1:] if a in REGELN] or None
    ergebnis = pruefen(regeln=auswahl)
    for name in auswahl or REGELN:
        treffer = ergebnis.get(name, [])
        halten = [t for t in treffer if t[4]]
        print(f"{name}: {len(halten)} bei konsistentem Start, {len(treffer) - len(halten)} beim Heilen")
        for t in halten[:4]:
            print("   ", t[:4])
    if not auswahl:
        e3 = e3_befunde()
        print(f"e3: {len(e3)}")
        for t in e3[:4]:
            print("   ", t)
