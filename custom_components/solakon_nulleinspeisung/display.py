"""Anzeigezustand der Instanz: Anzeigezone, Modus und Betriebszustand mit Labels und Zeitstempeln."""
from __future__ import annotations

import time

from .i18n import translate
from .const import MODE_AC_CHARGE, MODE_DISABLED, MODE_DISCHARGE

# Regelzustand → Betriebszustand. Laden liegt als Zustand über dem Entladezyklus.
OPERATING_BY_STATE = {
    "surplus": "exporting",
    "tariff_charge": "tariff_charging",
    "ac_charge": "ac_charging",
    "cycle": "battery_supply",
    "pv": "pv_direct",
}

# Modus des Wechselrichters → Schlüssel aus MODE_KEYS; andere Modi gelten als "unknown".
MODE_KEY_BY_MODE = {
    MODE_DISABLED: "disabled",
    MODE_DISCHARGE: "discharge",
    MODE_AC_CHARGE: "ac_charge",
}


class Display:
    """Anzeigezone, Modus und Betriebszustand, wie Panel und Sensoren sie zeigen."""

    def __init__(self, language: str) -> None:
        self.zone: int = 2
        self.zone_label: str = translate(language, "zone_init")
        self.mode_key: str = "waiting"
        self.mode_label: str = translate(language, "mode_waiting")
        self.mode_ts: float = time.time()
        # Schlüssel aus OPERATING_STATES; "" bis zum ersten Zyklus.
        self.operating_state: str = ""
        self.operating_state_ts: float = time.time()

    def set_mode(self, key: str, language: str, raw: str = "") -> None:
        """Modusschlüssel und Label setzen, Zeitstempel nur bei geändertem Schlüssel.

        Beim unbekannten Modus hängt `raw` am Label.
        """
        if key != self.mode_key:
            self.mode_ts = time.time()
        self.mode_key = key
        self.mode_label = translate(language, f"mode_{key}")
        if key == "unknown":
            self.mode_label = f"{self.mode_label}: {raw}"

    def update(
        self, language: str, soc: float, zone3_limit: int, mode: str, at_rest: bool,
        surplus_active: bool, cycle_active: bool,
    ) -> None:
        """Anzeigezone und Modus aus SOC, Flags und Modus des Wechselrichters.

        Zone 3 bei SOC ≤ zone3, sonst 0 bei Surplus, 1 bei Zyklus, sonst 2.
        Modus '1' im Ruhezustand zeigt `rest_discharge`.
        """
        if soc <= zone3_limit:
            self.zone = 3
        elif surplus_active:
            self.zone = 0
        elif cycle_active:
            self.zone = 1
        else:
            self.zone = 2
        self.zone_label = translate(language, f"zone_{self.zone}")

        key = MODE_KEY_BY_MODE.get(mode, "unknown")
        if mode == MODE_DISCHARGE and at_rest:
            key = "rest_discharge"
        self.set_mode(key, language, mode)

    def update_state(
        self, regulation_on: bool, blocked: bool, control: str, discharge_locked: bool, is_night: bool,
    ) -> bool:
        """Betriebszustand aus den Zustandsflags und der Anzeigezone; True bei Wechsel.

        Erster zutreffender Zustand gewinnt, Reihenfolge wie in OPERATING_STATES.
        Anders als `active_fall`, das den zuletzt ausgeführten Übergang hält,
        beschreibt der Zustand, was gerade gilt.
        """
        if not regulation_on:
            state = "disabled"
        elif blocked:
            state = "blocked"
        elif control in ("surplus", "tariff_charge", "ac_charge"):
            state = OPERATING_BY_STATE[control]
        elif discharge_locked:
            state = "discharge_locked"
        elif is_night:
            state = "night_off"
        elif control == "pv" and self.zone == 3:
            state = "safety_stop"
        else:
            state = OPERATING_BY_STATE[control]

        if state == self.operating_state:
            return False
        self.operating_state = state
        self.operating_state_ts = time.time()
        return True
