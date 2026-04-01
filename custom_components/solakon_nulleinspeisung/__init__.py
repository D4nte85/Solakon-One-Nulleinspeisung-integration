"""Solakon ONE Nulleinspeisung — HACS custom integration."""
from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.components import websocket_api, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import SolakonCoordinator

_LOGGER = logging.getLogger(__name__)

# Die URL, unter der das JS im Browser erreichbar sein wird
PANEL_JS_URL = "/solakon_nulleinspeisung/panel.js"

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    coordinator = SolakonCoordinator(hass, entry)
    await coordinator.async_setup()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # ── Register sidebar panel static file ───────────────────────────────────────────
    # Pfad zur Datei: custom_components/solakon_nulleinspeisung/frontend/solakon-panel.js
    panel_js_file = Path(__file__).parent / "frontend" / "solakon-panel.js"
    
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_JS_URL, str(panel_js_file), cache_headers=False)]
    )

    # ── Register Custom Panel ───────────────────────────────────────────────────────
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
        _LOGGER.info("Solakon ONE Panel erfolgreich registriert")
    except Exception as exc:
        _LOGGER.error("Fehler bei der Panel-Registrierung: %s", exc)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # WebSocket APIs registrieren
    websocket_api.async_register_command(hass, _ws_get_config)
    websocket_api.async_register_command(hass, _ws_save_config)
    websocket_api.async_register_command(hass, _ws_get_status)
    websocket_api.async_register_command(hass, _ws_reset_integral)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Panel entfernen
    from homeassistant.components.frontend import async_remove_panel
    async_remove_panel(hass, DOMAIN)
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

# ... (Rest der WebSocket-Funktionen bleibt gleich wie in deiner Datei)
