"""Coordinator for Solakon ONE Nulleinspeisung — all zone/PI logic."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN, STORAGE_VERSION, STORAGE_KEY_TEMPLATE,
    CONF_GRID_POWER_SENSOR, CONF_ACTUAL_POWER_SENSOR, CONF_SOLAR_POWER_SENSOR,
    CONF_SOC_SENSOR, CONF_REMOTE_TIMEOUT_COUNTDOWN, CONF_ACTIVE_POWER_NUMBER,
    CONF_MAX_DISCHARGE_CURRENT, CONF_REMOTE_TIMEOUT_SET, CONF_MODE_SELECT,
    CONF_P_FACTOR, CONF_I_FACTOR, CONF_TOLERANCE, CONF_WAIT_TIME,
    CONF_SOC_FAST_LIMIT, CONF_SOC_CONSERVATION_LIMIT, CONF_DISCHARGE_CURRENT_MAX,
    CONF_OFFSET_1, CONF_OFFSET_1_ENTITY, CONF_OFFSET_2, CONF_OFFSET_2_ENTITY,
    CONF_PV_CHARGE_RESERVE, CONF_MAX_ACTIVE_POWER,
    CONF_SURPLUS_ENABLED, CONF_SOC_EXPORT_LIMIT, CONF_SURPLUS_EXIT_HYSTERESIS,
    CONF_SURPLUS_PV_HYSTERESIS,
    CONF_AC_CHARGE_ENABLED, CONF_SOC_AC_CHARGE_LIMIT, CONF_AC_CHARGE_POWER_LIMIT,
    CONF_AC_CHARGE_HYSTERESIS, CONF_AC_CHARGE_OFFSET, CONF_AC_CHARGE_OFFSET_ENTITY,
    CONF_AC_CHARGE_P_FACTOR, CONF_AC_CHARGE_I_FACTOR,
    CONF_TARIFF_ENABLED, CONF_PRICE_SENSOR, CONF_CHEAP_THRESHOLD,
    CONF_EXPENSIVE_THRESHOLD, CONF_TARIFF_SOC_TARGET, CONF_TARIFF_CHARGE_POWER,
    CONF_NIGHT_SHUTDOWN,
    STATE_CYCLE_ACTIVE, STATE_INTEGRAL, STATE_SURPLUS_ACTIVE,
    STATE_AC_CHARGE_ACTIVE, STATE_TARIFF_CHARGE_ACTIVE,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


class SolakonCoordinator:
    """Central coordinator — replicates all blueprint automation logic."""

    def __init__(self, hass: HomeAssistant, entry: "ConfigEntry") -> None:
        self.hass = hass
        self.entry = entry
        self._lock = asyncio.Lock()
        self._unsub: list[Callable] = []
        self._entity_listeners: list[Callable] = []

        # ── Persistent internal state (replaces input_boolean / input_number helpers) ─
        self._cycle_active = False
        self._integral = 0.0
        self._surplus_active = False
        self._ac_charge_active = False
        self._tariff_charge_active = False

        # ── Status for entities / panel ───────────────────────────────────────────────
        self.current_zone: int = 0
        self.last_action: str = "—"

        storage_key = STORAGE_KEY_TEMPLATE.format(entry_id=entry.entry_id)
        self._store = Store(hass, STORAGE_VERSION, storage_key)

    # ──────────────────────────────────────────────────────────────────────────────────
    # Properties — read by sensor/switch/number entities
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

    # ──────────────────────────────────────────────────────────────────────────────────
    # Setup / Teardown
    # ──────────────────────────────────────────────────────────────────────────────────
    async def async_setup(self) -> None:
        """Load persisted state, register state-change listeners."""
        data = await self._store.async_load()
        if data:
            self._cycle_active       = data.get(STATE_CYCLE_ACTIVE, False)
            self._integral           = float(data.get(STATE_INTEGRAL, 0.0))
            self._surplus_active     = data.get(STATE_SURPLUS_ACTIVE, False)
            self._ac_charge_active   = data.get(STATE_AC_CHARGE_ACTIVE, False)
            self._tariff_charge_active = data.get(STATE_TARIFF_CHARGE_ACTIVE, False)

        cfg = self._cfg
        watch = [
            cfg.get(CONF_GRID_POWER_SENSOR),
            cfg.get(CONF_SOLAR_POWER_SENSOR),
            cfg.get(CONF_SOC_SENSOR),
            cfg.get(CONF_MODE_SELECT),
        ]
        for entity_id in watch:
            if entity_id:
                self._unsub.append(
                    async_track_state_change_event(
                        self.hass, entity_id, self._handle_trigger
                    )
                )
        _LOGGER.debug("Solakon coordinator started, watching: %s", watch)

    async def async_teardown(self) -> None:
        """Unsubscribe all listeners."""
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()

    def register_entity_listener(self, cb: Callable) -> None:
        self._entity_listeners.append(cb)

    def unregister_entity_listener(self, cb: Callable) -> None:
        self._entity_listeners.discard(cb) if hasattr(self._entity_listeners, 'discard') else None

    @callback
    def _notify_entities(self) -> None:
        """Update all registered HA entities."""
        # Derive current zone from internal state
        cfg = self._cfg
        mode = self._get_mode()
        soc = self._flt(cfg.get(CONF_SOC_SENSOR, ''))

        if self._surplus_active:
            self.current_zone = 0
        elif soc <= cfg.get(CONF_SOC_CONSERVATION_LIMIT, 20):
            self.current_zone = 3
        elif self._cycle_active:
            self.current_zone = 1
        elif mode == '1':
            self.current_zone = 2
        else:
            self.current_zone = 3

        for cb in self._entity_listeners:
            try:
                cb()
            except Exception:  # noqa: BLE001
                pass

    # ──────────────────────────────────────────────────────────────────────────────────
    # Config shorthand
    # ──────────────────────────────────────────────────────────────────────────────────
    @property
    def _cfg(self) -> dict:
        return {**self.entry.data, **self.entry.options}

    # ──────────────────────────────────────────────────────────────────────────────────
    # Helpers — state access
    # ──────────────────────────────────────────────────────────────────────────────────
    def _flt(self, entity_id: str | None, default: float = 0.0) -> float:
        if not entity_id:
            return default
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ('unknown', 'unavailable', 'none', ''):
            return default
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return default

    def _is_state(self, entity_id: str | None, check: str) -> bool:
        if not entity_id:
            return False
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == check

    def _get_mode(self) -> str:
        cfg = self._cfg
        state = self.hass.states.get(cfg.get(CONF_MODE_SELECT, ''))
        return state.state if state else '0'

    def _entity_available(self, entity_id: str | None) -> bool:
        if not entity_id or not isinstance(entity_id, str) or len(entity_id) == 0:
            return False
        state = self.hass.states.get(entity_id)
        return state is not None and state.state not in ('unknown', 'unavailable')

    # ──────────────────────────────────────────────────────────────────────────────────
    # Helpers — service calls
    # ──────────────────────────────────────────────────────────────────────────────────
    async def _set_number(self, entity_id: str, value: float) -> None:
        await self.hass.services.async_call(
            "number", "set_value",
            {"entity_id": entity_id, "value": value},
            blocking=True,
        )

    async def _select_option(self, entity_id: str, option: str) -> None:
        await self.hass.services.async_call(
            "select", "select_option",
            {"entity_id": entity_id, "option": option},
            blocking=True,
        )

    async def _timer_toggle(self) -> None:
        """Toggle remote timeout between 3598 and 3599."""
        cfg = self._cfg
        entity_id = cfg.get(CONF_REMOTE_TIMEOUT_SET, '')
        current = self._flt(entity_id, 3598.0)
        new_val = 3598 if int(current) == 3599 else 3599
        await self._set_number(entity_id, new_val)

    async def _set_mode(self, option: str, with_toggle: bool = False) -> None:
        cfg = self._cfg
        if with_toggle:
            await self._timer_toggle()
        await self._select_option(cfg.get(CONF_MODE_SELECT, ''), option)

    async def _reset_integral(self) -> None:
        self._integral = 0.0

    async def _save_state(self) -> None:
        await self._store.async_save({
            STATE_CYCLE_ACTIVE:        self._cycle_active,
            STATE_INTEGRAL:            self._integral,
            STATE_SURPLUS_ACTIVE:      self._surplus_active,
            STATE_AC_CHARGE_ACTIVE:    self._ac_charge_active,
            STATE_TARIFF_CHARGE_ACTIVE: self._tariff_charge_active,
        })

    # ──────────────────────────────────────────────────────────────────────────────────
    # PI calculation (Python equivalent of PI-Regler.yaml)
    # ──────────────────────────────────────────────────────────────────────────────────
    def _pi_calc(
        self,
        grid: float,
        current: float,
        target: float,
        max_pwr: float,
        p: float,
        i_factor: float,
        ac_mode: bool,
    ) -> tuple[float, float]:
        """Return (new_power, new_integral)."""
        raw_error = (target - grid) if ac_mode else (grid - target)

        # Capacity clamping
        if raw_error > 0:
            error = min(raw_error, max_pwr - current)
        else:
            error = max(raw_error, -current)

        integral_new = max(-1000.0, min(1000.0, self._integral + error))
        correction = (error * p) + (integral_new * i_factor)
        final_power = max(0.0, min(float(max_pwr), current + correction))

        return round(final_power), integral_new

    # ──────────────────────────────────────────────────────────────────────────────────
    # Dynamic offset resolution
    # ──────────────────────────────────────────────────────────────────────────────────
    def _resolve_offset(self, static: float, entity_id: str | None) -> float:
        if entity_id and isinstance(entity_id, str) and len(entity_id) > 0:
            state = self.hass.states.get(entity_id)
            if state and state.state not in ('unknown', 'unavailable', 'none', ''):
                try:
                    return float(state.state)
                except (ValueError, TypeError):
                    pass
        return static

    # ──────────────────────────────────────────────────────────────────────────────────
    # Derived price / tariff flags
    # ──────────────────────────────────────────────────────────────────────────────────
    def _price_flags(self, cfg: dict) -> tuple[bool, bool]:
        """Return (price_is_cheap, price_discharge_locked)."""
        tariff_enabled = cfg.get(CONF_TARIFF_ENABLED, False)
        if not tariff_enabled:
            return False, False

        cheap_thresh = float(cfg.get(CONF_CHEAP_THRESHOLD, 10))
        expensive_thresh = float(cfg.get(CONF_EXPENSIVE_THRESHOLD, 25))
        price_sensor = cfg.get(CONF_PRICE_SENSOR, '')

        if not self._entity_available(price_sensor):
            return False, False  # fallback: no lock, no charging

        try:
            current_price = float(self.hass.states.get(price_sensor).state)
        except (ValueError, TypeError, AttributeError):
            return False, False

        is_cheap = current_price < cheap_thresh
        is_locked = current_price < expensive_thresh
        return is_cheap, is_locked

    # ──────────────────────────────────────────────────────────────────────────────────
    # Main trigger handler
    # ──────────────────────────────────────────────────────────────────────────────────
    @callback
    def _handle_trigger(self, event: Event) -> None:
        self.hass.async_create_task(self._run_locked())

    async def _run_locked(self) -> None:
        if self._lock.locked():
            return  # mode: single — discard concurrent triggers
        async with self._lock:
            try:
                await self._run_logic()
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Solakon coordinator error: %s", exc, exc_info=True)
            finally:
                await self._save_state()
                self._notify_entities()

    # ──────────────────────────────────────────────────────────────────────────────────
    # Zone 0 — surplus status update (Falls 0A / 0B)
    # ──────────────────────────────────────────────────────────────────────────────────
    async def _zone0_update(self, cfg: dict, soc: float, solar: float, actual: float, grid: float) -> None:
        if not cfg.get(CONF_SURPLUS_ENABLED, False):
            return

        soc_export    = float(cfg.get(CONF_SOC_EXPORT_LIMIT, 90))
        soc_hyst      = float(cfg.get(CONF_SURPLUS_EXIT_HYSTERESIS, 5))
        pv_hyst       = float(cfg.get(CONF_SURPLUS_PV_HYSTERESIS, 50))

        # Fall 0A: start surplus
        if not self._surplus_active:
            if soc >= soc_export and (solar > (actual + grid + pv_hyst) or solar == 0):
                self._surplus_active = True
                _LOGGER.info("Solakon Zone 0 aktiviert (Überschuss)")

        # Fall 0B: end surplus
        elif self._surplus_active:
            if soc < (soc_export - soc_hyst) or solar <= (actual + grid - pv_hyst):
                self._surplus_active = False
                await self._reset_integral()
                _LOGGER.info("Solakon Zone 0 deaktiviert")

    # ──────────────────────────────────────────────────────────────────────────────────
    # Reusable zone-exit actions
    # ──────────────────────────────────────────────────────────────────────────────────
    async def _return_from_charge_mode(self, cfg: dict) -> None:
        """After HT/H/I: return to zone 1 (mode '1') or zone 2 (mode '0')."""
        active_power_entity = cfg.get(CONF_ACTIVE_POWER_NUMBER, '')

        if self._cycle_active:
            # Zone 1: output → 0, timer toggle, mode '1'
            if active_power_entity:
                await self._set_number(active_power_entity, 0)
            await self._set_mode('1', with_toggle=True)
        else:
            # Zone 2: output → 0, mode '0'
            if active_power_entity:
                await self._set_number(active_power_entity, 0)
            await self._set_mode('0')

    # ──────────────────────────────────────────────────────────────────────────────────
    # Main state-machine (Falls A – F, GT, G, HT, H, I)
    # Returns True if a fall matched (PI gate is then skipped).
    # Falls GT and G also return True (they end with `stop`).
    # ──────────────────────────────────────────────────────────────────────────────────
    async def _run_falls(
        self,
        cfg: dict,
        soc: float,
        grid: float,
        solar: float,
        actual: float,
        mode: str,
        price_is_cheap: bool,
        price_discharge_locked: bool,
    ) -> bool:

        zone1_limit  = float(cfg.get(CONF_SOC_FAST_LIMIT, 50))
        zone3_limit  = float(cfg.get(CONF_SOC_CONSERVATION_LIMIT, 20))
        pv_reserve   = float(cfg.get(CONF_PV_CHARGE_RESERVE, 50))
        night_on     = cfg.get(CONF_NIGHT_SHUTDOWN, False)
        active_power_entity  = cfg.get(CONF_ACTIVE_POWER_NUMBER, '')
        ac_hyst      = float(cfg.get(CONF_AC_CHARGE_HYSTERESIS, 50))
        ac_soc_limit = float(cfg.get(CONF_SOC_AC_CHARGE_LIMIT, 90))
        ac_offset_static = float(cfg.get(CONF_AC_CHARGE_OFFSET, -50))
        ac_offset    = self._resolve_offset(ac_offset_static, cfg.get(CONF_AC_CHARGE_OFFSET_ENTITY, ''))
        tariff_soc   = float(cfg.get(CONF_TARIFF_SOC_TARGET, 90))
        tariff_power = float(cfg.get(CONF_TARIFF_CHARGE_POWER, 800))
        tariff_on    = cfg.get(CONF_TARIFF_ENABLED, False)
        ac_on        = cfg.get(CONF_AC_CHARGE_ENABLED, False)

        # ── FALL A: Zone 1 start ──────────────────────────────────────────────────────
        if (not self._ac_charge_active
                and not price_discharge_locked
                and soc > zone1_limit
                and not self._cycle_active):
            _LOGGER.info("Solakon Fall A — Zone 1 Start, SOC=%.1f%%", soc)
            await self._reset_integral()
            self._cycle_active = True
            if self._surplus_active:
                self._surplus_active = False
            if self._ac_charge_active:
                self._ac_charge_active = False
            await self._set_mode('1', with_toggle=True)
            self.last_action = "Fall A — Zone 1 Start"
            return False  # continue to PI gate

        # ── FALL B: Zone 3 stop (cycle on) ───────────────────────────────────────────
        if (not self._ac_charge_active
                and soc < zone3_limit
                and self._cycle_active):
            _LOGGER.info("Solakon Fall B — Zone 3 Stop, SOC=%.1f%%", soc)
            await self._reset_integral()
            self._cycle_active = False
            self._surplus_active = False
            self._ac_charge_active = False
            if active_power_entity:
                await self._set_number(active_power_entity, 0)
            await self._set_mode('0')
            self.last_action = "Fall B — Zone 3 Stopp"
            return True

        # ── FALL C: Zone 3 safety (cycle off, mode not '0') ──────────────────────────
        if (not self._ac_charge_active
                and soc < zone3_limit
                and not self._cycle_active
                and mode != '0'):
            _LOGGER.info("Solakon Fall C — Zone 3 Absicherung")
            self._surplus_active = False
            self._ac_charge_active = False
            if active_power_entity:
                await self._set_number(active_power_entity, 0)
            await self._set_mode('0')
            self.last_action = "Fall C — Zone 3 Absicherung"
            return True

        # ── FALL D: Recovery (cycle on, mode fell to not '1' or '3') ─────────────────
        if (self._cycle_active
                and mode not in ('1', '3')
                and soc > zone3_limit):
            _LOGGER.info("Solakon Fall D — Recovery, mode was '%s'", mode)
            if self._ac_charge_active or self._tariff_charge_active:
                await self._set_mode('3', with_toggle=True)
            else:
                await self._set_mode('1', with_toggle=True)
            self.last_action = "Fall D — Recovery"
            return False  # continue to PI gate

        # ── FALL GT: Tariff charging start ────────────────────────────────────────────
        if (tariff_on
                and self._entity_available(cfg.get(CONF_PRICE_SENSOR, ''))
                and price_is_cheap
                and soc < tariff_soc
                and mode != '3'):
            _LOGGER.info("Solakon Fall GT — Tarif-Laden Start, SOC=%.1f%%", soc)
            self._tariff_charge_active = True
            await self._timer_toggle()
            if active_power_entity:
                await self._set_number(active_power_entity, tariff_power)
            await self._set_mode('3')
            self.last_action = "Fall GT — Tarif-Laden Start"
            return True  # stop

        # ── FALL G: AC charging start ─────────────────────────────────────────────────
        if (ac_on
                and self._entity_available(cfg.get(CONF_AC_CHARGE_ENABLED, None))  # always True when enabled
                and soc < ac_soc_limit
                and mode != '3'
                and not self._tariff_charge_active
                and (grid + actual) < -(ac_hyst)):
            _LOGGER.info("Solakon Fall G — AC Laden Start, SOC=%.1f%%", soc)
            self._ac_charge_active = True
            await self._timer_toggle()
            if active_power_entity:
                await self._set_number(active_power_entity, 0)
            await self._set_mode('3')
            self.last_action = "Fall G — AC Laden Start"
            return True  # stop

        # ── FALL HT: Tariff charging end ──────────────────────────────────────────────
        if (tariff_on
                and mode == '3'
                and self._tariff_charge_active
                and (soc >= tariff_soc or not price_is_cheap)):
            _LOGGER.info("Solakon Fall HT — Tarif-Laden Ende, SOC=%.1f%%", soc)
            await self._reset_integral()
            self._tariff_charge_active = False
            await self._return_from_charge_mode(cfg)
            self.last_action = "Fall HT — Tarif-Laden Ende"
            return True

        # ── FALL H: AC charging end ───────────────────────────────────────────────────
        if (ac_on and mode == '3'
                and (soc >= ac_soc_limit
                     or (grid >= ac_offset + ac_hyst and actual == 0))):
            _LOGGER.info("Solakon Fall H — AC Laden Ende, SOC=%.1f%%", soc)
            await self._reset_integral()
            self._ac_charge_active = False
            await self._return_from_charge_mode(cfg)
            self.last_action = "Fall H — AC Laden Ende"
            return True

        # ── FALL I: Safety — mode '3' without active charge session ──────────────────
        if mode == '3':
            # Is there any legitimate active charge session?
            ac_ok     = ac_on and self._ac_charge_active
            tariff_ok = tariff_on and self._tariff_charge_active
            if not ac_ok and not tariff_ok:
                _LOGGER.warning("Solakon Fall I — Modus '3' ohne aktive Lade-Session, Korrektur")
                await self._reset_integral()
                await self._return_from_charge_mode(cfg)
                self.last_action = "Fall I — Safety Korrektur"
                return True

        # ── FALL E: Zone 2 start ──────────────────────────────────────────────────────
        is_night = night_on and solar < pv_reserve
        if (not self._ac_charge_active
                and not price_discharge_locked
                and zone3_limit < soc <= zone1_limit
                and not self._cycle_active
                and mode == '0'
                and not is_night):
            _LOGGER.info("Solakon Fall E — Zone 2 Start, SOC=%.1f%%", soc)
            await self._reset_integral()
            await self._set_mode('1', with_toggle=True)
            self.last_action = "Fall E — Zone 2 Start"
            return False  # continue to PI gate

        # ── FALL F: Night shutdown ────────────────────────────────────────────────────
        if (not self._ac_charge_active
                and night_on
                and solar < pv_reserve
                and not self._cycle_active
                and mode != '0'):
            _LOGGER.info("Solakon Fall F — Nachtabschaltung, PV=%.0fW", solar)
            await self._reset_integral()
            if active_power_entity:
                await self._set_number(active_power_entity, 0)
            await self._set_mode('0')
            self.last_action = "Fall F — Nachtabschaltung"
            return True

        return False

    # ──────────────────────────────────────────────────────────────────────────────────
    # Step 1: Discharge current
    # ──────────────────────────────────────────────────────────────────────────────────
    async def _step_discharge_current(self, cfg: dict, mode: str) -> None:
        entity_id      = cfg.get(CONF_MAX_DISCHARGE_CURRENT, '')
        if not entity_id:
            return
        current_amps   = self._flt(entity_id, 999)
        discharge_max  = float(cfg.get(CONF_DISCHARGE_CURRENT_MAX, 40))

        in_charge_mode = mode == '3'
        in_surplus     = self._surplus_active

        # Zone 0 (surplus) → 2 A
        if in_surplus:
            if round(current_amps, 2) != 2.0:
                await self._set_number(entity_id, 2)
            return

        # Zone 1 (cycle on, not charge mode) → max discharge current
        if self._cycle_active and not in_charge_mode:
            if round(current_amps, 2) != round(discharge_max, 2):
                await self._set_number(entity_id, discharge_max)
            return

        # Zone 2 or charge mode → 0 A
        if round(current_amps, 2) != 0.0:
            await self._set_number(entity_id, 0)

    # ──────────────────────────────────────────────────────────────────────────────────
    # Step 3: Output + Integral (PI gate branches)
    # ──────────────────────────────────────────────────────────────────────────────────
    async def _step_pi_output(self, cfg: dict, grid: float, solar: float, actual: float, mode: str) -> None:
        tol              = float(cfg.get(CONF_TOLERANCE, 25))
        wait_s           = int(cfg.get(CONF_WAIT_TIME, 3))
        max_power        = float(cfg.get(CONF_MAX_ACTIVE_POWER, 800))
        pv_reserve       = float(cfg.get(CONF_PV_CHARGE_RESERVE, 50))
        active_power_entity = cfg.get(CONF_ACTIVE_POWER_NUMBER, '')

        offset_1 = self._resolve_offset(
            float(cfg.get(CONF_OFFSET_1, 30)), cfg.get(CONF_OFFSET_1_ENTITY, ''))
        offset_2 = self._resolve_offset(
            float(cfg.get(CONF_OFFSET_2, 30)), cfg.get(CONF_OFFSET_2_ENTITY, ''))
        ac_offset = self._resolve_offset(
            float(cfg.get(CONF_AC_CHARGE_OFFSET, -50)), cfg.get(CONF_AC_CHARGE_OFFSET_ENTITY, ''))

        tariff_power = float(cfg.get(CONF_TARIFF_CHARGE_POWER, 800))
        ac_power_limit = float(cfg.get(CONF_AC_CHARGE_POWER_LIMIT, 800))

        # Effective target offset
        if self._ac_charge_active:
            target = ac_offset
        elif self._cycle_active:
            target = offset_1
        else:
            target = offset_2

        # Dynamic max power
        if mode == '3':
            if self._tariff_charge_active:
                dynamic_max = tariff_power
            else:
                dynamic_max = ac_power_limit
        elif self._cycle_active:
            dynamic_max = max_power
        else:
            dynamic_max = max(0.0, solar - pv_reserve)

        raw_error    = grid - target
        error_abs    = abs(raw_error)

        # ── Branch A: Zone 0 — surplus (hard limit, freeze integral) ─────────────────
        if self._surplus_active:
            if active_power_entity:
                await self._set_number(active_power_entity, max_power)
            # Integral bleibt eingefroren (kein Update)
            await asyncio.sleep(wait_s)
            return

        # ── Branch BT: Tariff charging — direct set, no PI ───────────────────────────
        if self._tariff_charge_active:
            if active_power_entity:
                await self._set_number(active_power_entity, tariff_power)
            await asyncio.sleep(wait_s)
            return

        # ── Branch B: AC charging — PI with inverted error ───────────────────────────
        if self._ac_charge_active and error_abs > tol:
            p = float(cfg.get(CONF_AC_CHARGE_P_FACTOR, 0.5))
            i = float(cfg.get(CONF_AC_CHARGE_I_FACTOR, 0.07))
            new_power, new_integral = self._pi_calc(grid, actual, target, dynamic_max, p, i, ac_mode=True)
            self._integral = new_integral
            if active_power_entity:
                await self._set_number(active_power_entity, new_power)
            await asyncio.sleep(wait_s)
            return

        # ── Branch C: Normal PI ───────────────────────────────────────────────────────
        at_max = raw_error > 0 and actual >= max_power
        at_min = raw_error < 0 and actual <= 0
        if (not self._ac_charge_active
                and not self._tariff_charge_active
                and error_abs > tol
                and not at_max
                and not at_min):
            p = float(cfg.get(CONF_P_FACTOR, 1.3))
            i = float(cfg.get(CONF_I_FACTOR, 0.05))
            new_power, new_integral = self._pi_calc(grid, actual, target, dynamic_max, p, i, ac_mode=False)
            self._integral = new_integral
            if active_power_entity:
                await self._set_number(active_power_entity, new_power)
            await asyncio.sleep(wait_s)
            return

        # ── Default: Integral decay ───────────────────────────────────────────────────
        if abs(self._integral) > 10:
            self._integral = round(self._integral * 0.95, 2)

    # ──────────────────────────────────────────────────────────────────────────────────
    # Master logic runner
    # ──────────────────────────────────────────────────────────────────────────────────
    async def _run_logic(self) -> None:
        cfg = self._cfg

        # ── Read sensors ──────────────────────────────────────────────────────────────
        soc     = self._flt(cfg.get(CONF_SOC_SENSOR, ''))
        grid    = self._flt(cfg.get(CONF_GRID_POWER_SENSOR, ''))
        solar   = self._flt(cfg.get(CONF_SOLAR_POWER_SENSOR, ''))
        actual  = self._flt(cfg.get(CONF_ACTUAL_POWER_SENSOR, ''))
        countdown = self._flt(cfg.get(CONF_REMOTE_TIMEOUT_COUNTDOWN, ''), 9999)

        # ── Validation ────────────────────────────────────────────────────────────────
        zone1 = float(cfg.get(CONF_SOC_FAST_LIMIT, 50))
        zone3 = float(cfg.get(CONF_SOC_CONSERVATION_LIMIT, 20))
        soc_state = self.hass.states.get(cfg.get(CONF_SOC_SENSOR, ''))
        cnt_state = self.hass.states.get(cfg.get(CONF_REMOTE_TIMEOUT_COUNTDOWN, ''))

        if (zone1 <= zone3
                or soc_state is None or soc_state.state in ('unknown', 'unavailable')
                or cnt_state is None or cnt_state.state in ('unknown', 'unavailable')):
            _LOGGER.error(
                "Solakon: Kritischer Fehler — SOC-Limits ungültig oder Entitäten offline. Abbruch."
            )
            return

        mode = self._get_mode()
        price_is_cheap, price_discharge_locked = self._price_flags(cfg)

        # ── Zone 0 update (Falls 0A / 0B) ────────────────────────────────────────────
        await self._zone0_update(cfg, soc, solar, actual, grid)

        # ── Main state machine (Falls A – F, GT, G, HT, H, I) ────────────────────────
        matched = await self._run_falls(
            cfg, soc, grid, solar, actual, mode,
            price_is_cheap, price_discharge_locked,
        )
        if matched:
            return

        # ── PI Gate ───────────────────────────────────────────────────────────────────
        pv_reserve = float(cfg.get(CONF_PV_CHARGE_RESERVE, 50))
        night_on   = cfg.get(CONF_NIGHT_SHUTDOWN, False)

        if mode not in ('1', '3'):
            return
        if not (self._cycle_active or not night_on or solar >= pv_reserve):
            return

        # Refresh values before PI step
        grid   = self._flt(cfg.get(CONF_GRID_POWER_SENSOR, ''))
        solar  = self._flt(cfg.get(CONF_SOLAR_POWER_SENSOR, ''))
        actual = self._flt(cfg.get(CONF_ACTUAL_POWER_SENSOR, ''))
        mode   = self._get_mode()

        # ── Step 1: Discharge current ─────────────────────────────────────────────────
        await self._step_discharge_current(cfg, mode)

        # ── Step 2: Timeout-Reset ─────────────────────────────────────────────────────
        if countdown < 120:
            await self._timer_toggle()

        # ── Step 3: Output + Integral ─────────────────────────────────────────────────
        await self._step_pi_output(cfg, grid, solar, actual, mode)
