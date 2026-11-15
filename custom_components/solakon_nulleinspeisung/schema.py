"""Settings-Schicht: Prüfung gegen das Schema, Zyklus-Schnappschuss, SOC-Grenzen, Prüfung gespeicherter Werte."""
from __future__ import annotations

import logging
import re
from collections import namedtuple
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    Field, SETTINGS_SCHEMA, S_AC_ENABLED, S_AC_HYSTERESIS, S_AC_MIN_POWER, S_AC_POWER_LIMIT,
    S_AC_SOC_TARGET, S_DISCHARGE_MAX, S_HARD_LIMIT_Z0, S_HARD_LIMIT_Z1, S_I_FACTOR, S_NIGHT_ENABLED,
    S_NIGHT_HYSTERESIS, S_PI_ENABLED, S_PV_FORECAST_ENABLED, S_PV_FORECAST_THRESHOLD, S_PV_RESERVE,
    S_P_FACTOR, S_REGULATION_ENABLED, S_REST_IN_DISCHARGE, S_SELF_ADJUST, S_SELF_ADJUST_TOL,
    S_STDDEV_TRIM_COUNT, S_STDDEV_WINDOW, S_SURPLUS_ENABLED, S_SURPLUS_FORECAST_ENABLED,
    S_SURPLUS_FORECAST_THRESHOLD, S_SURPLUS_LOCK_ENABLED, S_SURPLUS_LOCK_FACTOR, S_SURPLUS_PV_HYST,
    S_SURPLUS_SOC_HYST, S_SURPLUS_SOC_THRESHOLD, S_TARGET_BATTERY_PRIORITY, S_TARGET_CHARGE_ENABLED,
    S_TARGET_GRID_CHARGE, S_TARGET_GRID_POWER, S_TARGET_SOC, S_TARGET_SOURCE_AC, S_TARGET_SOURCE_TARIFF,
    S_TARIFF_CHEAP_THRESHOLD, S_TARIFF_ENABLED, S_TARIFF_EXP_THRESHOLD, S_TARIFF_POWER,
    S_TARIFF_SOC_HYST, S_TARIFF_SOC_TARGET, S_TOLERANCE, S_WAIT_TIME, S_Z1_NIGHT_ENABLED,
    S_ZONE1_FORCE_ENABLED, S_ZONE1_FORCE_MIN_SOC, S_ZONE1_FORCE_THRESHOLD, S_ZONE1_LIMIT, S_ZONE3_LIMIT,
)
from .dynamic_offset import offset_params
from .i18n import translate

_LOGGER = logging.getLogger(__name__)

# Settings, die der Regelzyklus einmal je Durchlauf liest: (Feld, Schlüssel); Typ aus `Field.kind`.
# Dazu kommt das Feld `offsets` mit den Offset-Parametern je Zone aus DYN_ZONES.
CYCLE_SETTINGS = (
    ("zone1_limit", S_ZONE1_LIMIT),
    ("zone3_limit", S_ZONE3_LIMIT),
    ("hard_limit_z0", S_HARD_LIMIT_Z0),
    ("hard_limit_z1", S_HARD_LIMIT_Z1),
    ("tolerance", S_TOLERANCE),
    ("pi_enabled", S_PI_ENABLED),
    ("p_factor", S_P_FACTOR),
    ("i_factor", S_I_FACTOR),
    ("pv_reserve", S_PV_RESERVE),
    ("discharge_max", S_DISCHARGE_MAX),
    ("surplus_enabled", S_SURPLUS_ENABLED),
    ("surplus_threshold", S_SURPLUS_SOC_THRESHOLD),
    ("surplus_soc_hyst", S_SURPLUS_SOC_HYST),
    ("surplus_pv_hyst", S_SURPLUS_PV_HYST),
    ("ac_enabled", S_AC_ENABLED),
    ("ac_soc_target", S_AC_SOC_TARGET),
    ("ac_power_limit", S_AC_POWER_LIMIT),
    ("ac_hysteresis", S_AC_HYSTERESIS),
    ("ac_min_power", S_AC_MIN_POWER),
    ("tariff_enabled", S_TARIFF_ENABLED),
    ("tariff_cheap", S_TARIFF_CHEAP_THRESHOLD),
    ("tariff_exp", S_TARIFF_EXP_THRESHOLD),
    ("tariff_soc", S_TARIFF_SOC_TARGET),
    ("tariff_soc_hyst", S_TARIFF_SOC_HYST),
    ("tariff_power", S_TARIFF_POWER),
    ("pv_forecast_enabled", S_PV_FORECAST_ENABLED),
    ("pv_forecast_threshold", S_PV_FORECAST_THRESHOLD),
    ("surplus_forecast_enabled", S_SURPLUS_FORECAST_ENABLED),
    ("surplus_forecast_threshold", S_SURPLUS_FORECAST_THRESHOLD),
    ("surplus_lock_enabled", S_SURPLUS_LOCK_ENABLED),
    ("surplus_lock_factor", S_SURPLUS_LOCK_FACTOR),
    ("zone1_force_enabled", S_ZONE1_FORCE_ENABLED),
    ("zone1_force_threshold", S_ZONE1_FORCE_THRESHOLD),
    ("zone1_force_min_soc", S_ZONE1_FORCE_MIN_SOC),
    ("night_enabled", S_NIGHT_ENABLED),
    ("night_hysteresis", S_NIGHT_HYSTERESIS),
    ("target_enabled", S_TARGET_CHARGE_ENABLED),
    ("target_soc", S_TARGET_SOC),
    ("battery_priority", S_TARGET_BATTERY_PRIORITY),
    ("source_ac", S_TARGET_SOURCE_AC),
    ("source_tariff", S_TARGET_SOURCE_TARIFF),
    ("grid_charge_enabled", S_TARGET_GRID_CHARGE),
    ("grid_charge_power", S_TARGET_GRID_POWER),
    ("rest_in_discharge", S_REST_IN_DISCHARGE),
    ("z1_night_enabled", S_Z1_NIGHT_ENABLED),
    ("stddev_window", S_STDDEV_WINDOW),
    ("stddev_trim", S_STDDEV_TRIM_COUNT),
    ("wait_time", S_WAIT_TIME),
    ("self_adjust", S_SELF_ADJUST),
    ("self_adjust_tol", S_SELF_ADJUST_TOL),
)
CycleSettings = namedtuple("CycleSettings", [*(field for field, _ in CYCLE_SETTINGS), "offsets"])

# Typ eines Settings je `Field.kind`.
CASTS = {"int": int, "float": float, "bool": bool, "str": str}

# Schlüsselmuster mit dem Feld, das für jeden passenden Schlüssel gilt.
Extra = tuple[re.Pattern, Field] | None


def cycle_settings(settings: dict[str, Any]) -> CycleSettings:
    """Schnappschuss aller CYCLE_SETTINGS und der Offset-Parameter aus `settings` für einen Regelzyklus."""
    return CycleSettings(
        *(CASTS[SETTINGS_SCHEMA[key].kind](settings[key]) for _, key in CYCLE_SETTINGS),
        offsets=offset_params(settings),
    )


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


def couple_target(settings: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """`changes` mit der Kopplung von Zielladen und Regelung, einmal aus dem alten Stand gerechnet.

    Zielladen an → Regelung an. Zielladen aus → Regelung an, Netz-Laden aus.
    Regelung an bei Zielladen an und Regelung aus → Zielladen aus, Netz-Laden aus.
    """
    target_old = bool(settings[S_TARGET_CHARGE_ENABLED])
    regulation_old = bool(settings[S_REGULATION_ENABLED])
    target_new = bool(changes.get(S_TARGET_CHARGE_ENABLED, target_old))
    regulation_new = bool(changes.get(S_REGULATION_ENABLED, regulation_old))
    coupled = dict(changes)
    if target_new and not target_old:
        coupled[S_REGULATION_ENABLED] = True
    elif target_old and not target_new:
        coupled[S_REGULATION_ENABLED] = True
        coupled[S_TARGET_GRID_CHARGE] = False
    elif target_old and regulation_new and not regulation_old:
        coupled[S_TARGET_CHARGE_ENABLED] = False
        coupled[S_TARGET_GRID_CHARGE] = False
    return coupled

class InvalidSettings(HomeAssistantError):
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
