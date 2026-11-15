"""Feature-Sensoren: wirksamer Sensor je Vorgabe, Werte in Zieleinheit, Meldungen ohne Zahl."""
from __future__ import annotations

from typing import Any, NamedTuple

from homeassistant.core import HomeAssistant

from .i18n import Msg
from .readings import (
    NO_SENSOR, NOT_NUMERIC, UNAVAILABLE, UNIT_SCALE_KILO, UNIT_SCALE_KWH, WRONG_DOMAIN,
    Reading, read_scaled,
)
from .schema import CycleSettings
from .const import (
    S_TARIFF_PRICE_SENSOR, S_TARIFF_CHEAP_ENTITY, S_TARIFF_EXP_ENTITY, S_PV_FORECAST_SENSOR,
    S_SURPLUS_LOCK_SENSOR, S_ZONE1_FORCE_SENSOR,
)

# Fehlerschlüssel je Grund ohne Zahl, `{p}` ist das Präfix des Features.
FEATURE_ERRORS = {
    NO_SENSOR: "{p}_no_sensor",
    WRONG_DOMAIN: "{p}_sensor_wrong_domain",
    UNAVAILABLE: "{p}_sensor_unavailable",
    NOT_NUMERIC: "{p}_sensor_not_numeric",
}

# Instanzübergreifend pflegbare Sensor-Vorgaben: (lokaler Settings-Schlüssel, globaler
# Schlüssel der Verteilung). Lokal gewinnt, sonst der globale Wert.
SENSOR_SOURCES = {
    "tariff": (S_TARIFF_PRICE_SENSOR, "global_tariff_price_sensor"),
    "tariff_cheap": (S_TARIFF_CHEAP_ENTITY, "global_tariff_cheap_entity"),
    "tariff_exp": (S_TARIFF_EXP_ENTITY, "global_tariff_exp_entity"),
    "pv_forecast": (S_PV_FORECAST_SENSOR, "global_pv_forecast_today_sensor"),
    "surplus_lock": (S_SURPLUS_LOCK_SENSOR, "global_surplus_lock_sensor"),
    "zone1_force": (S_ZONE1_FORCE_SENSOR, "global_pv_forecast_tomorrow_sensor"),
}

# Ab dieser Stunde liest die Nacht-Forcierung die Prognose für morgen, davor die für heute.
TOMORROW_FROM_HOUR = 12


class Feature(NamedTuple):
    """Sensorgebundener Wert des Regelzyklus.

    `source` ist die Sensorvorgabe in SENSOR_SOURCES, `enabled` das Feld in CycleSettings,
    das den Wert einschaltet. Ohne `optional` Entität wird nicht gelesen und nichts
    gemeldet; nur Werte mit Pflicht-Entität stoßen bei Änderung den Regelzyklus an.
    """

    name: str
    source: str
    enabled: str
    err_prefix: str
    scale: dict[str, float]
    optional: bool


# Alle Funktionen mit Sensor. Der Tarifpreis liest `tariff_price` mit Einheit nach der
# Validierung, die übrigen `feature_values` in Tabellenreihenfolge.
FEATURES = (
    Feature("price", "tariff", "tariff_enabled", "err_tariff", {}, False),
    Feature("cheap", "tariff_cheap", "tariff_enabled", "err_tariff_cheap", {}, True),
    Feature("exp", "tariff_exp", "tariff_enabled", "err_tariff_exp", {}, True),
    Feature("surplus_forecast", "pv_forecast", "surplus_forecast_enabled", "err_surplus_forecast", UNIT_SCALE_KWH, False),
    Feature("surplus_lock", "surplus_lock", "surplus_lock_enabled", "err_exit_lock", UNIT_SCALE_KILO, False),
    Feature("pv_forecast", "pv_forecast", "pv_forecast_enabled", "err_pv_forecast", UNIT_SCALE_KWH, False),
    Feature("zone1_force", "zone1_force", "zone1_force_enabled", "err_zone1_force", UNIT_SCALE_KWH, False),
)
PRICE = FEATURES[0]


def sensor_triggers() -> dict[str, tuple[str, ...]]:
    """Sensorvorgaben mit Trigger und ihre einschaltenden CycleSettings-Felder (ODER), in Tabellenreihenfolge."""
    triggers: dict[str, tuple[str, ...]] = {}
    for feature in FEATURES:
        if not feature.optional:
            triggers[feature.source] = (*triggers.get(feature.source, ()), feature.enabled)
    return triggers


def effective_sensor(name: str, settings: dict[str, Any], dist_cfg: dict[str, Any], hour: int) -> str:
    """Wirksamer Sensor aus SENSOR_SOURCES: lokaler Override, sonst globale Vorgabe aus `dist_cfg`.

    `zone1_force` liest ab TOMORROW_FROM_HOUR die Vorhersage für morgen, davor die für
    heute (`pv_forecast`) — derselbe Zieltag, nur der Sensor wechselt.
    """
    if name == "zone1_force" and hour < TOMORROW_FROM_HOUR:
        name = "pv_forecast"
    local, global_key = SENSOR_SOURCES[name]
    return str(settings[local]) or str(dist_cfg.get(global_key, ""))


def feature_reading(
    hass: HomeAssistant, enabled: bool, sensor: str, err_prefix: str, scale: dict[str, float],
) -> tuple[Reading, Msg | None]:
    """Lesung des Feature-Sensors in der Zieleinheit und Meldung; ohne Wert, wenn das Feature aus ist oder keine Zahl kommt.

    Ohne Zahl ist die Meldung der Fehlerschlüssel des Grundes aus FEATURE_ERRORS.
    """
    if not enabled:
        return Reading(None), None
    reading = read_scaled(hass, sensor, scale)
    if not reading.reason:
        return reading, None
    params = {} if reading.reason == NO_SENSOR else {"sensor": sensor}
    return reading, (FEATURE_ERRORS[reading.reason].format(p=err_prefix), params)


def feature_values(
    hass: HomeAssistant, cs: CycleSettings, settings: dict[str, Any], dist_cfg: dict[str, Any], hour: int,
) -> tuple[dict[str, float | None], list[Msg]]:
    """Alle Werte aus FEATURES außer dem Tarifpreis nach Name und ihre Meldungen, in Tabellenreihenfolge gelesen."""
    values = {}
    warnings = []
    for feature in FEATURES:
        if feature is PRICE:
            continue
        sensor = effective_sensor(feature.source, settings, dist_cfg, hour)
        on = getattr(cs, feature.enabled) and (bool(sensor) or not feature.optional)
        reading, warning = feature_reading(hass, on, sensor, feature.err_prefix, feature.scale)
        values[feature.name] = reading.value
        if warning:
            warnings.append(warning)
    return values, warnings


def tariff_price(hass: HomeAssistant, enabled: bool, sensor: str) -> tuple[float | None, str, Msg | None]:
    """Tarifpreis ohne Einheitenumrechnung, seine Einheit und Meldung; Einheit "" ohne Preis."""
    reading, warning = feature_reading(hass, enabled, sensor, PRICE.err_prefix, PRICE.scale)
    return reading.value, reading.unit, warning
