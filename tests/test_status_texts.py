"""Letzte Aktion und Fehlerkette im WS-Status in der Sprache des Panels."""
from __future__ import annotations

import asyncio
import importlib

from tests import harness as h

integration = h.integration
i18n = importlib.import_module(h.PKG + ".i18n")


def _coord(language: str):
    hass = h.FakeHass(language)
    h.install_groups(hass)
    return hass, h.make_coord(hass)


def _status(hass, **extra) -> dict:
    return asyncio.run(h.ws_call(integration._ws_get_status, hass, entry_id="entry_a", **extra))[0][2]


def test_panelsprache_ueberschreibt_instanzsprache():
    hass, coord = _coord("en")
    coord._set_last_action("act_fall_a", soc=55)
    coord._messages.warn(("err_tariff_sensor_unavailable", {"sensor": "sensor.preis"}))
    coord._messages.warn(("warn_dist_soc_sensor", {}))
    coord._end_cycle()

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
