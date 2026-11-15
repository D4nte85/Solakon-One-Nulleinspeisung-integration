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
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN, PLATFORMS,
    CONF_INSTANCE_NAME,
    CONF_GRID_SENSOR,
    CAPACITY_FIELD, DIST_DEFAULTS, DIST_INST_FIELDS, DIST_SCHEMA, SETTINGS_SCHEMA, VERSION,
)
from . import group_store, number, runtime
from .migrations import SolakonSettingsStore, async_migrate_entry as async_migrate_entry
from .readings import NUMERIC_DOMAINS
from .schema import InvalidSettings
from .status_view import WS_STATUS_KEYS, snapshot_view

_LOGGER = logging.getLogger(__name__)

PANEL_JS_URL = f"/{DOMAIN}/panel.js"

# Keine YAML-Konfiguration; async_setup liefert nur Panel und Übersetzungen aus.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

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
    """WS: alle Instanzen mit Name und Netzsensor, nach Name sortiert."""
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
    vol.Required("type"): f"{DOMAIN}/get_groups",
})
@websocket_api.async_response
async def _ws_get_groups(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """WS: Netzgruppen der geladenen Instanzen mit Netzsensor, Gruppennummer, geladenen Mitgliedern und Zahl der eingerichteten Instanzen."""
    store = group_store.store_for(hass)
    numbers = {} if store is None else store.numbers
    members: dict[str, list[str]] = {}
    for entry_id, coord in hass.data.get(DOMAIN, {}).items():
        members.setdefault(coord.grid_sensor, []).append(entry_id)
    connection.send_result(msg["id"], {"groups": [
        {
            "grid_sensor": grid_sensor,
            "number":      numbers.get(grid_sensor),
            "members":     ids,
            "configured":  group_store.configured_members(hass, grid_sensor),
        }
        for grid_sensor, ids in members.items()
    ]})


@websocket_api.websocket_command({
    vol.Required("type"):     f"{DOMAIN}/get_config",
    vol.Required("entry_id"): str,
})
@websocket_api.async_response
async def _ws_get_config(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """WS: Settings der Instanz `entry_id`."""
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
    """WS: Settings-Änderungen übernehmen und die danach wirksamen Settings liefern; ungültige Werte als Befundliste zurück."""
    if (coord := _coord_or_error(hass, connection, msg)) is None:
        return
    try:
        await coord.async_update_settings(msg["changes"])
    except InvalidSettings as err:
        _send_invalid(connection, msg, err.findings)
        return
    connection.send_result(msg["id"], {"success": True, "settings": dict(coord.settings)})


@websocket_api.websocket_command({
    vol.Required("type"):     f"{DOMAIN}/get_status",
    vol.Required("entry_id"): str,
    vol.Optional("language"): str,
})
@websocket_api.async_response
async def _ws_get_status(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """WS: Zustand der Instanz; mit `language` Aktion und Fehlerkette in dieser Sprache."""
    if (coord := _coord_or_error(hass, connection, msg)) is None:
        return

    connection.send_result(msg["id"], {
        **snapshot_view(coord, WS_STATUS_KEYS),
        **coord.live_values(),
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
    """WS: PI-Integral der Instanz auf 0 setzen."""
    if (coord := _coord_or_error(hass, connection, msg)) is None:
        return
    await coord.async_reset_integral()
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
    """WS: Zyklus setzen, Integral nullen und sofort einen Regelzyklus anstoßen."""
    if (coord := _coord_or_error(hass, connection, msg)) is None:
        return
    await coord.async_set_cycle(msg["active"])
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command({
    vol.Required("type"):        f"{DOMAIN}/get_distribution_config",
    vol.Required("grid_sensor"): str,
})
@websocket_api.async_response
async def _ws_get_distribution_config(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """WS: Verteilungs-Einstellungen der Netzgruppe `grid_sensor`; Defaults ohne Store."""
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
    """WS: geänderte Verteilungsfelder speichern; ungültige Werte als Befundliste zurück."""
    store = _get_or_error(
        connection, msg, group_store.store_for(hass),
        "not_ready", "Distribution-Store nicht initialisiert",
    )
    if store is None:
        return
    try:
        await store.save_dist(msg["grid_sensor"], msg["distribution"])
    except InvalidSettings as err:
        _send_invalid(connection, msg, err.findings)
        return
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/get_schema",
})
@websocket_api.async_response
async def _ws_get_schema(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """WS: Typ, Bereich und Schrittweite aller Settings, der Verteilung und ihrer Felder je Instanz, Domains der Entitätsfelder."""
    connection.send_result(msg["id"], {
        "settings":        {key: field._asdict() for key, field in SETTINGS_SCHEMA.items()},
        "distribution":    {key: field._asdict() for key, field in DIST_SCHEMA.items()},
        "distribution_instance": {CAPACITY_FIELD: DIST_INST_FIELDS[1]._asdict()},
        "numeric_domains": list(NUMERIC_DOMAINS),
    })


# In `async_setup` registrierte WebSocket-Commands.
WS_COMMANDS = (
    _ws_get_all_instances, _ws_get_groups, _ws_get_config, _ws_save_config, _ws_get_status, _ws_get_schema,
    _ws_reset_integral, _ws_set_cycle, _ws_get_distribution_config, _ws_save_distribution_config,
)


# ── Setup / Teardown ─────────────────────────────────────────────────────────

async def _drop_shared_data(hass: HomeAssistant) -> None:
    """Ausstehendes Speichern der Netzgruppen schreiben, Instanzliste und Laufzeitzustand entfernen; nur ohne geladene Instanz aufrufen."""
    if (store := group_store.store_for(hass)) is not None:
        await store.async_write_pending()
    hass.data.pop(DOMAIN, None)
    runtime.drop(hass)


async def _teardown(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Coordinator der Instanz beenden und austragen, Träger abgeben; mit der letzten Instanz Panel und Laufzeitzustand entfernen."""
    from homeassistant.components.frontend import async_remove_panel

    if (coord := hass.data.get(DOMAIN, {}).get(entry.entry_id)) is not None:
        await coord.async_shutdown()
        hass.data[DOMAIN].pop(entry.entry_id)
    if (rt := runtime.peek(hass)) is None:
        return
    if rt.carriers is not None:
        await rt.carriers.release(entry.entry_id, entry.data.get(CONF_GRID_SENSOR, ""))
    if not hass.data.get(DOMAIN):
        if rt.panel_registered:
            async_remove_panel(hass, DOMAIN)
        await _drop_shared_data(hass)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """WebSocket-Commands registrieren, Panel-Skript und Übersetzungsdateien als statische Pfade ausliefern."""
    for handler in WS_COMMANDS:
        websocket_api.async_register_command(hass, handler)
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
    """Gruppenspeicher laden, Coordinator anlegen, Panel einmalig registrieren, Plattformen laden."""
    from .coordinator import SolakonCoordinator

    # Gruppen-Stores vor dem Coordinator laden: seine Trigger lesen globale Sensoren der Verteilung.
    # Kapazitätssensoren folgen dem Netzsensor ihres Eintrags.
    try:
        store = await group_store.async_load(hass)
        await store.tidy_capacity()
        coordinator = SolakonCoordinator(hass, entry)
        await coordinator.async_setup()
    except (HomeAssistantError, OSError) as ex:
        raise ConfigEntryNotReady(f"Solakon: Setup fehlgeschlagen: {ex}") from ex

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Eintrag neu laden wenn die Entitäten-Zuweisung im OptionsFlow geändert wurde
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Panel nur einmal registrieren — kein entry_id in config
    rt = runtime.runtime(hass)
    if not rt.panel_registered:
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
        rt.panel_registered = True

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception as ex:
        await _teardown(hass, entry)
        raise ConfigEntryNotReady(f"Solakon: Platform-Setup fehlgeschlagen: {ex}") from ex

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Plattformen entladen, danach die Instanz beenden; scheitert das Entladen, läuft sie weiter."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await _teardown(hass, entry)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Store der Instanz löschen; mit der letzten Instanz auch die Gruppen-Stores, sonst Kapazitätssensoren nachführen und die Netzgruppe neu zählen."""
    await SolakonSettingsStore(hass, entry.entry_id).async_remove()

    # Home Assistant trägt den Entry vor diesem Aufruf aus der Registrierung aus.
    # Ist danach keiner mehr übrig, werden auch die instanzübergreifenden Stores
    # entfernt; bei weiteren Instanzen bleiben sie bestehen.
    if not hass.config_entries.async_entries(DOMAIN):
        await group_store.async_remove(hass)
        return
    # Läuft keine Instanz mehr (die übrigen sind deaktiviert), ist der Gruppenspeicher
    # schon abgeräumt: für die Träger-Verwaltung laden und danach wieder entfernen.
    await (await group_store.async_load(hass)).tidy_capacity()
    await number.carriers(hass).assign(entry.data.get(CONF_GRID_SENSOR, ""))
    if not hass.data.get(DOMAIN):
        await _drop_shared_data(hass)
