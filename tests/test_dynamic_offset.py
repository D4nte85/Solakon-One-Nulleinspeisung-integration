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
    assert dyn.value("z1_night", settings) == 40.0
    settings[const.S_DYN_Z1_NIGHT_ENABLED] = True
    dyn.z1_night = 75
    assert dyn.value("z1_night", settings) == 75.0


def test_update_rechnet_nacht_offset():
    settings = {**const.SETTINGS_DEFAULTS, const.S_DYN_Z1_NIGHT_ENABLED: True,
                const.S_DYN_Z1_NIGHT_MIN: 20, const.S_DYN_Z1_NIGHT_NEGATIVE: True}
    dyn = DynamicOffset()
    dyn.update(dyn_mod.Sigma(), settings)
    assert dyn.z1_night == -20.0


def test_value_statisch_als_float():
    settings = {**const.SETTINGS_DEFAULTS, const.S_DYN_Z1_ENABLED: False, const.S_OFFSET_1: 30}
    value = DynamicOffset().value("z1", settings)
    assert value == 30.0
    assert isinstance(value, float)


def test_value_dynamisch():
    settings = {**const.SETTINGS_DEFAULTS, const.S_DYN_AC_ENABLED: True}
    dyn = DynamicOffset()
    dyn.ac = -42
    assert dyn.value("ac", settings) == -42.0
