"""Reproduktionsszenario abspielen: python tests/repro.py <szenario.yaml> [--still]

Ein Reproduktionsszenario beschreibt Ausgangszustand, Zeitschritte und erwartete
Beobachtungen eines Fehlervorgangs in YAML (Format: tests/README.md). Die Ausgabe
zeigt je Schritt gesetzte Sensoren, Schreibbefehle und geänderte Zustände, danach
das Ergebnis jeder Erwartung. Exit 0: alle Erwartungen erfüllt · 1: mindestens eine
nicht · 2: Szenario fehlerhaft.
"""
from __future__ import annotations

import asyncio
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from tests import harness as h  # noqa: E402
from tests import scenarios  # noqa: E402

C = h.const

# Kurzname → (Entity-Muster, Standardeinheit, Standardwert) je Instanz
INSTANZ_SENSOREN = {
    "soc":          ("sensor.{p}_soc", "%", 50),
    "solar":        ("sensor.{p}_solar", "W", 0),
    "ist":          ("sensor.{p}_actual", "W", 0),
    "countdown":    ("sensor.{p}_countdown", "s", 3000),
    "leistung":     ("number.{p}_power", None, 0),
    "entladestrom": ("number.{p}_discharge", None, 40),
    "timeout":      ("number.{p}_timeout", None, 3599),
    "modus":        ("select.{p}_mode", None, "1"),
    "export":       ("number.{p}_export", None, 800),
    "kapazitaet":   ("sensor.{p}_capacity", "kWh", 2.0),
}
FLAGS = ("cycle_active", "surplus_active", "ac_charge_active", "tariff_charge_active", "solar_zero_entry_armed")


class SzenarioFehler(Exception):
    """Szenariodatei entspricht nicht dem Format."""


def zustand(wert, einheit=None) -> dict:
    """Sensorangabe (Zahl, Text, null oder {wert, einheit, alter}) als State-Dict."""
    if isinstance(wert, dict):
        unbekannt = set(wert) - {"wert", "einheit", "alter"}
        if unbekannt:
            raise SzenarioFehler(f"unbekannte Sensorfelder {sorted(unbekannt)}")
        out = zustand(wert.get("wert"), wert.get("einheit", einheit))
        if "alter" in wert:
            out["age"] = wert["alter"]
        return out
    if wert is None:
        return {"state": None}
    return {"state": wert, "attrs": {"unit_of_measurement": einheit} if einheit else {}}


def entity_id(schluessel: str, prefixe: list[str]) -> tuple[str, str | None]:
    """`netz`, `<prefix>.<kurzname>` oder volle Entity-ID → (Entity-ID, Standardeinheit)."""
    if schluessel == "netz":
        return "sensor.grid", "W"
    kopf, _, kurz = schluessel.partition(".")
    if kopf in prefixe and kurz in INSTANZ_SENSOREN:
        muster, einheit, _ = INSTANZ_SENSOREN[kurz]
        return muster.format(p=kopf), einheit
    if "." in schluessel and kopf not in prefixe:
        return schluessel, None
    raise SzenarioFehler(f"unbekannter Sensorschlüssel {schluessel!r}")


def spec_aus(szenario: dict) -> dict:
    """Szenario-YAML in das Spec-Format von tests/scenarios.py übersetzen."""
    instanzen = szenario.get("instanzen") or [{"prefix": "a"}]
    prefixe = [i.get("prefix", "a") for i in instanzen]
    if prefixe[0] != "a":
        raise SzenarioFehler("die erste Instanz braucht prefix a")
    spec = {
        "language": szenario.get("sprache", "de"),
        "hour": szenario.get("stunde", 12),
        "grid": zustand(szenario.get("netz", 0), "W"),
        "dist": szenario.get("verteilung") or {},
        "has_dist_config": "verteilung" in szenario,
        "soc_switch_state": None,
        "shared": {},
        "instances": [],
        "steps": [],
    }
    for schluessel, wert in (szenario.get("sensoren") or {}).items():
        eid, einheit = entity_id(schluessel, prefixe)
        spec["shared"][eid] = zustand(wert, einheit)
    for inst in instanzen:
        p = inst.get("prefix", "a")
        unbekannt = set(inst.get("sensoren") or {}) - set(INSTANZ_SENSOREN)
        if unbekannt:
            raise SzenarioFehler(f"Instanz {p}: unbekannte Sensoren {sorted(unbekannt)}")
        states = {}
        for kurz, (muster, einheit, standard) in INSTANZ_SENSOREN.items():
            states[muster.format(p=p)] = zustand((inst.get("sensoren") or {}).get(kurz, standard), einheit)
        settings = {**copy.deepcopy(C.SETTINGS_DEFAULTS), **(inst.get("settings") or {})}
        unbekannt = set(inst.get("settings") or {}) - set(C.SETTINGS_DEFAULTS)
        if unbekannt:
            raise SzenarioFehler(f"Instanz {p}: unbekannte Settings {sorted(unbekannt)}")
        flags = {f: False for f in FLAGS}
        flags.update(inst.get("flags") or {})
        spec["instances"].append({
            "prefix": p,
            "grid_sensor": inst.get("netzsensor", "sensor.grid"),
            "export_limit": inst.get("export_limit", True),
            "settings": settings,
            "flags": flags,
            "stored": True,
            "drop_flags": [],
            "integral": float(inst.get("integral", 0.0)),
            "prev_actual": float(inst.get("vorheriger_ist", 0.0)),
            "follow_actual": inst.get("folgt_ist", 1),
            "states": states,
        })
    for nr, schritt in enumerate(szenario.get("schritte") or [{}], 1):
        unbekannt = set(schritt) - {"nach", "setzen", "settings", "wer"}
        if unbekannt:
            raise SzenarioFehler(f"Schritt {nr}: unbekannte Felder {sorted(unbekannt)}")
        setzen = {}
        for schluessel, wert in (schritt.get("setzen") or {}).items():
            eid, einheit = entity_id(schluessel, prefixe)
            setzen[eid] = zustand(wert, einheit)
        step = {"advance": schritt.get("nach", 0), "set": setzen, "who": schritt.get("wer", "a")}
        if schritt.get("settings"):
            step["changes"] = schritt["settings"]
        spec["steps"].append(step)
    return spec


def _zahl_gleich(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-6
    except (TypeError, ValueError):
        return a == b


def _aufrufe(schritt_rec: dict, entity: str) -> list:
    return [ev[4] for ev in schritt_rec["events"] if ev[0] == "call" and ev[3] == entity]


def pruefe(erwartung: dict, rec: dict) -> tuple[bool, str]:
    """Eine Erwartung gegen das Protokoll prüfen → (erfüllt, Beschreibung mit Istwert)."""
    schritte = rec["steps"]
    auswahl = erwartung.get("schritt", "letzter")
    if auswahl == "alle":
        nummern = list(range(1, len(schritte) + 1))
    elif auswahl == "letzter":
        nummern = [len(schritte)]
    elif isinstance(auswahl, int) and 1 <= auswahl <= len(schritte):
        nummern = [auswahl]
    else:
        raise SzenarioFehler(f"ungültiger Schritt {auswahl!r}")
    instanz = erwartung.get("instanz", "a")
    ort = f"Schritt {auswahl}" if auswahl != "alle" else "alle Schritte"

    for art, zeichen in (("zustand", "="), ("zustand_nicht", "≠")):
        if art not in erwartung:
            continue
        abweichend = []
        for nr in nummern:
            ist = schritte[nr - 1]["state"][instanz]
            for attr, soll in erwartung[art].items():
                if attr not in ist:
                    raise SzenarioFehler(f"unbekanntes Zustandsattribut {attr!r}")
                if _zahl_gleich(ist[attr], soll) != (art == "zustand"):
                    abweichend.append(f"{attr}={ist[attr]!r} (Schritt {nr})")
        text = f"{ort}, Instanz {instanz}: " + ", ".join(f"{k}{zeichen}{v!r}" for k, v in erwartung[art].items())
        return not abweichend, text + ("" if not abweichend else " — ist " + ", ".join(abweichend))

    for art in ("aufruf", "kein_aufruf"):
        if art not in erwartung:
            continue
        bed = erwartung[art]
        entity = entity_id(bed["entity"], list(rec["steps"][0]["state"]))[0]
        werte = [w for nr in nummern for w in _aufrufe(schritte[nr - 1], entity)]
        passend = [w for w in werte
                   if ("wert" not in bed or _zahl_gleich(w, bed["wert"]))
                   and ("wert_max" not in bed or float(w) <= bed["wert_max"])
                   and ("wert_min" not in bed or float(w) >= bed["wert_min"])]
        grenzen = ", ".join(f"{z} {bed[k]}" for k, z in (("wert", "="), ("wert_min", "≥"), ("wert_max", "≤")) if k in bed)
        text = f"{ort}: {'ein' if art == 'aufruf' else 'kein'} Schreibbefehl auf {entity}" \
               + (f" {grenzen}" if grenzen else "") + f" — geschrieben: {werte or 'nichts'}"
        return (bool(passend) if art == "aufruf" else not passend), text

    if "log" in erwartung:
        treffer = [r for r in rec["logs"] if erwartung["log"] in r[1]]
        return bool(treffer), f"Log enthält {erwartung['log']!r}" + ("" if treffer else " — nicht gefunden")
    raise SzenarioFehler(f"Erwartung ohne zustand/zustand_nicht/aufruf/kein_aufruf/log: {erwartung}")


def lade(pfad: Path) -> dict:
    try:
        szenario = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SzenarioFehler(f"YAML: {exc}") from exc
    if not isinstance(szenario, dict) or not szenario.get("erwartet"):
        raise SzenarioFehler("Szenario braucht mindestens eine Erwartung unter `erwartet`")
    return szenario


def spiele(szenario: dict) -> tuple[dict, list[tuple[bool, str]]]:
    """Szenario ausführen → (Protokoll, Ergebnis je Erwartung)."""
    spec = spec_aus(szenario)
    rec = h.jsonable(asyncio.run(scenarios._run_cycle_spec(spec)))
    return rec, [pruefe(e, rec) for e in szenario["erwartet"]]


def bericht(szenario: dict, rec: dict) -> list[str]:
    """Lesbarer Ablauf: je Schritt gesetzte Sensoren, Schreibbefehle, geänderte Zustände."""
    spec = spec_aus(szenario)
    zeilen = [f"# {szenario.get('titel', '(ohne Titel)')}"]
    vorher = {}
    zeit = 0
    for nr, (step, srec) in enumerate(zip(spec["steps"], rec["steps"]), 1):
        zeit += step["advance"]
        zeilen.append(f"\nSchritt {nr} · t={zeit} s · regelt: {step['who']}")
        for eid, st in step["set"].items():
            einheit = (st.get("attrs") or {}).get("unit_of_measurement", "") \
                if isinstance(st["state"], (int, float)) else ""
            zeilen.append(f"  gesetzt   {eid} = {st['state']} {einheit}".rstrip())
        if "changes" in step:
            zeilen.append(f"  Settings  {step['changes']}")
        for ev in srec["events"]:
            if ev[0] == "call":
                zeilen.append(f"  schreibt  {ev[3]} = {ev[4]}")
        for prefix, st in srec["state"].items():
            alt = vorher.get(prefix, {})
            geaendert = [f"{k}: {alt[k]!r} → {v!r}" for k, v in st.items()
                         if k in alt and alt[k] != v and not k.endswith("_ts")]
            if not alt:
                geaendert = [f"{k}={st[k]!r}" for k in ("active_fall", "operating_state", "current_zone",
                                                        "cycle_active", "resting", "last_error")]
            for g in geaendert:
                zeilen.append(f"  {prefix}         {g}")
        vorher = srec["state"]
    if rec["logs"]:
        zeilen.append("\nLog (WARNING und höher):")
        zeilen += [f"  {lvl} {msg}" for lvl, msg, *_ in rec["logs"]]
    return zeilen


def main(argv: list[str]) -> int:
    pfade = [a for a in argv if not a.startswith("--")]
    if len(pfade) != 1:
        print(__doc__)
        return 2
    try:
        szenario = lade(Path(pfade[0]))
        rec, ergebnisse = spiele(szenario)
    except SzenarioFehler as exc:
        print(f"Szenario fehlerhaft: {exc}")
        return 2
    if "--still" not in argv:
        print("\n".join(bericht(szenario, rec)))
        print()
    for ok, text in ergebnisse:
        print(f"{'✓' if ok else '✗'} {text}")
    erfuellt = all(ok for ok, _ in ergebnisse)
    print(f"\n{'Erwartungen erfüllt' if erfuellt else 'Erwartungen NICHT erfüllt'}"
          + (" (Szenario als offen markiert)" if szenario.get("offen") else ""))
    return 0 if erfuellt else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
