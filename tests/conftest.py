"""Gemeinsame pytest-Einstellungen der Testumgebung."""
from __future__ import annotations

import pytest

from tests import harness as h

# Klon der Geräteintegration (tests/README.md): eigene Tests, nicht Teil dieser Suite.
collect_ignore = ["geraet-integration"]


@pytest.fixture(autouse=True)
def _offene_tasks_schliessen():
    """Nach jedem Test nicht abgearbeitete Tasks schließen (siehe `harness.close_open_tasks`)."""
    yield
    h.close_open_tasks()


@pytest.fixture(params=["bis-2026.7", "ab-2026.8"])
def geraeteregistrierung(request, monkeypatch):
    """Test je Stand der Geräteregistrierung: alte API (Mindestversion) und API ab HA 2026.8."""
    if request.param == "ab-2026.8":
        monkeypatch.setattr(h.ha_stubs, "DeviceRegistry", h.ha_stubs.DeviceRegistry2026_8)
    return request.param
