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

# Zusätzliche Regel-Trigger in Registrierungsreihenfolge: Name → Aktivierungsschlüssel,
# ODER-verknüpft. "periodic" ist ein Zeitintervall, alle übrigen lauschen auf den Sensor
# ihrer Vorgabe laut `feature_sensors.FEATURES`.
_KEY_OF_FIELD = dict(CYCLE_SETTINGS)
TRACKERS: dict[str, tuple[str, ...]] = {
    **{name: tuple(_KEY_OF_FIELD[field] for field in fields) for name, fields in sensor_triggers().items()},
    "periodic": (S_PERIODIC_ENABLED,),
}


class Trackers:
    """Angemeldete TRACKERS einer Instanz mit ihren Abmeldefunktionen.

    `settings` liefert die aktuellen Settings, `effective` den wirksamen Sensor einer
    Vorgabe. `on_state` und `on_periodic` sind die Callbacks der Sensor- bzw. Intervall-Trigger.
    """

    def __init__(
        self, hass: HomeAssistant, settings: Callable[[], dict[str, Any]], effective: Callable[[str], str],
        on_state: Callable, on_periodic: Callable,
    ) -> None:
        self._hass = hass
        self._settings = settings
        self._effective = effective
        self._on_state = on_state
        self._on_periodic = on_periodic
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
                self._hass, self._on_periodic, timedelta(seconds=interval)
            )
            return
        sensor = self._effective(name)
        if sensor:
            self._unsubs[name] = async_track_state_change_event(
                self._hass, [sensor], self._on_state
            )

    def start(self) -> None:
        """Alle Trigger in Registrierungsreihenfolge anmelden."""
        for name in TRACKERS:
            self._retrack(name)

    def stop(self) -> None:
        """Alle Trigger abmelden."""
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
        """Sensorgebundene Trigger neu registrieren, etwa nach geänderten globalen Vorgaben."""
        for name in TRACKERS:
            if name != "periodic":
                self._retrack(name)

    def active(self) -> list[str]:
        """Namen der angemeldeten Trigger, sortiert."""
        return sorted(self._unsubs)
