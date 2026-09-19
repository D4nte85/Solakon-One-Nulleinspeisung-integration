"""Meldungen eines Zyklus ohne Coordinator: Reihenfolge, harter Fehler, Schreibwarnung."""
from __future__ import annotations

import importlib

import pytest

from tests import harness as h

messages = importlib.import_module(h.PKG + ".messages")

W1 = ("err_tariff_sensor_unavailable", {"sensor": "sensor.preis"})
W2 = ("warn_dist_soc_sensor", {})
F = ("err_soc_zone1_zone3", {})
H1 = ("warn_output_zero_unconfirmed", {"attempts": 2, "actual": 80.0})
H2 = ("warn_output_stuck", {"actual": 300.0, "limit": 800})


@pytest.mark.parametrize("calls, expected", [
    ([], []),
    ([("warn", W1), ("warn", W2)], [W1, W2]),
    ([("warn", W1), ("fail", F), ("warn", W2)], [F]),
    ([("hardware", H1), ("fail", F)], [F]),
    ([("hardware", H1), ("warn", W1)], [W1, H1]),
    ([("hardware", H1), ("hardware", H2)], [H2]),
    ([("warn", W1), ("warn", W1)], [W1, W1]),
])
def test_fehlerkette(calls, expected):
    m = messages.CycleMessages()
    for method, msg in calls:
        getattr(m, method)(msg)
    assert m.msgs == expected


def test_ergebnis_ist_eine_kopie():
    m = messages.CycleMessages()
    m.warn(W1)
    m.msgs.append(W2)
    assert m.msgs == [W1]
