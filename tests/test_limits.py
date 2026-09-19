"""Leistungsgrenzen ohne Coordinator: Zonen, PI-Phase, AC-Laden, Export-Limit."""
from __future__ import annotations

import importlib

import pytest

from tests import harness as h

limits = importlib.import_module(h.PKG + ".limits")
const = importlib.import_module(h.PKG + ".const")

MAX = const.DEVICE_MAX_POWER


def _limits(**kw):
    args = dict(hard_limit_z0=800, hard_limit_z1=600, ac_power_limit=700, pv_reserve=50, allocated=None)
    args.update(kw)
    return limits.power_limits(**args)


@pytest.mark.parametrize("z0, z1, allocated, zone0, zone12", [
    (800, 600, None, 800, 600),        # Einzelinstanz: Panel-Werte
    (800, 600, 700.0, 700, 600),       # Zuteilung zwischen den Panel-Werten
    (800, 600, 400.0, 400, 400),       # Zuteilung unter beiden
    (800, 600, 1000.0, 800, 600),      # Zuteilung über beiden
    (800, 600, 450.9, 450, 450),       # Zuteilung abgeschnitten, nicht gerundet
    (1500, 1400, None, MAX, MAX),      # Gerätegrenze
    (1500, 1400, 1300.0, MAX, MAX),
])
def test_zonengrenzen(z0, z1, allocated, zone0, zone12):
    lim = _limits(hard_limit_z0=z0, hard_limit_z1=z1, allocated=allocated)
    assert (lim.zone0, lim.zone12) == (zone0, zone12)
    assert type(lim.zone0) is int and type(lim.zone12) is int
    assert lim.zone_max(True) == zone0
    assert lim.zone_max(False) == zone12


@pytest.mark.parametrize("ac, erwartet", [(700, 700), (MAX, MAX), (1500, MAX)])
def test_ac_grenze_gedeckelt(ac, erwartet):
    lim = _limits(ac_power_limit=ac, allocated=300.0)
    assert lim.ac == erwartet
    # Die Zuteilung des Entlade-Pools begrenzt das AC-Laden nicht
    assert lim.pi_max(const.MODE_AC_CHARGE, cycle_active=True, solar=0.0) == erwartet


@pytest.mark.parametrize("z0, z1, erwartet", [(800, 600, 800), (500, 900, 900), (1500, 600, 1500)])
def test_export_aus_panel_werten(z0, z1, erwartet):
    # Weder Zuteilung noch Gerätegrenze gehen ins Export-Limit ein
    assert _limits(hard_limit_z0=z0, hard_limit_z1=z1, allocated=100.0).export == erwartet


def test_zone1_ohne_pv_bezug():
    lim = _limits(allocated=500.0)
    assert lim.pi_max(const.MODE_DISCHARGE, cycle_active=True, solar=0.0) == 500


@pytest.mark.parametrize("solar, erwartet", [
    (0.0, 0),          # PV unter der Reserve: Grenze 0 W
    (50.0, 0),         # genau an der Reserve
    (300.0, 250.0),    # PV minus Reserve unter dem Zone-1/2-Limit
    (650.0, 600),      # genau am Zone-1/2-Limit
    (2000.0, 600),     # Zone-1/2-Limit deckelt die PV-Grenze
])
def test_zone2_pv_minus_reserve(solar, erwartet):
    assert _limits().pi_max(const.MODE_DISCHARGE, cycle_active=False, solar=solar) == erwartet


def test_zone2_durch_zuteilung_gedeckelt():
    lim = _limits(allocated=300.0)
    assert lim.pi_max(const.MODE_DISCHARGE, cycle_active=False, solar=2000.0) == 300
