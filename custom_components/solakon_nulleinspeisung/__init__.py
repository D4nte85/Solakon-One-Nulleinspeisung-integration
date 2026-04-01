"""Solakon ONE Nulleinspeisung — HACS custom integration."""
from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.components import websocket_api, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, PLATFORMS, CONF_SOC_SENSOR
from .coordinator import SolakonCoordinator

_LOGGER = logging.getLogger(__name__)

# Die URL, unter der das JS im Browser erreichbar sein wird
PANEL_JS_URL = "/solakon_nulleinspeisung/panel.js"

# ── WebSocket Commands (Müssen vor der Registrierung definiert sein) ──────────

@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/get_config",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def _ws_get_config(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    coord: SolakonCoordinator = hass.data[DOMAIN].get(msg["entry_id"])
    if coord:
        connection.send_result(msg["id"], coord.settings)

@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/save_config",
    vol.Required("entry_id"): str,
    vol.Required("changes"): dict,
})
@websocket_api.async_response
async def _ws_save_config(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    coord: SolakonCoordinator = hass.data[DOMAIN].get(msg["entry_id"])
    if coord:
        await coord.async_update_settings(msg["changes"])
        connection.send_result(msg["id"], {"success": True})

@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/get_status",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def _ws_get_status(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    coord: SolakonCoordinator = hass.data[DOMAIN].get(msg["entry_id"])
    if not coord:
        connection.send_error(msg["id"], "not_found", "Coordinator not found")
        return

    cfg = coord.entry.data
    def sv(eid, fallback):
        state = hass.states.get(eid)
        return state.state if state else fallback

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

@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/reset_integral",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def _ws_reset_integral(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    coord: SolakonCoordinator = hass.data[DOMAIN].get(msg["entry_id"])
    if coord:
        await coord.async_reset_integral()
        connection.send_result(msg["id"], {"success": True})


# ── Setup Logic ───────────────────────────────────────────────────────────────

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solakon ONE from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = SolakonCoordinator(hass, entry)
    # Wir rufen async_setup auf, aber fangen Fehler ab, falls Sensoren noch offline sind
    await coordinator.async_setup()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # 1. Statische Datei registrieren
    panel_js_file = Path(__file__).parent / "frontend" / "solakon-panel.js"
    if not panel_js_file.exists():
        _LOGGER.error("Panel-Datei nicht gefunden unter: %s", panel_js_file)
    
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_JS_URL, str(panel_js_file), cache_headers=False)]
    )

    # 2. Panel in Seitenleiste registrieren
    try:
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
    except Exception as exc:
        _LOGGER.warning("Panel konnte nicht registriert werden: %s", exc)

    # 3. Plattformen (Sensoren etc.) laden
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # 4. WebSocket APIs registrieren
    websocket_api.async_register_command(hass, _ws_get_config)
    websocket_api.async_register_command(hass, _ws_save_config)
    websocket_api.async_register_command(hass, _ws_get_status)
    websocket_api.async_register_command(hass, _ws_reset_integral)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    from homeassistant.components.frontend import async_remove_panel
    async_remove_panel(hass, DOMAIN)
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
