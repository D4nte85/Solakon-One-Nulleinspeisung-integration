"""Dynamic Offset ohne Coordinator: Offsetzone des Regelzustands und wirksamer Offset."""
from __future__ import annotations

import importlib

import pytest

from tests import harness as h

dyn_mod = importlib.import_module(h.PKG + ".dynamic_offset")
const = importlib.import_module(h.PKG + ".const")

DynamicOffset = dyn_mod.DynamicOffset


@pytest.mark.parametrize("ac_charge, cycle, night, expected", [
    (True, True, False, "ac"),
    (True, True, True, "ac"),
    (True, False, False, "ac"),
    (False, True, False, "z1"),
    (False, True, True, "z1_night"),
    (False, False, False, "z2"),
    (False, False, True, "z2"),
])
def test_zone_of(ac_charge, cycle, night, expected):
    assert DynamicOffset.zone_of(ac_charge, cycle, night) == expected


def test_value_nacht_offset_statisch_und_dynamisch():
    settings = {**const.SETTINGS_DEFAULTS, const.S_OFFSET_1_NIGHT: 40}
    dyn = DynamicOffset()
    assert dyn.value("z1_night", dyn_mod.offset_params(settings)) == 40.0
    settings[const.dyn_key("z1_night", "enabled")] = True
    dyn.offsets["z1_night"] = 75
    assert dyn.value("z1_night", dyn_mod.offset_params(settings)) == 75.0


def test_update_rechnet_nacht_offset():
    settings = {**const.SETTINGS_DEFAULTS, const.dyn_key("z1_night", "enabled"): True,
                const.dyn_key("z1_night", "min"): 20, const.dyn_key("z1_night", "negative"): True}
    dyn = DynamicOffset()
    dyn.update(dyn_mod.Sigma(), dyn_mod.offset_params(settings))
    assert dyn.offsets["z1_night"] == -20.0


def test_value_statisch_als_float():
    settings = {**const.SETTINGS_DEFAULTS, const.dyn_key("z1", "enabled"): False, const.S_OFFSET_1: 30}
    value = DynamicOffset().value("z1", dyn_mod.offset_params(settings))
    assert value == 30.0
    assert isinstance(value, float)


def test_value_dynamisch():
    settings = {**const.SETTINGS_DEFAULTS, const.dyn_key("ac", "enabled"): True}
    dyn = DynamicOffset()
    dyn.offsets["ac"] = -42
    assert dyn.value("ac", dyn_mod.offset_params(settings)) == -42.0
