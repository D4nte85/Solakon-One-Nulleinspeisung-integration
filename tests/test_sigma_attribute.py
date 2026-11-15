"""σ-Attribute des Sensors Netz-Standardabweichung: Fenster und Trimmung des σ-Puffers der Netzgruppe."""
from __future__ import annotations

from tests import harness as h
from tests.test_status_texts import _coord

sensor = h.sensor_mod
C = h.const


def test_attribute_aus_dem_sigma_puffer_der_netzgruppe():
    _, coord = _coord("de")
    coord.settings[C.S_STDDEV_WINDOW] = 120
    coord.settings[C.S_STDDEV_TRIM_COUNT] = 0
    leader_settings = {C.S_STDDEV_WINDOW: 90, C.S_STDDEV_TRIM_COUNT: 2}
    coord.group.sigma.record(10.0, 1000.0, leader_settings)
    attrs = sensor.GridStdDevSensor(coord).extra_state_attributes
    assert attrs["window_seconds"] == 90
    assert attrs["trim_count"] == 2


def test_vor_der_ersten_aufnahme_eigene_settings():
    _, coord = _coord("de")
    coord.settings[C.S_STDDEV_WINDOW] = 120
    attrs = sensor.GridStdDevSensor(coord).extra_state_attributes
    assert attrs["window_seconds"] == 120
