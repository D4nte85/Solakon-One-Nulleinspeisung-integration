"""Entities der offiziellen Geräte-Integration, die die Nulleinspeisung liest und schreibt.

Einzige Quelle der Testumgebung für Einheiten und Attribute der Geräteseite. Werte aus
`solakon-de/solakon-one-homeassistant` (Stand GERAET_VERSION), nachlesbar im Klon unter
`tests/geraet-integration/custom_components/solakon_one/` (`sensor.py`, `number.py`, `select.py`).
Zur Laufzeit wird der Klon nicht gelesen. Die Entladegrenze 800 W aus 1.8.0 (Upstream #302,
`power_limit.py`) ist bewusst nicht nachgebildet, wie im Fork `anpassungen`, der sie zurücknimmt.
"""
from __future__ import annotations

from dataclasses import dataclass

from tests import harness as h

C = h.const

GERAET_VERSION = "1.7.0"


@dataclass(frozen=True)
class Entity:
    key: str
    domain: str
    einheit: str | None = None
    device_class: str | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    mode: str | None = None
    optionen: tuple[str, ...] = ()

    def attribute(self) -> dict:
        """Zustandsattribute, wie HA sie für diese Entity setzt."""
        attrs: dict = {}
        if self.domain == "number":
            attrs.update(min=self.min, max=self.max, step=self.step, mode=self.mode)
        if self.domain == "select":
            attrs["options"] = list(self.optionen)
        if self.einheit:
            attrs["unit_of_measurement"] = self.einheit
        if self.device_class:
            attrs["device_class"] = self.device_class
        return attrs


ENTITIES: dict[str, Entity] = {
    C.CONF_SOLAR_SENSOR: Entity(
        "total_pv_power", "sensor",
        einheit="W", device_class="power"),
    C.CONF_ACTUAL_SENSOR: Entity(
        "active_power", "sensor",
        einheit="W", device_class="power"),
    C.CONF_SOC_SENSOR: Entity(
        "battery_soc", "sensor",
        einheit="%", device_class="battery"),
    C.CONF_TIMEOUT_COUNTDOWN: Entity(
        "remote_timeout_countdown", "sensor",
        einheit="s", device_class="duration"),
    C.CONF_ACTIVE_POWER: Entity(
        "remote_active_power", "number",
        einheit="W", device_class="power", min=-100000, max=100000, step=100, mode="box"),
    C.CONF_DISCHARGE_CURRENT: Entity(
        "battery_max_discharge_current", "number",
        einheit="A", device_class="current", min=0, max=40, step=1, mode="box"),
    C.CONF_TIMEOUT_SET: Entity(
        "remote_timeout_set", "number",
        einheit="s", device_class="duration", min=0, max=3600, step=10, mode="box"),
    C.CONF_EXPORT_LIMIT: Entity(
        "grid_export_power_limit", "number",
        einheit="W", device_class="power", min=0, max=1200, step=10, mode="box"),
    C.CONF_MODE_SELECT: Entity(
        "remote_control_mode", "select",
        optionen=("0", "1", "3", "5", "7", "9", "11", "13", "15")),
}


def registrieren(hass, data: dict) -> None:
    """Geräte-Entities eines Config-Entrys in der Attrappe anmelden: Standardattribute und Schreibgrenzen."""
    for conf_key, entity in ENTITIES.items():
        eid = data.get(conf_key)
        if eid:
            hass.states.defaults[eid] = entity.attribute()
            hass.geraet[eid] = entity
