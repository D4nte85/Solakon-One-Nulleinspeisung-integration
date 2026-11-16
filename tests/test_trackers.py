"""Trigger der Funktionen mit Sensor: Anmeldung nach Settings und wirksamem Sensor."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from tests import harness as h
from tests.test_status_texts import _coord

C = h.const


def _state_targets(hass) -> list[list[str]]:
    """Sensoren aller noch angemeldeten Zustands-Trigger mit einem Sensor; der Kern-Trigger hat mehrere."""
    handles = {}
    for event in hass.events:
        if event[0] == "track" and event[1] == "state":
            handles[event[3]] = event[2]
        elif event[0] == "untrack":
            handles.pop(event[1], None)
    return sorted(t for t in handles.values() if len(t) == 1)


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


def _intervals(hass) -> list[float]:
    """Intervalle aller noch angemeldeten periodischen Trigger."""
    handles = {}
    for event in hass.events:
        if event[0] == "track" and event[1] == "interval":
            handles[event[3]] = event[2]
        elif event[0] == "untrack":
            handles.pop(event[1], None)
    return sorted(handles.values())


def test_geaenderte_globale_vorgabe_meldet_den_trigger_neu_an():
    hass, coord = _coord("de")
    coord.settings.update({C.S_TARIFF_ENABLED: True, C.S_TARIFF_PRICE_SENSOR: ""})
    store = h.group_store_mod.require_store(hass)
    store.dist.setdefault("sensor.grid", {})["global_tariff_price_sensor"] = "sensor.preis_alt"
    coord.trackers.start()
    assert ["sensor.preis_alt"] in _state_targets(hass)
    store.dist["sensor.grid"]["global_tariff_price_sensor"] = "sensor.preis_neu"
    coord.trackers.refresh_changed()
    targets = _state_targets(hass)
    assert ["sensor.preis_neu"] in targets and ["sensor.preis_alt"] not in targets


def test_trigger_ohne_sensor_oder_ausgeschaltet_bleibt_abgemeldet():
    hass, coord = _coord("de")
    coord.settings.update({C.S_TARIFF_ENABLED: True, C.S_TARIFF_PRICE_SENSOR: "", C.S_PERIODIC_ENABLED: False})
    coord.trackers.start()
    assert "tariff" not in coord.trackers.active()
    assert "periodic" not in coord.trackers.active()


def test_periodischer_trigger_im_eingestellten_intervall():
    hass, coord = _coord("de")
    coord.settings.update({C.S_PERIODIC_ENABLED: True, C.S_PERIODIC_INTERVAL: 30})
    coord.trackers.start()
    assert _intervals(hass) == [30.0]
    coord.settings[C.S_PERIODIC_INTERVAL] = 60
    coord.trackers.refresh_changed()
    assert _intervals(hass) == [60.0]
