"""Solakon ONE Nulleinspeisung — HACS custom integration."""
from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.components import websocket_api, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS, S_REGULATION_ENABLED

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

    def sv(eid: str, fallback: str = "—") -> str:
        s = hass.states.get(eid)
        return s.state if s and s.state not in ("unknown", "unavailable") else fallback

    connection.send_result(msg["id"], {
        "zone": coord.current_zone,
        "zone_label": coord.zone_label,
        "mode_label": coord.mode_label,
        "last_action": coord.last_action,
        "last_error": coord.last_error,
        "integral": round(coord.integral, 2),
        "regulation_enabled": coord.settings.get(S_REGULATION_ENABLED, False),
        "cycle_active": coord.cycle_active,
        "surplus_active": coord.surplus_active,
        "ac_charge_active": coord.ac_charge_active,
        "tariff_charge_active": coord.tariff_charge_active,
        "grid_w": sv(cfg.get("grid_power_sensor", ""), "—"),
        "solar_w": sv(cfg.get("solar_power_sensor", ""), "—"),
        "soc_pct": sv(cfg.get("soc_sensor", ""), "—"),
        "actual_w": sv(cfg.get("actual_power_sensor", ""), "—"),
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


# ── Setup ────────────────────────────────────────────────────────────────────

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .coordinator import SolakonCoordinator

    coordinator = SolakonCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Statische JS-Datei registrieren
    panel_js_file = Path(__file__).parent / "frontend" / "solakon-panel.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_JS_URL, str(panel_js_file), False)]
    )

    # Sidebar-Panel registrieren
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

    # WebSocket APIs registrieren
    websocket_api.async_register_command(hass, _ws_get_config)
    websocket_api.async_register_command(hass, _ws_save_config)
    websocket_api.async_register_command(hass, _ws_get_status)
    websocket_api.async_register_command(hass, _ws_reset_integral)

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
