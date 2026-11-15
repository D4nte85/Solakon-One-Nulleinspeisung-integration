"""Gemeinsame pytest-Einstellungen der Testumgebung."""
from __future__ import annotations

import pytest

from tests import harness as h


@pytest.fixture(autouse=True)
def _offene_tasks_schliessen():
    """Nach jedem Test nicht abgearbeitete Tasks schließen (siehe `harness.close_open_tasks`)."""
    yield
    h.close_open_tasks()
