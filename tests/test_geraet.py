"""Geräteseite der Attrappe gegen die Tabelle aus `geraet.py`."""
from __future__ import annotations

import asyncio

import pytest

from tests import geraet, harness as h

C = h.const


def _hass():
    hass = h.FakeHass("de")
    data = h.entry_data("a")
    geraet.registrieren(hass, data)
    for eid in data.values():
        if "." in eid:
            hass.states.set(eid, "1" if eid.startswith("select.") else 0)
    return hass, data


def _set(hass, eid, value):
    domain, service, key = ("select", "select_option", "option") if eid.startswith("select.") else ("number", "set_value", "value")
    asyncio.run(hass.services.async_call(domain, service, {"entity_id": eid, key: value}))
    return hass.states.get(eid)


@pytest.mark.parametrize("sprache, defaults", [("de", C.REQUIRED_ENTITY_DEFAULTS_DE), ("en", C.REQUIRED_ENTITY_DEFAULTS_EN)])
def test_default_ids(sprache, defaults):
    ids = {k: getattr(e, f"id_{sprache}") for k, e in geraet.ENTITIES.items()}
    assert ids == defaults


def test_attribute_an_zustaenden():
    hass, data = _hass()
    leistung = hass.states.get(data[C.CONF_ACTIVE_POWER]).attributes
    assert (leistung["min"], leistung["max"], leistung["step"]) == (-100000, 100000, 100)
    assert hass.states.get(data[C.CONF_MODE_SELECT]).attributes["options"][-1] == "15"
    assert hass.states.get(data[C.CONF_SOC_SENSOR]).attributes["unit_of_measurement"] == "%"


def test_ausserhalb_min_max_ohne_wirkung():
    hass, data = _hass()
    assert _set(hass, data[C.CONF_DISCHARGE_CURRENT], 41).state == "0"
    assert _set(hass, data[C.CONF_TIMEOUT_SET], 3601).state == "0"


def test_ganzzahl_ohne_step_rundung():
    hass, data = _hass()
    assert _set(hass, data[C.CONF_TIMEOUT_SET], 3599).state == "3599"
    assert _set(hass, data[C.CONF_ACTIVE_POWER], 743.9).state == "743"


def test_unbekannte_option_ohne_wirkung():
    hass, data = _hass()
    assert _set(hass, data[C.CONF_MODE_SELECT], "2").state == "1"
    assert _set(hass, data[C.CONF_MODE_SELECT], "3").state == "3"
