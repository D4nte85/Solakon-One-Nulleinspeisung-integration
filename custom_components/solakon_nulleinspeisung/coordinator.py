"""Coordinator — vollständige Nulleinspeisung-Regellogik mit Schreibguard."""
from __future__ import annotations

import asyncio
import logging
import time
from operator import attrgetter
from typing import Any, Callable, Iterable, NamedTuple

from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .display import Display
from .dynamic_offset import DynamicOffset
from .feature_sensors import effective_sensor, feature_values, tariff_price
from .i18n import Msg, translate, translate_msgs
from .paths import FIXED, IDLE, PI_STEP, SETPOINT, STALL_CHECK, STALL_RESET, PathInputs, decide as decide_path
from .pi import PIController
from .readings import UNIT_SCALE_KWH, UNIT_SCALE_W, read_number, read_scaled, valid_state
from .grid_group import NetGroup, Shares
from .group_store import require_store
from .limits import PowerLimits, power_limits, pv_cap_reason
from .messages import CycleMessages
from .migrations import SolakonSettingsStore
from .output import Actual, Output, Stall
from .schema import (
    CycleSettings, InvalidSettings, check, couple_target, cycle_settings, notify_reset,
    sanitize, soc_conflict,
)
from .tariff import Tariff, TariffState
from .timeout import Timeout
from .trackers import Trackers
from .zones import (
    FlagUpdate, ForecastFlags, Night, Surplus, Transition, ZoneInputs, at_rest, charging_to_target, control_state, decide,
    forecast_flags, night_active, required_discharge, rest_mode,
)
from .const import (
    DOMAIN, SETTINGS_DEFAULTS, SETTINGS_SCHEMA, CONF_GRID_SENSOR,
    CONF_ACTUAL_SENSOR, CONF_SOLAR_SENSOR, CONF_SOC_SENSOR, CONF_TIMEOUT_COUNTDOWN,
    CONF_ACTIVE_POWER, CONF_DISCHARGE_CURRENT, CONF_TIMEOUT_SET, CONF_MODE_SELECT,
    CONF_EXPORT_LIMIT, MODE_DISABLED, MODE_DISCHARGE, MODE_AC_CHARGE, S_REGULATION_ENABLED,
    S_ZONE3_LIMIT, DEVICE_MAX_CURRENT,
    S_AC_SOC_TARGET, S_REST_IN_DISCHARGE, S_PI_ENABLED,
    S_TARGET_CHARGE_ENABLED, CHARGE_SESSION_KEY, CHARGE_SESSIONS, SESSION_AC, SESSION_NONE,
)

_LOGGER = logging.getLogger(__name__)


# Über Neustarts gespeicherte Zustandsflags: (Speicherschlüssel, Attributpfad, Default, erlaubte Werte).
# Ohne erlaubte Werte ist das Flag ein Bool; sonst gilt für jeden anderen gespeicherten Wert der Default.
PERSISTED_FLAGS = (
    ("cycle_active", "cycle_active", False, None),
    ("surplus_active", "surplus_active", False, None),
    ("solar_zero_entry_armed", "surplus.armed", True, None),
    (CHARGE_SESSION_KEY, "charge_session", SESSION_NONE, CHARGE_SESSIONS),
)

# Kernsensoren der Instanz: (Konfigschlüssel, Einheitenfaktoren, löst Regelzyklus aus, Pflicht für den Zyklus).
# Ist-Leistung und Leistungssollwert werden gepollt und lösen keinen Zyklus aus.
CORE_SENSORS = (
    (CONF_GRID_SENSOR, UNIT_SCALE_W, True, True),
    (CONF_SOLAR_SENSOR, UNIT_SCALE_W, True, True),
    (CONF_ACTUAL_SENSOR, UNIT_SCALE_W, False, True),
    (CONF_ACTIVE_POWER, {}, False, True),
    (CONF_SOC_SENSOR, {}, True, True),
    (CONF_MODE_SELECT, {}, True, False),
)
_CORE_SCALE = {key: scale for key, scale, _, _ in CORE_SENSORS}


class CoreValues(NamedTuple):
    """Kernsensoren zu Beginn eines Regelzyklus.

    `mode` ist 'unknown' und `mode_ok` False, wenn der Modus-Select keinen gültigen Zustand hat;
    `timer` ist 0 ohne Zahl.
    """

    soc: float
    grid: float
    solar: float
    actual: float
    mode: str
    timer: float
    mode_ok: bool


def read_required(hass: HomeAssistant, cfg: Any, keys: Iterable[str]) -> dict[str, float] | str:
    """Kernsensoren `keys` in ihrer Einheit lesen; die Entity-ID des ersten ohne Zahl statt der Werte."""
    values = {}
    for key in keys:
        value = read_scaled(hass, cfg[key], _CORE_SCALE[key]).value
        if value is None:
            return cfg[key]
        values[key] = value
    return values


def read_core(hass: HomeAssistant, cfg: Any) -> CoreValues | str:
    """Kernsensoren eines Regelzyklus; die Entity-ID des ersten Pflichtsensors ohne Zahl statt der Werte."""
    values = read_required(hass, cfg, [key for key, _, _, required in CORE_SENSORS if required])
    if isinstance(values, str):
        return values
    mode = valid_state(hass, cfg[CONF_MODE_SELECT])
    timer = read_number(hass, cfg[CONF_TIMEOUT_COUNTDOWN]).value
    return CoreValues(
        values[CONF_SOC_SENSOR], values[CONF_GRID_SENSOR], values[CONF_SOLAR_SENSOR], values[CONF_ACTUAL_SENSOR],
        mode.state if mode else "unknown", 0.0 if timer is None else timer, mode is not None,
    )


class SolakonCoordinator:
    """Zentrale Logik-Klasse — PI-Regler, SOC-Zonen, Modbus-Steuerung."""

    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        self.hass = hass
        self.entry = entry
        self.settings: dict[str, Any] = SETTINGS_DEFAULTS.copy()
        self.settings_rev = 0
        self._store = SolakonSettingsStore(hass, entry.entry_id)
        self._unsub_dist: Callable[[], None] | None = None

        # Laufzeit-Zustände
        self.display = Display(hass.config.language)
        self.last_action_key: str = ""
        self.last_action_params: dict = {}
        # Bausteine von last_error als (Schlüssel, Parameter), für andere Sprachen.
        self.last_error_msgs: list[Msg] = []
        self.pi = PIController()
        self.active_fall: str = ""

        # Boolsche Status-Flags
        self.cycle_active: bool = False
        self.surplus_active: bool = False
        # Art der Lade-Session, SESSION_NONE ohne Lade-Session.
        self.charge_session: str = SESSION_NONE
        # Aufladen des Zielladens: Zielladen an, SOC unter dem Ziel-SOC.
        self.charging_to_target: bool = False
        # Ruhezustand: Output 0 im Ruhemodus, keine PI-Regelung.
        self.resting: bool = False
        self.is_night: bool = False
        # Nacht-Vorstufe mit Dunkelheits-Hysterese.
        self.night = Night()
        # Entladung durch den Tarif gesperrt (Preis unter Teuer-Schwelle, keine
        # Lade-Session, kein Überschuss) — der Zustand hinter Fall TM.
        self.discharge_locked: bool = False
        # Zyklus an einem Guard abgebrochen (Kernsensor fehlt, SOC-Limits ungültig)
        self._cycle_blocked: bool = False

        # Zeitstempel
        self.last_action_ts: float = time.time()
        self.out = Output(
            lambda value: self._set_number(self.entry.data[CONF_ACTIVE_POWER], value),
            self._read_actual, self._warn_hardware,
        )

        self.dyn = DynamicOffset()

        # Multi-Instancing: zugeteiltes Leistungslimit (None = Einzelbetrieb)
        self.allocated_power: float | None = None
        # Verwertbarer PV-Überschuss: Luft zwischen aktuellem Output und dem
        # Minimum aus Hard-Limit und aktueller PV-Leistung.
        self.surplus_power: float = 0.0
        # Meldungen des laufenden Zyklus, von _end_cycle nach last_error_msgs übernommen.
        self._messages = CycleMessages()
        # Tariflage je Zyklus; hält den Verdacht auf eine EUR/kWh-Preiseinheit über Zyklen.
        self.tariff = Tariff()
        # Zuletzt angewandter Verteilungsmodus aus _apply_shares(); weicht bei
        # Degradation vom konfigurierten distribution_mode ab.
        self.dist_mode_effective: str = ""

        # Surplus-Vorstufe mit PV-0-Entprellung und voriger Ist-Leistung.
        self.surplus = Surplus()

        # Interne Mechanik
        self.timeout = Timeout(
            lambda value: self._set_number(self.entry.data[CONF_TIMEOUT_SET], value),
            lambda: self._flt(self.entry.data[CONF_TIMEOUT_SET], 3599),
            lambda: self._entity_ok(self.entry.data[CONF_TIMEOUT_COUNTDOWN]),
        )
        self._lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []
        self.trackers = Trackers(
            hass, lambda: self.settings, self._effective, self._on_trigger,
            lambda: [self.entry.data.get(key, "") for key, _, triggers, _ in CORE_SENSORS if triggers],
        )
        # Prognoselage des letzten Regelzyklus.
        self.forecast = ForecastFlags(False, False, False)

    # ── Lesen: Settings ──────────────────────────────────────────────────────

    def _setting(self, key: str, cast: Callable[[Any], Any]) -> Any:
        """Setting typisiert lesen; `self.settings` ist stets mit SETTINGS_DEFAULTS gefüllt."""
        return cast(self.settings[key])

    @property
    def _regulation_on(self) -> bool:
        """Regelung aktiviert; Voraussetzung für jeden Schreibzugriff."""
        return self._setting(S_REGULATION_ENABLED, bool)

    # ── Lesen: Sensoren ──────────────────────────────────────────────────────

    def _read_scaled(self, entity_id: str, default: float, scale: dict[str, float]) -> float:
        """Zahl lesen und mit dem Faktor ihrer Einheit aus `scale` multiplizieren.

        Einheiten ohne Eintrag bleiben unverändert; ohne Zahl `default`.
        """
        value = read_scaled(self.hass, entity_id, scale).value
        return default if value is None else value

    def _flt(self, entity_id: str, default: float = 0.0) -> float:
        """Zahl ohne Einheitenumrechnung lesen."""
        return self._read_scaled(entity_id, default, {})

    def _flt_power(self, entity_id: str, default: float = 0.0) -> float:
        """Leistung in W lesen (kW ×1000)."""
        return self._read_scaled(entity_id, default, UNIT_SCALE_W)

    def _flt_kwh_normalized(self, entity_id: str, default: float | None = 0.0) -> float | None:
        """Energie in kWh lesen (Wh ÷1000, MWh ×1000).

        Ohne erkannte Energie-Einheit (z. B. input_number ohne Einheit) bleibt der
        Rohwert unverändert, wie es der kWh-Vertrag der Schwellenfelder vorsieht.
        """
        return self._read_scaled(entity_id, default, UNIT_SCALE_KWH)

    def _str(self, entity_id: str) -> str:
        """State als String lesen, 'unknown' bei Fehler."""
        state = valid_state(self.hass, entity_id)
        return state.state if state else "unknown"

    def _entity_ok(self, entity_id: str) -> bool:
        """Prüft ob Entity verfügbar und nicht unknown/unavailable ist."""
        return valid_state(self.hass, entity_id) is not None

    def _read_actual(self) -> Actual:
        """Schnappschuss des Ist-Sensors für die Ausgangsleistung."""
        eid = self.entry.data.get(CONF_ACTUAL_SENSOR, "")
        state = self.hass.states.get(eid)
        return Actual(
            self.actual_power(), self._entity_ok(eid),
            state.last_updated.timestamp() if state is not None else None,
        )

    # ── Lesen: Sensor-Vorgaben ───────────────────────────────────────────────

    def _effective(self, name: str) -> str:
        """Wirksamer Sensor der Vorgabe `name` für diese Instanz und die aktuelle Stunde."""
        return effective_sensor(name, self.settings, self.group.dist_cfg(), dt_util.now().hour)

    # ── Lesen: Netzgruppe ────────────────────────────────────────────────────

    @property
    def group(self) -> NetGroup:
        """Netzgruppe dieser Instanz aus dem Register."""
        return require_store(self.hass).group(self.grid_sensor)

    @property
    def member_id(self) -> str:
        """Kennung in der Netzgruppe: die entry_id."""
        return self.entry.entry_id

    @property
    def grid_sensor(self) -> str:
        """Netzsensor der Instanz; er bestimmt die Netzgruppe."""
        return self.entry.data.get(CONF_GRID_SENSOR, "")

    @property
    def regulating(self) -> bool:
        """Regelung aktiviert."""
        return self._regulation_on

    def in_discharge_pool(self) -> bool:
        """Regelung an, Modus '1' und nicht darin ruhend."""
        if not self._regulation_on:
            return False
        mode = self._str(self.entry.data.get(CONF_MODE_SELECT, ""))
        return mode == MODE_DISCHARGE and not self._at_rest(MODE_DISCHARGE)

    def soc_reading(self) -> float | None:
        """SOC-Sensor dieser Instanz; `None`, wenn er nicht verfügbar ist."""
        soc_eid = self.entry.data.get(CONF_SOC_SENSOR, "")
        if not self._entity_ok(soc_eid):
            return None
        return self._flt(soc_eid, 0)

    def hard_limit(self) -> float:
        """Hard-Limit der aktuellen Zone (Zone 0 bei Überschuss, sonst Zone 1/2), gedeckelt auf die Gerätegrenze."""
        return float(power_limits(cycle_settings(self.settings), None).zone_max(self.surplus_active))

    def zone3_limit(self) -> float:
        """SOC-Grenze der Zone 3 in % aus den Settings."""
        return self._setting(S_ZONE3_LIMIT, float)

    def ac_soc_target(self) -> float:
        """SOC-Ziel des AC-Ladens in % aus den Settings."""
        return self._setting(S_AC_SOC_TARGET, float)

    def capacity_kwh(self, entity_id: str) -> float | None:
        """Kapazität aus `entity_id` in kWh; None ohne Zahl."""
        return self._flt_kwh_normalized(entity_id, None)

    def actual_power(self) -> float:
        """Ist-Leistung in W."""
        return self._flt_power(self.entry.data.get(CONF_ACTUAL_SENSOR, ""))

    def output_setpoint(self) -> float:
        """Gesetzte Ausgangsleistung."""
        return self._flt(self.entry.data.get(CONF_ACTIVE_POWER, ""))

    def live_values(self) -> dict[str, float | None]:
        """Netz, Ist-Leistung und PV in W, SOC in %; ohne Zahl `None`."""
        cfg = self.entry.data
        return {
            "grid": self._flt_power(cfg.get(CONF_GRID_SENSOR, ""), None),
            "actual_power": self._flt_power(cfg.get(CONF_ACTUAL_SENSOR, ""), None),
            "solar": self._flt_power(cfg.get(CONF_SOLAR_SENSOR, ""), None),
            "soc": self._flt(cfg.get(CONF_SOC_SENSOR, ""), None),
        }

    # ── Ableiten: Regelzustand ───────────────────────────────────────────────

    @property
    def _control_state(self) -> str:
        """Regelzustand der Instanz laut `zones.control_state`."""
        return control_state(self.surplus_active, self.charge_session, self.cycle_active)

    def _at_rest(self, mode: str) -> bool:
        """Ruht die Instanz in `mode`, laut `zones.at_rest`."""
        return at_rest(mode, self._setting(S_REST_IN_DISCHARGE, bool), self.resting)

    def _persisted_flags(self) -> dict[str, Any]:
        """Gespeicherte Zustandsflags unter ihrem Speicherschlüssel."""
        return {key: attrgetter(attr)(self) for key, attr, _, _ in PERSISTED_FLAGS}

    def _store_data(self) -> dict:
        """Speicherinhalt: Settings plus gespeicherte Zustandsflags."""
        return {**self.settings, **self._persisted_flags()}

    # ── Ableiten: Verteilung ─────────────────────────────────────────────────

    def _apply_shares(self, shares: Shares | None) -> Msg | None:
        """Angewandten Verteilungsmodus übernehmen; liefert die Degradierungswarnung dieser Rechnung."""
        if shares is None:
            return None
        if shares.mode is not None:
            self.dist_mode_effective = shares.mode
        return (shares.warning, {}) if shares.warning else None

    # ── Darstellen: Texte ────────────────────────────────────────────────────

    def _tr(self, key: str, **params: object) -> str:
        """Textbaustein in der Sprache der Home-Assistant-Instanz."""
        return translate(self.hass.config.language, key, **params)

    def _set_last_action(self, key: str, **params: object) -> None:
        """Setzt Schlüssel, Parameter und Zeitstempel der letzten Aktion."""
        self.last_action_key = key
        self.last_action_params = params
        self.last_action_ts = time.time()

    @property
    def last_action(self) -> str:
        """Letzte Aktion in der Instanzsprache."""
        return self.status_texts(self.hass.config.language)["last_action"]

    @property
    def last_error(self) -> str:
        """Fehlerkette in der Instanzsprache."""
        return self.status_texts(self.hass.config.language)["last_error"]

    def status_texts(self, language: str) -> dict[str, str]:
        """Letzte Aktion und Fehlerkette in `language`."""
        return {
            "last_action": (translate(language, self.last_action_key, **self.last_action_params)
                            if self.last_action_key else ""),
            "last_error": translate_msgs(language, self.last_error_msgs),
        }

    # ── Darstellen: Anzeigezustand ───────────────────────────────────────────

    def _update_display(self, soc: float, zone3: float, mode: str) -> bool:
        """Anzeigezone, Modus und Betriebszustand nachziehen; True bei Wechsel des Betriebszustands."""
        self.display.update(
            self.hass.config.language, soc, zone3, mode, self._at_rest(mode),
            self.surplus_active, self.cycle_active, self._regulation_on,
        )
        return self._update_operating_state()

    def _update_operating_state(self) -> bool:
        """Betriebszustand aus den Zustandsflags nachziehen; True bei Wechsel."""
        return self.display.update_state(
            self._regulation_on, self._cycle_blocked, self._control_state, self.discharge_locked, self.is_night,
            self._setting(S_TARGET_CHARGE_ENABLED, bool), self.charging_to_target,
        )

    def offset_zone(self, night_enabled: bool) -> str:
        """Offsetzone des Regelzustands; Nacht-Offset bei Dunkelheit, wenn `night_enabled`."""
        night = self.night.dark and night_enabled
        return DynamicOffset.zone_of(self.charge_session == SESSION_AC, self.cycle_active, night)

    # ── Darstellen: Entity-Listener ──────────────────────────────────────────

    def register_entity_listener(self, cb: Callable[[], None]) -> None:
        """Callback anmelden, den `notify_listeners` aufruft."""
        self._listeners.append(cb)

    def unregister_entity_listener(self, cb: Callable[[], None]) -> None:
        """Callback abmelden; ein unbekannter Callback wird ignoriert."""
        if cb in self._listeners:
            self._listeners.remove(cb)

    def notify_listeners(self) -> None:
        """Alle Callbacks aufrufen; eine Exception wird geloggt, die übrigen laufen weiter."""
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                _LOGGER.exception("Solakon: Fehler in Entity-Listener")

    # ── Schreiben: Gerät ─────────────────────────────────────────────────────

    async def _set_number(
        self, entity_id: str, value: float, only_if_changed: bool = False,
        current: float | None = None,
    ) -> bool:
        """number.set_value — nur wenn Regulation aktiviert; True wenn geschrieben.

        `only_if_changed` schreibt nur bei Abweichung über 0,5 vom Ist-Wert. Der Ist-Wert
        ist `current` oder wird gelesen (fehlend: -1).
        """
        if not self._regulation_on:
            return False
        if only_if_changed:
            if current is None:
                current = self._flt(entity_id, -1)
            if abs(current - value) <= 0.5:
                return False
        await self.hass.services.async_call(
            "number", "set_value",
            {"entity_id": entity_id, "value": value},
        )
        return True

    async def _set_mode(self, mode: str) -> None:
        """select.select_option — nur wenn Regulation aktiviert."""
        if not self._regulation_on:
            return
        await self.hass.services.async_call(
            "select", "select_option",
            {"entity_id": self.entry.data[CONF_MODE_SELECT], "option": mode},
        )

    async def _set_discharge(self, amps: float) -> None:
        """Entladestrom setzen — nur wenn aktueller Wert abweicht."""
        await self._set_number(self.entry.data[CONF_DISCHARGE_CURRENT], amps, only_if_changed=True)

    async def _sync_export_limit(self, target: int) -> None:
        """grid_export_power_limit korrigieren wenn von Soll abgewichen — nur wenn Entity konfiguriert."""
        export_entity = self.entry.data.get(CONF_EXPORT_LIMIT, "")
        if not export_entity:
            return
        current = self._flt(export_entity, -1)
        if await self._set_number(export_entity, target, only_if_changed=True, current=current):
            _LOGGER.info("Solakon: Export-Limit korrigiert %d → %d W", int(current), target)

    # ── Schreiben: Ausgangsleistung ──────────────────────────────────────────

    def _warn_hardware(self, key: str, params: dict, log_suffix: str = "") -> None:
        """Schreibwarnung in die Fehlerkette des laufenden Regelzyklus und ins Log; `log_suffix` nur im Log."""
        self._messages.hardware((key, params))
        _LOGGER.error("Solakon: %s%s", self._tr(key, **params), log_suffix)

    async def _handle_output_stall(self, limit: float, rest_in_discharge: bool) -> bool:
        """Stillstand prüfen und das Urteil umsetzen; True, wenn ein Urteil die letzte Aktion gesetzt hat.

        `REWRITTEN` setzt nur die letzte Aktion. `RECOVERY`: Schreibwarnung,
        Integral-Reset, Output 0, Timer-Toggle, Ruhezustand im Ruhemodus laut
        `rest_in_discharge` — mit aktivem Zyklus holt Fall D im Folgezyklus zurück.
        """
        verdict = await self.out.check_stall(limit)
        if verdict is None:
            return False
        stall, actual = verdict
        if stall is Stall.REWRITTEN:
            self._set_last_action("act_output_rewritten", actual=actual, limit=limit)
            return True
        self._warn_hardware("warn_output_stuck", {"actual": actual, "limit": limit},
                            f" (Versuch {self.out.stall_actions})")
        await self._transition(Transition(reset_integral=True, output=0, mode=rest_mode(rest_in_discharge), rest=True))
        self._set_last_action("act_output_recovery", actual=actual, limit=limit)
        return True

    async def _set_fixed_output(
        self, target: float, current: float, action_key: str, ac_charge_mode: bool = False,
    ) -> None:
        """Fester Sollwert: schreibt nur bei Abweichung über 0,5 vom kommandierten Ist-Wert."""
        if abs(current - target) > 0.5:
            self._set_last_action(action_key, power=target)
            await self.out.set_and_wait(target, ac_charge_mode=ac_charge_mode)

    # ── Schreiben: Zustandsübergang und Integral ─────────────────────────────

    async def _transition(self, t: Transition) -> None:
        """Zustandsübergang in fester Folge: Integral, Flags, Output, Timer, Modus (siehe `zones.Transition`).

        `flags` setzt nur die Zustandsflags, die nicht None sind. Jeder geschriebene Modus
        setzt `resting` auf `t.rest`.
        """
        if t.reset_integral:
            self.pi.reset()
        if t.flags is not None:
            if t.flags.cycle_active is not None:
                self.cycle_active = t.flags.cycle_active
            if t.flags.surplus_active is not None:
                self.surplus_active = t.flags.surplus_active
            if t.flags.session is not None:
                self.charge_session = t.flags.session
        if t.timer and t.timer_first:
            await self.timeout.toggle()
        if t.output is not None:
            if t.wait:
                await self.out.set_and_wait(t.output, ac_charge_mode=t.ac_charge_mode)
            else:
                await self.out.set(t.output)
        if t.timer and not t.timer_first:
            await self.timeout.toggle()
        if t.mode is not None:
            self.resting = t.rest
            await self._set_mode(t.mode)

    @property
    def integral(self) -> float:
        """Integralanteil des PI-Reglers."""
        return self.pi.integral

    @integral.setter
    def integral(self, value: float) -> None:
        """Integralanteil des PI-Reglers setzen."""
        self.pi.integral = value

    async def async_reset_integral(self) -> None:
        """Unter dem Lock: Integral nullen, als letzte Aktion vermerken, Listener benachrichtigen."""
        async with self._lock:
            self.pi.reset()
            self._set_last_action("act_integral_reset")
            self.notify_listeners()

    async def async_set_cycle(self, active: bool) -> None:
        """Unter dem Lock: Zyklus über `_transition` setzen (Integral nullen, Timer-Toggle), speichern, benachrichtigen; danach Regelzyklus anstoßen."""
        async with self._lock:
            await self._transition(Transition(reset_integral=True, flags=FlagUpdate(cycle_active=active)))
            self.schedule_save()
            self.notify_listeners()
        self.request_regulation()

    # ── Lebenszyklus: Setup und Settings ─────────────────────────────────────

    async def async_setup(self) -> None:
        """Settings und Zustandsflags laden, Trigger registrieren.

        Gespeicherte Werte, die das Schema verletzen, und eine unbekannte Art der Lade-Session
        werden durch den Standard ersetzt, zurückgespeichert und per Benachrichtigung gemeldet.
        """
        stored = await self._store.async_load()
        if stored:
            stored, reset = sanitize(stored, SETTINGS_SCHEMA)
            self.settings = {**SETTINGS_DEFAULTS, **stored}
            for key, attr, default, allowed in PERSISTED_FLAGS:
                value = stored.get(key, default)
                if allowed is None:
                    value = bool(value)
                elif value not in allowed:
                    reset.append((key, value, default))
                    value = default
                owner, _, name = attr.rpartition(".")
                setattr(attrgetter(owner)(self) if owner else self, name, value)
            if reset:
                notify_reset(self.hass, f"{DOMAIN}_settings_reset_{self.entry.entry_id}", self.entry.title, reset)
                await self._store.async_save(self._store_data())
            _LOGGER.debug("Solakon: Einstellungen aus Speicher geladen")
        else:
            self.settings = SETTINGS_DEFAULTS.copy()
            _LOGGER.info("Solakon: Standardwerte geladen")

        self.trackers.start()
        self._unsub_dist = require_store(self.hass).listen_dist(self.grid_sensor, self.apply_group_change)

    async def async_shutdown(self) -> None:
        """Listener abräumen, ausstehendes Speichern sofort schreiben."""
        self.trackers.stop()
        if self._unsub_dist is not None:
            self._unsub_dist()
            self._unsub_dist = None
        await self._store.async_write_pending()

    async def async_update_settings(self, changes: dict[str, Any]) -> None:
        """Änderungen prüfen, mit der Kopplung von Zielladen und Regelung übernehmen und speichern.

        Läuft unter dem Lock: wartet einen laufenden Regelzyklus ab, damit dieser Settings,
        `resting` und Integral nicht mitten im Zyklus wechseln sieht.

        InvalidSettings, wenn eine Änderung das Schema verletzt.
        """
        if findings := check(changes, SETTINGS_SCHEMA):
            raise InvalidSettings(findings)
        async with self._lock:
            changes = couple_target(self.settings, changes)
            turning_off = (
                self._regulation_on
                and S_REGULATION_ENABLED in changes
                and not changes[S_REGULATION_ENABLED]
            )
            if turning_off:
                await self._disable_regulation()

            with self.trackers.refreshing():
                if S_REST_IN_DISCHARGE in changes and changes[S_REST_IN_DISCHARGE] != self._setting(S_REST_IN_DISCHARGE, bool):
                    self.resting = False
                if S_PI_ENABLED in changes and changes[S_PI_ENABLED] != self._setting(S_PI_ENABLED, bool):
                    self.pi.reset()
                self.settings.update(changes)
                await self._save_settings()
                _LOGGER.info("Solakon: Einstellungen gespeichert")

        self.notify_listeners()

        # Neuen Zustand sofort anwenden
        if self._regulation_on:
            self.request_regulation()

    async def _disable_regulation(self) -> None:
        """Regelung abschalten: erst der Abschaltpfad, dann `S_REGULATION_ENABLED` aus.

        Die Reihenfolge ist fest, weil `_set_number` und `_set_mode` bei ausgeschalteter
        Regelung jeden Schreibbefehl sperren. Speichern übernimmt der Aufrufer mit `_save_settings`.
        """
        await self._switch_off_sequence()
        self.settings[S_REGULATION_ENABLED] = False

    async def _save_settings(self) -> None:
        """Settings-Revision erhöhen und Settings samt Zustandsflags sofort speichern."""
        self.settings_rev += 1
        await self._store.async_save(self._store_data())

    async def _switch_off_sequence(self) -> None:
        """Abschaltpfad bei noch aktiver Regelung: neue Fehlerkette, Output 0, Entladestrom auf Gerätemaximum, Modus '0'."""
        self._messages = CycleMessages()
        _LOGGER.info("Solakon: Regelung wird deaktiviert — setze Output 0, Modus Disabled")
        await self._transition(Transition(output=0, wait=False, timer=False))
        await self._set_discharge(DEVICE_MAX_CURRENT)
        await self._transition(Transition(mode=MODE_DISABLED))
        self.display.set_mode("disabled_regulation_off", self.hass.config.language)

    def schedule_save(self) -> None:
        """Settings und Zustandsflags nach 5 s speichern."""
        self._store.async_delay_save(self._store_data, 5)

    # ── Lebenszyklus: Trigger ────────────────────────────────────────────────

    def apply_group_change(self) -> None:
        """Nach geänderter Verteilung der Netzgruppe: Trigger neu anmelden, Regelzyklus anstoßen."""
        self.trackers.refresh_sensors()
        self.request_regulation()

    def request_regulation(self) -> None:
        """Regelzyklus als Task anstoßen."""
        self.hass.async_create_task(self._async_regulate())

    # ── Ausführung: Regelzyklus ──────────────────────────────────────────────

    @callback
    def _on_trigger(self, _event: object) -> None:
        """Trigger aus `Trackers` (Zustandsänderung oder Intervall): Regelzyklus anstoßen."""
        self.request_regulation()

    async def _async_regulate(self) -> None:
        """Regelzyklus unter dem Lock; läuft bereits einer, entfällt dieser Aufruf.

        Eine Exception wird geloggt und beendet nur diesen Zyklus.
        """
        if self._lock.locked():
            return
        async with self._lock:
            try:
                await self._run_regulation_cycle()
            except Exception:
                _LOGGER.exception("Solakon: Fehler in Regelschleife")

    async def _run_regulation_cycle(self) -> None:
        """Ein Regelzyklus, aufgerufen unter dem Lock von `_async_regulate`.

        Liest die Sensoren, rechnet Verteilung, Grenzen, Prognoseflags und Tariflage, führt
        den fälligen Fall aus, gleicht den Entladestrom ab und regelt in Modus '1' oder '3'
        die Ausgangsleistung. Regelung aus, ein Kernsensor ohne Zahl oder ungültige
        Settings beenden den Zyklus vorzeitig über `_end_cycle`.
        """
        cfg = self.entry.data
        # Wirksamer Sensor kann ohne Settings-Änderung wechseln (Stunde, Verteilung).
        self.trackers.refresh_changed()

        # ── 0. Regelung aktiv? ───────────────────────────────────────────────
        if not self._regulation_on:
            soc = self.soc_reading()
            mode = self._str(cfg[CONF_MODE_SELECT])
            display = None if soc is None or mode == "unknown" else (soc, self.zone3_limit(), mode)
            self._end_cycle(display=display, notify_on_change=True)
            return

        self.timeout.start_cycle()
        self._messages = CycleMessages()
        self._cycle_blocked = False

        prev_flags = self._persisted_flags()

        # ── 1. Kernsensoren lesen ────────────────────────────────────────────
        # Pflichtsensoren müssen eine Zahl liefern
        core = read_core(self.hass, cfg)
        if isinstance(core, str):
            _LOGGER.debug("Solakon: Kernsensor %s ohne Zahlenwert, Zyklus übersprungen", core)
            self._messages.fail(("err_core_sensor", {"sensor": core}))
            self._end_cycle(blocked=True, notify_on_change=True)
            return
        soc, grid, solar, actual, mode, timer_val = core[:6]

        # ── 2. StdDev und dynamische Offsets ─────────────────────────────────
        # StdDev ist eine Eigenschaft der Netzgruppe, nicht der einzelnen Instanz:
        # nur der Gruppen-Leader nimmt in den σ-Puffer auf, alle Instanzen übernehmen
        # σ aus der Netzgruppe.
        cs = cycle_settings(self.settings)
        if self.group.leader() is self:
            self.group.sigma.record(grid, time.monotonic(), cs.stddev_window, cs.stddev_trim)
        self.dyn.update(self.group.sigma, cs.offsets)

        # ── 3. Settings und Feature-Sensoren ─────────────────────────────────
        self.out.begin_cycle(cs.wait_time, cs.self_adjust, cs.self_adjust_tol)
        ac_offset = self.dyn.value("ac", cs.offsets)

        tariff_sensor = self._effective("tariff")
        feature, feature_warnings = feature_values(
            self.hass, cs, self.settings, self.group.dist_cfg(), dt_util.now().hour,
        )
        for warning in feature_warnings:
            self._messages.warn(warning)

        # ── 4. Verteilung und Leistungsgrenzen ───────────────────────────────
        error_share, allocated_power, shares = self.group.distribution(self, soc)
        self.allocated_power = allocated_power
        if dist_warning := self._apply_shares(shares):
            self._messages.warn(dist_warning)
        limits = power_limits(cs, allocated_power)

        # Nutzt die Zone des vorherigen Zyklus — self.surplus_active ist hier noch
        # nicht aktualisiert.
        self.surplus_power = limits.surplus_power(self.surplus_active, solar, actual)

        # ── 5. Prognoseflags und Prognose-Unterdrückung ──────────────────────
        self.forecast = forecast_flags(cs, feature, solar, soc)

        self.tariff.forecast(feature["pv_forecast"], cs)

        # ── 6. Validierung ───────────────────────────────────────────────────
        invalid = soc_conflict(cs) or (None if core.mode_ok else "err_mode_select")
        if invalid:
            self._messages.fail((invalid, {}))
            self._end_cycle(blocked=True)
            return

        # ── 7. Export-Limit und Tariflage ────────────────────────────────────
        await self._sync_export_limit(limits.export)

        price, unit, price_warning = tariff_price(self.hass, cs.tariff_enabled, tariff_sensor)
        tariff = self.tariff.assess(
            cs, price=price, unit=unit, price_warning=price_warning,
            cheap_entity=feature["cheap"], exp_entity=feature["exp"], now=time.time(),
        )
        for warning in tariff.warnings:
            self._messages.warn(warning)

        # ── 8. Überschuss und Nacht ──────────────────────────────────────────
        total_actual = self.group.discharge_actual(self, actual)
        total_output = self.group.discharge_output(self, actual, self.output_setpoint())

        new_surplus = self.surplus.step(
            surplus_enabled=cs.surplus_enabled, surplus_active=self.surplus_active,
            forced=self.forecast.surplus_forced, exit_lock=self.forecast.exit_lock,
            solar=solar, soc=soc, actual=actual, total_actual=total_actual,
            total_output=total_output,
            grid=grid, error_share=error_share,
            in_pool=self.in_discharge_pool(),
            surplus_threshold=cs.surplus_threshold,
            surplus_soc_hyst=cs.surplus_soc_hyst, surplus_pv_hyst=cs.surplus_pv_hyst,
        )
        is_night = self.night.step(
            solar=solar, cycle_active=self.cycle_active, pv_reserve=cs.pv_reserve,
            night_hysteresis=cs.night_hysteresis, night_enabled=cs.night_enabled,
        )
        self.is_night = is_night
        self.charging_to_target = charging_to_target(cs.target_enabled, soc, cs.target_soc)

        # ── 9. Falls / Zonenwechsel ──────────────────────────────────────────
        fall_executed = await self._execute_falls(
            cs, soc=soc, grid=grid, actual=actual, mode=mode, new_surplus=new_surplus,
            ac_offset=ac_offset, tariff=tariff, is_night=is_night, total_output=total_output,
        )
        if fall_executed:
            self.active_fall = fall_executed
        # Fall ZE hat die Regelung abgeschaltet: Entladepause.
        if not self._regulation_on:
            self._end_cycle()
            return

        # Zustand hinter Fall TM: die Sperre selbst mit den Flags nach den Falls,
        # nicht ihr Auslöser. Ebenso die Nachtabschaltung mit dem Zyklus nach den Falls.
        self.discharge_locked = tariff.discharge_locked(self.charge_session != SESSION_NONE, self.surplus_active)
        self.is_night = night_active(night_enabled=cs.night_enabled, dark=self.night.dark,
                                     cycle_active=self.cycle_active)

        # ── 10. Entladestrom mit Regelzustand abgleichen ─────────────────────
        mode = self._str(cfg[CONF_MODE_SELECT])
        await self._set_discharge(required_discharge(self._control_state, mode, cs.discharge_max))

        # ── 11. PI-Phase (Modus '1' und '3') ─────────────────────────────────
        blocked = False
        if mode in (MODE_DISCHARGE, MODE_AC_CHARGE):
            blocked = await self._run_pi_phase(cs, soc, mode, timer_val, error_share, limits, ac_offset)

        # ── 12. Anzeige und Flag-Speicherung ─────────────────────────────────
        self._end_cycle(blocked=blocked, display=(soc, cs.zone3_limit, mode),
                        prev_flags=prev_flags)

    async def _execute_falls(
        self, cs: CycleSettings, *, soc: float, grid: float, actual: float, mode: str,
        new_surplus: bool, ac_offset: float, tariff: TariffState, is_night: bool, total_output: float,
    ) -> str | None:
        """Fall per `zones.decide` bestimmen, Übergang und Aktionstext ausführen, Kennung zurückgeben.

        Ein Fall mit `regulation_off` fährt danach den Abschaltpfad und speichert die Regelung als aus.
        """
        d = decide(ZoneInputs(
            cs=cs, soc=soc, grid=grid, actual=actual, total_output=total_output, mode=mode,
            new_surplus=new_surplus, ac_offset=ac_offset, tariff=tariff, is_night=is_night,
            zone1_forced=self.forecast.zone1_forced, charging_to_target=self.charging_to_target,
            surplus_active=self.surplus_active,
            session=self.charge_session,
            cycle_active=self.cycle_active,
            at_rest=at_rest(mode, cs.rest_in_discharge, self.resting),
        ))
        if d is None:
            return None
        await self._transition(d.transition)
        self._set_last_action(d.action, **d.params)
        if d.regulation_off:
            await self._disable_regulation()
            await self._save_settings()
        return d.name

    async def _run_pi_phase(
        self, cs: CycleSettings, soc: float, mode: str, timer_val: float, error_share: float,
        limits: PowerLimits, ac_offset: float,
    ) -> bool:
        """PI-Phase in Modus '1' oder '3': Timeout-Reset, dann ein Pfad je Regelzustand.

        Pfade laut `paths.decide`: Zone-0-Festwert, AC-Stellwert, Tarif- oder Netz-Lade-Festwert
        oder Entladen (PI-Schritt oder Stellwert) mit Stillstandsprüfung.
        Im Ruhemodus endet die Phase nach dem Timeout-Reset. Liefert die Zweitlesung von
        Netz oder PV keine Zahl, endet sie mit `err_core_sensor` ohne Schreibbefehl.
        True, wenn der Regelzyklus damit blockiert ist.
        """
        cfg = self.entry.data

        # ── 11a. Timeout-Reset ───────────────────────────────────────────────
        # Entfällt wenn ein Fall in diesem Zyklus bereits getoggelt hat
        await self.timeout.reset_if_due(timer_val)

        if at_rest(mode, cs.rest_in_discharge, self.resting):
            return False

        # ── 11b. Zweitlesung nach den Falls ──────────────────────────────────
        second = read_required(self.hass, cfg, (CONF_GRID_SENSOR, CONF_SOLAR_SENSOR))
        if isinstance(second, str):
            self._messages.fail(("err_core_sensor", {"sensor": second}))
            return True
        grid, solar = second[CONF_GRID_SENSOR], second[CONF_SOLAR_SENSOR]

        # Eine Energierichtung je Netzgruppe: lädt eine Schwester, entlädt Zone 1 nur PV.
        # Ebenso beim Aufladen mit Hausvorrang.
        cap_reason = pv_cap_reason(self.group.sister_charging(self), self.charging_to_target, cs.battery_priority)
        target_offset = self.dyn.value(self.offset_zone(cs.z1_night_enabled), cs.offsets)

        # Ausgangsleistung nach dem letzten Await vor der Pfadwahl; Basis für Gate,
        # PI-Basis und Aktionstext.
        current_power = self._flt(cfg[CONF_ACTIVE_POWER])
        # Ist-Leistung als Basis der Stellwertrechnung, im AC-Laden negativ.
        actual = self.actual_power()

        # Eigener Pool für AC-Laden, nach den Falls berechnet.
        ac_error_share, shares = self.group.ac_share(self, soc)
        if dist_warning := self._apply_shares(shares):
            self._messages.warn(dist_warning)

        # ── 11c. PI-Pfade ────────────────────────────────────────────────────
        d = decide_path(PathInputs(
            cs=cs, limits=limits, mode=mode, cycle_active=self.cycle_active,
            surplus_active=self.surplus_active, session=self.charge_session, cap_reason=cap_reason,
            grid=grid, solar=solar, current_power=current_power,
            ac_offset=ac_offset, target_offset=target_offset, ac_share=ac_error_share, share=error_share,
            ac_charge=-actual, ac_pool_charge=-self.group.ac_actual(self, actual),
            discharge=actual, discharge_pool=self.group.discharge_actual(self, actual),
            discharge_base=self.group.pi_base(self, current_power, error_share),
        ))
        if d.decay:
            self.pi.decay()
        stall_action = False
        if d.kind == IDLE:
            pass
        elif d.kind == FIXED:
            await self._set_fixed_output(d.value, current_power, d.action, ac_charge_mode=d.ac_charge_mode)
        elif d.kind == SETPOINT:
            self._set_last_action(d.action, frm=current_power, to=d.value)
            await self.out.set_and_wait(d.value, ac_charge_mode=d.ac_charge_mode)
        elif d.kind == PI_STEP:
            new_pw = self.pi.calculate(d.step, grid)
            self._set_last_action(d.step.action, frm=current_power, to=new_pw)
            await self.out.set_and_wait(new_pw)
        elif d.kind == STALL_CHECK:
            stall_action = await self._handle_output_stall(d.limit, cs.rest_in_discharge)
        elif d.kind == STALL_RESET:
            self.out.reset_stall()
        else:
            raise ValueError(f"unbekannte Pfadart {d.kind!r}")
        # Der Hinweis auf den PV-Deckel überschreibt keine Aktion der Stillstandsprüfung.
        if d.cap_note and not stall_action and self.last_action_key != f"act_zone1_{d.cap_note}":
            self._set_last_action(f"act_zone1_{d.cap_note}")
        return False

    def _end_cycle(
        self, *, blocked: bool = False,
        display: tuple[float, int, str] | None = None, prev_flags: dict[str, bool] | None = None,
        notify_on_change: bool = False,
    ) -> None:
        """Zyklus abschließen: Fehler, Anzeige, Flag-Speicherung, Benachrichtigung.

        Übernimmt die Meldungen des Zyklus nach `last_error_msgs`.
        `display` (soc, zone3, mode) zieht Zonen- und Modusanzeige nach, sonst nur
        den Betriebszustand. Mit `prev_flags` wird bei geänderten Flags verzögert gespeichert.
        `notify_on_change` benachrichtigt nur, wenn Meldungen, Anzeigezone, Modus oder
        Betriebszustand gewechselt haben.
        """
        shown = (self.last_error_msgs, self.display.zone, self.display.mode_key)
        self.last_error_msgs = self._messages.msgs
        if blocked:
            self._cycle_blocked = True
        if display is not None:
            changed = self._update_display(*display)
        else:
            changed = self._update_operating_state()
        changed = changed or shown != (self.last_error_msgs, self.display.zone, self.display.mode_key)
        if prev_flags is not None and self._persisted_flags() != prev_flags:
            self.schedule_save()
        if changed or not notify_on_change:
            self.notify_listeners()
