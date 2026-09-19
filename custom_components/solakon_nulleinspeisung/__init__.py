"""Solakon ONE Nulleinspeisung — HACS custom integration."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN, PLATFORMS,
    CONF_INSTANCE_NAME,
    CONF_GRID_SENSOR, CONF_ACTUAL_SENSOR, CONF_SOLAR_SENSOR, CONF_SOC_SENSOR,
    STORAGE_VERSION, DIST_DEFAULTS, DIST_SCHEMA, SETTINGS_SCHEMA, VERSION,
)
from . import group_store
from .schema import InvalidSettings

_LOGGER = logging.getLogger(__name__)

# Integrationsweite `hass.data`-Schlüssel (ohne DOMAIN-Präfix), entfernt mit der letzten Instanz.
DATA_KEYS = ("panel_registered", "ws_registered", *group_store.DATA_KEYS)
PANEL_JS_URL = f"/{DOMAIN}/panel.js"

# Schlüssel des WS-Status: Name im Panel oder Paar (Panel, Schnappschuss).
WS_STATUS_KEYS = (
    ("zone", "current_zone"), "zone_label", "mode_key", "mode_label", "last_action", "last_action_ts",
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


# ── WebSocket Commands ───────────────────────────────────────────────────────

def _get_or_error(connection: websocket_api.ActiveConnection, msg: dict, value: Any, code: str, text: str) -> Any:
    """`value` zurückgeben; bei None Fehler `code` an den Aufrufer senden."""
    if value is None:
        connection.send_error(msg["id"], code, text)
    return value


def _send_invalid(connection: websocket_api.ActiveConnection, msg: dict, findings: list[dict]) -> None:
    """Abgewiesene Änderungen als Fehler `invalid_settings`, Befunde als JSON im Text."""
    connection.send_error(msg["id"], "invalid_settings", json.dumps(findings))


def _coord_or_error(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> Any:
    """Coordinator zu `msg["entry_id"]`, sonst Fehler `not_found` und None."""
    return _get_or_error(
        connection, msg, hass.data.get(DOMAIN, {}).get(msg["entry_id"]),
        "not_found", "Coordinator not found",
    )


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
    if (coord := _coord_or_error(hass, connection, msg)) is None:
        return
    connection.send_result(msg["id"], coord.settings)


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
    if (coord := _coord_or_error(hass, connection, msg)) is None:
        return
    try:
        await coord.async_update_settings(msg["changes"])
    except InvalidSettings as err:
        _send_invalid(connection, msg, err.findings)
        return
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command({
    vol.Required("type"):     f"{DOMAIN}/get_status",
    vol.Required("entry_id"): str,
    vol.Optional("language"): str,
})
@websocket_api.async_response
async def _ws_get_status(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    if (coord := _coord_or_error(hass, connection, msg)) is None:
        return

    cfg = coord.entry.data
    connection.send_result(msg["id"], {
        **coord.snapshot_view(WS_STATUS_KEYS),
        "grid":         coord._flt_power(cfg.get(CONF_GRID_SENSOR, ""), 0),
        "actual_power": coord._flt_power(cfg.get(CONF_ACTUAL_SENSOR, ""), 0),
        "solar":        coord._flt_power(cfg.get(CONF_SOLAR_SENSOR, ""), 0),
        "soc":          coord._flt(cfg.get(CONF_SOC_SENSOR, ""), 0),
        # Mit Panelsprache: Aktion und Fehlerkette in dieser statt in der Instanzsprache.
        **(coord.status_texts(msg["language"]) if msg.get("language") else {}),
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
    if (coord := _coord_or_error(hass, connection, msg)) is None:
        return
    async with coord._lock:
        coord.reset_integral()
    connection.send_result(msg["id"], {"success": True})


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
    if (coord := _coord_or_error(hass, connection, msg)) is None:
        return
    async with coord._lock:
        coord.cycle_active = msg["active"]
        coord.integral = 0.0
        coord.schedule_save()
        coord.notify_listeners()
    coord.request_regulation()
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command({
    vol.Required("type"):        f"{DOMAIN}/get_distribution_config",
    vol.Required("grid_sensor"): str,
})
@websocket_api.async_response
async def _ws_get_distribution_config(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    store = group_store.store_for(hass)
    data = DIST_DEFAULTS.copy() if store is None else store.dist_view(msg["grid_sensor"])
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
    store = _get_or_error(
        connection, msg, group_store.store_for(hass),
        "not_ready", "Distribution-Store nicht initialisiert",
    )
    if store is None:
        return
    if findings := await store.save_dist(msg["grid_sensor"], msg["distribution"]):
        _send_invalid(connection, msg, findings)
        return

    # Globale Sensor-Felder ändern den wirksamen Sensor einer Instanz ohne Änderung
    # ihrer Settings; die Mitglieder melden ihre Trigger deshalb neu an.
    for coord in group_store.group_for(hass, msg["grid_sensor"]).members().values():
        coord.apply_group_change()

    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/get_schema",
})
@websocket_api.async_response
async def _ws_get_schema(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """WS: Typ, Bereich und Schrittweite aller Settings und der Verteilung."""
    connection.send_result(msg["id"], {
        "settings":     {key: field._asdict() for key, field in SETTINGS_SCHEMA.items()},
        "distribution": {key: field._asdict() for key, field in DIST_SCHEMA.items()},
    })


# Beim ersten Setup registrierte WebSocket-Commands.
WS_COMMANDS = (
    _ws_get_all_instances, _ws_get_config, _ws_save_config, _ws_get_status, _ws_get_schema,
    _ws_reset_integral, _ws_set_cycle, _ws_get_distribution_config, _ws_save_distribution_config,
)


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


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Eintrag neu laden wenn die Entitäten-Zuweisung (entry.data) geändert wurde."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .coordinator import SolakonCoordinator

    # Gruppen-Stores vor dem Coordinator laden: seine Trigger lesen globale Sensoren der Verteilung.
    await group_store.async_load(hass)

    try:
        coordinator = SolakonCoordinator(hass, entry)
        await coordinator.async_setup()
    except Exception as ex:
        raise ConfigEntryNotReady(f"Solakon: Setup fehlgeschlagen: {ex}") from ex

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Eintrag neu laden wenn die Entitäten-Zuweisung im OptionsFlow geändert wurde
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # WebSocket-Commands nur einmal registrieren
    if not hass.data.get(f"{DOMAIN}_ws_registered"):
        for handler in WS_COMMANDS:
            websocket_api.async_register_command(hass, handler)
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
        await group_store.async_remove(hass)
