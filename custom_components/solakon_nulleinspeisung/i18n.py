"""Textbausteine für Zonen-, Modus-, Aktions- und Fehlermeldungen in DE und EN."""
from __future__ import annotations

DEFAULT_LANGUAGE = "en"

_TEXTS: dict[str, dict[str, str]] = {
    # ── Zonen-Label ──────────────────────────────────────────────────────────
    "zone_init": {
        "de": "Initialisierung…",
        "en": "Initialising…",
    },
    "zone_0": {
        "de": "Zone 0 — Überschuss-Einspeisung",
        "en": "Zone 0 — Surplus export",
    },
    "zone_1": {
        "de": "Zone 1 — Aggressive Entladung",
        "en": "Zone 1 — Aggressive discharge",
    },
    "zone_2": {
        "de": "Zone 2 — Batterieschonend",
        "en": "Zone 2 — Battery-friendly",
    },
    "zone_3": {
        "de": "Zone 3 — Sicherheitsstopp",
        "en": "Zone 3 — Safety stop",
    },

    # ── Modus-Label ──────────────────────────────────────────────────────────
    "mode_waiting": {
        "de": "Warten auf Daten",
        "en": "Waiting for data",
    },
    "mode_disabled": {
        "de": "Disabled (Fernsteuerung abgegeben)",
        "en": "Disabled (remote control released)",
    },
    "mode_discharge": {
        "de": "INV Discharge PV Priority (Entladen mit PV-Vorrang)",
        "en": "INV Discharge PV Priority (PV-first discharge)",
    },
    "mode_ac_charge": {
        "de": "AC Charge (Netzladung)",
        "en": "AC Charge (grid charging)",
    },
    "mode_disabled_regulation_off": {
        "de": "Disabled (Regelung inaktiv)",
        "en": "Disabled (control inactive)",
    },
    "mode_unknown": {
        "de": "Unbekannter Modus: {mode}",
        "en": "Unknown mode: {mode}",
    },

    # ── Letzte Aktion ────────────────────────────────────────────────────────
    "act_integral_reset": {
        "de": "Integral manuell zurückgesetzt",
        "en": "Integral reset manually",
    },
    "act_output_rewritten": {
        "de": "Ausgang {actual:.0f} W statt {limit:.0f} W — neu geschrieben",
        "en": "Output {actual:.0f} W instead of {limit:.0f} W — rewritten",
    },
    "act_output_recovery": {
        "de": "Ausgang {actual:.0f} W statt {limit:.0f} W — Recovery über Modus 0",
        "en": "Output {actual:.0f} W instead of {limit:.0f} W — recovery via mode 0",
    },
    "act_zone0_output": {
        "de": "Zone 0: Output → {power:.0f} W",
        "en": "Zone 0: output → {power:.0f} W",
    },
    "act_ac_pi": {
        "de": "AC-PI: {frm:.0f} → {to:.0f} W",
        "en": "AC PI: {frm:.0f} → {to:.0f} W",
    },
    "act_tariff_power": {
        "de": "Tarif-Laden: {power:.0f} W",
        "en": "Tariff charging: {power:.0f} W",
    },
    "act_pi": {
        "de": "PI: {frm:.0f} → {to:.0f} W",
        "en": "PI: {frm:.0f} → {to:.0f} W",
    },
    "act_surplus_on": {
        "de": "Zone 0: Surplus aktiviert",
        "en": "Zone 0: surplus activated",
    },
    "act_surplus_off": {
        "de": "Zone 0: Surplus beendet",
        "en": "Zone 0: surplus ended",
    },
    "act_fall_a_forced": {
        "de": "Fall A: Zone 1 Start forciert (SOC {soc:.0f}%, Vorhersage morgen gut)",
        "en": "Case A: Zone 1 start forced (SOC {soc:.0f}%, good forecast for tomorrow)",
    },
    "act_fall_a": {
        "de": "Fall A: Zone 1 Start (SOC {soc:.0f}%)",
        "en": "Case A: Zone 1 start (SOC {soc:.0f}%)",
    },
    "act_fall_b": {
        "de": "Fall B: Zone 3 Stop (SOC {soc:.0f}%)",
        "en": "Case B: Zone 3 stop (SOC {soc:.0f}%)",
    },
    "act_fall_c": {
        "de": "Fall C: Zone 3 Absicherung",
        "en": "Case C: Zone 3 safeguard",
    },
    "act_fall_d": {
        "de": "Fall D: Recovery",
        "en": "Case D: recovery",
    },
    "act_fall_e": {
        "de": "Fall E: Zone 2 Start",
        "en": "Case E: Zone 2 start",
    },
    "act_fall_f": {
        "de": "Fall F: Nachtabschaltung",
        "en": "Case F: night shutdown",
    },
    "act_fall_g": {
        "de": "Fall G: AC Laden Start",
        "en": "Case G: AC charging start",
    },
    "act_fall_h": {
        "de": "Fall H: AC Laden Ende",
        "en": "Case H: AC charging end",
    },
    "act_fall_i": {
        "de": "Fall I: Safety-Korrektur (Modus 3 ohne Session)",
        "en": "Case I: safety correction (mode 3 without session)",
    },
    "act_fall_gt": {
        "de": "Fall GT: Tarif-Laden (Preis {price:.1f})",
        "en": "Case GT: tariff charging (price {price:.1f})",
    },
    "act_fall_ht": {
        "de": "Fall HT: Tarif-Laden beendet",
        "en": "Case HT: tariff charging ended",
    },
    "act_fall_tm": {
        "de": "Tarif: Discharge-Lock (Preis {price:.1f})",
        "en": "Tariff: discharge lock (price {price:.1f})",
    },

    # ── Harte Fehler ─────────────────────────────────────────────────────────
    "err_soc_zone1_zone3": {
        "de": "SOC-Limits ungültig (Zone1 muss > Zone3)",
        "en": "SOC limits invalid (Zone 1 must be > Zone 3)",
    },
    "err_soc_surplus_zone1": {
        "de": "SOC-Limits ungültig (Überschuss-Schwelle muss > Zone1)",
        "en": "SOC limits invalid (surplus threshold must be > Zone 1)",
    },
    "err_soc_zone1_force": {
        "de": "SOC-Limits ungültig (Zone-1-Forcierung-Mindest-SOC muss zwischen Zone3 und Zone1 liegen)",
        "en": "SOC limits invalid (Zone 1 forcing minimum SOC must lie between Zone 3 and Zone 1)",
    },
    "err_soc_sensor": {
        "de": "SOC-Sensor nicht verfügbar",
        "en": "SOC sensor unavailable",
    },
    "err_mode_select": {
        "de": "Modus-Selektor nicht verfügbar",
        "en": "Mode selector unavailable",
    },

    # ── Weiche Fehler ────────────────────────────────────────────────────────
    "err_surplus_forecast_no_sensor": {
        "de": "Surplus-Forecast: Kein Vorhersage-Sensor konfiguriert — Funktion inaktiv",
        "en": "Surplus forecast: no forecast sensor configured — function inactive",
    },
    "err_surplus_forecast_sensor_unavailable": {
        "de": "Surplus-Forecast: Sensor {sensor!r} nicht verfügbar",
        "en": "Surplus forecast: sensor {sensor!r} unavailable",
    },
    "err_exit_lock_no_sensor": {
        "de": "Austritts-Sperre: Kein Leistungs-Vorhersage-Sensor konfiguriert — Funktion inaktiv",
        "en": "Exit lock: no power forecast sensor configured — function inactive",
    },
    "err_exit_lock_sensor_unavailable": {
        "de": "Austritts-Sperre: Sensor {sensor!r} nicht verfügbar",
        "en": "Exit lock: sensor {sensor!r} unavailable",
    },
    "err_pv_forecast_no_sensor": {
        "de": "PV-Vorhersage: Kein Sensor konfiguriert — Funktion inaktiv",
        "en": "PV forecast: no sensor configured — function inactive",
    },
    "err_pv_forecast_sensor_unavailable": {
        "de": "PV-Vorhersage: Sensor {sensor!r} nicht verfügbar",
        "en": "PV forecast: sensor {sensor!r} unavailable",
    },
    "err_zone1_force_no_sensor": {
        "de": "Zone-1-Forcierung: Kein PV-Vorhersage-Sensor konfiguriert — Funktion inaktiv",
        "en": "Zone 1 forcing: no PV forecast sensor configured — function inactive",
    },
    "err_zone1_force_sensor_unavailable": {
        "de": "Zone-1-Forcierung: Sensor {sensor!r} nicht verfügbar",
        "en": "Zone 1 forcing: sensor {sensor!r} unavailable",
    },
    "err_tariff_no_sensor": {
        "de": "Tarif: Kein Preis-Sensor konfiguriert — Tarif-Funktion inaktiv",
        "en": "Tariff: no price sensor configured — tariff function inactive",
    },
    "err_tariff_sensor_unavailable": {
        "de": "Tarif: Preis-Sensor {sensor!r} nicht verfügbar",
        "en": "Tariff: price sensor {sensor!r} unavailable",
    },

    # ── Warnungen aus Ausgangs-, Verteilungs- und Tarifprüfung ───────────────
    "warn_output_zero_unconfirmed": {
        "de": "Output-Nullung nach {attempts} Versuchen nicht bestätigt (Ist: {actual:.0f} W)",
        "en": "Output zeroing not confirmed after {attempts} attempts (actual: {actual:.0f} W)",
    },
    "warn_output_stuck": {
        "de": "Ausgang bleibt bei {actual:.0f} W statt {limit:.0f} W — Recovery ausgelöst",
        "en": "Output stays at {actual:.0f} W instead of {limit:.0f} W — recovery triggered",
    },
    "warn_dist_soc_switch_sensor": {
        "de": "Verteilung (SOC-Switch): SOC-Sensor einer Instanz nicht verfügbar — auf Gleichverteilung zurückgefallen",
        "en": "Distribution (SOC switch): SOC sensor of one instance unavailable — fell back to equal distribution",
    },
    "warn_dist_capacity_sensor": {
        "de": "Verteilung: Kapazitätssensor einer Instanz nicht verfügbar — auf SOC-Gewichtung zurückgefallen",
        "en": "Distribution: capacity sensor of one instance unavailable — fell back to SOC weighting",
    },
    "warn_dist_soc_sensor": {
        "de": "Verteilung: SOC-Sensor einer anderen Instanz nicht verfügbar — auf Gleichverteilung zurückgefallen",
        "en": "Distribution: SOC sensor of another instance unavailable — fell back to equal distribution",
    },
    "warn_tariff_unit": {
        "de": "Tarif: Preis {price:g} passt nicht zur Günstig-Schwelle {cheap:g} ct/kWh — Sensor liefert vermutlich €/kWh",
        "en": "Tariff: price {price:g} does not match the cheap threshold {cheap:g} ct/kWh — sensor probably reports €/kWh",
    },
}


def translate(language: str, key: str, **params: object) -> str:
    """Text zu `key` in `language`, mit Rückfall auf Englisch und auf den Schlüssel."""
    texts = _TEXTS.get(key)
    if texts is None:
        return key
    template = texts.get((language or "").split("-")[0].lower()) or texts[DEFAULT_LANGUAGE]
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        return template
