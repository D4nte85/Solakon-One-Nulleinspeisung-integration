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
