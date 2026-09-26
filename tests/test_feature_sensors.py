"""Feature-Sensoren ohne Coordinator: wirksamer Sensor, Werte in Zieleinheit, Meldungen, Tarifpreis."""
from __future__ import annotations

import importlib

import pytest

from tests import harness as h

fs = importlib.import_module(h.PKG + ".feature_sensors")
schema = importlib.import_module(h.PKG + ".schema")
C = h.const


def _settings(**kw):
    return {**C.SETTINGS_DEFAULTS, **kw}


@pytest.mark.parametrize("name, local, dist, hour, erwartet", [
    ("tariff", "sensor.lokal", {"global_tariff_price_sensor": "sensor.global"}, 8, "sensor.lokal"),
    ("tariff", "", {"global_tariff_price_sensor": "sensor.global"}, 8, "sensor.global"),
    ("tariff", "", {}, 8, ""),
])
def test_effective_sensor_lokal_vor_global(name, local, dist, hour, erwartet):
    settings = _settings(**{C.S_TARIFF_PRICE_SENSOR: local})
    assert fs.effective_sensor(name, settings, dist, hour) == erwartet


@pytest.mark.parametrize("hour, erwartet", [(11, "sensor.heute"), (12, "sensor.morgen")])
def test_effective_sensor_zone1_force_wechselt_um_12(hour, erwartet):
    settings = _settings(**{C.S_PV_FORECAST_SENSOR: "sensor.heute", C.S_ZONE1_FORCE_SENSOR: "sensor.morgen"})
    assert fs.effective_sensor("zone1_force", settings, {}, hour) == erwartet


def test_feature_reading_aus_liest_nicht():
    reading, warning = fs.feature_reading(h.FakeHass(), False, "", "err_pv_forecast", {})
    assert reading.value is None and warning is None


@pytest.mark.parametrize("sensor, state, erwartet", [
    ("", None, ("err_pv_forecast_no_sensor", {})),
    ("switch.x", "1", ("err_pv_forecast_sensor_wrong_domain", {"sensor": "switch.x"})),
    ("sensor.x", None, ("err_pv_forecast_sensor_unavailable", {"sensor": "sensor.x"})),
    ("sensor.x", "abc", ("err_pv_forecast_sensor_not_numeric", {"sensor": "sensor.x"})),
])
def test_feature_reading_meldet_grund(sensor, state, erwartet):
    hass = h.FakeHass()
    if state is not None:
        hass.states.set(sensor, state)
    reading, warning = fs.feature_reading(hass, True, sensor, "err_pv_forecast", {})
    assert reading.value is None and warning == erwartet


def test_feature_values_skaliert_und_meldet_in_tabellenreihenfolge():
    hass = h.FakeHass()
    hass.states.set("sensor.pv", "5000", {"unit_of_measurement": "Wh"})
    settings = _settings(**{
        C.S_PV_FORECAST_SENSOR: "sensor.pv", C.S_PV_FORECAST_ENABLED: True,
        C.S_SURPLUS_LOCK_ENABLED: True, C.S_TARIFF_ENABLED: True,
    })
    cs = schema.cycle_settings(settings)
    values, warnings = fs.feature_values(hass, cs, settings, {}, 8)
    assert values["pv_forecast"] == pytest.approx(5.0)
    assert values["cheap"] is None and values["exp"] is None
    assert warnings == [("err_exit_lock_no_sensor", {})]


def test_tariff_price_mit_einheit():
    hass = h.FakeHass()
    hass.states.set("sensor.preis", "28.5", {"unit_of_measurement": "ct/kWh"})
    assert fs.tariff_price(hass, True, "sensor.preis") == (28.5, "ct/kwh", None)
    assert fs.tariff_price(hass, True, "") == (None, "", ("err_tariff_no_sensor", {}))
