"""Szenario-Gerüst aus einem HA-Verlauf: Regelschritte je Änderung des Netzsensors."""
from tests import repro_import as ri


def test_takt_netz_behaelt_aenderungen_nach_der_letzten_netzaenderung():
    zeilen = [(0.0, "netz", 100), (10.0, "a.soc", 50), (20.0, "netz", 200), (30.0, "a.soc", 49)]
    szenario = ri.baue(zeilen, von=0.0, bis=None, takt="netz", einheiten={})
    assert [s["setzen"] for s in szenario["schritte"]] == [{"a.soc": 50, "netz": 200}, {"a.soc": 49}]
