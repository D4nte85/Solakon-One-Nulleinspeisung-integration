/**
 * Solakon ONE Nulleinspeisung — Sidebar Panel
 */

const DOMAIN = "solakon_nulleinspeisung";

const ZONE_CFG = {
  0: { label: "Zone 0 — Überschuss", color: "#f59e0b", icon: "☀️" },
  1: { label: "Zone 1 — Aggressiv",  color: "#16a34a", icon: "⚡" },
  2: { label: "Zone 2 — Schonend",   color: "#0891b2", icon: "🔋" },
  3: { label: "Zone 3 — Stopp",      color: "#dc2626", icon: "⛔" },
};

const TABS = [
  { id: "status",  label: "Status",      icon: "📊" },
  { id: "pi",      label: "PI-Regler",   icon: "🎛️" },
  { id: "zones",   label: "Zonen",       icon: "🔋" },
  { id: "surplus", label: "Überschuss",  icon: "☀️" },
  { id: "ac",      label: "AC Laden",    icon: "⚡" },
  { id: "tariff",  label: "Tarif",       icon: "💹" },
  { id: "dynoff",  label: "Dyn. Offset", icon: "📈" },
  { id: "night",   label: "Nacht",       icon: "🌙" },
  { id: "debug",   label: "Debug",       icon: "🔧" },
];

const TAB_DOCS = {
  pi: {
    summary: "PI-Regler — Kern des Regelkreises",
    text: "Der P-Anteil reagiert sofort auf Abweichungen (Proportional), der I-Anteil summiert Abweichungen über die Zeit und eliminiert dauerhaften Offset (Integral). Anti-Windup begrenzt das Integral auf ±1000. Bei jedem Zonenwechsel wird das Integral zurückgesetzt. Toleranz-Decay baut das Integral um 5 % pro Zyklus ab, wenn der Fehler innerhalb der Toleranz liegt und |Integral| > 10.\n\nEinstieg: P = 0.5, I = 0, Wartezeit = 15 s. P schrittweise erhöhen bis stabil. I erst einführen wenn P-Regelung stabil ist.",
  },
  zones: {
    summary: "SOC-Zonenlogik — Verhalten abhängig vom Batterieladestand",
    text: "Zone 1 (aggressiv): SOC > Zone-1-Schwelle → erhöhter Entladestrom, hoher PI-Offset. Läuft bis Zone-3-Stopp — kein Yo-Yo zwischen den Zonen.\n\nZone 2 (schonend): Normalbetrieb. Output dynamisch auf max(0, PV − Reserve) begrenzt. Entladestrom 0 A.\n\nZone 3 (Stopp): SOC < Zone-3-Schwelle → Output 0 W, Modus Disabled. AC Laden bleibt aktiv.\n\nDer Nullpunkt-Offset verschiebt das Regelziel: +30 W = Regler hält 30 W Netzbezug (Puffer gegen Einspeisung). Negativer Wert = leichte Einspeisung.",
  },
  surplus: {
    summary: "Überschuss-Einspeisung (Zone 0) — optional",
    text: "Wenn PV den Eigenbedarf um mehr als die PV-Hysterese übersteigt UND SOC die Eintrittsschwelle erreicht, wird Output → Hard Limit gesetzt. Das PI-Integral wird in Zone 0 eingefroren.\n\nSOC-Hysterese verhindert Flackern: Austritt erst wenn SOC < (Schwelle − Hysterese). PV-Hysterese verhindert Flackern bei schwankender PV.\n\nBesonderheit: Wenn Hardware-Max-SOC erreicht und MPPT PV auf 0 W drosselt, gilt PV = 0 ebenfalls als Eintritts-Bedingung.",
  },
  ac: {
    summary: "AC Laden bei externem Überschuss — optional",
    text: "Startet wenn (Grid + Output) < −Hysterese (externer Überschuss erkennbar). Eigener invertierter PI-Regler: Fehler = ac_offset − Grid.\n\nWegen der langen Hardware-Flanke des Wechselrichters (~25 s von min auf max) empfiehlt sich ein kleiner P-Faktor (~0.3–0.5). Der I-Anteil macht die eigentliche Regelarbeit.\n\nSOC-Schutz (Zone 3) bleibt vollständig aktiv. Eintritt möglich aus Zone 1 und Zone 2.",
  },
  tariff: {
    summary: "Tarif-Arbitrage (Tibber, aWATTar …) — optional",
    text: "Drei Preisstufen:\n• Günstig (< Günstig-Schwelle): AC-Laden mit fester Leistung bis SOC-Ziel\n• Mittel (zwischen den Schwellen): Discharge-Lock in Zone 2 — Entladung gesperrt, Batterie schonen. Zone 1 läuft weiter.\n• Teuer (≥ Teuer-Schwelle): normale SOC-Logik\n\nErfordert externen Preis-Sensor mit numerischem Wert in ct/kWh.",
  },
  dynoff: {
    summary: "Dynamischer Offset — automatisch aus Netz-Volatilität — optional",
    text: "Berechnet den Nullpunkt-Offset automatisch aus der Standardabweichung der Netzleistung. Bei ruhigem Netz bleibt der Offset auf dem Minimum. Bei unruhigem Netz (Kompressoren, Waschmaschinen) steigt er automatisch.\n\nFormel: offset = clamp(min + max(0, (StdDev − Rausch) × Faktor), min, max)\n\nJede Zone (Zone 1, Zone 2, Zone AC) ist einzeln aktivierbar und überschreibt den statischen Offset der jeweiligen Zone.",
  },
  night: {
    summary: "Nachtabschaltung — Zone 2 bei PV-Mangel deaktivieren — optional",
    text: "Deaktiviert Zone 2 automatisch wenn PV < PV-Ladereserve (aus den Zonen-Einstellungen). Damit wird nachts und bei starker Bewölkung keine Batterie entladen.\n\nZone 1 (aggressive Entladung) und AC Laden laufen auch nachts weiter. Kein separater Schwellwert — die PV-Ladereserve aus dem Zonen-Tab wird direkt verwendet.",
  },
  debug: {
    summary: "Debug — manuelle Eingriffe in den Regelzustand",
    text: "Ermöglicht manuelle Eingriffe in den internen Zustand des Reglers zu Diagnosezwecken.\n\nIntegral zurücksetzen: Setzt den I-Anteil des PI-Reglers auf 0. Nützlich nach einem manuellen Eingriff oder bei starkem Integral-Windup.\n\nZone manuell setzen: Schaltet den Entlade-Zyklus (Zone 1 / Zone 2) manuell um. Setzt das Integral zurück. Nützlich wenn der Regler in einem Zwischenzustand feststeckt.",
  },
};

const TAB_LAYOUT = {
  pi: {
    cols: [
      {
        title: "Regelparameter", icon: "🎛️", color: "#0891b2",
        fields: [
          { k: "p_factor",  l: "P-Faktor (Proportional)", d: "Reagiert sofort auf Abweichung. Höher = aggressiver. Typisch: 0.8–1.5", t: "num", min: 0.1, max: 5, step: 0.1 },
          { k: "i_factor",  l: "I-Faktor (Integral)",     d: "Eliminiert dauerhaften Offset. Typisch: 0.03–0.08", t: "num", min: 0, max: 0.5, step: 0.01 },
          { k: "tolerance", l: "Toleranzbereich (W)",      d: "Totband — keine Korrektur innerhalb dieses Bereichs", t: "num", min: 0, max: 200, step: 1 },
          { k: "wait_time", l: "Wartezeit / Max-Timeout (s)", d: "Feste Pause (ohne Self-Adjust) oder maximales Timeout als Sicherheitsnetz", t: "num", min: 0, max: 30, step: 1 },
        ],
      },
      {
        title: "Self-Adjusting Wait", icon: "🎯", color: "#7c3aed",
        fields: [
          { k: "self_adjust_enabled",   l: "Self-Adjusting Wait aktivieren", d: "Wartet auf tatsächliche WR-Ausgangsleistung statt fester Wartezeit. Wartezeit wird zum Max-Timeout.", t: "bool" },
          { k: "self_adjust_tolerance", l: "Zielwert-Toleranz (W)",          d: "Abweichung, ab der der Zielwert als erreicht gilt", t: "num", min: 1, max: 50, step: 1 },
        ],
      },
    ],
  },

  zones: {
    cols: [
      {
        title: "SOC-Grenzen", icon: "🔋", color: "#0891b2",
        fields: [
          { k: "zone1_limit", l: "Zone 1 SOC-Schwelle (%)", d: "SOC über diesem Wert → Zone 1 (aggressiv)", t: "num", min: 1, max: 99, step: 1 },
          { k: "zone3_limit", l: "Zone 3 SOC-Schwelle (%)", d: "SOC unter diesem Wert → Zone 3 (Stopp)", t: "num", min: 1, max: 49, step: 1 },
          { k: "pv_reserve",  l: "PV-Ladereserve (W)",      d: "Watt die für Batterie-Laden reserviert bleiben (Zone-2-Limit + Nachtschwelle)", t: "num", min: 0, max: 500, step: 10 },
        ],
      },
      {
        title: "Leistungsgrenzen", icon: "⚙️", color: "#b45309",
        fields: [
          { k: "hard_limit",    l: "Hard Limit (W)",               d: "Absolute Obergrenze der Ausgangsleistung in Zone 0 und Zone 1", t: "num", min: 100, max: 2000, step: 50 },
          { k: "discharge_max", l: "Max. Entladestrom Zone 1 (A)", d: "In Zone 2 automatisch 0 A, in Zone 0 (Surplus) 2 A", t: "num", min: 0, max: 100, step: 1 },
        ],
      },
      {
        title: "Regelziel-Offsets", icon: "🎯", color: "#16a34a",
        fields: [
          { k: "offset_1", l: "Zone 1 Offset (W)", d: "Statischer Zielwert in Zone 1. Bei aktivem Dyn. Offset überschrieben", t: "num", min: -200, max: 500, step: 1 },
          { k: "offset_2", l: "Zone 2 Offset (W)", d: "Statischer Zielwert in Zone 2 (batterieschonend)", t: "num", min: -200, max: 500, step: 1 },
        ],
      },
    ],
  },

  surplus: {
    top: [
      { k: "surplus_enabled", l: "Überschuss-Einspeisung aktivieren", d: "Aktives Einspeisen bei vollem Akku (Zone 0)", t: "bool" },
    ],
    enabledKey: "surplus_enabled",
    cols: [
      {
        title: "SOC-Bedingung", icon: "🔋", color: "#0891b2",
        fields: [
          { k: "surplus_soc_threshold", l: "SOC-Schwelle (%)",  d: "Ab diesem SOC wird Überschuss eingespeist", t: "num", min: 80, max: 100, step: 1 },
          { k: "surplus_soc_hyst",      l: "SOC-Hysterese (%)", d: "Austritt erst bei SOC < (Schwelle − Hysterese)", t: "num", min: 1, max: 20, step: 1 },
        ],
      },
      {
        title: "PV-Bedingung", icon: "☀️", color: "#f59e0b",
        fields: [
          { k: "surplus_pv_hyst", l: "PV-Hysterese (W)", d: "Eintritt: PV > Verbrauch + Hysterese. Austritt: PV ≤ Verbrauch − Hysterese. Verhindert Flackern.", t: "num", min: 10, max: 200, step: 10 },
        ],
      },
    ],
  },

  ac: {
    top: [
      { k: "ac_enabled", l: "AC Laden aktivieren", d: "Laden bei erkanntem externem Überschuss (Grid + Output < −Hysterese)", t: "bool" },
    ],
    enabledKey: "ac_enabled",
    cols: [
      {
        title: "Eintritt & Grenzen", icon: "⚡", color: "#7c3aed",
        fields: [
          { k: "ac_soc_target",  l: "Ladeziel SOC (%)",        d: "Laden stoppt bei diesem SOC. Empfohlen: ≤ Zone-1-Schwelle", t: "num", min: 50, max: 100, step: 1 },
          { k: "ac_power_limit", l: "Max. Ladeleistung (W)",   d: "Obergrenze der AC-Ladeleistung", t: "num", min: 100, max: 2000, step: 50 },
          { k: "ac_hysteresis",  l: "Eintritts-Hysterese (W)", d: "(Grid + Output) muss unter −Hysterese liegen", t: "num", min: 10, max: 500, step: 10 },
          { k: "ac_offset",      l: "Regel-Offset (W)",        d: "Zielwert für PI während AC Laden (typisch negativ). Bei Dyn. Offset überschrieben", t: "num", min: -500, max: 200, step: 5 },
        ],
      },
      {
        title: "PI-Parameter", icon: "🎛️", color: "#0891b2",
        fields: [
          { k: "ac_p_factor", l: "AC P-Faktor", d: "Klein halten (~0.3–0.5) wegen langer Hardware-Flanke (~25 s)", t: "num", min: 0.1, max: 3, step: 0.1 },
          { k: "ac_i_factor", l: "AC I-Faktor", d: "I macht bei AC Laden die eigentliche Regelarbeit", t: "num", min: 0, max: 0.5, step: 0.01 },
        ],
      },
    ],
  },

  tariff: {
    top: [
      { k: "tariff_enabled",      l: "Tarif-Steuerung aktivieren", d: "Laden bei günstigem Stromtarif, Discharge-Lock bei mittlerem", t: "bool" },
      { k: "tariff_price_sensor", l: "Preis-Sensor",               d: "Sensor-Entität mit aktuellem Strompreis in ct/kWh", t: "entity", domain: "sensor" },
    ],
    enabledKey: "tariff_enabled",
    cols: [
      {
        title: "Preisschwellen", icon: "💹", color: "#0891b2",
        fields: [
          { k: "tariff_cheap_threshold", l: "Günstig-Schwelle (ct/kWh)", d: "Unter diesem Preis → Tarif-Laden", t: "num", min: 0, max: 100, step: 0.5 },
          { k: "tariff_exp_threshold",   l: "Teuer-Schwelle (ct/kWh)",   d: "Über diesem Preis → normale SOC-Logik. Dazwischen → Discharge-Lock (Zone 2)", t: "num", min: 0, max: 100, step: 0.5 },
        ],
      },
      {
        title: "Laden", icon: "🔋", color: "#16a34a",
        fields: [
          { k: "tariff_soc_target", l: "Ladeziel SOC (%)", d: "Tarif-Laden stoppt bei diesem SOC", t: "num", min: 50, max: 100, step: 1 },
          { k: "tariff_power",      l: "Ladeleistung (W)", d: "Feste Leistung während Tarif-Laden", t: "num", min: 100, max: 2000, step: 50 },
        ],
      },
    ],
  },

  dynoff: {
    top: [
      { k: "stddev_window", l: "Stabw.-Fenster (s)", d: "Zeitfenster für die Standardabweichungs-Berechnung (30–300 s). Gilt für alle Zonen.", t: "num", min: 30, max: 300, step: 10 },
    ],
    cols: [
      {
        title: "Zone 1", icon: "⚡", color: "#16a34a",
        fields: [
          { k: "dyn_z1_enabled", l: "Aktivieren",          d: "Dynamischen Offset für Zone 1 verwenden. Überschreibt den statischen Zone-1-Offset.", t: "bool" },
          { k: "dyn_z1_min",     l: "Min. Offset (W)",     d: "Grundpuffer bei ruhigem Netz", t: "num", min: 0, max: 500, step: 1 },
          { k: "dyn_z1_max",     l: "Max. Offset (W)",     d: "Obergrenze bei unruhigem Netz", t: "num", min: 50, max: 1000, step: 10 },
          { k: "dyn_z1_noise",   l: "Rausch-Schwelle (W)", d: "StdDev darunter = Messrauschen, kein Anstieg", t: "num", min: 0, max: 100, step: 1 },
          { k: "dyn_z1_factor",  l: "Volatilitäts-Faktor", d: "Verstärkung oberhalb Rausch-Schwelle", t: "num", min: 0.5, max: 5, step: 0.1 },
          { k: "dyn_z1_negative",l: "Negativer Offset",    d: "Offset negieren (Regelziel < 0 W)", t: "bool" },
        ],
      },
      {
        title: "Zone 2", icon: "🔋", color: "#0891b2",
        fields: [
          { k: "dyn_z2_enabled", l: "Aktivieren",          d: "Dynamischen Offset für Zone 2 verwenden. Überschreibt den statischen Zone-2-Offset.", t: "bool" },
          { k: "dyn_z2_min",     l: "Min. Offset (W)",     d: "Grundpuffer bei ruhigem Netz", t: "num", min: 0, max: 500, step: 1 },
          { k: "dyn_z2_max",     l: "Max. Offset (W)",     d: "Obergrenze bei unruhigem Netz", t: "num", min: 50, max: 1000, step: 10 },
          { k: "dyn_z2_noise",   l: "Rausch-Schwelle (W)", d: "StdDev darunter = Messrauschen, kein Anstieg", t: "num", min: 0, max: 100, step: 1 },
          { k: "dyn_z2_factor",  l: "Volatilitäts-Faktor", d: "Verstärkung oberhalb Rausch-Schwelle", t: "num", min: 0.5, max: 5, step: 0.1 },
          { k: "dyn_z2_negative",l: "Negativer Offset",    d: "Offset negieren (Regelziel < 0 W)", t: "bool" },
        ],
      },
      {
        title: "Zone AC", icon: "🔌", color: "#7c3aed",
        fields: [
          { k: "dyn_ac_enabled", l: "Aktivieren",          d: "Dynamischen Offset für AC Laden verwenden. Überschreibt den statischen AC-Offset.", t: "bool" },
          { k: "dyn_ac_min",     l: "Min. Offset (W)",     d: "Grundpuffer bei ruhigem Netz", t: "num", min: 0, max: 500, step: 1 },
          { k: "dyn_ac_max",     l: "Max. Offset (W)",     d: "Obergrenze bei unruhigem Netz", t: "num", min: 50, max: 1000, step: 10 },
          { k: "dyn_ac_noise",   l: "Rausch-Schwelle (W)", d: "StdDev darunter = Messrauschen, kein Anstieg", t: "num", min: 0, max: 100, step: 1 },
          { k: "dyn_ac_factor",  l: "Volatilitäts-Faktor", d: "Verstärkung oberhalb Rausch-Schwelle", t: "num", min: 0.5, max: 5, step: 0.1 },
          { k: "dyn_ac_negative",l: "Negativer Offset",    d: "Offset negieren (Regelziel < 0 W)", t: "bool" },
        ],
      },
    ],
  },

  night: {
    top: [
      { k: "night_enabled", l: "Nachtabschaltung aktivieren", d: "Zone 2 bei PV < PV-Ladereserve deaktivieren. Zone 1 und AC Laden laufen weiter.", t: "bool" },
    ],
  },
};

class SolakonPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._initialized = false;
    this._settings = {};
    this._dirty = {};
    this._status = null;
    this._activeTab = "status";
    this._polling = null;
  }

  set panel(val) {
    this._panel = val;
    if (val?.config?.entry_id) { this._entryId = val.config.entry_id; this._checkInit(); }
  }

  set hass(val) { this._hass = val; this._checkInit(); }

  _checkInit() {
    if (this._hass && this._entryId && !this._initialized) {
      this._initialized = true;
      this._build();
      this._loadConfig();
      this._polling = setInterval(() => this._loadStatus(), 1000);
    }
  }

  async _ws(cmd, extra = {}) {
    return this._hass.callWS({ type: `${DOMAIN}/${cmd}`, entry_id: this._entryId, ...extra });
  }

  async _loadConfig() {
    try { this._settings = await this._ws("get_config"); this._renderActiveTab(); }
    catch (e) { console.error("Solakon: config load failed", e); }
  }

  async _loadStatus() {
    try {
      this._status = await this._ws("get_status");
      if (this._activeTab === "status") this._updateStatusView();
      if (this._activeTab === "debug") {
        const el = this.shadowRoot.getElementById("dbg-zone-state");
        if (el) el.textContent = this._status.cycle_active ? "Zone 1 (Zyklus aktiv)" : "Zone 2";
      }
      this._updateRegBanner();
    } catch (e) { /* ignore polling errors */ }
  }

  async _saveSettings() {
    if (!Object.keys(this._dirty).length) return;
    try {
      await this._ws("save_config", { changes: this._dirty });
      this._settings = { ...this._settings, ...this._dirty };
      this._dirty = {};
      this._showToast("✅ Einstellungen gespeichert");
      this._renderActiveTab();
    } catch (e) { this._showToast("❌ " + e.message, true); }
  }

  async _toggleRegulation() {
    const on = !this._settings.regulation_enabled;
    try {
      await this._ws("save_config", { changes: { regulation_enabled: on } });
      this._settings.regulation_enabled = on;
      this._updateRegBanner();
      this._showToast(on ? "✅ Regelung aktiviert" : "⏸️ Regelung deaktiviert");
    } catch (e) { this._showToast("❌ " + e.message, true); }
  }

  async _resetIntegral() {
    try {
      await this._ws("reset_integral");
      this._showToast("🔄 Integral zurückgesetzt");
    } catch (e) { this._showToast("❌ " + e.message, true); }
  }

  async _toggleCycle(activate) {
    try {
      await this._ws("set_cycle", { active: activate });
      this._showToast(activate ? "⚡ Zone 1 aktiviert" : "🔋 Zone 2 aktiviert");
      this._status = await this._ws("get_status");
      const el = this.shadowRoot.getElementById("dbg-zone-state");
      if (el) el.textContent = this._status.cycle_active ? "Zone 1 (Zyklus aktiv)" : "Zone 2";
    } catch (e) { this._showToast("❌ " + e.message, true); }
  }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        /* ── Host & Wrapper ──────────────────────────────────────────────── */
        :host {
          display: block;
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
          color: var(--primary-text-color, #333);
          background-color: var(--primary-background-color, #fafafa);
        }
        .wrap { max-width: 940px; margin: 0 auto; padding: 16px; }

        /* ── App bar (Burger-Menü für HA-Sidebar) ────────────────────────── */
        .app-bar {
          position: sticky;
          top: 0;
          z-index: 20;
          background: var(--app-header-background-color, var(--primary-color, #03a9f4));
          color: var(--app-header-text-color, #fff);
          display: flex;
          align-items: center;
          height: 56px;
          padding: 0 4px;
        }
        .menu-btn {
          background: none;
          border: none;
          color: inherit;
          cursor: pointer;
          padding: 10px 12px;
          border-radius: 50%;
          font-size: 1.4em;
          line-height: 1;
          display: flex;
          align-items: center;
        }
        .menu-btn:hover { background: rgba(255,255,255,0.12); }
        .app-bar-title { font-size: 1.05em; font-weight: 500; flex: 1; padding-left: 4px; }

        /* ── Top card (Titel + Regelschalter + Info) ─────────────────────── */
        .top-card {
          border: 1px solid var(--divider-color, #ddd);
          border-radius: 10px;
          overflow: hidden;
          margin-bottom: 14px;
        }
        .top-card-hdr {
          background: var(--primary-color, #03a9f4);
          color: #fff;
          padding: 12px 16px;
          font-size: 1.1em;
          font-weight: 600;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .top-card-body {
          padding: 12px 16px;
          background: var(--card-background-color, #fff);
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        /* ── Regulation bar ──────────────────────────────────────────────── */
        .reg-bar { display: flex; align-items: center; gap: 12px; padding: 10px 14px; border-radius: 8px; cursor: pointer; user-select: none; }
        .reg-bar.on  { background: #16a34a22; border: 1px solid #16a34a; }
        .reg-bar.off { background: #dc262622; border: 1px solid #dc2626; }
        .reg-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
        .reg-bar.on  .reg-dot { background: #16a34a; }
        .reg-bar.off .reg-dot { background: #dc2626; }

        /* ── Global info accordion ───────────────────────────────────────── */
        .global-info { border: 1px solid var(--divider-color, #ddd); border-radius: 8px; overflow: hidden; }
        .global-info summary { padding: 9px 14px; cursor: pointer; font-weight: 600; font-size: .88em; background: var(--secondary-background-color, #f5f5f5); color: var(--primary-color, #03a9f4); list-style: none; display: flex; align-items: center; gap: 8px; user-select: none; }
        .global-info summary::-webkit-details-marker { display: none; }
        .global-info summary::before { content: "▶"; font-size: .7em; transition: transform .2s; }
        .global-info[open] summary::before { transform: rotate(90deg); }
        .global-info .global-body { padding: 12px 14px; font-size: .83em; line-height: 1.7; color: var(--secondary-text-color, #555); border-top: 1px solid var(--divider-color, #ddd); display: flex; flex-direction: column; gap: 8px; }
        .global-info .global-body strong { color: var(--primary-text-color, #333); }

        /* ── Tab panel (Tabs + Inhalt als ein Element) ───────────────────── */
        .tab-panel {
          border: 1px solid var(--divider-color, #ddd);
          border-radius: 10px;
          overflow: hidden;
          margin-bottom: 14px;
        }
        .tab-bar {
          background: var(--secondary-background-color, #f0f0f0);
          border-bottom: 2px solid var(--divider-color, #ddd);
          display: flex;
          flex-wrap: wrap;
          padding: 8px 8px 0;
          gap: 2px;
        }
        .tab {
          padding: 7px 11px;
          border-radius: 8px 8px 0 0;
          cursor: pointer;
          background: var(--card-background-color, #fff);
          border: 1px solid var(--divider-color, #ddd);
          border-bottom: 2px solid var(--card-background-color, #fff);
          font-size: .82em;
          white-space: nowrap;
          position: relative;
          bottom: -2px;
          transition: background .15s;
        }
        .tab:hover:not(.active) { background: var(--secondary-background-color, #f5f5f5); }
        .tab.active {
          background: var(--primary-color, #03a9f4);
          color: #fff;
          border-color: var(--primary-color, #03a9f4);
          border-bottom-color: var(--primary-color, #03a9f4);
          font-weight: 600;
        }
        .tab-content { background: var(--card-background-color, #fff); padding: 16px; min-height: 200px; }

        /* ── Info accordion (inside tab) ─────────────────────────────────── */
        .info-details { margin-bottom: 14px; border: 1px solid var(--divider-color, #ddd); border-radius: 8px; overflow: hidden; }
        .info-details summary { padding: 9px 14px; cursor: pointer; font-weight: 600; font-size: .88em; background: var(--secondary-background-color, #f5f5f5); color: var(--primary-color, #03a9f4); list-style: none; display: flex; align-items: center; gap: 8px; user-select: none; }
        .info-details summary::-webkit-details-marker { display: none; }
        .info-details summary::before { content: "▶"; font-size: .7em; transition: transform .2s; }
        .info-details[open] summary::before { transform: rotate(90deg); }
        .info-details .info-body { padding: 11px 14px; font-size: .83em; line-height: 1.65; color: var(--secondary-text-color, #555); white-space: pre-wrap; border-top: 1px solid var(--divider-color, #ddd); }

        /* ── Column grid layout ──────────────────────────────────────────── */
        .col-grid { display: grid; gap: 12px; }
        .col-grid.cols-1 { grid-template-columns: 1fr; }
        .col-grid.cols-2 { grid-template-columns: repeat(2, 1fr); }
        .col-grid.cols-3 { grid-template-columns: repeat(3, 1fr); }
        @media (max-width: 680px) { .col-grid.cols-2, .col-grid.cols-3 { grid-template-columns: 1fr; } }
        .col-grid.disabled { opacity: 0.4; pointer-events: none; }
        .col-card { border: 1px solid var(--divider-color, #ddd); border-radius: 10px; overflow: hidden; }
        .col-card.top-item { margin-bottom: 12px; }
        .col-header { padding: 8px 12px; font-weight: 600; font-size: .85em; color: #fff; display: flex; align-items: center; gap: 6px; }
        .col-body { padding: 12px; }

        /* ── Form fields ─────────────────────────────────────────────────── */
        .field { margin-bottom: 12px; }
        .field:last-child { margin-bottom: 0; }
        .field label { display: block; font-weight: 500; margin-bottom: 2px; font-size: .9em; }
        .field .desc { font-size: .79em; color: var(--secondary-text-color, #888); margin-bottom: 4px; line-height: 1.4; }
        .field input[type=number], .field input[type=text] { width: 100%; padding: 6px 8px; border: 1px solid var(--divider-color, #ccc); border-radius: 6px; font-size: .92em; box-sizing: border-box; background: var(--card-background-color, #fff); color: var(--primary-text-color, #333); }
        .field .toggle { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; }
        .field .toggle input { width: 17px; height: 17px; }

        /* ── Status grid ─────────────────────────────────────────────────── */
        .stat-col-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 0; }
        @media (max-width: 680px) { .stat-col-grid { grid-template-columns: 1fr; } }
        .stat-col-card { border: 1px solid var(--divider-color, #ddd); border-radius: 10px; overflow: hidden; }
        .stat-col-header { padding: 8px 12px; font-weight: 600; font-size: .85em; color: #fff; display: flex; align-items: center; gap: 6px; }
        .stat-col-body { padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }
        .stat-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .stat { padding: 7px 10px; border-radius: 6px; background: var(--secondary-background-color, #f0f0f0); }
        .stat .val { font-size: 1.15em; font-weight: 600; }
        .stat .lbl { font-size: .76em; color: var(--secondary-text-color, #888); margin-top: 2px; }
        .stat-full { padding: 7px 10px; border-radius: 6px; background: var(--secondary-background-color, #f0f0f0); }
        .stat-full .val { font-size: 1.15em; font-weight: 600; }
        .stat-full .lbl { font-size: .76em; color: var(--secondary-text-color, #888); margin-top: 2px; }
        .stat-full .lbl-src { font-size: .76em; color: var(--secondary-text-color, #888); margin-top: 1px; font-style: italic; }

        /* ── Flags ───────────────────────────────────────────────────────── */
        .flag-row { display: flex; flex-wrap: wrap; gap: 5px; }
        .flag { padding: 3px 9px; border-radius: 12px; font-size: .8em; font-weight: 500; }
        .flag.on  { background: #16a34a22; color: #16a34a; }
        .flag.off { background: #6b728022; color: #6b7280; }

        /* ── Mode labels ─────────────────────────────────────────────────── */
        .mode-lbl { color: var(--secondary-text-color, #888); margin-bottom: 2px; font-size: .85em; }
        .mode-val { font-size: .88em; color: var(--primary-text-color, #333); }
        .mode-err { font-size: .88em; color: #dc2626; }

        /* ── Zone banner ─────────────────────────────────────────────────── */
        .zone-banner { padding: 12px; border-radius: 8px; color: #fff; font-weight: 600; font-size: 1.1em; margin-bottom: 12px; text-align: center; }

        /* ── Buttons ─────────────────────────────────────────────────────── */
        .btn { padding: 8px 18px; border: none; border-radius: 6px; cursor: pointer; font-size: .9em; font-weight: 500; }
        .btn-secondary { background: var(--secondary-background-color, #eee); color: var(--primary-text-color, #333); }

        /* ── Save bar ────────────────────────────────────────────────────── */
        #save-bar { display: none; position: sticky; bottom: 0; background: var(--primary-color, #03a9f4); color: #fff; padding: 10px 16px; border-radius: 8px; margin-top: 12px; align-items: center; justify-content: space-between; z-index: 10; }
        #save-bar button { background: #fff; color: var(--primary-color, #03a9f4); border: none; padding: 6px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; }
        #toast { display: none; position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); padding: 10px 24px; border-radius: 8px; color: #fff; z-index: 999; font-size: .9em; }
      </style>

      <div class="app-bar">
        <button class="menu-btn" id="menu-btn">☰</button>
        <span class="app-bar-title">Solakon ONE</span>
      </div>
      <div class="wrap">

        <!-- ── Top card ──────────────────────────────────────────── -->
        <div class="top-card">
          <div class="top-card-hdr">⚡ Solakon ONE Nulleinspeisung</div>
          <div class="top-card-body">
            <div class="reg-bar off" id="reg-bar">
              <div class="reg-dot"></div>
              <span id="reg-text">Regelung inaktiv</span>
            </div>
            <details class="global-info">
              <summary>ℹ️ Über diese Integration</summary>
              <div class="global-body">
                <p>Die <strong>Solakon ONE Nulleinspeisung</strong> regelt die Ausgangsleistung des Wechselrichters vollautomatisch so, dass der Netzbezug möglichst bei 0 W gehalten wird — ohne Einspeisung ins öffentliche Netz.</p>
                <p>Kern ist ein <strong>PI-Regler</strong> mit der Netzleistung als Regelgröße und der WR-Ausgangsleistung als Stellgröße. Das Verhalten richtet sich nach vier <strong>SOC-Zonen</strong>: Zone 1 entlädt aggressiv, Zone 2 batterieschonend, Zone 3 sperrt die Entladung, Zone 0 speist aktiv Überschuss ein.</p>
                <p>Optionale Module: <strong>AC-Laden</strong>, <strong>Tarif-Arbitrage</strong>, <strong>Dynamischer Offset</strong> (pro Zone einzeln), <strong>Nachtabschaltung</strong>. Alle Parameter werden persistent hier im Panel gespeichert — kein YAML, keine Helfer-Entitäten.</p>
              </div>
            </details>
          </div>
        </div>

        <!-- ── Tab panel (tabs + content als ein Element) ────────── -->
        <div class="tab-panel">
          <div class="tab-bar" id="tabs"></div>
          <div class="tab-content" id="content"></div>
        </div>

        <div id="save-bar">
          <span>Ungespeicherte Änderungen</span>
          <button onclick="this.getRootNode().host._saveSettings()">💾 Speichern</button>
        </div>
      </div>
      <div id="toast"></div>
    `;

    this.shadowRoot.getElementById("reg-bar").addEventListener("click", () => this._toggleRegulation());
    this.shadowRoot.getElementById("menu-btn").addEventListener("click", () => {
      this.dispatchEvent(new Event("hass-sidebar-toggle", { bubbles: true, composed: true }));
    });

    const tabWrap = this.shadowRoot.getElementById("tabs");
    for (const t of TABS) {
      const el = document.createElement("div");
      el.className = "tab" + (t.id === this._activeTab ? " active" : "");
      el.textContent = `${t.icon} ${t.label}`;
      el.dataset.id = t.id;
      el.addEventListener("click", () => {
        this._activeTab = t.id;
        tabWrap.querySelectorAll(".tab").forEach(x => x.classList.toggle("active", x.dataset.id === t.id));
        this._renderActiveTab();
      });
      tabWrap.appendChild(el);
    }
  }

  // ── Tab rendering ─────────────────────────────────────────────────────────

  _renderActiveTab() {
    const c = this.shadowRoot.getElementById("content");

    if (this._activeTab === "status") {
      this._renderStatus(c);
      this._updateStatusView();
      this._updateSaveBar();
      return;
    }

    if (this._activeTab === "debug") {
      this._renderDebug();
      this._updateSaveBar();
      return;
    }

    c.innerHTML = "";

    const doc = TAB_DOCS[this._activeTab];
    if (doc) {
      const details = document.createElement("details");
      details.className = "info-details";
      details.innerHTML = `<summary>ℹ️ ${doc.summary}</summary><div class="info-body">${doc.text}</div>`;
      c.appendChild(details);
    }

    const layout = TAB_LAYOUT[this._activeTab];
    if (layout) this._renderLayout(c, layout);
    this._updateSaveBar();
  }

  _renderLayout(container, layout) {
    const enabledKey = layout.enabledKey || null;

    // Top fields → in einem "Allgemein"-Kasten
    if (layout.top?.length) {
      const topCard = document.createElement("div");
      topCard.className = "col-card top-item";
      const topHdr = document.createElement("div");
      topHdr.className = "col-header";
      topHdr.style.background = "#475569";
      topHdr.textContent = "⚙️ Allgemein";
      topCard.appendChild(topHdr);
      const topBody = document.createElement("div");
      topBody.className = "col-body";
      for (const f of layout.top) topBody.appendChild(this._makeField(f));
      topCard.appendChild(topBody);
      container.appendChild(topCard);
    }

    if (!layout.cols?.length) return;

    const colGrid = document.createElement("div");
    colGrid.className = `col-grid cols-${Math.min(layout.cols.length, 3)}`;
    colGrid.id = "col-grid-main";
    if (enabledKey && !this._effectiveValue(enabledKey)) colGrid.classList.add("disabled");

    for (const col of layout.cols) {
      const card = document.createElement("div");
      card.className = "col-card";
      const hdr = document.createElement("div");
      hdr.className = "col-header";
      hdr.style.background = col.color;
      hdr.textContent = `${col.icon} ${col.title}`;
      card.appendChild(hdr);
      const body = document.createElement("div");
      body.className = "col-body";
      for (const f of col.fields) body.appendChild(this._makeField(f));
      card.appendChild(body);
      colGrid.appendChild(card);
    }

    container.appendChild(colGrid);

    if (enabledKey) {
      const masterCb = container.querySelector(`input[data-key="${enabledKey}"]`);
      if (masterCb) {
        masterCb.addEventListener("change", (e) => {
          container.querySelector("#col-grid-main")?.classList.toggle("disabled", !e.target.checked);
        });
      }
    }
  }

  _makeField(f) {
    const cur = this._effectiveValue(f.k);
    const div = document.createElement("div");
    div.className = "field";

    if (f.t === "bool") {
      div.innerHTML = `<label class="toggle"><input type="checkbox" data-key="${f.k}" ${cur ? "checked" : ""}/> ${f.l}</label><div class="desc">${f.d || ""}</div>`;
      div.querySelector("input").addEventListener("change", (e) => {
        this._dirty[f.k] = e.target.checked;
        this._updateSaveBar();
      });
    } else if (f.t === "num") {
      div.innerHTML = `<label>${f.l}</label><div class="desc">${f.d || ""}</div><input type="number" min="${f.min}" max="${f.max}" step="${f.step}" value="${cur ?? f.min}"/>`;
      div.querySelector("input").addEventListener("change", (e) => {
        this._dirty[f.k] = parseFloat(e.target.value);
        this._updateSaveBar();
      });
    } else if (f.t === "entity") {
      const eid = `ep_${f.k}`;
      div.innerHTML = `<label>${f.l}</label><div class="desc">${f.d || ""}</div><input type="text" list="${eid}_list" value="${cur || ""}" placeholder="sensor.xxx"/><datalist id="${eid}_list"></datalist>`;
      const inp = div.querySelector("input");
      const dl = div.querySelector("datalist");
      if (this._hass?.states) {
        const domain = f.domain || "";
        Object.keys(this._hass.states).filter(e => !domain || e.startsWith(domain + ".")).sort().forEach(e => {
          const opt = document.createElement("option");
          opt.value = e;
          const name = this._hass.states[e]?.attributes?.friendly_name || "";
          if (name) opt.label = name;
          dl.appendChild(opt);
        });
      }
      inp.addEventListener("change", () => { this._dirty[f.k] = inp.value; this._updateSaveBar(); });
    }
    return div;
  }

  // ── Status tab ────────────────────────────────────────────────────────────

  _renderStatus(c) {
    c.innerHTML = `
      <div class="zone-banner" id="zone-banner">Lade…</div>
      <div class="stat-col-grid">

        <div class="stat-col-card">
          <div class="stat-col-header" style="background:#0891b2">⚡ Messwerte</div>
          <div class="stat-col-body">
            <div class="stat-row">
              <div class="stat"><div class="val" id="st-grid">—</div><div class="lbl">Netzleistung</div></div>
              <div class="stat"><div class="val" id="st-soc">—</div><div class="lbl">SOC</div></div>
            </div>
            <div class="stat-row">
              <div class="stat"><div class="val" id="st-actual">—</div><div class="lbl">Ausgangsleistung</div></div>
              <div class="stat"><div class="val" id="st-solar">—</div><div class="lbl">Solarleistung</div></div>
            </div>
          </div>
        </div>

        <div class="stat-col-card">
          <div class="stat-col-header" style="background:#7c3aed">📈 Regelzustand</div>
          <div class="stat-col-body">
            <div class="stat-row">
              <div class="stat"><div class="val" id="st-int">—</div><div class="lbl">PI Integral</div></div>
              <div class="stat"><div class="val" id="st-stddev">—</div><div class="lbl">Netz-StdDev</div></div>
            </div>
            <div class="stat-full">
              <div class="val" id="st-offset-val">—</div>
              <div class="lbl" id="st-offset-lbl">Aktiver Offset</div>
              <div class="lbl-src" id="st-offset-src">—</div>
            </div>
            <div class="stat-row">
              <div class="stat"><div class="val" id="st-elapsed">—</div><div class="lbl">Seit letztem Output</div></div>
              <div class="stat"><div class="val" id="st-mode-elapsed">—</div><div class="lbl">Seit Moduswechsel</div></div>
            </div>
          </div>
        </div>

        <div class="stat-col-card">
          <div class="stat-col-header" style="background:#b45309">🚦 Module & Status</div>
          <div class="stat-col-body">
            <div>
              <div class="mode-lbl">Aktive Module</div>
              <div class="flag-row" id="st-flags"></div>
            </div>
            <div>
              <div class="mode-lbl">Betriebsmodus</div>
              <div class="mode-val" id="st-mode">—</div>
            </div>
            <div>
              <div class="mode-lbl">Letzte Aktion</div>
              <div class="mode-val" id="st-action">—</div>
            </div>
            <div>
              <div class="mode-lbl">Fehler</div>
              <div class="mode-err" id="st-error">—</div>
            </div>
          </div>
        </div>

      </div>
    `;
  }

  _fmt_elapsed(ts) {
    if (!ts) return "—";
    const el = Math.round(Date.now() / 1000 - ts);
    if (el < 0)    return "—";
    if (el < 60)   return `${el} s`;
    if (el < 3600) return `${Math.floor(el / 60)} min ${el % 60} s`;
    return `${Math.floor(el / 3600)} h ${Math.floor((el % 3600) / 60)} min`;
  }

  _updateStatusView() {
    const st = this._status;
    if (!st) return;

    const z = ZONE_CFG[st.zone] || ZONE_CFG[2];
    const b = this.shadowRoot.getElementById("zone-banner");
    if (b) { b.textContent = `${z.icon} ${z.label}`; b.style.background = z.color; }

    const set = (id, v) => { const e = this.shadowRoot.getElementById(id); if (e) e.textContent = v; };

    set("st-grid",        `${(st.grid ?? 0).toFixed(0)} W`);
    set("st-actual",      `${st.actual_power ?? "—"} W`);
    set("st-solar",       `${st.solar ?? "—"} W`);
    set("st-soc",         `${st.soc ?? "—"} %`);
    set("st-int",         `${(st.integral ?? 0).toFixed(2)}`);
    set("st-stddev",      `${(st.stddev ?? 0).toFixed(1)} W`);
    set("st-elapsed",     this._fmt_elapsed(st.last_output_ts));
    set("st-mode-elapsed",this._fmt_elapsed(st.mode_label_ts));
    set("st-mode",        st.mode_label  || "—");
    set("st-action",      st.last_action || "—");
    set("st-error",       st.last_error  || "Keine");

    // ── Aktiver Offset: nur für den aktuell relevanten Arbeitsbereich ──────
    let offsetLabel, offsetActive, isDyn, offsetStatic;
    if (st.ac_charge) {
      offsetLabel   = "Zone AC Laden";
      isDyn         = !!st.dyn_ac_enabled;
      offsetStatic  = this._settings.ac_offset ?? "—";
      offsetActive  = isDyn ? (st.dyn_ac ?? 0).toFixed(0) : offsetStatic;
    } else if (st.cycle_active) {
      offsetLabel   = "Zone 1";
      isDyn         = !!st.dyn_z1_enabled;
      offsetStatic  = this._settings.offset_1 ?? "—";
      offsetActive  = isDyn ? (st.dyn_z1 ?? 0).toFixed(0) : offsetStatic;
    } else {
      offsetLabel   = "Zone 2";
      isDyn         = !!st.dyn_z2_enabled;
      offsetStatic  = this._settings.offset_2 ?? "—";
      offsetActive  = isDyn ? (st.dyn_z2 ?? 0).toFixed(0) : offsetStatic;
    }
    set("st-offset-val", `${offsetActive} W`);
    set("st-offset-lbl", `Aktiver Offset — ${offsetLabel}`);
    set("st-offset-src", isDyn
      ? `dynamisch ● statisch: ${offsetStatic} W`
      : `statisch ● dyn. inaktiv`
    );

    const fl = this.shadowRoot.getElementById("st-flags");
    if (fl) fl.innerHTML = [
      ["Zyklus",      st.cycle_active],
      ["Surplus",     st.surplus_active],
      ["AC Laden",    st.ac_charge],
      ["Tarif-Laden", st.tariff_charge],
    ].map(([n, v]) => `<span class="flag ${v ? "on" : "off"}">${v ? "●" : "○"} ${n}</span>`).join("");
  }

  // ── Debug tab ─────────────────────────────────────────────────────────────

  _renderDebug() {
    const c = this.shadowRoot.getElementById("content");
    const zoneState = this._status
      ? (this._status.cycle_active ? "Zone 1 (Zyklus aktiv)" : "Zone 2")
      : "—";

    c.innerHTML = `
      <div class="col-grid cols-2">

        <div class="col-card">
          <div class="col-header" style="background:#7c3aed">🔄 PI-Integral</div>
          <div class="col-body">
            <p style="font-size:.85em;color:var(--secondary-text-color,#888);margin:0 0 12px">
              Setzt den I-Anteil des PI-Reglers manuell auf 0 zurück.
              Nützlich nach einem manuellen Eingriff oder bei starkem Integral-Windup.
            </p>
            <button class="btn btn-secondary"
              onclick="this.getRootNode().host._resetIntegral()">
              🔄 Integral zurücksetzen
            </button>
          </div>
        </div>

        <div class="col-card">
          <div class="col-header" style="background:#0891b2">🔁 Zone manuell setzen</div>
          <div class="col-body">
            <p style="font-size:.85em;color:var(--secondary-text-color,#888);margin:0 0 4px">
              Schaltet den Entlade-Zyklus manuell um und setzt das Integral zurück.
            </p>
            <p style="font-size:.85em;margin:0 0 12px">
              Aktuell: <strong id="dbg-zone-state">${zoneState}</strong>
            </p>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <button class="btn" style="background:#16a34a;color:#fff"
                onclick="this.getRootNode().host._toggleCycle(true)">
                ⚡ Zone 1 aktivieren
              </button>
              <button class="btn" style="background:#0891b2;color:#fff"
                onclick="this.getRootNode().host._toggleCycle(false)">
                🔋 Zone 2 aktivieren
              </button>
            </div>
          </div>
        </div>

      </div>
    `;
  }

  // ── Shared helpers ────────────────────────────────────────────────────────

  _updateRegBanner() {
    const on = this._settings.regulation_enabled;
    const bar = this.shadowRoot.getElementById("reg-bar");
    const txt = this.shadowRoot.getElementById("reg-text");
    if (bar) bar.className = `reg-bar ${on ? "on" : "off"}`;
    if (txt) txt.textContent = on ? "Regelung aktiv — klicken zum Deaktivieren" : "Regelung inaktiv — klicken zum Aktivieren";
  }

  _effectiveValue(key) { return key in this._dirty ? this._dirty[key] : this._settings[key]; }

  _updateSaveBar() {
    const bar = this.shadowRoot.getElementById("save-bar");
    if (bar) bar.style.display = Object.keys(this._dirty).length ? "flex" : "none";
  }

  _showToast(msg, err = false) {
    const t = this.shadowRoot.getElementById("toast");
    t.textContent = msg;
    t.style.background = err ? "#dc2626" : "#16a34a";
    t.style.display = "block";
    setTimeout(() => { t.style.display = "none"; }, 3000);
  }

  disconnectedCallback() {
    if (this._polling) { clearInterval(this._polling); this._polling = null; }
  }
}

customElements.define("solakon-panel", SolakonPanel);
