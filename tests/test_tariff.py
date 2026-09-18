"""Tariflage ohne Coordinator: Schwellen, Vergleiche, Prognosesperre, Entladesperre, Einheitenwarnung."""
from __future__ import annotations

import importlib

import pytest

from tests import harness as h

tariff = importlib.import_module(h.PKG + ".tariff")
const = importlib.import_module(h.PKG + ".const")

T0 = 1_800_000_000.0


def _assess(t=None, **kw):
    args = dict(enabled=True, suppressed=False, price=30.0, cheap_entity=None, cheap_setting=10.0,
                exp_entity=None, exp_setting=25.0, unit="ct/kwh", now=T0)
    args.update(kw)
    return (t or tariff.Tariff()).assess(**args)


def test_schwellen_aus_entitaet_sonst_setting():
    s = _assess(cheap_entity=12.0)
    assert (s.cheap, s.exp) == (12.0, 25.0)
    s = _assess(exp_entity=30.0)
    assert (s.cheap, s.exp) == (10.0, 30.0)


@pytest.mark.parametrize("price, below_exp, below_cheap, at_least_cheap", [
    (5.0, True, True, False),
    (10.0, True, False, True),     # genau an der Günstig-Schwelle
    (24.9, True, False, True),
    (25.0, False, False, True),    # genau an der Teuer-Schwelle
    (40.0, False, False, True),
])
def test_vergleiche_an_den_schwellen(price, below_exp, below_cheap, at_least_cheap):
    s = _assess(price=price)
    assert (s.below_exp, s.below_cheap, s.at_least_cheap) == (below_exp, below_cheap, at_least_cheap)
    assert s.allows_discharge is not below_exp


def test_ungueltiger_preis_sperrt_nichts():
    s = _assess(price=None)
    assert (s.price, s.below_exp, s.below_cheap, s.at_least_cheap) == (0.0, False, False, False)
    assert s.allows_discharge and s.unit_warning is None
    # Günstig-Schwelle ≤ 0 (Börsenpreise): der Ersatzwert 0.0 zählt nicht als Preis
    assert not _assess(price=None, cheap_setting=-2.0).at_least_cheap


@pytest.mark.parametrize("kw", [dict(enabled=False), dict(suppressed=True)])
def test_abgeschaltet_nur_at_least_cheap(kw):
    s = _assess(price=12.0, **kw)
    assert (s.below_exp, s.below_cheap, s.at_least_cheap) == (False, False, True)
    s = _assess(price=5.0, **kw)
    assert (s.below_exp, s.below_cheap, s.at_least_cheap) == (False, False, False)


@pytest.mark.parametrize("value, threshold, expected", [
    (None, 10.0, False), (9.9, 10.0, False), (10.0, 10.0, True), (15.0, 10.0, True),
])
def test_prognosesperre(value, threshold, expected):
    assert tariff.forecast_suppressed(value, threshold) is expected


@pytest.mark.parametrize("charging, surplus, expected", [
    (False, False, True), (True, False, False), (False, True, False), (True, True, False),
])
def test_entladesperre_mit_flags(charging, surplus, expected):
    assert _assess(price=5.0).discharge_locked(charging, surplus) is expected
    assert _assess(price=12.0).discharge_locked(charging, surplus) is expected
    assert _assess(price=30.0).discharge_locked(charging, surplus) is False


def test_einheitenwarnung_erst_nach_frist():
    t = tariff.Tariff()
    suspect = dict(price=0.25, cheap_setting=10.0, unit="")
    assert _assess(t, now=T0, **suspect).unit_warning is None
    assert t.unit_suspect_since == T0
    wait = const.TARIFF_UNIT_SUSPECT_SECONDS
    assert _assess(t, now=T0 + wait - 1, **suspect).unit_warning is None
    assert _assess(t, now=T0 + wait, **suspect).unit_warning == (
        "warn_tariff_unit", {"price": 0.25, "cheap": 10.0})


def test_einheitenwarnung_setzt_verdacht_zurueck():
    t = tariff.Tariff()
    _assess(t, price=0.25, unit="")
    assert t.unit_suspect_since == T0
    _assess(t, price=30.0, unit="")
    assert t.unit_suspect_since == 0.0


@pytest.mark.parametrize("unit, warned", [("ct/kwh", False), ("€/kwh", True), ("eur/kwh", True)])
def test_einheitenwarnung_nach_einheit(unit, warned):
    s = _assess(price=0.25, unit=unit)
    assert (s.unit_warning is not None) is warned


def test_einheitenwarnung_nicht_bei_negativem_preis_oder_kleiner_schwelle():
    assert _assess(price=-0.05, unit="€/kwh").unit_warning is None
    small = const.TARIFF_UNIT_SUSPECT_THRESHOLD / 2
    assert _assess(price=0.25, cheap_setting=small, exp_setting=small * 2, unit="€/kwh").unit_warning is None


def test_ungueltiger_preis_laesst_verdacht_stehen():
    t = tariff.Tariff()
    _assess(t, price=0.25, unit="")
    _assess(t, price=None, now=T0 + 5)
    assert t.unit_suspect_since == T0
