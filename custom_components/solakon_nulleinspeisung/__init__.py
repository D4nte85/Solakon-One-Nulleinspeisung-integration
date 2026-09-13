"""Solakon ONE Nulleinspeisung — HACS custom integration."""
from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.components import websocket_api, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN, PLATFORMS, S_REGULATION_ENABLED,
    CONF_INSTANCE_NAME,
    CONF_GRID_SENSOR, CONF_ACTUAL_SENSOR, CONF_SOLAR_SENSOR, CONF_SOC_SENSOR,
    STORAGE_VERSION, DIST_DEFAULTS, VERSION,
)

STORAGE_VERSION_DIST = 2
STORAGE_KEY_DIST     = f"{DOMAIN}_distribution"

STORAGE_VERSION_SOC_SWITCH = 1
STORAGE_KEY_SOC_SWITCH     = f"{DOMAIN}_soc_switch_state"

_LOGGER = logging.getLogger(__name__)

# Integrationsweite `hass.data`-Schlüssel (ohne DOMAIN-Präfix), entfernt mit der letzten Instanz.
DATA_KEYS = ("dist_store", "dist_config", "soc_switch_store", "soc_switch_state",
             "panel_registered", "ws_registered")
PANEL_JS_URL = f"/{DOMAIN}/panel.js"


class SolakonDistStore(Store):
    """Verteilungs-Store mit Schemamigration."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict
    ) -> dict:
        """Hebt Version 1 auf 2: flache Form verschachteln, Zwei-Feld-Modus auflösen."""
        if old_major_version >= 2 or not old_data:
            return old_data

        if "distribution_mode" in old_data or "global_max_power" in old_data:
            flat = _migrate_dist_mode(old_data)
            group_keys = {
                e.data.get(CONF_GRID_SENSOR, "")
                for e in self.hass.config_entries.async_entries(DOMAIN)
            }
            return {gk: dict(flat) for gk in group_keys}
        return {gk: _migrate_dist_mode(cfg) for gk, cfg in old_data.items()}


def _migrate_dist_mode(cfg: dict) -> dict:
    """Bildet das alte `capacity_weighting`-Bool auf den Drei-Wert-`distribution_mode` ab."""
    if "capacity_weighting" not in cfg:
        return cfg
    migrated = dict(cfg)
    if migrated.pop("capacity_weighting", False):
        migrated["distribution_mode"] = "capacity"
    elif migrated.get("distribution_mode") == "weighted":
        migrated["distribution_mode"] = "soc"
    return migrated


# ── WebSocket Commands ───────────────────────────────────────────────────────

@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/get_all_instances",
})
@websocket_api.async_response
async def _ws_get_all_instances(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    instances = []
    for entry_id, coord in hass.data.get(DOMAIN, {}).items():
        name = coord.entry.data.get(CONF_INSTANCE_NAME) or coord.entry.title or entry_id
        instances.append({
            "entry_id":      entry_id,
            "instance_name": name,
            "grid_sensor":   coord.entry.data.get(CONF_GRID_SENSOR, ""),
        })
    instances.sort(key=lambda x: x["instance_name"].lower())
    connection.send_result(msg["id"], {"instances": instances})


@websocket_api.websocket_command({
    vol.Required("type"):     f"{DOMAIN}/get_config",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def _ws_get_config(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    coord = hass.data.get(DOMAIN, {}).get(msg["entry_id"])
    if coord:
        connection.send_result(msg["id"], coord.settings)
    else:
        connection.send_error(msg["id"], "not_found", "Coordinator not found")


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"):     f"{DOMAIN}/save_config",
    vol.Required("entry_id"): str,
    vol.Required("changes"):  dict,
})
@websocket_api.async_response
async def _ws_save_config(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    coord = hass.data.get(DOMAIN, {}).get(msg["entry_id"])
    if coord:
        await coord.async_update_settings(msg["changes"])
        connection.send_result(msg["id"], {"success": True})
    else:
        connection.send_error(msg["id"], "not_found", "Coordinator not found")


# Schlüssel des WS-Status: Name im Panel oder Paar (Panel, Schnappschuss).
WS_STATUS_KEYS = (
    ("zone", "current_zone"), "zone_label", "mode_label", "last_action", "last_action_ts",
    "last_output_ts", "mode_label_ts", "last_error", "integral",
    "cycle_active", "surplus_active", ("ac_charge", "ac_charge_active"),
    ("tariff_charge", "tariff_charge_active"), "regulation_enabled",
    ("stddev", "grid_stddev"), ("stddev_raw", "grid_stddev_raw"),
    "dyn_z1_enabled", "dyn_z2_enabled", "dyn_ac_enabled",
    ("dyn_z1", "dyn_offset_z1"), ("dyn_z2", "dyn_offset_z2"), ("dyn_ac", "dyn_offset_ac"),
    "active_fall", "operating_state", "discharge_locked", "dist_mode_effective", "is_night",
    "forecast_tariff_suppressed", "forecast_surplus_forced", "forecast_exit_lock", "allocated_power",
    "offset_zone", "offset_dynamic", "offset_static", "offset_value", "capacity_kwh",
)


@websocket_api.websocket_command({
    vol.Required("type"):     f"{DOMAIN}/get_status",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def _ws_get_status(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    coord = hass.data.get(DOMAIN, {}).get(msg["entry_id"])
    if not coord:
        connection.send_error(msg["id"], "not_found", "Coordinator not found")
        return

    cfg = coord.entry.data
    connection.send_result(msg["id"], {
        **coord.snapshot_view(WS_STATUS_KEYS),
        "grid":         coord._flt_power(cfg.get(CONF_GRID_SENSOR, ""), 0),
        "actual_power": coord._flt_power(cfg.get(CONF_ACTUAL_SENSOR, ""), 0),
        "solar":        coord._flt_power(cfg.get(CONF_SOLAR_SENSOR, ""), 0),
        "soc":          coord._flt(cfg.get(CONF_SOC_SENSOR, ""), 0),
    })


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"):     f"{DOMAIN}/reset_integral",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def _ws_reset_integral(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    coord = hass.data.get(DOMAIN, {}).get(msg["entry_id"])
    if coord:
        async with coord._lock:
            coord.reset_integral()
        connection.send_result(msg["id"], {"success": True})
    else:
        connection.send_error(msg["id"], "not_found", "Coordinator not found")


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"):     f"{DOMAIN}/set_cycle",
    vol.Required("entry_id"): str,
    vol.Required("active"):   bool,
})
@websocket_api.async_response
async def _ws_set_cycle(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    coord = hass.data.get(DOMAIN, {}).get(msg["entry_id"])
    if coord:
        async with coord._lock:
            coord.cycle_active = msg["active"]
            coord.integral = 0.0
            # Flag persistieren (Teil von _store_data)
            coord._store.async_delay_save(coord._store_data, 5)
            coord.notify_listeners()
        # Neuen Zustand sofort anwenden
        hass.async_create_task(coord._async_regulate())
        connection.send_result(msg["id"], {"success": True})
    else:
        connection.send_error(msg["id"], "not_found", "Coordinator not found")


# ── Setup / Teardown ─────────────────────────────────────────────────────────

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    frontend_dir = Path(__file__).parent / "frontend"
    translations_dir = Path(__file__).parent / "translations"
    # Übersetzungsdateien für das Panel ausliefern: Zustandstexte, Entitätsnamen.
    await hass.http.async_register_static_paths([
        StaticPathConfig(PANEL_JS_URL,               str(frontend_dir / "solakon-panel.js"), False),
        StaticPathConfig(f"/{DOMAIN}/panel.de.json", str(frontend_dir / "panel.de.json"),    False),
        StaticPathConfig(f"/{DOMAIN}/panel.en.json", str(frontend_dir / "panel.en.json"),    False),
        StaticPathConfig(f"/{DOMAIN}/entity.de.json", str(translations_dir / "de.json"),     False),
        StaticPathConfig(f"/{DOMAIN}/entity.en.json", str(translations_dir / "en.json"),     False),
    ])
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .coordinator import SolakonCoordinator

    try:
        coordinator = SolakonCoordinator(hass, entry)
        await coordinator.async_setup()
    except Exception as ex:
        raise ConfigEntryNotReady(f"Solakon: Setup fehlgeschlagen: {ex}") from ex

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Eintrag neu laden wenn die Entitäten-Zuweisung im OptionsFlow geändert wurde
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Distribution-Store einmalig anlegen + Config in synchron lesbaren Cache laden.
    # Cache ist nach grid_power_sensor verschachtelt ({gruppe: {...DIST_DEFAULTS...}})
    # — jede Netzgruppe hat unabhängige Verteilungs-Einstellungen.
    await _ensure_store(
        hass, "dist_store", "dist_config",
        lambda: SolakonDistStore(hass, STORAGE_VERSION_DIST, STORAGE_KEY_DIST), {}, lambda stored: stored,
    )

    # SOC-Switch-Laufzeitzustand (Modus `soc_switch`) — eigener Store, getrennt
    # von _dist_store
    await _ensure_store(
        hass, "soc_switch_store", "soc_switch_state",
        lambda: Store(hass, STORAGE_VERSION_SOC_SWITCH, STORAGE_KEY_SOC_SWITCH),
        {"active_id": None, "start_soc": None},
        lambda stored: {"active_id": stored.get("active_id"), "start_soc": stored.get("start_soc")},
    )

    # WebSocket-Commands nur einmal registrieren
    if not hass.data.get(f"{DOMAIN}_ws_registered"):
        websocket_api.async_register_command(hass, _ws_get_all_instances)
        websocket_api.async_register_command(hass, _ws_get_config)
        websocket_api.async_register_command(hass, _ws_save_config)
        websocket_api.async_register_command(hass, _ws_get_status)
        websocket_api.async_register_command(hass, _ws_reset_integral)
        websocket_api.async_register_command(hass, _ws_set_cycle)
        websocket_api.async_register_command(hass, _ws_get_distribution_config)
        websocket_api.async_register_command(hass, _ws_save_distribution_config)
        hass.data[f"{DOMAIN}_ws_registered"] = True

    # Panel nur einmal registrieren — kein entry_id in config
    if not hass.data.get(f"{DOMAIN}_panel_registered"):
        await panel_custom.async_register_panel(
            hass,
            webcomponent_name="solakon-panel",
            sidebar_title="Solakon ONE",
            sidebar_icon="mdi:solar-power",
            frontend_url_path=DOMAIN,
            # Versionierte URL erzwingt einen frischen Browser-Fetch bei jedem Update.
            module_url=f"{PANEL_JS_URL}?v={VERSION}",
            config={},
            require_admin=False,
        )
        hass.data[f"{DOMAIN}_panel_registered"] = True

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception as ex:
        coord = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coord:
            await coord.async_shutdown()
        raise ConfigEntryNotReady(f"Solakon: Platform-Setup fehlgeschlagen: {ex}") from ex

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Eintrag neu laden wenn die Entitäten-Zuweisung (entry.data) geändert wurde."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _ensure_store(
    hass: HomeAssistant, store_key: str, data_key: str, make_store, empty: dict, from_stored,
) -> None:
    """Store unter `<DOMAIN>_<store_key>` einmalig anlegen und in `<DOMAIN>_<data_key>` laden.

    `empty` steht synchron im Cache, bevor `async_load()` an den Event-Loop abgibt;
    danach ersetzt `from_stored(geladen or {})` den Inhalt.
    """
    if hass.data.get(f"{DOMAIN}_{store_key}"):
        return
    store = make_store()
    hass.data[f"{DOMAIN}_{store_key}"] = store
    hass.data[f"{DOMAIN}_{data_key}"] = empty
    hass.data[f"{DOMAIN}_{data_key}"] = from_stored(await store.async_load() or {})


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.components.frontend import async_remove_panel

    coord = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coord:
        await coord.async_shutdown()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

        # Panel + Store nur entfernen wenn keine Instanz mehr läuft
        if not hass.data.get(DOMAIN):
            async_remove_panel(hass, DOMAIN)
            hass.data.pop(DOMAIN, None)
            for key in DATA_KEYS:
                hass.data.pop(f"{DOMAIN}_{key}", None)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")
    await store.async_remove()

    # Home Assistant traegt den Entry vor diesem Aufruf aus der Registrierung aus.
    # Ist danach keiner mehr uebrig, werden auch die instanzuebergreifenden Stores
    # entfernt; bei weiteren Instanzen bleiben sie bestehen.
    if not hass.config_entries.async_entries(DOMAIN):
        await SolakonDistStore(hass, STORAGE_VERSION_DIST, STORAGE_KEY_DIST).async_remove()
        await Store(hass, STORAGE_VERSION_SOC_SWITCH, STORAGE_KEY_SOC_SWITCH).async_remove()


@websocket_api.websocket_command({
    vol.Required("type"):        f"{DOMAIN}/get_distribution_config",
    vol.Required("grid_sensor"): str,
})
@websocket_api.async_response
async def _ws_get_distribution_config(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    store = hass.data.get(f"{DOMAIN}_dist_store")
    if store is None:
        connection.send_result(msg["id"], {"distribution": DIST_DEFAULTS.copy()})
        return
    stored = await store.async_load() or {}
    data = {**DIST_DEFAULTS, **stored.get(msg["grid_sensor"], {})}
    connection.send_result(msg["id"], {"distribution": data})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"):         f"{DOMAIN}/save_distribution_config",
    vol.Required("grid_sensor"):  str,
    vol.Required("distribution"): dict,
})
@websocket_api.async_response
async def _ws_save_distribution_config(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    store = hass.data.get(f"{DOMAIN}_dist_store")
    if store is None:
        connection.send_error(msg["id"], "not_ready", "Distribution-Store nicht initialisiert")
        return

    group_key = msg["grid_sensor"]
    all_groups = await store.async_load() or {}
    all_groups[group_key] = msg["distribution"]

    await store.async_save(all_groups)
    hass.data[f"{DOMAIN}_dist_config"] = all_groups

    # Neue Verteilung sofort auf die Instanzen dieser Gruppe anwenden, andere
    # Gruppen bleiben unberührt. Lock-geschützt, parallele Läufe werden verworfen.
    # Globale Sensor-Felder (PV-Vorhersage heute/morgen, Austritts-Sperre, Tarif)
    # ändern die effektiv wirksame Sensor-Entität einer Instanz ohne Änderung ihrer
    # eigenen Settings — Listener werden deshalb hier neu registriert.
    for coord in hass.data.get(DOMAIN, {}).values():
        if coord.entry.data.get(CONF_GRID_SENSOR, "") != group_key:
            continue
        coord.update_sensor_trackers()
        hass.async_create_task(coord._async_regulate())

    connection.send_result(msg["id"], {"success": True})
