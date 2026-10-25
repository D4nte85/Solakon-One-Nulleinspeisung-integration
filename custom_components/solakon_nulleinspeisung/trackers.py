"""Zusätzliche Regel-Trigger einer Instanz: an- und abmelden nach Settings und wirksamem Sensor."""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .const import (
    S_PERIODIC_ENABLED, S_PERIODIC_INTERVAL, S_PV_FORECAST_ENABLED, S_SURPLUS_FORECAST_ENABLED,
    S_SURPLUS_LOCK_ENABLED, S_TARIFF_ENABLED, S_ZONE1_FORCE_ENABLED,
)

# Zusätzliche Regel-Trigger in Registrierungsreihenfolge: (Name, Aktivierungsschlüssel,
# ODER-verknüpft). "periodic" ist ein Zeitintervall, alle übrigen lauschen auf ihren Sensor.
TRACKERS = (
    ("tariff", (S_TARIFF_ENABLED,)),
    ("periodic", (S_PERIODIC_ENABLED,)),
    ("pv_forecast", (S_PV_FORECAST_ENABLED, S_SURPLUS_FORECAST_ENABLED)),
    ("surplus_lock", (S_SURPLUS_LOCK_ENABLED,)),
    ("zone1_force", (S_ZONE1_FORCE_ENABLED,)),
)


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

    def _input(self, name: str) -> tuple:
        """Eingaben eines Triggers: Aktivierungswerte und Sensor bzw. Intervall."""
        settings = self._settings()
        keys = dict(TRACKERS)[name]
        target = settings[S_PERIODIC_INTERVAL] if name == "periodic" else self._effective(name)
        return tuple(settings[k] for k in keys), target

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
        settings = self._settings()
        if not any(settings[k] for k in dict(TRACKERS)[name]):
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
        for name, _ in TRACKERS:
            self._retrack(name)

    def stop(self) -> None:
        """Alle Trigger abmelden."""
        for name, _ in TRACKERS:
            self._untrack(name)

    def inputs(self) -> dict[str, tuple]:
        """Eingaben aller Trigger nach Name, als Vergleichsstand für `refresh`."""
        return {name: self._input(name) for name, _ in TRACKERS}

    def refresh(self, before: dict[str, tuple]) -> None:
        """Trigger neu anmelden, deren Eingaben sich gegenüber `before` geändert haben."""
        for name, _ in TRACKERS:
            if self._input(name) != before[name]:
                self._retrack(name)

    def refresh_sensors(self) -> None:
        """Sensorgebundene Trigger neu registrieren, etwa nach geänderten globalen Vorgaben."""
        for name, _ in TRACKERS:
            if name != "periodic":
                self._retrack(name)

    def active(self) -> list[str]:
        """Namen der angemeldeten Trigger, sortiert."""
        return sorted(self._unsubs)
