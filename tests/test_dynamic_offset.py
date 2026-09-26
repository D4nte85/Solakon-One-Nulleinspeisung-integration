"""Dynamic Offset ohne Coordinator: Offsetzone des Regelzustands und wirksamer Offset."""
from __future__ import annotations

import importlib

import pytest

from tests import harness as h

dyn_mod = importlib.import_module(h.PKG + ".dynamic_offset")
const = importlib.import_module(h.PKG + ".const")

DynamicOffset = dyn_mod.DynamicOffset


@pytest.mark.parametrize("ac_charge, cycle, expected", [
    (True, True, "ac"),
    (True, False, "ac"),
    (False, True, "z1"),
    (False, False, "z2"),
])
def test_zone_of(ac_charge, cycle, expected):
    assert DynamicOffset.zone_of(ac_charge, cycle) == expected


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
