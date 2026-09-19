"""Prüfung von Settings gegen ihr Schema: beim Speichern abweisen, beim Laden zurücksetzen."""
from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant

from .const import Field
from .i18n import translate

_LOGGER = logging.getLogger(__name__)

# Schlüsselmuster mit dem Feld, das für jeden passenden Schlüssel gilt.
Extra = tuple[re.Pattern, Field] | None


class InvalidSettings(Exception):
    """Änderungen verletzen das Schema; `findings` nennt je Schlüssel den Grund."""

    def __init__(self, findings: list[dict]) -> None:
        super().__init__(findings)
        self.findings = findings


def _field(key: str, schema: dict[str, Field], extra: Extra) -> Field | None:
    """Feld zu `key`, bei Musterschlüsseln das Feld des Musters."""
    field = schema.get(key)
    if field is None and extra and extra[0].fullmatch(key):
        field = extra[1]
    return field


def _reason(value: Any, field: Field) -> str | None:
    """Grund, aus dem `value` nicht zu `field` passt, sonst None."""
    if field.kind == "bool":
        return None if isinstance(value, bool) else "type"
    if field.kind == "str":
        return None if isinstance(value, str) else "type"
    if field.kind == "enum":
        return None if value in field.choices else "type"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "type"
    if field.kind == "int" and not float(value).is_integer():
        return "integer"
    if (field.min is not None and value < field.min) or (field.max is not None and value > field.max):
        return "range"
    return None


def check(
    values: dict[str, Any], schema: dict[str, Field], extra: Extra = None,
) -> list[dict]:
    """Befunde `{key, reason, min, max}` zu `values`; leer, wenn alles gültig ist."""
    findings = []
    for key, value in values.items():
        field = _field(key, schema, extra)
        reason = "unknown" if field is None else _reason(value, field)
        if reason:
            findings.append({
                "key": key, "reason": reason,
                "min": field.min if field else None, "max": field.max if field else None,
            })
    return findings


def sanitize(
    stored: dict[str, Any], schema: dict[str, Field], extra: Extra = None,
) -> tuple[dict[str, Any], list[tuple[str, Any, Any]]]:
    """Ungültige Werte durch den Standard ersetzen; zurück kommen Ergebnis und `(key, alt, neu)`.

    Kommazahlen in Ganzzahlfeldern werden still abgeschnitten, wie der Zyklus sie
    liest. Unbekannte Schlüssel bleiben, damit Migrationen und fremde Einträge im
    Store nicht verloren gehen.
    """
    clean = dict(stored)
    reset = []
    for finding in check(stored, schema, extra):
        key, reason = finding["key"], finding["reason"]
        if reason == "integer":
            clean[key] = int(stored[key])
            if not check({key: clean[key]}, schema, extra):
                continue
        if reason == "unknown":
            continue
        clean[key] = _field(key, schema, extra).default
        reset.append((key, stored[key], clean[key]))
    return clean, reset


def notify_reset(
    hass: HomeAssistant, notification_id: str, scope: str,
    reset: list[tuple[str, Any, Any]],
) -> None:
    """Zurückgesetzte Werte als Log-Warnung und HA-Benachrichtigung in der Instanzsprache melden."""
    items = ", ".join(f"{key} ({old!r} → {new!r})" for key, old, new in reset)
    _LOGGER.warning("Solakon: ungültige gespeicherte Werte zurückgesetzt (%s): %s", scope, items)
    language = hass.config.language
    persistent_notification.async_create(
        hass,
        translate(language, "settings_reset_body", items=items),
        title=translate(language, "settings_reset_title", scope=scope),
        notification_id=notification_id,
    )
