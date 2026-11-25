"""Zweitlesung in der PI-Phase: ohne Netz- oder PV-Wert ist der Regelzyklus blockiert."""
from __future__ import annotations

from tests import harness as h
from tests import repro

C = h.const

# Zone 1 mit laufendem Zyklus in Modus '1': die Falls lassen die Instanz entladen, die PI-Phase läuft.
SZENARIO = {
    "titel": "Zweitlesung ohne Netzwert",
    "netz": 100,
    "instanzen": [{"prefix": "a", "settings": {"regulation_enabled": True}, "sensoren": {"soc": 70, "modus": "1"}}],
    "schritte": [{"nach": 0}],
    "erwartet": [{"zustand": {"display.operating_state": "blocked", "_cycle_blocked": True}}],
}


def test_zweitlesung_ohne_netzwert_blockiert_den_regelzyklus(monkeypatch):
    original = h.coordinator_mod.read_required
    zweit = (C.CONF_GRID_SENSOR, C.CONF_SOLAR_SENSOR)

    def ohne_netz_in_der_zweitlesung(hass, cfg, keys):
        if tuple(keys) == zweit:
            return cfg[C.CONF_GRID_SENSOR]
        return original(hass, cfg, keys)

    monkeypatch.setattr(h.coordinator_mod, "read_required", ohne_netz_in_der_zweitlesung)
    rec, ergebnisse = repro.spiele(SZENARIO)
    assert all(ok for ok, _ in ergebnisse), ergebnisse
    assert rec["steps"][-1]["state"]["a"]["last_error_msgs"] == [["err_core_sensor", {"sensor": "sensor.grid"}]]
