"""Coordinator — all zone/PI/offset logic + settings management."""
from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN, STORAGE_VERSION, SETTINGS_DEFAULTS,
    CONF_GRID_SENSOR, CONF_ACTUAL_SENSOR, CONF_SOLAR_SENSOR,
    CONF_SOC_SENSOR, CONF_TIMEOUT_COUNTDOWN, CONF_ACTIVE_POWER,
    CONF_DISCHARGE_CURRENT, CONF_TIMEOUT_SET, CONF_MODE_SELECT,
    S_P_FACTOR, S_I_FACTOR, S_TOLERANCE, S_WAIT_TIME, S_STDDEV_WINDOW,
    S_ZONE1_LIMIT, S_ZONE3_LIMIT, S_DISCHARGE_MAX,
    S_OFFSET_1, S_OFFSET_2, S_PV_RESERVE, S_HARD_LIMIT,
    S_SURPLUS_ENABLED, S_SURPLUS_SOC_THRESHOLD, S_SURPLUS_SOC_HYST, S_SURPLUS_PV_HYST,
    S_AC_ENABLED, S_AC_SOC_TARGET, S_AC_POWER_LIMIT, S_AC_HYSTERESIS,
    S_AC_OFFSET, S_AC_P_FACTOR, S_AC_I_FACTOR,
    S_TARIFF_ENABLED, S_TARIFF_PRICE_SENSOR, S_TARIFF_CHEAP_THRESHOLD,
    S_TARIFF_EXP_THRESHOLD, S_TARIFF_SOC_TARGET, S_TARIFF_POWER,
    S_NIGHT_ENABLED
)

_LOGGER = logging.getLogger(__name__)


class SolakonCoordinator:
    def __init__(self, hass: HomeAssistant, entry_id: str, config: dict) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.config = config

        self.settings: dict[str, Any] = dict(SETTINGS_DEFAULTS)
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_settings")

        # Live State
        self.current_zone = 3
        self.mode_label = "Initialisiere..."
        self.last_action = "Warte auf ersten Durchlauf..."
        self.grid_stddev = 0.0
        self.integral = 0.0

        self._grid_buffer: list[tuple[float, float]] = []
        self._last_run = 0.0
        self._run_task: asyncio.Task | None = None

    async def async_setup(self) -> None:
        """Lädt gespeicherte Einstellungen und startet den Regel-Loop."""
        stored = await self._store.async_load()
        if stored:
            self.settings.update(stored)

        grid_sensor = self.config.get(CONF_GRID_SENSOR)
        if grid_sensor:
            async_track_state_change_event(self.hass, [grid_sensor], self._on_grid_change)

        self._run_task = asyncio.create_task(self._main_loop())

    async def async_unload(self) -> None:
        """Stoppt den Coordinator."""
        if self._run_task:
            self._run_task.cancel()
            try:
                await self._run_task
            except asyncio.CancelledError:
                pass

    async def save_settings(self, changes: dict[str, Any]) -> None:
        """Sichert veränderte Einstellungen im Store."""
        self.settings.update(changes)
        await self._store.async_save(self.settings)

    @callback
    def _on_grid_change(self, event) -> None:
        """Wird aufgerufen, sobald der Grid-Sensor neue Daten liefert."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            return
        try:
            val = float(new_state.state)
            self._push_grid_value(val)
        except ValueError:
            pass

    def _push_grid_value(self, value: float) -> None:
        """Fügt einen neuen Messwert hinzu und berechnet die Standardabweichung."""
        now = time.monotonic()
        window = float(self.settings.get(S_STDDEV_WINDOW, 60))

        self._grid_buffer.append((now, value))

        # Veraltete Einträge entfernen
        cutoff = now - window
        self._grid_buffer = [(t, v) for t, v in self._grid_buffer if t >= cutoff]

        # Standardabweichung berechnen
        if len(self._grid_buffer) >= 2:
            vals = [v for _, v in self._grid_buffer]
            mean = sum(vals) / len(vals)
            variance = sum((v - mean) ** 2 for v in vals) / len(vals)
            self.grid_stddev = round(math.sqrt(variance), 1)
        else:
            self.grid_stddev = 0.0

    async def _main_loop(self) -> None:
        """Der Haupttaktgeber der PI-Regelung."""
        while True:
            try:
                wait_time = float(self.settings.get(S_WAIT_TIME, 3))
                await asyncio.sleep(wait_time)
                await self._process_iteration()
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error("Fehler im Hauptloop: %s", e, exc_info=True)

    def _get_dynamic_offset(self, prefix: str) -> float:
        """Berechnet den dynamischen Offset basierend auf der internen Standardabweichung."""
        enabled = self.settings.get(f"dyn_offset_{prefix}_enabled", False)
        if not enabled:
            return 0.0

        stddev = self.grid_stddev
        noise_floor = float(self.settings.get(f"dyn_offset_{prefix}_noise_floor", 0.0))
        
        # Falls die StdDev unter der Rausch-Schwelle liegt, ist der Offset 0
        if stddev < noise_floor:
            return 0.0

        factor = float(self.settings.get(f"dyn_offset_{prefix}_factor", 1.0))
        min_offset = float(self.settings.get(f"dyn_offset_{prefix}_min", 0.0))
        max_offset = float(self.settings.get(f"dyn_offset_{prefix}_max", 1000.0))

        calc_val = stddev * factor
        out_val = max(min_offset, min(calc_val, max_offset))

        negative = self.settings.get(f"dyn_offset_{prefix}_negative", False)
        return -out_val if negative else out_val

    async def _process_iteration(self) -> None:
        """Wichtigste Methode: Liest Daten, bestimmt Zone und regelt die AC-Leistung."""
        grid = self._flt(self.config.get(CONF_GRID_SENSOR), 0.0)
        actual = self._flt(self.config.get(CONF_ACTUAL_SENSOR), 0.0)
        solar = self._flt(self.config.get(CONF_SOLAR_SENSOR), 0.0)
        soc = self._flt(self.config.get(CONF_SOC_SENSOR), 0.0)

        p_factor = float(self.settings.get(S_P_FACTOR, 1.3))
        i_factor = float(self.settings.get(S_I_FACTOR, 0.02))
        tolerance = float(self.settings.get(S_TOLERANCE, 15))

        # Zonenberechnung
        zone1_limit = float(self.settings.get(S_ZONE1_LIMIT, 20))
        zone3_limit = float(self.settings.get(S_ZONE3_LIMIT, 10))

        # Dynamische Offsets ermitteln
        dyn_1 = self._get_dynamic_offset("1")
        dyn_2 = self._get_dynamic_offset("2")
        dyn_ac = self._get_dynamic_offset("ac")

        if soc >= zone1_limit:
            self.current_zone = 1
            self.mode_label = "Zone 1 — Aggressive Entladung"
            offset = float(self.settings.get(S_OFFSET_1, 30)) + dyn_1
        elif soc > zone3_limit:
            self.current_zone = 2
            self.mode_label = "Zone 2 — Batterieschonend"
            offset = float(self.settings.get(S_OFFSET_2, 10)) + dyn_2
        else:
            self.current_zone = 3
            self.mode_label = "Zone 3 — Sicherheitsstopp"
            offset = 0.0

        # PI-Fehlerberechnung
        error = grid - offset

        # Integral-Windup und Decay bei kleiner Abweichung
        if abs(error) <= tolerance:
            self.integral *= 0.95
        else:
            self.integral += error
            self.integral = max(-1000.0, min(1000.0, self.integral))

        # Stellgröße
        output = actual + (error * p_factor) + (self.integral * i_factor)

        # Harte Limits anwenden
        hard_limit = float(self.settings.get(S_HARD_LIMIT, 800))
        if output > hard_limit:
            output = hard_limit
        if output < 0:
            output = 0

        # Wenn Zone 3 aktiv ist, wird kein Strom entnommen
        if self.current_zone == 3:
            output = 0
            self.integral = 0.0

        # Hier würde nun der Serviceaufruf an das `number`-Feld des Wechselrichters erfolgen
        # (z.B. self.hass.services.async_call('number', 'set_value', ...))
        self.last_action = f"Geregelt auf {round(output)} W (P={round(error*p_factor)}, I={round(self.integral*i_factor)})"

    def _flt(self, entity_id: str | None, default: float = 0.0) -> float:
        """Holt einen Float-Wert sicher aus einem HA State."""
        if not entity_id:
            return default
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return default
        try:
            return float(state.state)
        except ValueError:
            return default
