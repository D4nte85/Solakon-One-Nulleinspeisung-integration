"""Lebenszyklus über `async_setup_entry`, `async_unload_entry` und `async_remove_entry`.

Setup, Entladen, Löschen, Deaktivieren (entladen, aber eingerichtet) und Neu laden mit den
Store- und Task-Attrappen aus `ha_stubs.py`. Die number-Plattform wird wie in HA nach dem
Setup des Eintrags geladen, weil sie den Träger des Gesamtlimits verwaltet.
"""
from __future__ import annotations


import pytest

from tests import harness as h

C = h.const
DOMAIN = C.DOMAIN
DIST_KEY = f"{DOMAIN}_distribution"
SWITCH_KEY = f"{DOMAIN}_soc_switch_state"
NUMBERS_KEY = f"{DOMAIN}_group_numbers"


def _key(entry) -> str:
    return f"{DOMAIN}_{entry.entry_id}"


class Umgebung:
    """FakeHass mit Einträgen je Präfix am selben Netzsensor; Plattform-Entitäten je Eintrag."""

    def __init__(self, prefixes: str):
        self.hass = h.FakeHass("de")
        self.entries = {p: h.FakeEntry(f"entry_{p}", h.entry_data(p)) for p in prefixes}
        self.hass.config_entries.entries = list(self.entries.values())
        self.added: dict[str, list] = {}

    def coord(self, p):
        return self.hass.data[DOMAIN][self.entries[p].entry_id]

    async def setup(self, *prefixes):
        for p in prefixes:
            entry = self.entries[p]
            await h.integration.async_setup_entry(self.hass, entry)
            await h.number_mod.async_setup_entry(self.hass, entry, self.added.setdefault(entry.entry_id, []).extend)

    async def unload(self, *prefixes):
        for p in prefixes:
            assert await h.integration.async_unload_entry(self.hass, self.entries[p])

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


# ── Befunde der geschärften Attrappen (offen) ────────────────────────────────

@pytest.mark.xfail(strict=True, reason="Befund L1: Entladen schreibt ausstehendes async_delay_save nicht sofort; "
                                        "Neu laden binnen der Frist lädt den alten Stand")
def test_neu_laden_binnen_der_frist_sieht_den_letzten_stand():
    u = Umgebung("a")

    async def lauf():
        await u.setup("a")
        await u.coord("a").async_set_cycle(True)
        await u.unload("a")
        await u.setup("a")

    _run(lauf())
    assert u.coord("a").cycle_active is True


@pytest.mark.xfail(strict=True, reason="Befund L2: ausstehendes async_delay_save der gelöschten Instanz "
                                        "legt ihren Store nach dem Löschen wieder an")
def test_loeschen_binnen_der_frist_hinterlaesst_keinen_store():
    u = Umgebung("a")

    async def lauf():
        await u.setup("a")
        await u.coord("a").async_set_cycle(True)
        await u.remove("a")
        await u.frist_abwarten()

    _run(lauf())
    assert _key(u.entries["a"]) not in u.hass.storage


@pytest.mark.xfail(strict=True, reason="Befund L3: ausstehendes async_delay_save des soc_switch-Zustands "
                                        "legt den Gruppen-Store nach dem Löschen der letzten Instanz wieder an")
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
