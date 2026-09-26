"""Anzeigezustand ohne Coordinator: Anzeigezone, Modus mit Zeitstempel, Betriebszustand."""
from __future__ import annotations

import importlib

import pytest

from tests import harness as h

display = importlib.import_module(h.PKG + ".display")
i18n = importlib.import_module(h.PKG + ".i18n")


def _display():
    h.CLOCK.now = h.Clock.START
    return display.Display("de")


@pytest.mark.parametrize("soc, surplus, cycle, zone", [
    (20, True, True, 3),
    (21, True, True, 0),
    (21, False, True, 1),
    (21, False, False, 2),
])
def test_update_anzeigezone(soc, surplus, cycle, zone):
    d = _display()
    d.update("de", soc, 20, "1", False, surplus, cycle)
    assert d.zone == zone
    assert d.zone_label == i18n.translate("de", f"zone_{zone}")


@pytest.mark.parametrize("mode, at_rest, key", [
    ("0", False, "disabled"),
    ("1", False, "discharge"),
    ("1", True, "rest_discharge"),
    ("0", True, "disabled"),
    ("3", False, "ac_charge"),
    ("x", False, "unknown"),
])
def test_update_modusschluessel(mode, at_rest, key):
    d = _display()
    d.update("de", 60, 20, mode, at_rest, False, False)
    assert d.mode_key == key


def test_set_mode_unbekannt_haengt_rohwert_an():
    d = _display()
    d.set_mode("unknown", "de", "x")
    assert d.mode_label == f"{i18n.translate('de', 'mode_unknown')}: x"


def test_set_mode_zeitstempel_nur_bei_wechsel():
    d = _display()
    h.CLOCK.now += 10
    d.set_mode("discharge", "de")
    assert d.mode_ts == h.Clock.START + 10
    h.CLOCK.now += 10
    d.set_mode("discharge", "de")
    assert d.mode_ts == h.Clock.START + 10


@pytest.mark.parametrize("kw, zone, state", [
    (dict(regulation_on=False, blocked=True), 2, "disabled"),
    (dict(blocked=True, control="surplus"), 2, "blocked"),
    (dict(control="surplus", discharge_locked=True), 2, "exporting"),
    (dict(control="tariff_charge"), 2, "tariff_charging"),
    (dict(control="ac_charge", is_night=True), 2, "ac_charging"),
    (dict(control="cycle", discharge_locked=True), 2, "discharge_locked"),
    (dict(control="cycle", is_night=True), 2, "night_off"),
    (dict(control="cycle"), 3, "battery_supply"),
    (dict(control="pv"), 3, "safety_stop"),
    (dict(control="pv"), 2, "pv_direct"),
])
def test_update_state_reihenfolge(kw, zone, state):
    d = _display()
    d.zone = zone
    args = dict(regulation_on=True, blocked=False, control="pv", discharge_locked=False, is_night=False)
    assert d.update_state(**{**args, **kw}) is True
    assert d.operating_state == state


def test_update_state_ohne_wechsel():
    d = _display()
    args = dict(regulation_on=True, blocked=False, control="pv", discharge_locked=False, is_night=False)
    d.update_state(**args)
    ts = d.operating_state_ts
    h.CLOCK.now += 5
    assert d.update_state(**args) is False
    assert d.operating_state_ts == ts
