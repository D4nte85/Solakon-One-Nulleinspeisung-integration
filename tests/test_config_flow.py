"""Config-Flow: Geräteauswahl, Auflösung der Solakon-Entitäten, Aktivieren deaktivierter Zuweisungen."""
import asyncio

from tests import geraet, harness as h

C = h.const
cf = h.config_flow_mod
stubs = h.ha_stubs

KEYS = {field: (e.domain, e.key) for field, e in geraet.ENTITIES.items()}


def _device(hass, dev_id, prefix, name="Solakon ONE", name_by_user=None, disabled=()):
    """Solakon-Gerät `dev_id` mit allen neun Entitäten `<domain>.<prefix>_<key>`; gibt Feld → entity_id."""
    devs = stubs.device_registry_get(hass)
    ents = stubs.entity_registry_get(hass)
    devs.devices[dev_id] = stubs.DeviceEntry(dev_id, {("solakon_one", f"ce_{dev_id}")}, name, name_by_user)
    ids = {}
    for field, (domain, key) in KEYS.items():
        eid = f"{domain}.{prefix}_{key}"
        ents.add(stubs.RegistryEntry(eid, "solakon_one", f"ce_{dev_id}_{key}", f"ce_{dev_id}", dev_id,
                                     "integration" if key in disabled else None))
        ids[field] = eid
    ents.add(stubs.RegistryEntry(f"sensor.{prefix}_fremd", "solakon_one", f"ce_{dev_id}_grid_frequency",
                                 f"ce_{dev_id}", dev_id))
    return ids


def _hass(entries=()):
    fh = h.FakeHass("de")
    fh.config.language = "de"
    fh.config_entries.entries = list(entries)
    return fh


def _defaults(form) -> dict:
    return {str(k): k.default() for k in form["data_schema"].schema if callable(getattr(k, "default", None))}


def _options(form) -> list:
    sel = form["data_schema"].schema[next(k for k in form["data_schema"].schema if str(k) == "device")]
    return [(o["value"], o["label"]) for o in sel.config["options"]]


def _flow(fh):
    flow = cf.SolakonConfigFlow()
    flow.hass = fh
    return flow


def _options_flow(fh, entry):
    opt = cf.SolakonConfigFlow.async_get_options_flow(entry)
    opt.hass = fh
    opt.config_entry = entry
    return opt


def _run(coro):
    return asyncio.run(coro)


def test_geraet_mit_bereichspraefix_belegt_alle_felder_vor():
    fh = _hass()
    ids = _device(fh, "d1", "keller_solakon_one", name_by_user="Balkon")
    flow = _flow(fh)
    form = _run(flow.async_step_user(None))
    assert form["step_id"] == "user" and _options(form) == [("d1", "Balkon")]
    form = _run(flow.async_step_user({"device": "d1"}))
    assert form["step_id"] == "entities"
    defaults = _defaults(form)
    assert {f: defaults[f] for f in KEYS} == ids
    assert defaults[C.CONF_INSTANCE_NAME] == "Balkon"
    assert defaults.get(C.CONF_GRID_SENSOR, "") == ""
    assert "enable_disabled" not in defaults


def test_belegtes_geraet_fehlt_in_der_auswahl():
    fh = _hass()
    ids_a = _device(fh, "d1", "a")
    _device(fh, "d2", "b", name="Solakon ONE 2")
    fh.config_entries.entries = [h.FakeEntry("entry_a", {**h.entry_data("x"), C.CONF_MODE_SELECT: ids_a[C.CONF_MODE_SELECT]})]
    form = _run(_flow(fh).async_step_user(None))
    assert _options(form) == [("d2", "Solakon ONE 2")]


def test_ohne_geraet_hinweis_dann_leeres_formular():
    fh = _hass()
    flow = _flow(fh)
    form = _run(flow.async_step_user(None))
    assert form["step_id"] == "no_device"
    form = _run(flow.async_step_no_device({}))
    assert form["step_id"] == "entities"
    defaults = _defaults(form)
    assert all(defaults.get(f, "") == "" for f in KEYS)
    assert defaults[C.CONF_INSTANCE_NAME] == "Speicher 1"


def test_deaktivierte_zuweisung_wird_beim_absenden_aktiviert():
    fh = _hass()
    ids = _device(fh, "d1", "s", disabled=("battery_max_discharge_current",))
    flow = _flow(fh)
    _run(flow.async_step_user({"device": "d1"}))
    form = _run(flow.async_step_entities(None))
    assert _defaults(form)["enable_disabled"] is True
    assert ids[C.CONF_DISCHARGE_CURRENT] in form["description_placeholders"]["disabled"]
    data = {**ids, C.CONF_INSTANCE_NAME: "S", C.CONF_GRID_SENSOR: "sensor.grid", "enable_disabled": True}
    result = _run(flow.async_step_entities(data))
    assert result["type"] == "create_entry" and "enable_disabled" not in result["data"]
    assert stubs.entity_registry_get(fh).async_get(ids[C.CONF_DISCHARGE_CURRENT]).disabled_by is None
    sensor = stubs.entity_registry_get(fh).async_get("sensor.s_fremd")
    assert sensor.disabled_by is None


def test_ohne_haken_bleibt_deaktiviert():
    fh = _hass()
    ids = _device(fh, "d1", "s", disabled=("battery_max_discharge_current",))
    flow = _flow(fh)
    _run(flow.async_step_user({"device": "d1"}))
    data = {**ids, C.CONF_INSTANCE_NAME: "S", C.CONF_GRID_SENSOR: "sensor.grid", "enable_disabled": False}
    _run(flow.async_step_entities(data))
    assert stubs.entity_registry_get(fh).async_get(ids[C.CONF_DISCHARGE_CURRENT]).disabled_by == "integration"


def test_anpassen_ersetzt_nur_fehlende_entitaeten():
    fh = _hass()
    ids = _device(fh, "d1", "keller_solakon_one")
    alt = {**ids, C.CONF_SOLAR_SENSOR: "sensor.solakon_one_pv_leistung", C.CONF_SOC_SENSOR: "sensor.mein_soc",
           C.CONF_MODE_SELECT: ids[C.CONF_MODE_SELECT], C.CONF_INSTANCE_NAME: "Alt", C.CONF_GRID_SENSOR: "sensor.grid"}
    fh.states.set("sensor.mein_soc", "50")
    entry = h.FakeEntry("entry_a", alt)
    fh.config_entries.entries = [entry]
    opt = _options_flow(fh, entry)
    form = _run(opt.async_step_init(None))
    assert form["step_id"] == "init" and _options(form) == [("d1", "Solakon ONE")]
    assert _defaults(form)["device"] == "d1"
    form = _run(opt.async_step_init({"device": "d1"}))
    defaults = _defaults(form)
    assert defaults[C.CONF_SOLAR_SENSOR] == ids[C.CONF_SOLAR_SENSOR]
    assert defaults[C.CONF_SOC_SENSOR] == "sensor.mein_soc"
    assert defaults[C.CONF_INSTANCE_NAME] == "Alt"


def test_anpassen_ohne_vorhandenes_geraet_nichts_vorgewaehlt():
    fh = _hass()
    _device(fh, "d1", "keller_solakon_one")
    entry = h.FakeEntry("entry_a", {**h.entry_data("x"), C.CONF_MODE_SELECT: "select.solakon_one_modus_fernsteuern"})
    fh.config_entries.entries = [entry]
    form = _run(_options_flow(fh, entry).async_step_init(None))
    assert "device" not in {k for k, v in _defaults(form).items() if v}
