"""Letzte Aktion und Fehlerkette im WS-Status in der Sprache des Panels."""
from __future__ import annotations

import asyncio
import importlib

from tests import harness as h
from tests.ha_stubs import ActiveConnection

integration = h.integration
i18n = importlib.import_module(h.PKG + ".i18n")


def _coord(language: str):
    hass = h.FakeHass(language)
    entry = h.FakeEntry("entry_a", h.entry_data("a"))
    coord = h.coordinator_mod.SolakonCoordinator(hass, entry)
    hass.data.setdefault(h.const.DOMAIN, {})[entry.entry_id] = coord
    return hass, coord


def _status(hass, **extra) -> dict:
    conn = ActiveConnection()
    asyncio.run(integration._ws_get_status(hass, conn, {"id": 1, "entry_id": "entry_a", **extra}))
    return conn.sent[0][2]


def test_panelsprache_ueberschreibt_instanzsprache():
    hass, coord = _coord("en")
    coord._set_last_action("act_fall_a", soc=55)
    errors = []
    coord._add_soft_error(errors, ("err_tariff_sensor_unavailable", {"sensor": "sensor.preis"}))
    coord._add_soft_error(errors, ("warn_dist_soc_sensor", {}))

    ohne = _status(hass)
    assert ohne["last_action"] == "Case A: Zone 1 start (SOC 55%)"

    de = _status(hass, language="de")
    assert de["last_action"] == "Fall A: Zone 1 Start (SOC 55%)"
    assert de["last_error"] == " • ".join(
        i18n.translate("de", k, **p) for k, p in coord.last_error_msgs)
    assert de["last_error"] != ohne["last_error"]
    assert "sensor.preis" in de["last_error"]


def test_ohne_aktion_bleibt_text_leer():
    hass, _ = _coord("en")
    assert _status(hass, language="de")["last_action"] == ""
    assert _status(hass, language="de")["last_error"] == ""
