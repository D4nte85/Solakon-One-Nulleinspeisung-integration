"""Zusätzliche Regel-Trigger einer Instanz: an- und abmelden nach Settings und wirksamem Sensor."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Callable, Iterator

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .const import S_PERIODIC_ENABLED, S_PERIODIC_INTERVAL
from .feature_sensors import sensor_triggers
from .schema import CYCLE_SETTINGS

# Trigger der Kernsensoren; immer an, vor TRACKERS angemeldet.
CORE = "core"

# Zusätzliche Regel-Trigger in Registrierungsreihenfolge: Name → Aktivierungsschlüssel,
# ODER-verknüpft. "periodic" ist ein Zeitintervall, alle übrigen lauschen auf den Sensor
# ihrer Vorgabe laut `feature_sensors.FEATURES`.
_KEY_OF_FIELD = dict(CYCLE_SETTINGS)
TRACKERS: dict[str, tuple[str, ...]] = {
    **{name: tuple(_KEY_OF_FIELD[field] for field in fields) for name, fields in sensor_triggers().items()},
    "periodic": (S_PERIODIC_ENABLED,),
}


class Trackers:
    """Angemeldete Trigger einer Instanz mit ihren Abmeldefunktionen: CORE und TRACKERS.

    `settings` liefert die aktuellen Settings, `effective` den wirksamen Sensor einer
    Vorgabe, `core` die Kernsensoren, die einen Regelzyklus auslösen. `on_trigger` ist der
    Callback aller Trigger.
    """

    def __init__(
        self, hass: HomeAssistant, settings: Callable[[], dict[str, Any]], effective: Callable[[str], str],
        on_trigger: Callable, core: Callable[[], list[str]],
    ) -> None:
        self._hass = hass
        self._settings = settings
        self._effective = effective
        self._on_trigger = on_trigger
        self._core = core
        # Abmeldefunktionen nach Name
        self._unsubs: dict[str, Callable] = {}
        # Eingaben je Trigger beim letzten Anmelden oder Prüfen
        self._inputs: dict[str, tuple] = {}

    def _input(self, name: str) -> tuple:
        """Eingaben eines Triggers: Aktivierungswerte und Sensor bzw. Intervall; ausgeschaltet ohne Ziel."""
        settings = self._settings()
        enables = tuple(settings[k] for k in TRACKERS[name])
        if not any(enables):
            return enables, None
        return enables, settings[S_PERIODIC_INTERVAL] if name == "periodic" else self._effective(name)

    def _untrack(self, name: str) -> None:
        """Trigger `name` abmelden, falls registriert."""
        unsub = self._unsubs.pop(name, None)
        if unsub:
            unsub()

    def _retrack(self, name: str) -> None:
        """Trigger `name` abmelden und neu registrieren, wenn aktiviert und Sensor gesetzt.

        Der periodische Trigger läuft im Intervall S_PERIODIC_INTERVAL, mindestens 5 s.
        """
        self._untrack(name)
        self._inputs[name] = self._input(name)
        settings = self._settings()
        if not any(settings[k] for k in TRACKERS[name]):
            return
        if name == "periodic":
            interval = max(5, int(settings[S_PERIODIC_INTERVAL]))
            self._unsubs[name] = async_track_time_interval(
                self._hass, self._on_trigger, timedelta(seconds=interval)
            )
            return
        sensor = self._effective(name)
        if sensor:
            self._unsubs[name] = async_track_state_change_event(
                self._hass, [sensor], self._on_trigger
            )

    def start(self) -> None:
        """Kern-Trigger, dann alle TRACKERS in Registrierungsreihenfolge anmelden."""
        core = [e for e in self._core() if e]
        if core:
            self._unsubs[CORE] = async_track_state_change_event(self._hass, core, self._on_trigger)
        for name in TRACKERS:
            self._retrack(name)

    def stop(self) -> None:
        """Alle Trigger abmelden, den Kern-Trigger zuerst."""
        self._untrack(CORE)
        for name in TRACKERS:
            self._untrack(name)
        self._inputs.clear()

    @contextmanager
    def refreshing(self) -> Iterator[None]:
        """Rahmen um eine Settings-Änderung: danach die Trigger neu anmelden, deren Eingaben sich darin geändert haben."""
        before = {name: self._input(name) for name in TRACKERS}
        yield
        for name in TRACKERS:
            if self._input(name) != before[name]:
                self._retrack(name)

    def refresh_changed(self) -> None:
        """Angemeldete Trigger neu anmelden, deren Eingaben sich seit dem Anmelden geändert haben.

        Fängt den Wechsel des wirksamen Sensors ohne Settings-Änderung, etwa der
        Nacht-Forcierung um TOMORROW_FROM_HOUR.
        """
        for name, before in list(self._inputs.items()):
            if self._input(name) != before:
                self._retrack(name)

    def refresh_sensors(self) -> None:
        """Sensorgebundene TRACKERS neu registrieren, etwa nach geänderten globalen Vorgaben; CORE bleibt."""
        for name in TRACKERS:
            if name != "periodic":
                self._retrack(name)

    def active(self) -> list[str]:
        """Namen der angemeldeten Trigger, sortiert."""
        return sorted(self._unsubs)
