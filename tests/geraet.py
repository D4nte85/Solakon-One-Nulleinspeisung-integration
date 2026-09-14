"""Entities der offiziellen Geräte-Integration, die die Nulleinspeisung liest und schreibt.

Einzige Quelle der Testumgebung für Einheiten und Attribute der Geräteseite. Werte aus
`solakon-de/solakon-one-homeassistant` (Stand GERAET_VERSION), Belege je Eintrag als
`datei:zeile` im Klon unter `tests/geraet-integration/custom_components/solakon_one/`.
Zur Laufzeit wird der Klon nicht gelesen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tests import harness as h

C = h.const

GERAET_VERSION = "1.7.0"
POLL_SEKUNDEN = 30  # const.py:16 DEFAULT_SCAN_INTERVAL


@dataclass(frozen=True)
class Entity:
    key: str
    domain: str
    id_de: str
    id_en: str
    einheit: str | None = None
    device_class: str | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    mode: str | None = None
    optionen: tuple[str, ...] = ()
    ab_werk_aus: bool = False
    beleg: str = ""
    register: str = ""
    extra: dict = field(default_factory=dict)

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
        "total_pv_power", "sensor", "sensor.solakon_one_pv_leistung", "sensor.solakon_one_pv_power",
        einheit="W", device_class="power", beleg="sensor.py:106", register="const.py:77 i32 scale 1"),
    C.CONF_ACTUAL_SENSOR: Entity(
        "active_power", "sensor", "sensor.solakon_one_leistung", "sensor.solakon_one_active_power",
        einheit="W", device_class="power", beleg="sensor.py:112", register="const.py:90 i32 scale 1"),
    C.CONF_SOC_SENSOR: Entity(
        "battery_soc", "sensor", "sensor.solakon_one_batterie_ladestand", "sensor.solakon_one_battery_state_of_charge",
        einheit="%", device_class="battery", beleg="sensor.py:151", register="const.py:122 i16 scale 1"),
    C.CONF_TIMEOUT_COUNTDOWN: Entity(
        "remote_timeout_countdown", "sensor", "sensor.solakon_one_fernsteuerung_zeituberschreitung",
        "sensor.solakon_one_remote_timeout_countdown",
        einheit="s", device_class="duration", beleg="sensor.py:364", register="const.py:133 u16 scale 1"),
    C.CONF_ACTIVE_POWER: Entity(
        "remote_active_power", "number", "number.solakon_one_fernsteuerung_leistung",
        "number.solakon_one_remote_control_power",
        einheit="W", device_class="power", min=-100000, max=100000, step=100, mode="box",
        beleg="number.py:114", register="const.py:131 i32 scale 1"),
    C.CONF_DISCHARGE_CURRENT: Entity(
        "battery_max_discharge_current", "number", "number.solakon_one_maximaler_entladestrom",
        "number.solakon_one_maximum_discharge_current",
        einheit="A", device_class="current", min=0, max=40, step=1, mode="box", ab_werk_aus=True,
        beleg="number.py:93", register="const.py:124 i16 scale 10"),
    C.CONF_TIMEOUT_SET: Entity(
        "remote_timeout_set", "number", "number.solakon_one_fernsteuerung_zeituberschreitung",
        "number.solakon_one_remote_control_timeout",
        einheit="s", device_class="duration", min=0, max=3600, step=10, mode="box",
        beleg="number.py:134", register="const.py:130 u16 scale 1"),
    C.CONF_EXPORT_LIMIT: Entity(
        "grid_export_power_limit", "number", "number.solakon_one_netz_ausgangsleistungsgrenze",
        "number.solakon_one_grid_export_power_limit",
        einheit="W", device_class="power", min=0, max=1200, step=10, mode="box",
        beleg="number.py:104", register="const.py:95 i32 scale 1"),
    C.CONF_MODE_SELECT: Entity(
        "remote_control_mode", "select", "select.solakon_one_modus_fernsteuern",
        "select.solakon_one_remote_control_mode",
        optionen=("0", "1", "3", "5", "7", "9", "11", "13", "15"), beleg="select.py:57"),
}


def registrieren(hass, data: dict) -> None:
    """Geräte-Entities eines Config-Entrys in der Attrappe anmelden: Standardattribute und Schreibgrenzen."""
    for conf_key, entity in ENTITIES.items():
        eid = data.get(conf_key)
        if eid:
            hass.states.defaults[eid] = entity.attribute()
            hass.geraet[eid] = entity
