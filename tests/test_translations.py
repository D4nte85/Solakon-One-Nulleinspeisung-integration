"""Übersetzungsdateien: gleiche Schlüssel in jeder Sprache, Schlüsselform wie hassfest, ENUM-Optionen übersetzt."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests import harness as h

KOMPONENTE = Path(__file__).parent.parent / "custom_components" / "solakon_nulleinspeisung"


def _schluessel(daten: dict, praefix: str = "") -> set[str]:
    ergebnis = set()
    for k, v in daten.items():
        if isinstance(v, dict):
            ergebnis |= _schluessel(v, f"{praefix}{k}.")
        else:
            ergebnis.add(f"{praefix}{k}")
    return ergebnis


@pytest.mark.parametrize("links, rechts", [
    ("translations/de.json", "translations/en.json"),
    ("frontend/panel.de.json", "frontend/panel.en.json"),
    ("strings.json", "translations/en.json"),
])
def test_gleiche_schluessel(links, rechts):
    a = _schluessel(json.loads((KOMPONENTE / links).read_text(encoding="utf-8")))
    b = _schluessel(json.loads((KOMPONENTE / rechts).read_text(encoding="utf-8")))
    assert not a - b, f"nur in {links}: {sorted(a - b)}"
    assert not b - a, f"nur in {rechts}: {sorted(b - a)}"


# Regel aus hassfest (translations): Schlüssel nur [a-z0-9-_], nicht mit - oder _ am Rand.
SCHLUESSEL = re.compile(r"[a-z0-9]([a-z0-9_-]*[a-z0-9])?")


@pytest.mark.parametrize("datei", ["strings.json", "translations/de.json", "translations/en.json"])
def test_schluesselform(datei):
    daten = json.loads((KOMPONENTE / datei).read_text(encoding="utf-8"))
    falsch = [s for s in _schluessel(daten) if not all(SCHLUESSEL.fullmatch(t) for t in s.split("."))]
    assert not falsch, f"{datei}: {sorted(falsch)}"


def test_fall_optionen_uebersetzt():
    zustaende = json.loads((KOMPONENTE / "strings.json").read_text(encoding="utf-8"))
    zustaende = zustaende["entity"]["sensor"]["active_fall"]["state"]
    assert set(h.const.FALL_KEYS) == set(zustaende)
