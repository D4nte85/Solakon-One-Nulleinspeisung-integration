"""Reproduktionsszenario aus einem HA-Verlauf bauen.

Aufruf:
  python tests/repro_import.py verlauf.csv --map netz=sensor.shelly_power \\
      --map a.soc=sensor.solakon_soc --map a.ist=sensor.solakon_ist [--einheit netz=kW] \\
      [--von 2026-09-01T10:00] [--bis 2026-09-01T10:30] [--takt netz|<sekunden>] > szenario.yaml

Eingabe ist der CSV-Export des HA-Verlaufs (Spalten `entity_id,state,last_changed`).
`--map` ordnet einer Szenario-Größe (`netz`, `<prefix>.<kurzname>` oder eine volle
Entity-ID) die Entity des Reporters zu. Startwerte sind die letzten Werte vor `--von`.
`--takt netz` (Standard) legt einen Regelschritt je Änderung des Netzsensors an, wie
der Trigger der Integration; eine Zahl legt Schritte im festen Sekundenraster an.
Settings, Flags und Erwartungen trägt man danach von Hand ein.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from tests.repro import INSTANZ_SENSOREN  # noqa: E402


def zeit(text: str) -> float:
    """ISO-Zeitstempel (mit Z oder Offset, ohne Zone als UTC) → Unix-Sekunden."""
    dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()


def wert(text: str):
    """Zustandstext als Zahl, sonst unverändert (z. B. `unavailable`)."""
    try:
        zahl = float(text)
    except ValueError:
        return text
    return int(zahl) if zahl.is_integer() else zahl


def lies_verlauf(pfad: Path, zuordnung: dict[str, str]) -> list[tuple[float, str, object]]:
    """Zeilen der zugeordneten Entities als (Zeit, Szenario-Größe, Wert), zeitlich sortiert."""
    rueckwaerts = {eid: groesse for groesse, eid in zuordnung.items()}
    with pfad.open(encoding="utf-8", newline="") as fh:
        zeilen = [(zeit(r["last_changed"]), rueckwaerts[r["entity_id"]], wert(r["state"]))
                  for r in csv.DictReader(fh) if r.get("entity_id") in rueckwaerts]
    return sorted(zeilen, key=lambda z: z[0])


def baue(zeilen, von: float | None, bis: float | None, takt: str, einheiten: dict[str, str]) -> dict:
    """Szenario-Dict: Startwerte vor `von`, danach Regelschritte im gewählten Takt."""
    def angabe(groesse, w):
        return {"wert": w, "einheit": einheiten[groesse]} if groesse in einheiten else w

    start = von if von is not None else (zeilen[0][0] if zeilen else 0.0)
    stand, schritte = {}, []
    davor = [z for z in zeilen if z[0] <= start]
    danach = [z for z in zeilen if z[0] > start and (bis is None or z[0] <= bis)]
    for _, groesse, w in davor:
        stand[groesse] = w

    if takt == "netz":
        gruppen, offen, t_letzt = [], {}, start
        for t, groesse, w in danach:
            offen[groesse] = w
            if groesse == "netz":
                gruppen.append((t, offen))
                offen = {}
        for t, setzen in gruppen:
            schritte.append({"nach": round(t - t_letzt, 1),
                             "setzen": {g: angabe(g, w) for g, w in setzen.items()}})
            t_letzt = t
    else:
        raster = float(takt)
        t, i = start + raster, 0
        ende = bis if bis is not None else (danach[-1][0] if danach else start)
        while t <= ende + 1e-9:
            setzen = {}
            while i < len(danach) and danach[i][0] <= t:
                setzen[danach[i][1]] = danach[i][2]
                i += 1
            schritte.append({"nach": raster, "setzen": {g: angabe(g, w) for g, w in setzen.items()}})
            t += raster

    szenario: dict = {"titel": "TODO", "bezug": "TODO", "netz": angabe("netz", stand.pop("netz", 0))}
    instanzen: dict[str, dict] = {}
    geteilt = {}
    for groesse, w in stand.items():
        kopf, _, kurz = groesse.partition(".")
        if kurz in INSTANZ_SENSOREN and "." not in kurz and len(kopf) == 1:
            instanzen.setdefault(kopf, {"prefix": kopf, "settings": {"regulation_enabled": True},
                                        "sensoren": {}})["sensoren"][kurz] = angabe(groesse, w)
        else:
            geteilt[groesse] = angabe(groesse, w)
    if geteilt:
        szenario["sensoren"] = geteilt
    szenario["instanzen"] = [instanzen[p] for p in sorted(instanzen)] or [
        {"prefix": "a", "settings": {"regulation_enabled": True}}]
    szenario["schritte"] = schritte or [{"nach": 0}]
    szenario["erwartet"] = [{"schritt": "letzter", "zustand": {"last_error": ""}}]
    return szenario


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--map", action="append", default=[], metavar="GROESSE=ENTITY", required=True)
    ap.add_argument("--einheit", action="append", default=[], metavar="GROESSE=EINHEIT")
    ap.add_argument("--von")
    ap.add_argument("--bis")
    ap.add_argument("--takt", default="netz")
    args = ap.parse_args(argv)
    zuordnung = dict(m.split("=", 1) for m in args.map)
    einheiten = dict(e.split("=", 1) for e in args.einheit)
    if "netz" not in zuordnung:
        ap.error("--map netz=<entity> fehlt")
    zeilen = lies_verlauf(args.csv, zuordnung)
    if not zeilen:
        print("Keine Zeilen der zugeordneten Entities im Verlauf.", file=sys.stderr)
        return 1
    szenario = baue(zeilen, zeit(args.von) if args.von else None, zeit(args.bis) if args.bis else None,
                    args.takt, einheiten)
    print("# Aus HA-Verlauf erzeugt — Settings, Flags und Erwartungen von Hand ergänzen.")
    print(yaml.safe_dump(szenario, allow_unicode=True, sort_keys=False, width=100), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
