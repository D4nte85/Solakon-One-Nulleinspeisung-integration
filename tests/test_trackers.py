"""Trigger der Funktionen mit Sensor: Anmeldung nach Settings und wirksamem Sensor."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from tests import harness as h
from tests.test_status_texts import _coord

C = h.const


def _state_targets(hass) -> list[list[str]]:
    """Sensoren aller noch angemeldeten Zustands-Trigger."""
    handles = {}
    for event in hass.events:
        if event[0] == "track" and event[1] == "state":
            handles[event[3]] = event[2]
        elif event[0] == "untrack":
            handles.pop(event[1], None)
    return sorted(handles.values())


def test_nacht_forcierung_wechselt_um_12_uhr_den_sensor(monkeypatch):
    """F2: ab 12 Uhr lauscht der Trigger der Nacht-Forcierung auf die Prognose für morgen."""
    hass, coord = _coord("de")
    coord.settings.update({
        C.S_ZONE1_FORCE_ENABLED: True,
        C.S_PV_FORECAST_SENSOR: "sensor.heute",
        C.S_ZONE1_FORCE_SENSOR: "sensor.morgen",
    })
    monkeypatch.setattr(h.ha_stubs._DtState, "now", datetime(2026, 9, 13, 11, 59, tzinfo=timezone.utc))
    coord.trackers.start()
    assert _state_targets(hass) == [["sensor.heute"]]

    monkeypatch.setattr(h.ha_stubs._DtState, "now", datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc))
    asyncio.run(coord._async_regulate())
    assert _state_targets(hass) == [["sensor.morgen"]]
