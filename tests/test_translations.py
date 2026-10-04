"""Übersetzungsdateien: gleiche Schlüssel in jeder Sprache und in strings.json."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

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
