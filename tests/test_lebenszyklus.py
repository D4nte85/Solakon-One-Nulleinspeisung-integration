"""Lebenszyklus über `async_setup_entry`, `async_unload_entry` und `async_remove_entry`.

Setup, Entladen, Löschen, Deaktivieren (entladen, aber eingerichtet) und Neu laden mit den
Store- und Task-Attrappen aus `ha_stubs.py`. Die number-Plattform wird wie in HA nach dem
Setup des Eintrags geladen, weil sie den Träger des Gesamtlimits verwaltet. Wie in HA laufen
`async_added_to_hass` beim Hinzufügen und `async_will_remove_from_hass` beim Entfernen.
"""
from __future__ import annotations

import asyncio


import pytest

from tests import harness as h

C = h.const
DOMAIN = C.DOMAIN
DIST_KEY = f"{DOMAIN}_distribution"
SWITCH_KEY = f"{DOMAIN}_soc_switch_state"
NUMBERS_KEY = f"{DOMAIN}_group_numbers"


def _sofort(coro) -> None:
    """Hook ohne Wartepunkt im Aufrufer zu Ende führen; die Hinzufüge-Funktion von HA ist synchron."""
    try:
        coro.send(None)
    except StopIteration:
        return
    raise AssertionError("Hook mit Wartepunkt")


def _key(entry) -> str:
    return f"{DOMAIN}_{entry.entry_id}"


class Umgebung:
    """FakeHass mit Einträgen je Präfix am selben Netzsensor; Plattform-Entitäten je Eintrag."""

    def __init__(self, prefixes: str):
        self.hass = h.FakeHass("de")
        self.entries = {p: h.FakeEntry(f"entry_{p}", h.entry_data(p)) for p in prefixes}
        self.hass.config_entries.entries = list(self.entries.values())
        self.added: dict[str, list] = {}
        self._integration_setup = False

    def coord(self, p):
        return self.hass.data[DOMAIN][self.entries[p].entry_id]

    async def setup(self, *prefixes):
        """Wie HA: `async_setup` der Integration einmal vor dem ersten Eintrag."""
        if not self._integration_setup:
            await h.integration.async_setup(self.hass, {})
            self._integration_setup = True
        for p in prefixes:
            entry = self.entries[p]
            await h.integration.async_setup_entry(self.hass, entry)
            for platform in (h.sensor_mod, h.binary_mod, h.switch_mod, h.number_mod):
                await platform.async_setup_entry(self.hass, entry, self._adder(entry.entry_id))

    def _adder(self, entry_id):
        """Hinzufüge-Funktion wie in HA: Entitäten eintragen und `async_added_to_hass` ausführen."""
        def add(entities):
            for entity in entities:
                self.added.setdefault(entry_id, []).append(entity)
                _sofort(entity.async_added_to_hass())
        return add

    async def unload(self, *prefixes):
        """Entladen wie in HA: mit der Plattform verschwinden auch die Entitäten des Eintrags."""
        for p in prefixes:
            entry = self.entries[p]
            assert await h.integration.async_unload_entry(self.hass, entry)
            for entity in self.added.get(entry.entry_id, []):
                if not entity.__dict__.get("removed"):
                    await entity.async_remove()

    async def remove(self, *prefixes):
        """Löschen wie in HA: entladen, aus der Registrierung austragen, dann `async_remove_entry`."""
        for p in prefixes:
            entry = self.entries[p]
            if entry.entry_id in self.hass.data.get(DOMAIN, {}):
                await self.unload(p)
            self.hass.config_entries.entries.remove(entry)
            await h.integration.async_remove_entry(self.hass, entry)

    async def frist_abwarten(self, seconds=10):
        """Uhr vorstellen und eingeplante Tasks samt fälliger Schreibaufträge abarbeiten."""
        h.CLOCK.now += seconds
        await self.hass.async_block_till_done()

    def keys(self, prefix=DOMAIN) -> list[str]:
        return sorted(k for k in self.hass.data if k.startswith(prefix))


def _run(coro):
    return h.run(coro)


@pytest.fixture(autouse=True)
def _uhr(monkeypatch):
    monkeypatch.setattr(h.CLOCK, "now", h.Clock.START)


# ── Setup ────────────────────────────────────────────────────────────────────

def test_setup_laedt_settings_und_flags_aus_dem_store():
    u = Umgebung("a")
    h.put_store(u.hass, _key(u.entries["a"]), {C.S_ZONE1_LIMIT: 42, "cycle_active": True, "charge_session": C.SESSION_AC})

    async def lauf():
        await u.setup("a")
        return u.coord("a")

    coord = _run(lauf())
    assert coord.settings[C.S_ZONE1_LIMIT] == 42
    assert coord.cycle_active is True and coord.charge_session == C.SESSION_AC
    assert [e for e in u.hass.events if e[0] in ("store_save", "notify")] == []


def test_setup_migriert_settings_aus_version_2_2():
    u = Umgebung("a")
    key = _key(u.entries["a"])
    h.put_store(u.hass, key, {C.S_ZONE1_LIMIT: 42, "ac_charge_active": True}, version=2, minor_version=2)

    coord = _run(_setup_coord(u))
    assert coord.charge_session == C.SESSION_AC and coord.settings[C.S_ZONE1_LIMIT] == 42
    env = u.hass.storage[key]
    assert (env["version"], env["minor_version"]) == (C.STORAGE_VERSION, C.STORAGE_MINOR_VERSION)
    assert "ac_charge_active" not in env["data"] and env["data"]["charge_session"] == C.SESSION_AC


def test_unbekannter_settings_schluessel_bleibt_beim_laden_und_speichern():
    u = Umgebung("a")
    key = _key(u.entries["a"])
    h.put_store(u.hass, key, {C.S_ZONE1_LIMIT: 42, "aus_neuerer_version": 7})

    async def lauf():
        await u.setup("a")
        await u.coord("a").async_update_settings({C.S_ZONE1_LIMIT: 33})

    _run(lauf())
    assert u.coord("a").settings["aus_neuerer_version"] == 7
    assert u.hass.storage[key]["data"]["aus_neuerer_version"] == 7


async def _setup_coord(u):
    await u.setup("a")
    return u.coord("a")


def test_setup_migriert_gruppen_stores_aus_version_1():
    u = Umgebung("ab")
    h.put_store(u.hass, DIST_KEY, {"distribution_mode": "soc_switch", "global_max_power": 900}, version=1)
    h.put_store(u.hass, SWITCH_KEY, {"active_id": "entry_a", "start_soc": 55}, version=1)
    _run(u.setup("a", "b"))
    dist = h.stored(u.hass, DIST_KEY)
    assert list(dist) == ["sensor.grid"] and dist["sensor.grid"]["global_max_power"] == 900
    assert h.stored(u.hass, SWITCH_KEY) == {"sensor.grid": {"active_id": "entry_a", "start_soc": 55}}
    assert u.hass.storage[DIST_KEY]["version"] == h.group_store_mod.STORAGE_VERSION_DIST


def test_setup_registriert_ws_und_panel_einmal():
    u = Umgebung("ab")
    _run(u.setup("a", "b"))
    kinds = [e[0] for e in u.hass.events]
    assert kinds.count("panel_register") == 1
    assert kinds.count("ws_register") == len(h.integration.WS_COMMANDS)


# ── Entladen ─────────────────────────────────────────────────────────────────

def test_entladen_meldet_alle_trigger_ab():
    u = Umgebung("a")
    _run(u.setup("a"))
    angemeldet = {e[3] for e in u.hass.events if e[0] == "track"}
    u.hass.events = []
    _run(u.unload("a"))
    assert {e[1] for e in u.hass.events if e[0] == "untrack"} >= angemeldet



def test_entitaeten_melden_sich_beim_coordinator_an_und_beim_entladen_ab():
    u = Umgebung("a")
    _run(u.setup("a"))
    coord = u.coord("a")
    assert len(coord._listeners) == sum(isinstance(e, h.entity_base_mod.SolakonEntity) for e in u.added["entry_a"])
    assert coord._listeners
    _run(u.unload("a"))
    assert coord._listeners == []


def test_gesamtlimit_meldet_sich_bei_der_verteilung_an_und_beim_traegerwechsel_ab():
    u = Umgebung("ab")
    _run(u.setup("a", "b"))
    store = h.group_store_mod.require_store(u.hass)

    def angemeldet():
        return [getattr(cb, "__self__", None).carrier for cb in store._dist_listeners["sensor.grid"]
                if isinstance(getattr(cb, "__self__", None), h.number_mod.GroupLimitNumber)]
    assert angemeldet() == ["entry_a"]
    _run(u.unload("a"))
    assert _gesamtlimits(u) == {"sensor.grid": ["entry_b"]}
    assert angemeldet() == ["entry_b"]


def test_schalter_setzen_ihr_setting():
    u = Umgebung("a")
    _run(u.setup("a"))
    schalter = next(e for e in u.added["entry_a"]
                    if isinstance(e, h.switch_mod.SettingSwitch) and e._key == C.S_TARIFF_ENABLED)
    _run(schalter.async_turn_on())
    assert u.coord("a").settings[C.S_TARIFF_ENABLED] is True and schalter.is_on
    _run(schalter.async_turn_off())
    assert u.coord("a").settings[C.S_TARIFF_ENABLED] is False and not schalter.is_on

def test_entladen_der_letzten_instanz_raeumt_panel_und_hass_data_ab():
    u = Umgebung("ab")
    _run(u.setup("a", "b"))
    _run(u.unload("a"))
    assert [e for e in u.hass.events if e[0] == "panel_remove"] == []
    assert DOMAIN in u.hass.data
    _run(u.unload("b"))
    assert [e[0] for e in u.hass.events].count("panel_remove") == 1
    assert u.keys() == []


def test_entladen_schreibt_ausstehendes_speichern_nach_der_frist():
    u = Umgebung("a")

    async def lauf():
        await u.setup("a")
        await u.coord("a").async_set_cycle(True)
        await u.unload("a")
        await u.frist_abwarten()

    _run(lauf())
    assert h.stored(u.hass, _key(u.entries["a"]))["cycle_active"] is True


# ── Löschen ──────────────────────────────────────────────────────────────────

def test_loeschen_entfernt_settings_store_der_instanz():
    u = Umgebung("ab")
    h.put_store(u.hass, _key(u.entries["b"]), {C.S_ZONE1_LIMIT: 30})
    _run(u.setup("a", "b"))
    _run(u.remove("b"))
    assert _key(u.entries["b"]) not in u.hass.storage
    assert NUMBERS_KEY in u.hass.storage


def test_loeschen_der_letzten_instanz_entfernt_gruppen_stores_und_hass_data():
    u = Umgebung("ab")
    h.put_store(u.hass, DIST_KEY, {"sensor.grid": {"distribution_mode": "soc_switch"}})
    h.put_store(u.hass, SWITCH_KEY, {"sensor.grid": {"active_id": "entry_a", "start_soc": 50}})
    _run(u.setup("a", "b"))
    _run(u.remove("b", "a"))
    assert sorted(u.hass.storage) == []
    assert u.keys() == []


# ── Deaktivieren ─────────────────────────────────────────────────────────────

def test_deaktivierte_instanz_behaelt_store_und_kommt_mit_ihren_settings_zurueck():
    u = Umgebung("ab")

    async def lauf():
        await u.setup("a", "b")
        await u.coord("a").async_update_settings({C.S_ZONE1_LIMIT: 33})
        await u.unload("a")
        assert list(u.hass.data[DOMAIN]) == ["entry_b"]
        await u.frist_abwarten()
        await u.setup("a")

    _run(lauf())
    assert u.coord("a").settings[C.S_ZONE1_LIMIT] == 33
    assert h.stored(u.hass, NUMBERS_KEY) == {"sensor.grid": 1}


def test_deaktivieren_aller_instanzen_raeumt_hass_data_ab_und_behaelt_stores():
    u = Umgebung("ab")
    h.put_store(u.hass, DIST_KEY, {"sensor.grid": {"distribution_mode": "soc"}})
    _run(u.setup("a", "b"))
    _run(u.unload("a", "b"))
    assert u.keys() == []
    assert {DIST_KEY, NUMBERS_KEY} <= set(u.hass.storage)


def _settings(coord) -> dict:
    """Nur die Settings-Schlüssel; nach dem Laden stehen auch die Zustandsflags in `coord.settings`."""
    return {k: coord.settings[k] for k in C.SETTINGS_DEFAULTS}


# ── Neu laden ────────────────────────────────────────────────────────────────

def test_neu_laden_nach_der_frist_stellt_settings_und_gruppe_wieder_her():
    u = Umgebung("ab")
    h.put_store(u.hass, DIST_KEY, {"sensor.grid": {"distribution_mode": "soc_switch"}})

    async def lauf():
        await u.setup("a", "b")
        await u.coord("a").async_update_settings({C.S_ZONE1_LIMIT: 33})
        await u.coord("a").async_set_cycle(True)
        h.group_store_mod.store_for(u.hass).soc_switch_changed("sensor.grid", {"active_id": "entry_b", "start_soc": 61, "was_zone0": False})
        vorher = (_settings(u.coord("a")), u.coord("a").cycle_active, h.groups_state(u.hass))
        await u.unload("a", "b")
        await u.frist_abwarten()
        await u.setup("a", "b")
        return vorher

    settings, cycle, gruppen = _run(lauf())
    assert _settings(u.coord("a")) == settings and u.coord("a").cycle_active is cycle
    assert h.groups_state(u.hass) == gruppen


# ── Ausstehendes Speichern beim Abräumen (L1–L3) ────────────────────────────────

def test_neu_laden_binnen_der_frist_sieht_den_letzten_stand():
    u = Umgebung("a")

    async def lauf():
        await u.setup("a")
        await u.coord("a").async_set_cycle(True)
        await u.unload("a")
        await u.setup("a")

    _run(lauf())
    assert u.coord("a").cycle_active is True


def test_loeschen_binnen_der_frist_hinterlaesst_keinen_store():
    u = Umgebung("a")

    async def lauf():
        await u.setup("a")
        await u.coord("a").async_set_cycle(True)
        await u.remove("a")
        await u.frist_abwarten()

    _run(lauf())
    assert _key(u.entries["a"]) not in u.hass.storage


def test_loeschen_der_letzten_instanz_binnen_der_frist_hinterlaesst_keinen_gruppen_store():
    u = Umgebung("ab")
    h.put_store(u.hass, DIST_KEY, {"sensor.grid": {"distribution_mode": "soc_switch"}})

    async def lauf():
        await u.setup("a", "b")
        h.group_store_mod.store_for(u.hass).soc_switch_changed("sensor.grid", {"active_id": "entry_a", "start_soc": 50})
        await u.remove("b", "a")
        await u.frist_abwarten()

    _run(lauf())
    assert sorted(u.hass.storage) == []


# ── Kapazitätssensoren der Verteilung ────────────────────────────────────────

CAP = C.capacity_key


def _caps(u, grid="sensor.grid") -> dict:
    """Kapazitätsschlüssel der gespeicherten Verteilung einer Netzgruppe."""
    dist = h.stored(u.hass, DIST_KEY, {}).get(grid, {})
    return {k: v for k, v in dist.items() if C.CAPACITY_KEY.fullmatch(k)}


def test_loeschen_entfernt_den_kapazitaetssensor_der_instanz():
    u = Umgebung("abc")
    h.put_store(u.hass, DIST_KEY, {"sensor.grid": {
        CAP("entry_a"): "sensor.cap_a", CAP("entry_b"): "sensor.cap_b", CAP("entry_c"): "sensor.cap_c"}})
    _run(u.setup("a", "b", "c"))
    _run(u.remove("b"))
    assert _caps(u) == {CAP("entry_a"): "sensor.cap_a", CAP("entry_c"): "sensor.cap_c"}


def test_setup_entfernt_kapazitaetssensor_ohne_eintrag():
    u = Umgebung("ab")
    h.put_store(u.hass, DIST_KEY, {"sensor.grid": {CAP("entry_a"): "sensor.cap_a", CAP("entry_x"): "sensor.cap_x"}})
    _run(u.setup("a", "b"))
    assert _caps(u) == {CAP("entry_a"): "sensor.cap_a"}


def _wechsel(u, p, grid):
    """Netzsensor im Options-Flow ändern wie in HA: erst `entry.data`, dann über den Update-Listener neu laden."""
    async def lauf():
        u.entries[p].data = {**u.entries[p].data, C.CONF_GRID_SENSOR: grid}
        await u.unload(p)
        await u.setup(p)
    _run(lauf())


def _gesamtlimits(u) -> dict[str, list[str]]:
    """Lebende Gesamtlimit-Entitäten je Netzsensor mit ihrem Träger."""
    limits: dict[str, list[str]] = {}
    for entities in u.added.values():
        for e in entities:
            if isinstance(e, h.number_mod.GroupLimitNumber) and not e.__dict__.get("removed"):
                limits.setdefault(e.grid_sensor, []).append(e.carrier)
    return limits


def _registriertes_gesamtlimit(u, number: int) -> tuple:
    """Gesamtlimit-Entität und Gerät der Netzgruppe `number` in den Registrierungen, wie HA sie anlegt."""
    ents, devs = h.ha_stubs.entity_registry_get(u.hass), h.ha_stubs.device_registry_get(u.hass)
    ents.entities[f"number.netzgruppe_{number}"] = ("number", DOMAIN, f"group_{number}_global_max_power")
    devs.devices[f"dev_{number}"] = h.ha_stubs.DeviceEntry(f"dev_{number}", {(DOMAIN, f"group_{number}")})
    return ents, devs



def test_paralleles_laden_ohne_gruppennummer_legt_ein_gesamtlimit_an(monkeypatch):
    """O3: Zwei Einträge laden gleichzeitig, die Gruppennummer wird erst gespeichert (Wartepunkt)."""
    u = Umgebung("ab")
    vergeben = h.group_store_mod.GroupStore.group_number

    async def mit_wartepunkt(self, grid_sensor):
        await asyncio.sleep(0)
        return await vergeben(self, grid_sensor)
    monkeypatch.setattr(h.group_store_mod.GroupStore, "group_number", mit_wartepunkt)

    async def lauf():
        await u.setup()
        await asyncio.gather(u.setup("a"), u.setup("b"))
    _run(lauf())
    assert _gesamtlimits(u) == {"sensor.grid": ["entry_a"]}

def test_netzsensor_wechsel_der_traegerin_gibt_das_gesamtlimit_der_alten_netzgruppe_weiter():
    u = Umgebung("abc")
    _run(u.setup("a", "b", "c"))
    _wechsel(u, "a", "sensor.other")
    assert _gesamtlimits(u) == {"sensor.grid": ["entry_b"]}


def test_netzsensor_rueckwechsel_der_traegerin_legt_das_gesamtlimit_neu_an():
    u = Umgebung("abc")
    _run(u.setup("a", "b", "c"))
    _wechsel(u, "a", "sensor.other")
    _wechsel(u, "a", "sensor.grid")
    assert _gesamtlimits(u) == {"sensor.grid": ["entry_a"]}


def test_netzsensor_wechsel_raeumt_gesamtlimit_der_einzeln_gewordenen_netzgruppe_ab():
    for wechselt in "ab":
        u = Umgebung("ab")
        _run(u.setup("a", "b"))
        ents, devs = _registriertes_gesamtlimit(u, 1)
        _wechsel(u, wechselt, "sensor.other")
        assert _gesamtlimits(u) == {}, wechselt
        assert ents.entities == {} and devs.devices == {}, wechselt


def test_netzsensor_wechsel_nimmt_den_kapazitaetssensor_mit():
    u = Umgebung("abc")
    h.put_store(u.hass, DIST_KEY, {"sensor.grid": {CAP("entry_a"): "sensor.cap_a", CAP("entry_b"): "sensor.cap_b"}})
    _run(u.setup("a", "b", "c"))
    _wechsel(u, "a", "sensor.other")
    assert _caps(u) == {CAP("entry_b"): "sensor.cap_b"}
    assert _caps(u, "sensor.other") == {CAP("entry_a"): "sensor.cap_a"}
    assert u.coord("a").group.dist_cfg()[CAP("entry_a")] == "sensor.cap_a"


def test_netzsensor_wechsel_behaelt_den_eintrag_der_neuen_netzgruppe():
    u = Umgebung("abc")
    h.put_store(u.hass, DIST_KEY, {"sensor.grid": {CAP("entry_a"): "sensor.cap_alt"}})
    _run(u.setup("a", "b", "c"))
    h.group_store_mod.require_store(u.hass).dist["sensor.other"] = {CAP("entry_a"): "sensor.cap_neu"}
    _wechsel(u, "a", "sensor.other")
    assert _caps(u) == {}
    assert _caps(u, "sensor.other") == {CAP("entry_a"): "sensor.cap_neu"}


# ── Fehler im Setup ──────────────────────────────────────────────────────────

def test_setup_mit_unlesbarem_gruppenspeicher_ist_nicht_bereit(monkeypatch):
    u = Umgebung("a")

    async def laden(self):
        raise h.ha_stubs.HomeAssistantError("Speicher defekt")
    monkeypatch.setattr(h.ha_stubs.Store, "async_load", laden)
    with pytest.raises(h.ha_stubs.ConfigEntryNotReady):
        _run(u.setup("a"))


def test_programmierfehler_im_setup_bleibt_ein_fehler(monkeypatch):
    u = Umgebung("a")

    async def kaputt(self):
        raise TypeError("Programmierfehler")
    monkeypatch.setattr(h.coordinator_mod.SolakonCoordinator, "async_setup", kaputt)
    with pytest.raises(TypeError):
        _run(u.setup("a"))



def test_geloeschte_instanz_nach_gescheitertem_setup_hinterlaesst_keinen_gruppenspeicher(monkeypatch):
    """F3: Scheitert das Setup nach dem Laden des Gruppenspeichers, darf er das Löschen nicht überleben."""
    u = Umgebung("ab")
    u.hass.config_entries.entries.remove(u.entries["b"])   # b wird erst nach dem Löschen von a angelegt
    h.put_store(u.hass, DIST_KEY, {"sensor.grid": {"global_max_power": 500}})

    async def kaputt(self):
        raise h.ha_stubs.HomeAssistantError("Sensor fehlt")
    with monkeypatch.context() as m:
        m.setattr(h.coordinator_mod.SolakonCoordinator, "async_setup", kaputt)
        with pytest.raises(h.ha_stubs.ConfigEntryNotReady):
            _run(u.setup("a"))
    _run(u.remove("a"))
    assert DIST_KEY not in u.hass.storage
    u.hass.config_entries.entries.append(u.entries["b"])
    _run(u.setup("b"))
    assert u.coord("b").group.dist_cfg()["global_max_power"] == C.DIST_SCHEMA["global_max_power"].default

def test_gescheitertes_entladen_der_plattformen_laesst_die_instanz_laufen(monkeypatch):
    u = Umgebung("a")
    _run(u.setup("a"))
    u.hass.events = []

    async def scheitert(self, entry, platforms):
        return False
    monkeypatch.setattr(h.FakeConfigEntries, "async_unload_platforms", scheitert)
    assert not _run(h.integration.async_unload_entry(u.hass, u.entries["a"]))
    assert [e for e in u.hass.events if e[0] == "untrack"] == []
    assert u.coord("a").trackers.active()
    assert u.keys() == [DOMAIN, f"{DOMAIN}_runtime"]


def test_gescheitertes_plattform_setup_raeumt_die_instanz_ab(monkeypatch):
    u = Umgebung("ab")
    _run(u.setup("a"))

    async def scheitert(self, entry, platforms):
        raise h.ha_stubs.HomeAssistantError("Plattform defekt")
    monkeypatch.setattr(h.FakeConfigEntries, "async_forward_entry_setups", scheitert)
    with pytest.raises(h.ha_stubs.ConfigEntryNotReady):
        _run(u.setup("b"))
    assert list(u.hass.data[DOMAIN]) == ["entry_a"]
    assert [e for e in u.hass.events if e[0] == "panel_remove"] == []


def test_gescheitertes_plattform_setup_der_einzigen_instanz_raeumt_alles_ab(monkeypatch):
    u = Umgebung("a")

    async def scheitert(self, entry, platforms):
        raise h.ha_stubs.HomeAssistantError("Plattform defekt")
    monkeypatch.setattr(h.FakeConfigEntries, "async_forward_entry_setups", scheitert)
    with pytest.raises(h.ha_stubs.ConfigEntryNotReady):
        _run(u.setup("a"))
    angemeldet = {e[3] for e in u.hass.events if e[0] == "track"}
    assert {e[1] for e in u.hass.events if e[0] == "untrack"} >= angemeldet
    assert [e[0] for e in u.hass.events].count("panel_remove") == 1
    assert u.keys() == []
