"""Vergleicht das heutige Verhalten mit den Referenzprotokollen in golden/."""
from __future__ import annotations

import difflib
import gzip
import json
from pathlib import Path

import pytest

from tests import scenarios
from tests.regen import spec_sha

GOLDEN = Path(__file__).resolve().parent / "golden"


def _load(kind: str) -> list[dict]:
    text = gzip.decompress((GOLDEN / f"{kind}.jsonl.gz").read_bytes()).decode("utf-8")
    return [json.loads(ln) for ln in text.splitlines() if ln]


def _diff(expected, actual) -> str:
    a = json.dumps(expected, indent=1, sort_keys=True, ensure_ascii=False).splitlines()
    b = json.dumps(actual, indent=1, sort_keys=True, ensure_ascii=False).splitlines()
    return "\n".join(list(difflib.unified_diff(a, b, "referenz", "aktuell", lineterm="", n=4))[:120])


@pytest.mark.parametrize("kind", list(scenarios.COUNTS))
def test_golden(kind):
    golden = _load(kind)
    specs = scenarios.generate(kind)
    assert [g["spec_sha"] for g in golden] == [spec_sha(sp) for sp in specs], "Szenariogenerator geändert — regen.py prüfen"
    failures = []
    for item, spec in zip(golden, specs):
        rec = json.loads(json.dumps(scenarios.run(kind, spec), sort_keys=True, ensure_ascii=False))
        if rec != item["rec"]:
            failures.append((spec["id"], _diff(item["rec"], rec)))
    if failures:
        first_id, first_diff = failures[0]
        ids = ", ".join(f for f, _ in failures[:30])
        pytest.fail(f"{len(failures)} abweichende Szenarien ({ids})\n\nErstes: {first_id}\n{first_diff}")
