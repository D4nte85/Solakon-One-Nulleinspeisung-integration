"""Coordinator — all zone/PI/offset logic + settings management."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN, STORAGE_VERSION, SETTINGS_DEFAULTS,
    CONF_GRID_SENSOR, CONF_ACTUAL_SENSOR, CONF_SOLAR_SENSOR,
    CONF_SOC_SENSOR, CONF_TIMEOUT_COUNTDOWN, CONF_ACTIVE_POWER,
    CONF_DISCHARGE_CURRENT, CONF_TIMEOUT_SET, CONF_MODE_SELECT,
    S_P_FACTOR, S_I_FACTOR, S_TOLERANCE, S_WAIT_TIME,
    S_ZONE1_LIMIT, S_ZONE3_LIMIT, S_DISCHARGE_MAX,
    S_OFFSET_1, S_OFFSET_2, S_PV_RESERVE, S_HARD_LIMIT,
    S_DYN_OFFSET_1_ENABLED, S_DYN_OFFSET_1_SENSOR, S_DYN_OFFSET_1_MIN,
    S_DYN_OFFSET_1_MAX, S_DYN_OFFSET_1_NOISE, S_DYN_OFFSET_1_FACTOR, S_DYN_OFFSET_1_NEGATIVE,
    S_DYN_OFFSET_2_ENABLED, S_DYN_OFFSET_2_SENSOR, S_DYN_OFFSET_2_MIN,
    S_DYN_OFFSET_2_MAX, S_DYN_OFFSET_2_NOISE, S_DYN_OFFSET_2_FACTOR, S_DYN_OFFSET_2_NEGATIVE,
    S_SURPLUS_ENABLED, S_SURPLUS_SOC_THRESHOLD, S_SURPLUS_SOC_HYST, S_SURPLUS_PV_HYST,
    S_AC_ENABLED, S_AC_SOC_TARGET, S_AC_POWER_LIMIT, S_AC_HYSTERESIS,
    S_AC_OFFSET, S_AC_P_FACTOR, S_AC_I_FACTOR,
    S_DYN_OFFSET_AC_ENABLED, S_DYN_OFFSET_AC_SENSOR, S_DYN_OFFSET_AC_MIN,
    S_DYN_OFFSET_AC_MAX, S_DYN_OFFSET_AC_NOISE, S_DYN_OFFSET_AC_FACTOR, S_DYN_OFFSET_AC_NEGATIVE,
    S_TARIFF_ENABLED, S_TARIFF_PRICE_SENSOR, S_TARIFF_CHEAP_THRESHOLD,
    S_TARIFF_EXP_THRESHOLD, S_TARIFF_SOC_TARGET, S_TARIFF_POWER,
    S_NIGHT_ENABLED,
    RS_CYCLE_ACTIVE, RS_INTEGRAL, RS_SURPLUS_ACTIVE,
    RS_AC_CHARGE_ACTIVE, RS_TARIFF_CHARGE_ACTIVE,
    MODE_LABELS, ZONE_LABELS,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


class SolakonCoordinator:
    """Central coordinator — state machine, PI calc, settings persistence."""

    def __init__(self, hass: HomeAssistant, entry: "ConfigEntry") -> None:
        self.hass = hass
        self.entry = entry
        self._lock = asyncio.Lock()
        self._unsub: list[Callable] = []
        self._entity_listeners: list[Callable] = []

        # ── Settings (loaded from own store, editable from panel at runtime) ─────────
        self._settings: dict = dict(SETTINGS_DEFAULTS)

        # ── Runtime state (persisted in own store) ────────────────────────────────────
        self._cycle_active         = False
        self._integral             = 0.0
        self._surplus_active       = False
        self._ac_charge_active     = False
        self._tariff_charge_active = False

        # ── Observable state for entities / panel ────────────────────────────────────
        self.current_zone: int   = 3
        self.zone_label: str     = ZONE_LABELS[3]
        self.mode_label: str     = MODE_LABELS["0"]
        self.last_action: str    = "—"
        self.last_error: str     = ""

        # ── Two stores: settings + runtime state ──────────────────────────────────────
        self._settings_store = Store(
            hass, STORAGE_VERSION, f"solakon_settings_{entry.entry_id}"
        )
        self._state_store = Store(
            hass, STORAGE_VERSION, f"solakon_state_{entry.entry_id}"
        )

    # ──────────────────────────────────────────────────────────────────────────────────
    # Public properties
    # ──────────────────────────────────────────────────────────────────────────────────
    @property
    def cycle_active(self) -> bool:
        return self._cycle_active

    @property
    def surplus_active(self) -> bool:
        return self._surplus_active

    @property
    def ac_charge_active(self) -> bool:
        return self._ac_charge_active

    @property
    def tariff_charge_active(self) -> bool:
        return self._tariff_charge_active

    @property
    def integral(self) -> float:
        return self._integral

    @property
    def settings(self) -> dict:
        return dict(self._settings)

    # ──────────────────────────────────────────────────────────────────────────────────
    # Setup / Teardown
    # ──────────────────────────────────────────────────────────────────────────────────
    async def async_setup(self) -> None:
        # Load persisted settings
        saved_settings = await self._settings_store.async_load()
        if saved_settings:
            self._settings = {**SETTINGS_DEFAULTS, **saved_settings}

        # Load persisted runtime state
        saved_state = await self._state_store.async_load()
        if saved_state:
            self._cycle_active         = saved_state.get(RS_CYCLE_ACTIVE, False)
            self._integral             = float(saved_state.get(RS_INTEGRAL, 0.0))
            self._surplus_active       = saved_state.get(RS_SURPLUS_ACTIVE, False)
            self._ac_charge_active     = saved_state.get(RS_AC_CHARGE_ACTIVE, False)
            self._tariff_charge_active = saved_state.get(RS_TARIFF_CHARGE_ACTIVE, False)

        # Watch triggers
        cfg = self.entry.data
        watch = [
            cfg.get(CONF_GRID_SENSOR),
            cfg.get(CONF_SOLAR_SENSOR),
            cfg.get(CONF_SOC_SENSOR),
            cfg.get(CONF_MODE_SELECT),
        ]
        for eid in watch:
            if eid:
                self._unsub.append(
                    async_track_state_change_event(self.hass, eid, self._handle_trigger)
                )

        _LOGGER.info("Solakon coordinator started")

    async def async_teardown(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()

    # ──────────────────────────────────────────────────────────────────────────────────
    # Settings management (called from WS handler in __init__.py)
    # ──────────────────────────────────────────────────────────────────────────────────
    async def async_update_settings(self, new_settings: dict) -> dict:
        """Merge and persist new settings. Returns updated full settings."""
        # Validate numeric types and ranges before accepting
        validated = {}
        for key, val in new_settings.items():
            if key not in SETTINGS_DEFAULTS:
                continue  # ignore unknown keys
            default = SETTINGS_DEFAULTS[key]
            try:
                if isinstance(default, bool):
                    validated[key] = bool(val)
                elif isinstance(default, int):
                    validated[key] = int(float(val))
                elif isinstance(default, float):
                    validated[key] = float(val)
                else:
                    validated[key] = str(val)
            except (TypeError, ValueError):
                _LOGGER.warning("Solakon: ignoring invalid value for %s: %r", key, val)

        self._settings.update(validated)
        await self._settings_store.async_save(self._settings)
        _LOGGER.debug("Solakon settings updated: %s", list(validated.keys()))
        return dict(self._settings)

    async def async_reset_integral(self) -> None:
        self._integral = 0.0
        await self._persist_state()
        self._notify_entities()

    # ──────────────────────────────────────────────────────────────────────────────────
    # Entity listener management
    # ──────────────────────────────────────────────────────────────────────────────────
    def register_entity_listener(self, cb: Callable) -> None:
        self._entity_listeners.append(cb)

    def unregister_entity_listener(self, cb: Callable) -> None:
        if cb in self._entity_listeners:
            self._entity_listeners.remove(cb)

    @callback
    def _notify_entities(self) -> None:
        mode = self._get_mode()
        soc  = self._flt(self.entry.data.get(CONF_SOC_SENSOR, ''))

        # Derive zone
        if self._surplus_active:
            self.current_zone = 0
        elif soc <= self._settings[S_ZONE3_LIMIT]:
            self.current_zone = 3
        elif self._cycle_active:
            self.current_zone = 1
        elif mode == '1':
            self.current_zone = 2
        else:
            self.current_zone = 3

        self.zone_label  = ZONE_LABELS.get(self.current_zone, "Unbekannt")
        self.mode_label  = MODE_LABELS.get(mode, f"Unbekannt ({mode})")

        for cb in self._entity_listeners:
            try:
                cb()
            except Exception:  # noqa: BLE001
                pass

    # ──────────────────────────────────────────────────────────────────────────────────
    # State / sensor helpers
    # ──────────────────────────────────────────────────────────────────────────────────
    def _flt(self, entity_id: str | None, default: float = 0.0) -> float:
        if not entity_id:
            return default
        s = self.hass.states.get(entity_id)
        if s is None or s.state in ('unknown', 'unavailable', 'none', ''):
            return default
        try:
            return float(s.state)
        except (ValueError, TypeError):
            return default

    def _available(self, entity_id: str | None) -> bool:
        if not entity_id or not isinstance(entity_id, str):
            return False
        s = self.hass.states.get(entity_id)
        return s is not None and s.state not in ('unknown', 'unavailable')

    def _get_mode(self) -> str:
        s = self.hass.states.get(self.entry.data.get(CONF_MODE_SELECT, ''))
        return s.state if s else '0'

    # ──────────────────────────────────────────────────────────────────────────────────
    # Dynamic offset calculation (replaces separate blueprint)
    # Formula: clamp(min + max(0, (stddev - noise) * factor), min, max) * sign
    # ──────────────────────────────────────────────────────────────────────────────────
    def _calc_dynamic_offset(
        self,
        enabled: bool,
        stddev_sensor: str,
        static_fallback: float,
        min_offset: float,
        max_offset: float,
        noise_floor: float,
        factor: float,
        negative: bool,
    ) -> float:
        if not enabled or not self._available(stddev_sensor):
            return static_fallback

        stddev = self._flt(stddev_sensor, -1.0)
        if stddev < 0:
            result = min_offset
        else:
            buf    = max(0.0, (stddev - noise_floor) * factor)
            result = max(min_offset, min(max_offset, min_offset + buf))

        return -result if negative else result

    def _effective_offset_1(self) -> float:
        s = self._settings
        return self._calc_dynamic_offset(
            s[S_DYN_OFFSET_1_ENABLED], s[S_DYN_OFFSET_1_SENSOR],
            float(s[S_OFFSET_1]),
            float(s[S_DYN_OFFSET_1_MIN]), float(s[S_DYN_OFFSET_1_MAX]),
            float(s[S_DYN_OFFSET_1_NOISE]), float(s[S_DYN_OFFSET_1_FACTOR]),
            bool(s[S_DYN_OFFSET_1_NEGATIVE]),
        )

    def _effective_offset_2(self) -> float:
        s = self._settings
        return self._calc_dynamic_offset(
            s[S_DYN_OFFSET_2_ENABLED], s[S_DYN_OFFSET_2_SENSOR],
            float(s[S_OFFSET_2]),
            float(s[S_DYN_OFFSET_2_MIN]), float(s[S_DYN_OFFSET_2_MAX]),
            float(s[S_DYN_OFFSET_2_NOISE]), float(s[S_DYN_OFFSET_2_FACTOR]),
            bool(s[S_DYN_OFFSET_2_NEGATIVE]),
        )

    def _effective_offset_ac(self) -> float:
        s = self._settings
        return self._calc_dynamic_offset(
            s[S_DYN_OFFSET_AC_ENABLED], s[S_DYN_OFFSET_AC_SENSOR],
            float(s[S_AC_OFFSET]),
            float(s[S_DYN_OFFSET_AC_MIN]), float(s[S_DYN_OFFSET_AC_MAX]),
            float(s[S_DYN_OFFSET_AC_NOISE]), float(s[S_DYN_OFFSET_AC_FACTOR]),
            bool(s[S_DYN_OFFSET_AC_NEGATIVE]),
        )

    # ──────────────────────────────────────────────────────────────────────────────────
    # PI calculation
    # ──────────────────────────────────────────────────────────────────────────────────
    def _pi_calc(
        self,
        grid: float,
        current: float,
        target: float,
        max_pwr: float,
        p: float,
        i_f: float,
        ac_mode: bool,
    ) -> tuple[float, float]:
        raw_error = (target - grid) if ac_mode else (grid - target)
        error = (min(raw_error, max_pwr - current) if raw_error > 0
                 else max(raw_error, -current))
        integral_new = max(-1000.0, min(1000.0, self._integral + error))
        correction   = error * p + integral_new * i_f
        final_power  = max(0.0, min(float(max_pwr), current + correction))
        return round(final_power), integral_new

    # ──────────────────────────────────────────────────────────────────────────────────
    # Tariff helpers
    # ──────────────────────────────────────────────────────────────────────────────────
    def _price_flags(self) -> tuple[bool, bool]:
        s = self._settings
        if not s[S_TARIFF_ENABLED]:
            return False, False
        sensor = s[S_TARIFF_PRICE_SENSOR]
        if not sensor or not self._available(sensor):
            return False, False  # sensor absent → neither lock nor charge
        try:
            price = float(self.hass.states.get(sensor).state)
        except (ValueError, TypeError, AttributeError):
            return False, False
        return price < s[S_TARIFF_CHEAP_THRESHOLD], price < s[S_TARIFF_EXP_THRESHOLD]

    # ──────────────────────────────────────────────────────────────────────────────────
    # Service helpers
    # ──────────────────────────────────────────────────────────────────────────────────
    async def _set_number(self, entity_id: str, value: float) -> None:
        await self.hass.services.async_call(
            "number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
        )

    async def _select_option(self, entity_id: str, option: str) -> None:
        await self.hass.services.async_call(
            "select", "select_option", {"entity_id": entity_id, "option": option}, blocking=True
        )

    async def _timer_toggle(self) -> None:
        eid = self.entry.data.get(CONF_TIMEOUT_SET, '')
        cur = self._flt(eid, 3598.0)
        await self._set_number(eid, 3598 if int(cur) == 3599 else 3599)

    async def _set_mode(self, option: str, toggle: bool = False) -> None:
        if toggle:
            await self._timer_toggle()
        await self._select_option(self.entry.data.get(CONF_MODE_SELECT, ''), option)

    async def _reset_integral(self) -> None:
        self._integral = 0.0

    async def _persist_state(self) -> None:
        await self._state_store.async_save({
            RS_CYCLE_ACTIVE:         self._cycle_active,
            RS_INTEGRAL:             self._integral,
            RS_SURPLUS_ACTIVE:       self._surplus_active,
            RS_AC_CHARGE_ACTIVE:     self._ac_charge_active,
            RS_TARIFF_CHARGE_ACTIVE: self._tariff_charge_active,
        })

    # ──────────────────────────────────────────────────────────────────────────────────
    # Trigger handler
    # ──────────────────────────────────────────────────────────────────────────────────
    @callback
    def _handle_trigger(self, event: Event) -> None:
        self.hass.async_create_task(self._run_locked())

    async def _run_locked(self) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            try:
                await self._run_logic()
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Solakon error: %s", exc, exc_info=True)
                self.last_error = str(exc)
            finally:
                await self._persist_state()
                self._notify_entities()

    # ──────────────────────────────────────────────────────────────────────────────────
    # Zone 0: surplus update
    # ──────────────────────────────────────────────────────────────────────────────────
    async def _zone0_update(self, s: dict, soc: float, solar: float, actual: float, grid: float) -> None:
        if not s[S_SURPLUS_ENABLED]:
            if self._surplus_active:
                self._surplus_active = False
            return
        thr  = float(s[S_SURPLUS_SOC_THRESHOLD])
        hyst = float(s[S_SURPLUS_SOC_HYST])
        pvh  = float(s[S_SURPLUS_PV_HYST])

        if not self._surplus_active:
            if soc >= thr and (solar > (actual + grid + pvh) or solar == 0):
                self._surplus_active = True
                _LOGGER.info("Solakon Zone 0 aktiviert (Überschuss-Einspeisung)")
        else:
            if soc < (thr - hyst) or solar <= (actual + grid - pvh):
                self._surplus_active = False
                await self._reset_integral()
                _LOGGER.info("Solakon Zone 0 deaktiviert")

    # ──────────────────────────────────────────────────────────────────────────────────
    # Shared zone exit: return from mode '3' to zone 1/2
    # ──────────────────────────────────────────────────────────────────────────────────
    async def _exit_charge_mode(self) -> None:
        eid = self.entry.data.get(CONF_ACTIVE_POWER, '')
        if eid:
            await self._set_number(eid, 0)
        if self._cycle_active:
            await self._set_mode('1', toggle=True)
        else:
            await self._set_mode('0')

    # ──────────────────────────────────────────────────────────────────────────────────
    # State machine: Falls A – F, GT, G, HT, H, I
    # Returns True → stop (skip PI gate)
    # Returns False → continue to PI gate
    # ──────────────────────────────────────────────────────────────────────────────────
    async def _run_falls(
        self,
        s: dict,
        soc: float, grid: float, solar: float, actual: float,
        mode: str,
        price_cheap: bool,
        price_locked: bool,
    ) -> bool:
        z1   = float(s[S_ZONE1_LIMIT])
        z3   = float(s[S_ZONE3_LIMIT])
        pvr  = float(s[S_PV_RESERVE])
        eid  = self.entry.data.get(CONF_ACTIVE_POWER, '')
        ac_on     = bool(s[S_AC_ENABLED])
        tariff_on = bool(s[S_TARIFF_ENABLED])
        night_on  = bool(s[S_NIGHT_ENABLED])
        ac_hyst   = float(s[S_AC_HYSTERESIS])
        ac_soc    = float(s[S_AC_SOC_TARGET])
        tariff_soc  = float(s[S_TARIFF_SOC_TARGET])
        tariff_pwr  = float(s[S_TARIFF_POWER])

        # ── FALL A ────────────────────────────────────────────────────────────────────
        if (not self._ac_charge_active
                and not price_locked
                and soc > z1
                and not self._cycle_active):
            _LOGGER.info("Fall A — Zone 1 Start, SOC=%.1f%%", soc)
            await self._reset_integral()
            self._cycle_active = True
            self._surplus_active = False
            self._ac_charge_active = False
            await self._set_mode('1', toggle=True)
            self.last_action = "Fall A — Zone 1 Start"
            return False

        # ── FALL B ────────────────────────────────────────────────────────────────────
        if (not self._ac_charge_active and soc < z3 and self._cycle_active):
            _LOGGER.info("Fall B — Zone 3 Stop, SOC=%.1f%%", soc)
            await self._reset_integral()
            self._cycle_active = False
            self._surplus_active = False
            self._ac_charge_active = False
            if eid:
                await self._set_number(eid, 0)
            await self._set_mode('0')
            self.last_action = "Fall B — Zone 3 Stopp"
            return True

        # ── FALL C ────────────────────────────────────────────────────────────────────
        if (not self._ac_charge_active and soc < z3 and not self._cycle_active and mode != '0'):
            _LOGGER.info("Fall C — Zone 3 Absicherung")
            self._surplus_active = False
            self._ac_charge_active = False
            if eid:
                await self._set_number(eid, 0)
            await self._set_mode('0')
            self.last_action = "Fall C — Zone 3 Absicherung"
            return True

        # ── FALL D ────────────────────────────────────────────────────────────────────
        if (self._cycle_active and mode not in ('1', '3') and soc > z3):
            _LOGGER.info("Fall D — Recovery, Modus war '%s'", mode)
            if self._ac_charge_active or self._tariff_charge_active:
                await self._set_mode('3', toggle=True)
            else:
                await self._set_mode('1', toggle=True)
            self.last_action = "Fall D — Recovery"
            return False

        # ── FALL GT ───────────────────────────────────────────────────────────────────
        price_sensor = s[S_TARIFF_PRICE_SENSOR]
        if (tariff_on and self._available(price_sensor)
                and price_cheap and soc < tariff_soc and mode != '3'):
            _LOGGER.info("Fall GT — Tarif-Laden Start, SOC=%.1f%%", soc)
            self._tariff_charge_active = True
            await self._timer_toggle()
            if eid:
                await self._set_number(eid, tariff_pwr)
            await self._set_mode('3')
            self.last_action = "Fall GT — Tarif-Laden Start"
            return True

        # ── FALL G ────────────────────────────────────────────────────────────────────
        if (ac_on and soc < ac_soc and mode != '3'
                and not self._tariff_charge_active
                and (grid + actual) < -ac_hyst):
            _LOGGER.info("Fall G — AC Laden Start, SOC=%.1f%%", soc)
            self._ac_charge_active = True
            await self._timer_toggle()
            if eid:
                await self._set_number(eid, 0)
            await self._set_mode('3')
            self.last_action = "Fall G — AC Laden Start"
            return True

        # ── FALL HT ───────────────────────────────────────────────────────────────────
        if (tariff_on and mode == '3' and self._tariff_charge_active
                and (soc >= tariff_soc or not price_cheap)):
            _LOGGER.info("Fall HT — Tarif-Laden Ende")
            await self._reset_integral()
            self._tariff_charge_active = False
            await self._exit_charge_mode()
            self.last_action = "Fall HT — Tarif-Laden Ende"
            return True

        # ── FALL H ────────────────────────────────────────────────────────────────────
        ac_offset = self._effective_offset_ac()
        if (ac_on and mode == '3'
                and (soc >= ac_soc or (grid >= ac_offset + ac_hyst and actual == 0))):
            _LOGGER.info("Fall H — AC Laden Ende")
            await self._reset_integral()
            self._ac_charge_active = False
            await self._exit_charge_mode()
            self.last_action = "Fall H — AC Laden Ende"
            return True

        # ── FALL I ────────────────────────────────────────────────────────────────────
        if mode == '3':
            if not (ac_on and self._ac_charge_active) and not (tariff_on and self._tariff_charge_active):
                _LOGGER.warning("Fall I — Modus '3' ohne aktive Lade-Session")
                await self._reset_integral()
                await self._exit_charge_mode()
                self.last_action = "Fall I — Safety Korrektur"
                return True

        # ── FALL E ────────────────────────────────────────────────────────────────────
        is_night = night_on and solar < pvr
        if (not self._ac_charge_active
                and not price_locked
                and z3 < soc <= z1
                and not self._cycle_active
                and mode == '0'
                and not is_night):
            _LOGGER.info("Fall E — Zone 2 Start, SOC=%.1f%%", soc)
            await self._reset_integral()
            await self._set_mode('1', toggle=True)
            self.last_action = "Fall E — Zone 2 Start"
            return False

        # ── FALL F ────────────────────────────────────────────────────────────────────
        if (not self._ac_charge_active
                and night_on and solar < pvr
                and not self._cycle_active and mode != '0'):
            _LOGGER.info("Fall F — Nachtabschaltung")
            await self._reset_integral()
            if eid:
                await self._set_number(eid, 0)
            await self._set_mode('0')
            self.last_action = "Fall F — Nachtabschaltung"
            return True

        return False

    # ──────────────────────────────────────────────────────────────────────────────────
    # Discharge current step
    # ──────────────────────────────────────────────────────────────────────────────────
    async def _step_discharge_current(self, s: dict, mode: str) -> None:
        eid = self.entry.data.get(CONF_DISCHARGE_CURRENT, '')
        if not eid:
            return
        cur_amps    = self._flt(eid, 999)
        disch_max   = float(s[S_DISCHARGE_MAX])
        in_charge   = mode == '3'

        if self._surplus_active:
            if round(cur_amps, 2) != 2.0:
                await self._set_number(eid, 2)
        elif self._cycle_active and not in_charge:
            if round(cur_amps, 2) != round(disch_max, 2):
                await self._set_number(eid, disch_max)
        elif round(cur_amps, 2) != 0.0:
            await self._set_number(eid, 0)

    # ──────────────────────────────────────────────────────────────────────────────────
    # PI output step
    # ──────────────────────────────────────────────────────────────────────────────────
    async def _step_pi_output(self, s: dict, grid: float, solar: float, actual: float, mode: str) -> None:
        tol      = float(s[S_TOLERANCE])
        wait_s   = int(s[S_WAIT_TIME])
        max_pwr  = float(s[S_HARD_LIMIT])
        pvr      = float(s[S_PV_RESERVE])
        eid      = self.entry.data.get(CONF_ACTIVE_POWER, '')
        tariff_pwr = float(s[S_TARIFF_POWER])
        ac_lim   = float(s[S_AC_POWER_LIMIT])

        # Effective target
        if self._ac_charge_active:
            target = self._effective_offset_ac()
        elif self._cycle_active:
            target = self._effective_offset_1()
        else:
            target = self._effective_offset_2()

        # Dynamic max power
        if mode == '3':
            dyn_max = tariff_pwr if self._tariff_charge_active else ac_lim
        elif self._cycle_active:
            dyn_max = max_pwr
        else:
            dyn_max = max(0.0, solar - pvr)

        raw_err   = grid - target
        err_abs   = abs(raw_err)

        # ── Branch A: Zone 0 — surplus ────────────────────────────────────────────────
        if self._surplus_active:
            if eid:
                await self._set_number(eid, max_pwr)
            # Integral frozen — no update
            await asyncio.sleep(wait_s)
            return

        # ── Branch BT: Tariff — direct set ───────────────────────────────────────────
        if self._tariff_charge_active:
            if eid:
                await self._set_number(eid, tariff_pwr)
            await asyncio.sleep(wait_s)
            return

        # ── Branch B: AC charging PI ──────────────────────────────────────────────────
        if self._ac_charge_active and err_abs > tol:
            new_pwr, new_int = self._pi_calc(
                grid, actual, target, dyn_max,
                float(s[S_AC_P_FACTOR]), float(s[S_AC_I_FACTOR]), ac_mode=True
            )
            self._integral = new_int
            if eid:
                await self._set_number(eid, new_pwr)
            await asyncio.sleep(wait_s)
            return

        # ── Branch C: Normal PI ───────────────────────────────────────────────────────
        at_max = raw_err > 0 and actual >= max_pwr
        at_min = raw_err < 0 and actual <= 0
        if (not self._ac_charge_active and not self._tariff_charge_active
                and err_abs > tol and not at_max and not at_min):
            new_pwr, new_int = self._pi_calc(
                grid, actual, target, dyn_max,
                float(s[S_P_FACTOR]), float(s[S_I_FACTOR]), ac_mode=False
            )
            self._integral = new_int
            if eid:
                await self._set_number(eid, new_pwr)
            await asyncio.sleep(wait_s)
            return

        # ── Default: Integral decay ───────────────────────────────────────────────────
        if abs(self._integral) > 10:
            self._integral = round(self._integral * 0.95, 2)

    # ──────────────────────────────────────────────────────────────────────────────────
    # Master runner
    # ──────────────────────────────────────────────────────────────────────────────────
    async def _run_logic(self) -> None:
        cfg = self.entry.data
        s   = self._settings

        soc      = self._flt(cfg.get(CONF_SOC_SENSOR))
        grid     = self._flt(cfg.get(CONF_GRID_SENSOR))
        solar    = self._flt(cfg.get(CONF_SOLAR_SENSOR))
        actual   = self._flt(cfg.get(CONF_ACTUAL_SENSOR))
        countdown = self._flt(cfg.get(CONF_TIMEOUT_COUNTDOWN), 9999)

        # Validation
        z1_lim = float(s[S_ZONE1_LIMIT])
        z3_lim = float(s[S_ZONE3_LIMIT])
        soc_st  = self.hass.states.get(cfg.get(CONF_SOC_SENSOR, ''))
        cnt_st  = self.hass.states.get(cfg.get(CONF_TIMEOUT_COUNTDOWN, ''))

        if (z1_lim <= z3_lim
                or soc_st is None or soc_st.state in ('unknown', 'unavailable')
                or cnt_st is None or cnt_st.state in ('unknown', 'unavailable')):
            _LOGGER.error("Solakon: SOC-Limits ungültig oder Entitäten offline. Abbruch.")
            self.last_error = "SOC-Limits ungültig oder Entitäten offline"
            return

        self.last_error = ""
        mode = self._get_mode()
        price_cheap, price_locked = self._price_flags()

        # Zone 0 update
        await self._zone0_update(s, soc, solar, actual, grid)

        # State machine
        if await self._run_falls(s, soc, grid, solar, actual, mode, price_cheap, price_locked):
            return

        # PI Gate
        pvr     = float(s[S_PV_RESERVE])
        night   = bool(s[S_NIGHT_ENABLED])

        if mode not in ('1', '3'):
            return
        if not (self._cycle_active or not night or solar >= pvr):
            return

        # Refresh fresh values for PI
        grid   = self._flt(cfg.get(CONF_GRID_SENSOR))
        solar  = self._flt(cfg.get(CONF_SOLAR_SENSOR))
        actual = self._flt(cfg.get(CONF_ACTUAL_SENSOR))
        mode   = self._get_mode()

        await self._step_discharge_current(s, mode)

        if countdown < 120:
            await self._timer_toggle()

        await self._step_pi_output(s, grid, solar, actual, mode)
