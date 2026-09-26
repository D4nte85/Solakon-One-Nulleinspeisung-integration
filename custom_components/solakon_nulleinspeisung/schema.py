"""Settings-Schicht: Prüfung gegen das Schema, Zyklus-Schnappschuss, SOC-Grenzen, Speicher mit Migration."""
from __future__ import annotations

import logging
import re
from collections import namedtuple
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    Field,
    S_AC_ENABLED, S_AC_HYSTERESIS, S_AC_MIN_POWER, S_AC_POWER_LIMIT, S_AC_SOC_TARGET,
    S_DISCHARGE_MAX, S_HARD_LIMIT_Z0, S_HARD_LIMIT_Z1, S_I_FACTOR, S_NIGHT_ENABLED,
    S_NIGHT_HYSTERESIS, S_PV_FORECAST_ENABLED, S_PV_FORECAST_SENSOR, S_PV_FORECAST_THRESHOLD,
    S_PV_RESERVE, S_P_FACTOR, S_SURPLUS_ENABLED, S_SURPLUS_FORECAST_ENABLED,
    S_SURPLUS_FORECAST_THRESHOLD, S_SURPLUS_LOCK_ENABLED, S_SURPLUS_LOCK_FACTOR, S_SURPLUS_PV_HYST,
    S_SURPLUS_SOC_HYST, S_SURPLUS_SOC_THRESHOLD, S_TARIFF_CHEAP_THRESHOLD, S_TARIFF_ENABLED,
    S_TARIFF_EXP_THRESHOLD, S_TARIFF_POWER, S_TARIFF_SOC_HYST, S_TARIFF_SOC_TARGET, S_TOLERANCE,
    S_ZONE1_FORCE_ENABLED, S_ZONE1_FORCE_MIN_SOC, S_ZONE1_FORCE_THRESHOLD, S_ZONE1_LIMIT,
    S_ZONE3_LIMIT,
)
from .i18n import translate

_LOGGER = logging.getLogger(__name__)

# Settings, die der Regelzyklus einmal je Durchlauf liest: (Feld, Schlüssel, Typ).
CYCLE_SETTINGS = (
    ("zone1_limit", S_ZONE1_LIMIT, int),
    ("zone3_limit", S_ZONE3_LIMIT, int),
    ("hard_limit_z0", S_HARD_LIMIT_Z0, int),
    ("hard_limit_z1", S_HARD_LIMIT_Z1, int),
    ("tolerance", S_TOLERANCE, int),
    ("p_factor", S_P_FACTOR, float),
    ("i_factor", S_I_FACTOR, float),
    ("pv_reserve", S_PV_RESERVE, int),
    ("discharge_max", S_DISCHARGE_MAX, int),
    ("surplus_enabled", S_SURPLUS_ENABLED, bool),
    ("surplus_threshold", S_SURPLUS_SOC_THRESHOLD, int),
    ("surplus_soc_hyst", S_SURPLUS_SOC_HYST, int),
    ("surplus_pv_hyst", S_SURPLUS_PV_HYST, int),
    ("ac_enabled", S_AC_ENABLED, bool),
    ("ac_soc_target", S_AC_SOC_TARGET, int),
    ("ac_power_limit", S_AC_POWER_LIMIT, int),
    ("ac_hysteresis", S_AC_HYSTERESIS, int),
    ("ac_min_power", S_AC_MIN_POWER, int),
    ("tariff_enabled", S_TARIFF_ENABLED, bool),
    ("tariff_cheap", S_TARIFF_CHEAP_THRESHOLD, float),
    ("tariff_exp", S_TARIFF_EXP_THRESHOLD, float),
    ("tariff_soc", S_TARIFF_SOC_TARGET, int),
    ("tariff_soc_hyst", S_TARIFF_SOC_HYST, int),
    ("tariff_power", S_TARIFF_POWER, int),
    ("pv_forecast_enabled", S_PV_FORECAST_ENABLED, bool),
    ("pv_forecast_threshold", S_PV_FORECAST_THRESHOLD, float),
    ("surplus_forecast_enabled", S_SURPLUS_FORECAST_ENABLED, bool),
    ("surplus_forecast_threshold", S_SURPLUS_FORECAST_THRESHOLD, float),
    ("surplus_lock_enabled", S_SURPLUS_LOCK_ENABLED, bool),
    ("surplus_lock_factor", S_SURPLUS_LOCK_FACTOR, float),
    ("zone1_force_enabled", S_ZONE1_FORCE_ENABLED, bool),
    ("zone1_force_threshold", S_ZONE1_FORCE_THRESHOLD, float),
    ("zone1_force_min_soc", S_ZONE1_FORCE_MIN_SOC, int),
    ("night_enabled", S_NIGHT_ENABLED, bool),
    ("night_hysteresis", S_NIGHT_HYSTERESIS, int),
)
CycleSettings = namedtuple("CycleSettings", [field for field, _, _ in CYCLE_SETTINGS])

# Schlüsselmuster mit dem Feld, das für jeden passenden Schlüssel gilt.
Extra = tuple[re.Pattern, Field] | None


def cycle_settings(settings: dict[str, Any]) -> CycleSettings:
    """Schnappschuss aller CYCLE_SETTINGS aus `settings` für einen Regelzyklus."""
    return CycleSettings(*(cast(settings[key]) for _, key, cast in CYCLE_SETTINGS))


def soc_conflict(cs: CycleSettings) -> str | None:
    """Fehlerschlüssel der ersten verletzten SOC-Grenzregel, sonst None.

    Zone 1 über Zone 3, Surplus-Schwelle über Zone 1, Mindest-SOC der Zone-1-Forcierung
    zwischen Zone 3 und Zone 1.
    """
    if cs.zone1_limit <= cs.zone3_limit:
        return "err_soc_zone1_zone3"
    if cs.surplus_enabled and cs.surplus_threshold <= cs.zone1_limit:
        return "err_soc_surplus_zone1"
    if cs.zone1_force_enabled and not (cs.zone3_limit < cs.zone1_force_min_soc < cs.zone1_limit):
        return "err_soc_zone1_force"
    return None

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


class SolakonSettingsStore(Store):
    """Settings-Store mit Schemamigration."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict
    ) -> dict:
        """Hebt Version 1 auf 2: Hard-Limit aufgespalten, Forecast-Sensor umbenannt."""
        if old_major_version < 2:
            old_limit = old_data.pop("hard_limit", 800)
            old_data.setdefault(S_HARD_LIMIT_Z0, old_limit)
            old_data.setdefault(S_HARD_LIMIT_Z1, old_limit)

            old_forecast = old_data.pop("surplus_forecast_sensor", "")
            if old_forecast and not old_data.get(S_PV_FORECAST_SENSOR):
                old_data[S_PV_FORECAST_SENSOR] = old_forecast
        return old_data
