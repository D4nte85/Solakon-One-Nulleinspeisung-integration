"""Live-Werte im WS-Status: Zahl oder None, nie ein Ersatzwert."""
from __future__ import annotations

from tests.test_status_texts import _coord, _status


def test_fehlender_wert_ist_none():
    hass, _ = _coord("de")
    hass.states.set("sensor.grid", "unavailable")
    hass.states.set("sensor.a_actual", "250", {"unit_of_measurement": "W"})
    hass.states.set("sensor.a_solar", "abc")
    st = _status(hass)
    assert st["grid"] is None
    assert st["actual_power"] == 250.0
    assert st["solar"] is None
    assert st["soc"] is None


def test_soc_ohne_zahl_ist_none():
    hass, coord = _coord("de")
    hass.states.set("sensor.a_soc", "abc")
    assert coord.soc_reading() is None
