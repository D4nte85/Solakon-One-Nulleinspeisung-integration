"""Panel und Schema: Zahlenfelder ohne eigene Grenzen, Mock-Antwort gleich get_schema."""
from __future__ import annotations

import asyncio
import json
import re

from tests import harness as h
from tests.ha_stubs import ActiveConnection

PANEL = (h.ROOT / "custom_components/solakon_nulleinspeisung/frontend/solakon-panel.js").read_text(encoding="utf-8")
MOCK = (h.ROOT / "index.html").read_text(encoding="utf-8")


def _schema() -> dict:
    conn = ActiveConnection()
    asyncio.run(h.integration._ws_get_schema(h.FakeHass("de"), conn, {"id": 1}))
    return json.loads(json.dumps(conn.sent[0][2]))


def _num_keys() -> set[str]:
    """Schlüssel aller Zahlenfelder im Layout, Vorlagen aufgelöst."""
    keys = set(re.findall(r'\{ *k: *"([a-z0-9_]+)", *t: *"num"', PANEL))
    for prefix, k in re.findall(r'sensorFeatureFields\("([a-z0-9_]+)", "([a-z]+)"\)', PANEL):
        keys.add(f"{prefix}_{k}")
    templates = re.findall(r'\{ *k: *`dyn_\$\{prefix\}_([a-z]+)`, *t: *"num"', PANEL)
    for prefix in re.findall(r'dynOffSection\("[a-z0-9_]+", "([a-z0-9]+)"', PANEL):
        keys.update(f"dyn_{prefix}_{t}" for t in templates)
    return keys


def test_layout_ohne_grenzen():
    assert not re.search(r"\b(min|max|step): *-?[\d.]", PANEL)


def test_zahlenfelder_im_schema():
    settings = _schema()["settings"]
    keys = _num_keys()
    assert len(keys) >= 40
    assert sorted(k for k in keys if settings.get(k, {}).get("kind") not in ("int", "float")) == []
    assert sorted(k for k in keys if len(settings[k].get("ui") or ()) != 3) == []


def test_mock_antwortet_wie_get_schema():
    block = re.search(r"// SCHEMA-BEGIN\n *const SCHEMA = (.*);\n *// SCHEMA-END", MOCK)
    assert block and json.loads(block.group(1)) == _schema()
