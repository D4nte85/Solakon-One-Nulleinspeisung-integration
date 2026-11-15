"""Panel und Schema: Zahlenfelder ohne eigene Grenzen, Mock-Antwort gleich get_schema."""
from __future__ import annotations

import asyncio
import json
import re

from tests import harness as h

PANEL = (h.ROOT / "custom_components/solakon_nulleinspeisung/frontend/solakon-panel.js").read_text(encoding="utf-8")
MOCK = (h.ROOT / "index.html").read_text(encoding="utf-8")


def _schema() -> dict:
    sent = asyncio.run(h.ws_call(h.integration._ws_get_schema, h.FakeHass("de")))
    return json.loads(json.dumps(sent[0][2]))


def _num_keys() -> set[str]:
    """Schlüssel aller Zahlenfelder im Layout, Vorlagen aufgelöst."""
    keys = set(re.findall(r'\{ *k: *"([a-z0-9_]+)", *t: *"num"', PANEL))
    for prefix, k in re.findall(r'sensorFeatureFields\("([a-z0-9_]+)", "([a-z]+)"\)', PANEL):
        keys.add(f"{prefix}_{k}")
    templates = re.findall(r'\{ *k: *`dyn_\$\{prefix\}_([a-z]+)`, *t: *"num"', PANEL)
    for prefix in re.findall(r'dynOffSection\("[a-z0-9_]+", "([a-z0-9_]+)"', PANEL):
        keys.update(f"dyn_{prefix}_{t}" for t in templates)
    return keys


def test_layout_ohne_grenzen():
    assert not re.search(r"\b(min|max|step): *-?[\d.]", PANEL)


def test_zahlenfelder_im_schema():
    schema = _schema()
    fields = {**schema["distribution"], **schema["settings"]}
    keys = _num_keys()
    assert len(keys) >= 40
    assert sorted(k for k in keys if fields.get(k, {}).get("kind") not in ("int", "float")) == []
    assert sorted(k for k in keys if len(fields[k].get("ui") or ()) != 3) == []


def test_verteilungsseite_fuehrt_jedes_feld_der_verteilung():
    layout = set(re.findall(r'\{ *k: *"([a-z0-9_]+)", *t: *"[a-z]+", *lk:', PANEL))
    assert layout == set(_schema()["distribution"]) | {"capacity_sensor"}


def test_mock_antwortet_wie_get_schema():
    block = re.search(r"// SCHEMA-BEGIN\n *const SCHEMA = (.*);\n *// SCHEMA-END", MOCK)
    assert block and json.loads(block.group(1)) == _schema()


def test_jeder_ws_statusschluessel_wird_im_panel_gelesen():
    status_view = __import__(h.PKG + ".status_view", fromlist=["WS_STATUS_KEYS"])
    names = [n if isinstance(n, str) else n[0] for n in status_view.WS_STATUS_KEYS]
    ungelesen = [n for n in names if not re.search(rf"\.{n}\b|\b{n}:|\"{n}\"", PANEL)]
    assert ungelesen == []
