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

from .const import (
    DOMAIN, PLATFORMS, S_REGULATION_ENABLED,
    CONF_GRID_SENSOR, CONF_ACTUAL_SENSOR, CONF_SOLAR_SENSOR, CONF_SOC_SENSOR,
)

_LOGGER = logging.getLogger(__name__)
PANEL_JS_URL = f"/{DOMAIN}/panel.js"


# ── WebSocket Commands ───────────────────────────────────────────────────────

@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/get_config",
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


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/save_config",
    vol.Required("entry_id"): str,
    vol.Required("changes"): dict,
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


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/get_status",
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
        "zone": coord.current_zone,
        "zone_label": coord.zone_label,
        "mode_label": coord.mode_label,
        "last_action": coord.last_action,
        "last_action_ts": coord.last_action_ts,
        "last_output_ts": coord.last_output_ts,
        "mode_label_ts": coord.mode_label_ts,
        "last_error": coord.last_error,
        "integral": round(coord.integral, 2),
        "grid": coord._flt(cfg.get(CONF_GRID_SENSOR, ""), 0),
        "actual_power": coord._flt(cfg.get(CONF_ACTUAL_SENSOR, ""), 0),
        "solar": coord._flt(cfg.get(CONF_SOLAR_SENSOR, ""), 0),
        "soc": coord._flt(cfg.get(CONF_SOC_SENSOR, ""), 0),
        "cycle_active": coord.cycle_active,
        "surplus_active": coord.surplus_active,
        "ac_charge": coord.ac_charge_active,
        "tariff_charge": coord.tariff_charge_active,
        "regulation_enabled": coord.settings.get(S_REGULATION_ENABLED, False),
        # StdDev
        "stddev": coord.grid_stddev,
        # Dynamic Offset — pro Zone einzeln
        "dyn_z1_enabled": coord.settings.get("dyn_z1_enabled", False),
        "dyn_z2_enabled": coord.settings.get("dyn_z2_enabled", False),
        "dyn_ac_enabled": coord.settings.get("dyn_ac_enabled", False),
        "dyn_z1": coord.dyn_offset_z1,
        "dyn_z2": coord.dyn_offset_z2,
        "dyn_ac": coord.dyn_offset_ac,
    })


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/reset_integral",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def _ws_reset_integral(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    coord = hass.data.get(DOMAIN, {}).get(msg["entry_id"])
    if coord:
        coord.reset_integral()
        connection.send_result(msg["id"], {"success": True})
    else:
        connection.send_error(msg["id"], "not_found", "Coordinator not found")

@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/set_cycle",
    vol.Required("entry_id"): str,
    vol.Required("active"): bool,
})
@websocket_api.async_response
async def _ws_set_cycle(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    coord = hass.data.get(DOMAIN, {}).get(msg["entry_id"])
    if not coord:
        connection.send_error(msg["id"], "not_found", "Coordinator not found")
        return
    coord.cycle_active = bool(msg["active"])
    coord.integral = 0.0
    coord._set_last_action(
        f"Debug: Zone {'1' if coord.cycle_active else '2'} manuell aktiviert"
    )
    coord.notify_listeners()
    connection.send_result(msg["id"], {"success": True, "cycle_active": coord.cycle_active})


# ── Setup / Unload ───────────────────────────────────────────────────────────

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .coordinator import SolakonCoordinator

    coordinator = SolakonCoordinator(hass, entry)
    try:
        await coordinator.async_setup()
    except Exception as ex:
        raise ConfigEntryNotReady(f"Solakon: Setup fehlgeschlagen: {ex}") from ex

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    panel_js_file = Path(__file__).parent / "frontend" / "solakon-panel.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_JS_URL, str(panel_js_file), False)]
    )

    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="solakon-panel",
        sidebar_title="Solakon ONE",
        sidebar_icon="mdi:solar-power",
        frontend_url_path=DOMAIN,
        module_url=PANEL_JS_URL,
        config={"entry_id": entry.entry_id},
        require_admin=False,
    )

    websocket_api.async_register_command(hass, _ws_get_config)
    websocket_api.async_register_command(hass, _ws_save_config)
    websocket_api.async_register_command(hass, _ws_get_status)
    websocket_api.async_register_command(hass, _ws_reset_integral)
    websocket_api.async_register_command(hass, _ws_set_cycle)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.components.frontend import async_remove_panel

    coord = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coord:
        await coord.async_shutdown()

    async_remove_panel(hass, DOMAIN)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
    
async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    from homeassistant.helpers.storage import Store
    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")
    await store.async_remove()
