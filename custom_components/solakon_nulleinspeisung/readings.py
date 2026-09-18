"""Sensorwerte als Zahl lesen: Wert in der Zieleinheit oder Grund, warum es keinen gibt."""
from __future__ import annotations

from typing import NamedTuple

from homeassistant.core import HomeAssistant

# Domains mit Zahlenzustand; nur sie werden als Zahl gelesen.
NUMERIC_DOMAINS = ("sensor", "input_number", "number")

# Einheitenfaktoren je Zieleinheit, Schlüssel kleingeschrieben.
UNIT_SCALE_W = {"kw": 1000.0}
UNIT_SCALE_KILO = {"kw": 1000.0, "kwh": 1000.0, "mwh": 1_000_000.0}
UNIT_SCALE_KWH = {"wh": 0.001, "mwh": 1000.0}

# Gründe, aus denen eine Entität keine Zahl liefert.
NO_SENSOR = "no_sensor"
WRONG_DOMAIN = "wrong_domain"
UNAVAILABLE = "unavailable"
NOT_NUMERIC = "not_numeric"


class Reading(NamedTuple):
    """Gelesene Zahl mit Einheit; ohne Zahl `value` None und `reason` gesetzt."""

    value: float | None
    unit: str = ""
    reason: str = ""


def valid_state(hass: HomeAssistant, entity_id: str):
    """State der Entity, oder None wenn sie fehlt oder unknown/unavailable ist."""
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable"):
        return None
    return state


def unit_of(state) -> str:
    """`unit_of_measurement` des States, getrimmt und kleingeschrieben; "" ohne State."""
    return str(state.attributes.get("unit_of_measurement") or "").strip().lower() if state else ""


def numeric_domain(entity_id: str) -> bool:
    """True, wenn die Entity zu einer Domain aus NUMERIC_DOMAINS gehört."""
    return entity_id.split(".", 1)[0] in NUMERIC_DOMAINS


def read_number(hass: HomeAssistant, entity_id: str) -> Reading:
    """Zahl mit Einheit lesen, ohne Umrechnung.

    Prüft in dieser Reihenfolge: Entity gesetzt, Domain aus NUMERIC_DOMAINS, verfügbar,
    Zustand per float() lesbar. `on`/`off` und andere Texte sind keine Zahl.
    """
    if not entity_id:
        return Reading(None, reason=NO_SENSOR)
    if not numeric_domain(entity_id):
        return Reading(None, reason=WRONG_DOMAIN)
    state = valid_state(hass, entity_id)
    if state is None:
        return Reading(None, reason=UNAVAILABLE)
    try:
        return Reading(float(state.state), unit_of(state))
    except (ValueError, TypeError):
        return Reading(None, reason=NOT_NUMERIC)


def read_scaled(hass: HomeAssistant, entity_id: str, scale: dict[str, float]) -> Reading:
    """Zahl lesen und mit dem Faktor ihrer Einheit aus `scale` multiplizieren.

    Einheiten ohne Eintrag bleiben unverändert.
    """
    reading = read_number(hass, entity_id)
    if reading.value is None:
        return reading
    return reading._replace(value=reading.value * scale.get(reading.unit, 1.0))
