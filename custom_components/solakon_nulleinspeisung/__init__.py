"""Solakon ONE Nulleinspeisung — HACS custom integration."""
from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import SolakonCoordinator

_LOGGER = logging.getLogger(__name__)

PANEL_JS_PATH  = "/solakon_nulleinspeisung/panel.js"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    coordinator = SolakonCoordinator(hass, entry)
    await coordinator.async_setup()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # ── Register sidebar panel static file ───────────────────────────────────────────
    panel_js = Path(__file__).parent / "frontend" / "solakon-panel.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_JS_PATH, str(panel_js), cache_headers=False)]
    )

    try:
        hass.components.frontend.async_register_panel(
            component_name="solakon-panel",
            sidebar_title="Solakon ONE",
            sidebar_icon="mdi:solar-power",
            frontend_url_path=DOMAIN,
            config={"entry_id": entry.entry_id},
            require_admin=False,
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("Solakon panel registration (non-critical): %s", exc)

    # ── WebSocket commands for panel ──────────────────────────────────────────────────
    websocket_api.async_register_command(hass, _ws_get_config)
    websocket_api.async_register_command(hass, _ws_save_config)
    websocket_api.async_register_command(hass, _ws_get_status)
    websocket_api.async_register_command(hass, _ws_reset_integral)

    # ── Forward to platforms ──────────────────────────────────────────────────────────
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coord: SolakonCoordinator | None = hass.data[DOMAIN].get(entry.entry_id)
    if coord:
        await coord.async_teardown()

    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    try:
        hass.components.frontend.async_remove_panel(DOMAIN)
    except Exception:  # noqa: BLE001
        pass

    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok


# ── WebSocket: get current settings ───────────────────────────────────────────
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/get_config",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def _ws_get_config(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    coord = hass.data.get(DOMAIN, {}).get(msg["entry_id"])
    if not coord:
        connection.send_error(msg["id"], "not_found", "Integration nicht gefunden")
        return
    connection.send_result(msg["id"], {
        "settings": coord.settings,
        "entities": dict(coord.entry.data),
    })


# ── WebSocket: save settings ───────────────────────────────────────────────────
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/save_config",
    vol.Required("entry_id"): str,
    vol.Required("settings"): dict,
})
@websocket_api.async_response
async def _ws_save_config(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    coord = hass.data.get(DOMAIN, {}).get(msg["entry_id"])
    if not coord:
        connection.send_error(msg["id"], "not_found", "Integration nicht gefunden")
        return
    updated = await coord.async_update_settings(msg["settings"])
    connection.send_result(msg["id"], {"settings": updated})


# ── WebSocket: live status snapshot ───────────────────────────────────────────
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/get_status",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def _ws_get_status(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    coord = hass.data.get(DOMAIN, {}).get(msg["entry_id"])
    if not coord:
        connection.send_error(msg["id"], "not_found", "Integration nicht gefunden")
        return

    cfg = coord.entry.data
    def sv(eid, default=None):
        if not eid:
            return default
        st = hass.states.get(eid)
        return st.state if st and st.state not in ('unknown','unavailable') else default

    connection.send_result(msg["id"], {
        "zone":              coord.current_zone,
        "zone_label":        coord.zone_label,
        "mode_label":        coord.mode_label,
        "last_action":       coord.last_action,
        "last_error":        coord.last_error,
        "cycle_active":      coord.cycle_active,
        "surplus_active":    coord.surplus_active,
        "ac_charge_active":  coord.ac_charge_active,
        "tariff_active":     coord.tariff_charge_active,
        "integral":          round(coord.integral, 2),
        "grid_w":            sv(cfg.get("grid_power_sensor"), "—"),
        "solar_w":           sv(cfg.get("solar_power_sensor"), "—"),
        "output_w":          sv(cfg.get("actual_power_sensor"), "—"),
        "soc_pct":           sv(cfg.get("soc_sensor"), "—"),
        "mode_raw":          sv(cfg.get("mode_select"), "—"),
    })


# ── WebSocket: reset integral ──────────────────────────────────────────────────
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/reset_integral",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def _ws_reset_integral(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    coord = hass.data.get(DOMAIN, {}).get(msg["entry_id"])
    if not coord:
        connection.send_error(msg["id"], "not_found", "Integration nicht gefunden")
        return
    await coord.async_reset_integral()
    connection.send_result(msg["id"], {"ok": True})
