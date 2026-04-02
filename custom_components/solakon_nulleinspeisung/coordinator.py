"""Coordinator — settings management with defaults."""
from __future__ import annotations
import logging
from homeassistant.helpers.storage import Store
from .const import DOMAIN, STORAGE_VERSION, SETTINGS_DEFAULTS

_LOGGER = logging.getLogger(__name__)

class SolakonCoordinator:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.settings = SETTINGS_DEFAULTS.copy()
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")
        
        # Runtime states
        self.current_zone = 2
        self.zone_label = "Initialisierung"
        self.mode_label = "Warten..."
        self.last_action = "Startvorgang"
        self.integral = 0.0

    async def async_setup(self):
        stored = await self._store.async_load()
        if stored:
            # Bestehende Werte mit Defaults mergen (falls neue Felder dazu kamen)
            self.settings = {**SETTINGS_DEFAULTS, **stored}
        else:
            self.settings = SETTINGS_DEFAULTS.copy()
        _LOGGER.info("Solakon Einstellungen geladen (Defaults angewendet)")

    async def async_update_settings(self, changes: dict):
        self.settings.update(changes)
        await self._store.async_save(self.settings)
        _LOGGER.info("Solakon Einstellungen gespeichert.")

    def register_entity_listener(self, cb): pass
    def unregister_entity_listener(self, cb): pass
