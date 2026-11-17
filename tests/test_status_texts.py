"""Letzte Aktion und Fehlerkette im WS-Status in der Sprache des Panels."""
from __future__ import annotations

import asyncio
import importlib

from tests import harness as h

integration = h.integration
i18n = importlib.import_module(h.PKG + ".i18n")
group = importlib.import_module(h.PKG + ".grid_group")
schema = importlib.import_module(h.PKG + ".schema")


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


def test_nicht_formatierbarer_text_warnt_einmal(monkeypatch):
    logs = h.capture_logs()
    monkeypatch.setattr(i18n, "_WARNED", set())
    monkeypatch.setitem(i18n._TEXTS, "x_test", {"de": "Wert {fehlt}", "en": "value {fehlt}"})
    assert i18n.translate("de", "x_test") == "Wert {fehlt}"
    assert i18n.translate("de", "x_test") == "Wert {fehlt}"
    assert [r[0] for r in logs.records] == ["WARNING"]
    assert "x_test" in logs.records[0][1]


def test_verteilungslage_ersetzt_modus_und_warnung():
    _, coord = _coord("de")
    cs = schema.cycle_settings(h.const.SETTINGS_DEFAULTS)._replace(hard_limit_z1=800)
    vorher = group.PoolPosition((True, False), False, 0.5, 400, 0.0, group.Shares({}, "equal", "warn_dist_soc_sensor"))
    limits = coord._adopt_position(vorher, cs)
    assert (coord.dist_mode_effective, coord._messages.msgs) == ("equal", [("warn_dist_soc_sensor", {})])
    assert (coord.allocated_power, limits.zone12) == (400, 400)
    nachher = group.PoolPosition((False, False), False, 0.0, None, 0.0, None)
    limits = coord._adopt_position(nachher, cs, vorher)
    assert (coord.dist_mode_effective, coord._messages.msgs) == ("", [])
    assert (coord.allocated_power, limits.zone12) == (None, 800)


def test_verteilungslage_gleiche_warnung_bleibt_an_ihrem_platz():
    _, coord = _coord("de")
    cs = schema.cycle_settings(h.const.SETTINGS_DEFAULTS)
    vorher = group.PoolPosition((True, False), False, 0.5, 400, 0.0, group.Shares({}, "equal", "warn_dist_soc_sensor"))
    coord._adopt_position(vorher, cs)
    coord._messages.warn(("warn_test_danach", {}))
    nachher = group.PoolPosition((True, False), True, 0.5, 800, 0.0, group.Shares({}, "equal", "warn_dist_soc_sensor"))
    coord._adopt_position(nachher, cs, vorher)
    assert coord._messages.msgs == [("warn_dist_soc_sensor", {}), ("warn_test_danach", {})]
