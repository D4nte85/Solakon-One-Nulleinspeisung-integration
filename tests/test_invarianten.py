"""Prüft die Verhaltensregeln aus `invarianten.py` über alle Charakterisierungsszenarien.

Gezählt werden nur Regelläufe mit konsistentem Start. Eine Regel mit offener Bugfix-Seite
steht in OFFEN und muss rot sein (strikt erwarteter Fehlschlag); wird sie grün, ist der
Eintrag zu entfernen.
"""
from __future__ import annotations

import dataclasses

import pytest

from tests import invarianten as inv

OFFEN = {
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


def _gesperrtes_ladeende() -> inv.Ctx:
    """Regellauf des Repros zum Lade-Ende in der Tarifsperre, in dem Fall H feuert."""
    from pathlib import Path
    from tests import repro
    szenario = repro.lade(Path(__file__).parent / "repro" / "fix-2026-11-16-ladeende-in-tarifsperre-entlaedt.yaml")
    spec = {**repro.spec_aus(szenario), "id": "ladeende-tarifsperre"}
    ctx = [c for c in inv.kontexte("repro", spec) if inv._fall_neu(c, "H")]
    assert ctx, "Repro ohne Fall H"
    return ctx[0]


def test_j7_haelt_im_repro_und_schlaegt_bei_verstoss_an():
    c = _gesperrtes_ladeende()
    assert inv.j7(c) is None
    assert inv.j7(dataclasses.replace(c, flags={**c.flags, "cycle_active": True}))
    assert inv.j7(dataclasses.replace(c, flags={**c.flags, "resting": False}))
    schreiben = ("call", "number", "set_value", c.e(inv.C.CONF_ACTIVE_POWER), 300)
    assert inv.j7(dataclasses.replace(c, aufrufe=[*c.aufrufe, schreiben]))
