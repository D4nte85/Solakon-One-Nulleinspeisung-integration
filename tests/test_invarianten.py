"""Prüft die Verhaltensregeln aus `invarianten.py` über alle Charakterisierungsszenarien.

Gezählt werden nur Regelläufe mit konsistentem Start. Eine Regel mit offener Bugfix-Seite
steht in OFFEN und muss rot sein (strikt erwarteter Fehlschlag); wird sie grün, ist der
Eintrag zu entfernen.
"""
from __future__ import annotations

import pytest

from tests import invarianten as inv

OFFEN = {
    "c5": "fix-2026-09-19-verteilungswarnung-doppelt-ac-laden",
}


@pytest.fixture(scope="module")
def befunde():
    return inv.pruefen()


@pytest.mark.parametrize("regel", sorted(inv.REGELN))
def test_regel(befunde, regel):
    treffer = [t[:4] for t in befunde.get(regel, []) if t[4]]
    if regel in OFFEN:
        assert treffer, f"als offen markiert, aber ohne Verstoß — Eintrag in OFFEN entfernen ({OFFEN[regel]})"
        pytest.xfail(f"offener Fehler {OFFEN[regel]}: {len(treffer)} Verstöße")
    assert not treffer, "\n".join(map(str, treffer[:10]))


def test_e3():
    treffer = inv.e3_befunde()
    assert not treffer, "\n".join(map(str, treffer[:10]))
