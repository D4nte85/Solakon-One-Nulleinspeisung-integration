/**
 * Solakon ONE Nulleinspeisung — Sidebar Panel
 * Alle Blueprint-Parameter, Dynamic Offset, Entity-Picker, Aktivierungs-Banner.
 */

const DOMAIN = "solakon_nulleinspeisung";

const ZONE_CFG = {
  0: { label: "Zone 0 — Überschuss", color: "#f59e0b", icon: "☀️" },
  1: { label: "Zone 1 — Aggressiv",  color: "#16a34a", icon: "⚡" },
  2: { label: "Zone 2 — Schonend",   color: "#0891b2", icon: "🔋" },
  3: { label: "Zone 3 — Stopp",      color: "#dc2626", icon: "⛔" },
};

const TABS = [
  { id: "status",  label: "Status",     icon: "📊" },
  { id: "pi",      label: "PI-Regler",  icon: "🎛️" },
  { id: "zones",   label: "Zonen",      icon: "🔋" },
  { id: "surplus", label: "Überschuss", icon: "☀️" },
  { id: "ac",      label: "AC Laden",   icon: "⚡" },
  { id: "tariff",  label: "Tarif",      icon: "💹" },
  { id: "dynoff",  label: "Dyn. Offset",icon: "📈" },
  { id: "night",   label: "Nacht",      icon: "🌙" },
];

/* ── Tab-Dokumentation (ausklappbare Header) ────────────────────────────────── */

const TAB_DOCS = {
  status: {
    summary: "Echtzeit-Übersicht aller Regelzustände",
    text: "Zeigt Zone, Messwerte, interne Flags und die letzte Regelaktion auf einen Blick. Das PI-Integral kann hier manuell zurückgesetzt werden. Die Statusanzeige aktualisiert sich automatisch alle 3 Sekunden.",
  },
  pi: {
    summary: "PI-Regler — Kern des Regelkreises",
    text: "Der P-Anteil reagiert sofort auf Abweichungen (Proportional), der I-Anteil summiert Abweichungen über die Zeit und eliminiert dauerhaften Offset (Integral). Anti-Windup begrenzt das Integral auf ±1000. Bei jedem Zonenwechsel wird das Integral zurückgesetzt.\n\nSelf-Adjusting Wait: Statt einer festen Pause wartet der Regler bis die tatsächliche WR-Ausgangsleistung den Zielwert innerhalb der Zielwert-Toleranz erreicht. Die Wartezeit wird dabei zum maximalen Timeout als Sicherheitsnetz.\n\nEinstieg: P = 0.5, I = 0, Wartezeit = 15 s. P schrittweise erhöhen bis stabil. I erst einführen wenn P-Regelung stabil ist.",
  },
  zones: {
    summary: "SOC-Zonenlogik — Verhalten nach Ladestand",
    text: "Zone 1 (aggressiv): SOC > Zone-1-Schwelle → erhöhter Entladestrom, hoher PI-Offset. Läuft bis Zone-3-Stopp — kein Yo-Yo zwischen den Zonen.\n\nZone 2 (schonend): Normalbetrieb zwischen den Grenzen. Output dynamisch auf max(0, PV − Reserve) begrenzt. Entladestrom 0 A.\n\nZone 3 (Stopp): SOC < Zone-3-Schwelle → Output 0 W, Modus Disabled. AC Laden bleibt aktiv.\n\nDer Nullpunkt-Offset verschiebt das Regelziel: +30 W = Regler hält 30 W Netzbezug (Puffer). Negativer Wert = leichte Einspeisung.",
  },
  surplus: {
    summary: "Überschuss-Einspeisung (Zone 0) — optional",
    text: "Wenn PV den Eigenbedarf um mehr als PV-Hysterese übersteigt UND SOC die Eintrittsschwelle erreicht, wird Output → Hard Limit gesetzt (volle Einspeisung). Das PI-Integral wird in Zone 0 eingefroren — kein Decay, kein PI-Aufruf.\n\nSOC-Hysterese verhindert Flackern: Austritt erst wenn SOC < (Schwelle − Hysterese). PV-Hysterese verhindert Flackern bei schwankender PV.\n\nBesonderheit: Wenn der Wechselrichter den Hardware-Max-SOC erreicht und MPPT PV auf 0 W drosselt, wird PV = 0 ebenfalls als Eintritts-Bedingung akzeptiert.",
  },
  ac: {
    summary: "AC Laden bei externem Überschuss — optional",
    text: "Startet wenn (Grid + Output) < −Hysterese (externer Überschuss erkennbar). Eigener invertierter PI-Regler: Fehler = ac_offset − Grid (Ladeleistung steigt wenn Grid < Sollwert).\n\nWegen der langen Hardware-Flanke des Wechselrichters (~25 s von min auf max) empfiehlt sich kleiner P-Faktor (~0.3–0.5). Der I-Anteil macht die eigentliche Regelarbeit.\n\nSOC-Schutz (Zone 3) bleibt vollständig aktiv. Eintritt möglich aus Zone 1 und Zone 2.",
  },
  tariff: {
    summary: "Tarif-Arbitrage (Tibber, aWATTar…) — optional",
    text: "Drei Preisstufen:\n• Günstig (< Günstig-Schwelle): AC-Laden mit fester Leistung bis SOC-Ziel\n• Mittel (zwischen den Schwellen): Discharge-Lock in Zone 2 — Entladung gesperrt, Batterie schonen. Zone 1 läuft weiter.\n• Teuer (≥ Teuer-Schwelle): normale SOC-Logik\n\nErfordert externen Preis-Sensor mit numerischem Wert in ct/kWh (z.B. Tibber-Integration, aWATTar-Integration).",
  },
  dynoff: {
    summary: "Dynamischer Offset — automatisch aus Netz-Volatilität — optional",
    text: "Berechnet den Nullpunkt-Offset automatisch aus der Standardabweichung der Netzleistung. Bei ruhigem Netz bleibt der Offset auf dem Minimum. Bei unruhigem Netz (Kompressoren, Waschmaschinen, Heizstäbe) steigt er automatisch an.\n\nFormel: offset = clamp(min + max(0, (StdDev − Rausch) × Faktor), min, max)\n\nÜberschreibt die statischen Offsets aus den Zonen-Einstellungen. Jede Zone (Zone 1, Zone 2, Zone AC) ist separat konfigurierbar. Das Stabw.-Fenster legt fest über wie viele Sekunden die Netz-Standardabweichung berechnet wird.",
  },
  night: {
    summary: "Nachtabschaltung — Zone 2 deaktivieren — optional",
    text: "Deaktiviert Zone 2 automatisch wenn PV < PV-Ladereserve (aus den Zonen-Einstellungen). Damit wird nachts und bei starker Bewölkung keine Batterie entladen.\n\nZone 1 (aggressive Entladung) und AC Laden laufen auch bei aktivierter Nachtabschaltung weiter. Kein separater Schwellwert — die PV-Ladereserve aus dem Zonen-Tab wird direkt verwendet.",
  },
};

/* ── Field definitions per tab ─────────────────────────────────────────────── */

const FIELDS = {
  pi: [
    { k: "p_factor",    l: "P-Faktor (Proportional)", d: "Reagiert auf aktuelle Abweichung. Höher = aggressiver. Typisch: 0.8–1.5", t: "num", min: 0.1, max: 5, step: 0.1 },
    { k: "i_factor",    l: "I-Faktor (Integral)",      d: "Eliminiert bleibende Abweichungen. Typisch: 0.03–0.08", t: "num", min: 0, max: 0.5, step: 0.01 },
    { k: "tolerance",   l: "Toleranzbereich (W)",       d: "Totband um Regelziel — keine Korrektur innerhalb dieses Bereichs", t: "num", min: 0, max: 200, step: 1 },
    { k: "wait_time",   l: "Wartezeit / Max-Timeout (s)", d: "Feste Wartezeit (ohne Self-Adjust) oder maximale Wartezeit als Sicherheitsnetz (mit Self-Adjust)", t: "num", min: 0, max: 30, step: 1 },
    { k: "self_adjust_enabled", l: "🎯 Self-Adjusting Wait", d: "Wartet auf tatsächliche WR-Ausgangsleistung statt fester Wartezeit. Wartezeit wird zum Max-Timeout.", t: "bool" },
    { k: "self_adjust_tolerance", l: "📏 Zielwert-Toleranz (W)", d: "Abweichung in Watt, ab der der Zielwert als erreicht gilt", t: "num", min: 1, max: 50, step: 1 },
  ],
  zones: [
    { k: "zone1_limit",    l: "Zone 1 SOC-Schwelle (%)", d: "SOC über diesem Wert → Zone 1 (aggressiv)", t: "num", min: 1, max: 99, step: 1 },
    { k: "zone3_limit",    l: "Zone 3 SOC-Schwelle (%)", d: "SOC unter diesem Wert → Zone 3 (Stopp)", t: "num", min: 1, max: 49, step: 1 },
    { k: "discharge_max",  l: "Max. Entladestrom Zone 1 (A)", d: "In Zone 2 automatisch 0 A, Surplus 2 A", t: "num", min: 0, max: 100, step: 1 },
    { k: "hard_limit",     l: "Hard Limit (W)",          d: "Maximale Ausgangsleistung in Zone 1 und Zone 0", t: "num", min: 100, max: 2000, step: 50 },
    { k: "offset_1",       l: "Zone 1 Offset (W)",       d: "Statischer Zielwert. Bei aktivem Dyn. Offset wird dieser überschrieben", t: "num", min: -200, max: 500, step: 1 },
    { k: "offset_2",       l: "Zone 2 Offset (W)",       d: "Statischer Zielwert für batterieschonenden Betrieb", t: "num", min: -200, max: 500, step: 1 },
    { k: "pv_reserve",     l: "PV-Ladereserve (W)",      d: "Watt die für Batterie-Laden reserviert bleiben (Zone 2 Limit + Nachtschwelle)", t: "num", min: 0, max: 500, step: 10 },
  ],
  surplus: [
    { k: "surplus_enabled",       l: "Überschuss-Einspeisung aktivieren", d: "Aktives Einspeisen bei vollem Akku (Zone 0)", t: "bool" },
    { k: "surplus_soc_threshold", l: "SOC-Schwelle (%)",   d: "Ab diesem SOC wird Überschuss eingespeist", t: "num", min: 80, max: 100, step: 1 },
    { k: "surplus_soc_hyst",      l: "SOC-Hysterese (%)",  d: "Austritt erst bei SOC < (Schwelle − Hysterese)", t: "num", min: 1, max: 20, step: 1 },
    { k: "surplus_pv_hyst",       l: "PV-Hysterese (W)",   d: "Verhindert Flackern bei schwankender PV", t: "num", min: 10, max: 200, step: 10 },
  ],
  ac: [
    { k: "ac_enabled",     l: "AC Laden aktivieren",      d: "Laden bei erkanntem externem Überschuss", t: "bool" },
    { k: "ac_soc_target",  l: "Ladeziel SOC (%)",         d: "Laden stoppt bei diesem SOC", t: "num", min: 50, max: 100, step: 1 },
    { k: "ac_power_limit", l: "Max. Ladeleistung (W)",    d: "Obergrenze für AC-Lade-Output", t: "num", min: 100, max: 2000, step: 50 },
    { k: "ac_hysteresis",  l: "Eintritts-Hysterese (W)",  d: "(Grid + Output) muss unter −Hysterese liegen", t: "num", min: 10, max: 500, step: 10 },
    { k: "ac_offset",      l: "Regel-Offset (W)",         d: "Zielwert für PI während AC Laden (typisch negativ). Bei Dyn. Offset überschrieben", t: "num", min: -500, max: 200, step: 5 },
    { k: "ac_p_factor",    l: "AC P-Faktor",              d: "Klein halten (~0.3–0.5) wegen langer Hardware-Flanke", t: "num", min: 0.1, max: 3, step: 0.1 },
    { k: "ac_i_factor",    l: "AC I-Faktor",              d: "I macht bei AC Laden die eigentliche Regelarbeit", t: "num", min: 0, max: 0.5, step: 0.01 },
  ],
  tariff: [
    { k: "tariff_enabled",         l: "Tarif-Steuerung aktivieren",   d: "Laden bei günstigem Stromtarif, Discharge-Lock bei mittlerem", t: "bool" },
    { k: "tariff_price_sensor",    l: "Preis-Sensor (Entity-ID)",     d: "Sensor mit aktuellem Strompreis in ct/kWh", t: "entity", domain: "sensor" },
    { k: "tariff_cheap_threshold", l: "Günstig-Schwelle (ct/kWh)",    d: "Unter diesem Preis → Laden", t: "num", min: 0, max: 100, step: 0.5 },
    { k: "tariff_exp_threshold",   l: "Teuer-Schwelle (ct/kWh)",      d: "Über diesem Preis → normale SOC-Logik. Dazwischen → Discharge-Lock (Zone 2)", t: "num", min: 0, max: 100, step: 0.5 },
    { k: "tariff_soc_target",      l: "Ladeziel SOC (%)",             d: "Tarif-Laden stoppt bei diesem SOC", t: "num", min: 50, max: 100, step: 1 },
    { k: "tariff_power",           l: "Ladeleistung (W)",             d: "Feste Leistung während Tarif-Laden", t: "num", min: 100, max: 2000, step: 50 },
  ],
  // dynoff wird nicht über _renderFields gerendert, sondern über _renderDynoffTab
  night: [
    { k: "night_enabled", l: "Nachtabschaltung aktivieren", d: "Zone 2 bei PV < Reserve deaktivieren (Zone 1 + AC läuft weiter)", t: "bool" },
  ],
};

/* ── Dynamischer Offset: obere Felder + 3-Spalten-Definition ───────────────── */

const DYNOFF_TOP = [
  { k: "dyn_offset_enabled", l: "Dynamischen Offset aktivieren", d: "Offset automatisch aus Netz-Volatilität berechnen. Überschreibt statische Offsets in Zone 1, Zone 2 und AC Laden.", t: "bool" },
  { k: "stddev_window", l: "Stabw.-Fenster (s)", d: "Zeitfenster für die Standardabweichungs-Berechnung (30–300 s). Längeres Fenster = trägere Reaktion, stabilerer Wert.", t: "num", min: 30, max: 300, step: 10 },
];

const DYNOFF_COLS = [
  {
    id: "z1", title: "Zone 1", icon: "⚡", color: "#16a34a",
    fields: [
      { k: "dyn_z1_min",      l: "Min. Offset (W)",     d: "Grundpuffer bei ruhigem Netz", t: "num", min: 0, max: 500, step: 1 },
      { k: "dyn_z1_max",      l: "Max. Offset (W)",     d: "Obergrenze bei unruhigem Netz", t: "num", min: 50, max: 1000, step: 10 },
      { k: "dyn_z1_noise",    l: "Rausch-Schwelle (W)", d: "StdDev darunter = Messrauschen, kein Anstieg", t: "num", min: 0, max: 100, step: 1 },
      { k: "dyn_z1_factor",   l: "Volatilitäts-Faktor", d: "Verstärkung oberhalb Rausch-Schwelle", t: "num", min: 0.5, max: 5, step: 0.1 },
      { k: "dyn_z1_negative", l: "Negativer Offset",    d: "Offset negieren (Regelziel < 0 W)", t: "bool" },
    ],
  },
  {
    id: "z2", title: "Zone 2", icon: "🔋", color: "#0891b2",
    fields: [
      { k: "dyn_z2_min",      l: "Min. Offset (W)",     d: "Grundpuffer bei ruhigem Netz", t: "num", min: 0, max: 500, step: 1 },
      { k: "dyn_z2_max",      l: "Max. Offset (W)",     d: "Obergrenze bei unruhigem Netz", t: "num", min: 50, max: 1000, step: 10 },
      { k: "dyn_z2_noise",    l: "Rausch-Schwelle (W)", d: "StdDev darunter = Messrauschen, kein Anstieg", t: "num", min: 0, max: 100, step: 1 },
      { k: "dyn_z2_factor",   l: "Volatilitäts-Faktor", d: "Verstärkung oberhalb Rausch-Schwelle", t: "num", min: 0.5, max: 5, step: 0.1 },
      { k: "dyn_z2_negative", l: "Negativer Offset",    d: "Offset negieren (Regelziel < 0 W)", t: "bool" },
    ],
  },
  {
    id: "ac", title: "Zone AC", icon: "⚡", color: "#7c3aed",
    fields: [
      { k: "dyn_ac_min",      l: "Min. Offset (W)",     d: "Grundpuffer bei ruhigem Netz", t: "num", min: 0, max: 500, step: 1 },
      { k: "dyn_ac_max",      l: "Max. Offset (W)",     d: "Obergrenze bei unruhigem Netz", t: "num", min: 50, max: 1000, step: 10 },
      { k: "dyn_ac_noise",    l: "Rausch-Schwelle (W)", d: "StdDev darunter = Messrauschen, kein Anstieg", t: "num", min: 0, max: 100, step: 1 },
      { k: "dyn_ac_factor",   l: "Volatilitäts-Faktor", d: "Verstärkung oberhalb Rausch-Schwelle", t: "num", min: 0.5, max: 5, step: 0.1 },
      { k: "dyn_ac_negative", l: "Negativer Offset",    d: "Offset negieren (Regelziel < 0 W)", t: "bool" },
    ],
  },
];

/* ── Panel Class ───────────────────────────────────────────────────────────── */

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
    if (val?.config?.entry_id) {
      this._entryId = val.config.entry_id;
      this._checkInit();
    }
  }

  set hass(val) {
    this._hass = val;
    this._checkInit();
  }

  _checkInit() {
    if (this._hass && this._entryId && !this._initialized) {
      this._initialized = true;
      this._build();
      this._loadConfig();
      this._polling = setInterval(() => this._loadStatus(), 3000);
    }
  }

  /* ── WebSocket ─────────────────────────────────────────────────────────── */

  async _ws(cmd, extra = {}) {
    return this._hass.callWS({ type: `${DOMAIN}/${cmd}`, entry_id: this._entryId, ...extra });
  }

  async _loadConfig() {
    try {
      this._settings = await this._ws("get_config");
      this._renderActiveTab();
    } catch (e) { console.error("Solakon: config load failed", e); }
  }

  async _loadStatus() {
    try {
      this._status = await this._ws("get_status");
      if (this._activeTab === "status") this._updateStatusView();
      this._updateRegBanner();
    } catch (e) { /* ignore */ }
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

  /* ── Build DOM ─────────────────────────────────────────────────────────── */

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; font-family:var(--paper-font-body1_-_font-family, Roboto, sans-serif); color:var(--primary-text-color,#333); }
        .wrap { max-width:900px; margin:0 auto; padding:16px; }
        h1 { margin:0 0 8px; font-size:1.5em; }

        /* Regulation banner */
        .reg-bar { display:flex; align-items:center; gap:12px; padding:10px 16px; border-radius:10px; margin-bottom:12px; cursor:pointer; user-select:none; transition:background .2s; }
        .reg-bar.on  { background:#16a34a22; border:1px solid #16a34a; }
        .reg-bar.off { background:#dc262622; border:1px solid #dc2626; }
        .reg-dot { width:12px; height:12px; border-radius:50%; flex-shrink:0; }
        .reg-bar.on .reg-dot  { background:#16a34a; }
        .reg-bar.off .reg-dot { background:#dc2626; }

        /* Tabs */
        .tabs { display:flex; gap:2px; flex-wrap:wrap; margin-bottom:12px; }
        .tab { padding:7px 12px; border-radius:8px 8px 0 0; cursor:pointer; background:var(--card-background-color,#f5f5f5); border:1px solid var(--divider-color,#ddd); border-bottom:none; font-size:.85em; transition:background .15s; white-space:nowrap; }
        .tab.active { background:var(--primary-color,#03a9f4); color:#fff; }

        /* Content area */
        .content { background:var(--card-background-color,#fff); border:1px solid var(--divider-color,#ddd); border-radius:0 8px 8px 8px; padding:16px; min-height:200px; }

        /* Ausklappbarer Info-Header */
        .info-details { margin-bottom:16px; border:1px solid var(--divider-color,#ddd); border-radius:8px; overflow:hidden; }
        .info-details summary {
          padding:10px 14px; cursor:pointer; font-weight:600; font-size:.9em;
          background:var(--secondary-background-color,#f5f5f5);
          color:var(--primary-color,#03a9f4);
          list-style:none; display:flex; align-items:center; gap:8px;
          user-select:none;
        }
        .info-details summary::-webkit-details-marker { display:none; }
        .info-details summary::before { content:"▶"; font-size:.7em; transition:transform .2s; }
        .info-details[open] summary::before { transform:rotate(90deg); }
        .info-details .info-body {
          padding:12px 14px; font-size:.85em; line-height:1.6;
          color:var(--secondary-text-color,#555);
          white-space:pre-wrap;
          border-top:1px solid var(--divider-color,#ddd);
        }

        /* Form fields */
        .field { margin-bottom:14px; }
        .field label { display:block; font-weight:500; margin-bottom:2px; font-size:.92em; }
        .field .desc { font-size:.8em; color:var(--secondary-text-color,#888); margin-bottom:4px; }
        .field input[type=number], .field input[type=text] { width:100%; max-width:260px; padding:6px 10px; border:1px solid var(--divider-color,#ccc); border-radius:6px; font-size:.95em; box-sizing:border-box; background:var(--card-background-color,#fff); color:var(--primary-text-color,#333); }
        .field select { width:100%; max-width:260px; padding:6px 10px; border:1px solid var(--divider-color,#ccc); border-radius:6px; font-size:.95em; background:var(--card-background-color,#fff); color:var(--primary-text-color,#333); }
        .field .toggle { display:inline-flex; align-items:center; gap:8px; cursor:pointer; }
        .field .toggle input { width:18px; height:18px; }

        /* 3-Spalten-Layout für Dyn. Offset */
        .col-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:12px; }
        @media (max-width:660px) { .col-grid { grid-template-columns:1fr; } }
        .col-card { border:1px solid var(--divider-color,#ddd); border-radius:10px; overflow:hidden; }
        .col-header { padding:8px 12px; font-weight:600; font-size:.88em; color:#fff; display:flex; align-items:center; gap:6px; }
        .col-body { padding:12px; }
        .col-body .field input[type=number] { max-width:100%; }

        /* Status */
        .zone-banner { padding:12px; border-radius:8px; color:#fff; font-weight:600; font-size:1.1em; margin-bottom:12px; text-align:center; }
        .stat-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
        .stat { padding:8px 12px; border-radius:6px; background:var(--secondary-background-color,#f0f0f0); }
        .stat .val { font-size:1.2em; font-weight:600; }
        .stat .lbl { font-size:.78em; color:var(--secondary-text-color,#888); }
        .stat-ac { margin-top:8px; padding:8px 12px; border-radius:6px; background:#7c3aed18; border:1px solid #7c3aed44; }
        .stat-ac .val { font-size:1.1em; font-weight:600; color:#7c3aed; }
        .stat-ac .lbl { font-size:.78em; color:var(--secondary-text-color,#888); }
        .flags { margin-top:10px; display:flex; flex-wrap:wrap; gap:6px; }
        .flags span { padding:3px 10px; border-radius:12px; font-size:.82em; }
        .flags .on  { background:#16a34a22; color:#16a34a; }
        .flags .off { background:#6b728022; color:#6b7280; }

        /* Buttons */
        .btn { padding:8px 18px; border:none; border-radius:6px; cursor:pointer; font-size:.9em; }
        .btn-primary { background:var(--primary-color,#03a9f4); color:#fff; }
        .btn-secondary { background:var(--secondary-background-color,#eee); color:var(--primary-text-color,#333); }

        /* Save bar */
        #save-bar { display:none; position:sticky; bottom:0; background:var(--primary-color,#03a9f4); color:#fff; padding:10px 16px; border-radius:8px; margin-top:12px; align-items:center; justify-content:space-between; z-index:10; }
        #save-bar button { background:#fff; color:var(--primary-color,#03a9f4); border:none; padding:6px 16px; border-radius:6px; cursor:pointer; font-weight:600; }

        /* Toast */
        #toast { display:none; position:fixed; bottom:20px; left:50%; transform:translateX(-50%); padding:10px 24px; border-radius:8px; color:#fff; z-index:999; font-size:.9em; }
      </style>
      <div class="wrap">
        <h1>⚡ Solakon ONE Nulleinspeisung</h1>
        <div class="reg-bar off" id="reg-bar"><div class="reg-dot"></div><span id="reg-text">Regelung inaktiv</span></div>
        <div class="tabs" id="tabs"></div>
        <div class="content" id="content"></div>
        <div id="save-bar"><span>Ungespeicherte Änderungen</span><button onclick="this.getRootNode().host._saveSettings()">💾 Speichern</button></div>
      </div>
      <div id="toast"></div>
    `;

    this.shadowRoot.getElementById("reg-bar").addEventListener("click", () => this._toggleRegulation());

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

  /* ── Render ────────────────────────────────────────────────────────────── */

  _renderActiveTab() {
    const c = this.shadowRoot.getElementById("content");

    if (this._activeTab === "status") {
      this._renderStatus(c);
      this._updateStatusView();
      this._updateSaveBar();
      return;
    }

    c.innerHTML = "";

    // Ausklappbarer Info-Header
    const doc = TAB_DOCS[this._activeTab];
    if (doc) {
      const details = document.createElement("details");
      details.className = "info-details";
      details.innerHTML = `<summary>ℹ️ ${doc.summary}</summary><div class="info-body">${doc.text}</div>`;
      c.appendChild(details);
    }

    if (this._activeTab === "dynoff") {
      this._renderDynoffTab(c);
    } else {
      this._renderFields(c, FIELDS[this._activeTab] || []);
    }

    this._updateSaveBar();
  }

  /* ── Status Tab ────────────────────────────────────────────────────────── */

  _renderStatus(c) {
    c.innerHTML = `
      <div class="zone-banner" id="zone-banner">Lade…</div>
      <div class="stat-grid">
        <div class="stat"><div class="lbl">Netzleistung</div><div class="val" id="st-grid">—</div></div>
        <div class="stat"><div class="lbl">Ausgangsleistung</div><div class="val" id="st-actual">—</div></div>
        <div class="stat"><div class="lbl">Solarleistung</div><div class="val" id="st-solar">—</div></div>
        <div class="stat"><div class="lbl">SOC</div><div class="val" id="st-soc">—</div></div>
        <div class="stat"><div class="lbl">PI Integral</div><div class="val" id="st-int">—</div></div>
        <div class="stat"><div class="lbl">Netz-StdDev</div><div class="val" id="st-stddev">—</div></div>
        <div class="stat"><div class="lbl">Dyn. Offset Z1 / Z2</div><div class="val" id="st-dynoff">—</div></div>
        <div class="stat"><div class="lbl">Seit letzter Änderung</div><div class="val" id="st-elapsed">—</div></div>
      </div>
      <div id="st-ac-row" style="display:none" class="stat-ac">
        <div class="lbl">AC Lade-Offset (aktiv)</div>
        <div class="val" id="st-ac-offset">—</div>
      </div>
      <div style="margin-top:10px"><span class="lbl">Letzte Aktion:</span> <span id="st-action">—</span></div>
      <div style="margin-top:4px"><span class="lbl">Fehler:</span> <span id="st-error" style="color:#dc2626">—</span></div>
      <div class="flags" id="st-flags"></div>
      <div style="margin-top:12px"><button class="btn btn-secondary" onclick="this.getRootNode().host._resetIntegral()">🔄 Integral zurücksetzen</button></div>
    `;
  }

  _updateStatusView() {
    const st = this._status;
    if (!st) return;

    const z = ZONE_CFG[st.zone] || ZONE_CFG[2];
    const b = this.shadowRoot.getElementById("zone-banner");
    if (b) { b.textContent = `${z.icon} ${z.label}`; b.style.background = z.color; }

    const set = (id, v) => { const e = this.shadowRoot.getElementById(id); if (e) e.textContent = v; };
    set("st-grid", `${st.grid ?? "—"} W`);
    set("st-actual", `${st.actual_power ?? "—"} W`);
    set("st-solar", `${st.solar ?? "—"} W`);
    set("st-soc", `${st.soc ?? "—"} %`);
    set("st-int", `${(st.integral ?? 0).toFixed(2)}`);
    set("st-stddev", `${(st.stddev ?? 0).toFixed(1)} W`);
    set("st-dynoff", st.dyn_offset_enabled
      ? `${st.dyn_z1?.toFixed(0) ?? "—"} / ${st.dyn_z2?.toFixed(0) ?? "—"} W`
      : "inaktiv");
    set("st-action", st.last_action || "—");
    set("st-error", st.last_error || "Keine");

    // AC Offset-Anzeige: sichtbar wenn AC Laden aktiv
    const acRow = this.shadowRoot.getElementById("st-ac-row");
    if (acRow) {
      if (st.ac_charge) {
        acRow.style.display = "";
        const acOffsetVal = st.dyn_offset_enabled
          ? `${st.dyn_ac?.toFixed(0) ?? "—"} W (dynamisch)`
          : `${this._settings.ac_offset ?? "—"} W (statisch)`;
        set("st-ac-offset", acOffsetVal);
      } else {
        acRow.style.display = "none";
      }
    }

    // Elapsed seit letzter Aktion
    if (st.last_action_ts) {
      const elapsed = Math.round(Date.now() / 1000 - st.last_action_ts);
      if (elapsed < 0) {
        set("st-elapsed", "—");
      } else if (elapsed < 60) {
        set("st-elapsed", `${elapsed} s`);
      } else if (elapsed < 3600) {
        set("st-elapsed", `${Math.floor(elapsed / 60)} min ${elapsed % 60} s`);
      } else {
        set("st-elapsed", `${Math.floor(elapsed / 3600)} h ${Math.floor((elapsed % 3600) / 60)} min`);
      }
    } else {
      set("st-elapsed", "—");
    }

    const fl = this.shadowRoot.getElementById("st-flags");
    if (fl) {
      const flags = [
        ["Zyklus", st.cycle_active],
        ["Surplus", st.surplus_active],
        ["AC Laden", st.ac_charge],
        ["Tarif-Laden", st.tariff_charge],
      ];
      fl.innerHTML = flags.map(([n, v]) =>
        `<span class="${v ? "on" : "off"}">${v ? "●" : "○"} ${n}</span>`
      ).join("");
    }
  }

  _updateRegBanner() {
    const on = this._settings.regulation_enabled;
    const bar = this.shadowRoot.getElementById("reg-bar");
    const txt = this.shadowRoot.getElementById("reg-text");
    if (bar) { bar.className = `reg-bar ${on ? "on" : "off"}`; }
    if (txt) { txt.textContent = on ? "Regelung aktiv — klicken zum Deaktivieren" : "Regelung inaktiv — klicken zum Aktivieren"; }
  }

  /* ── Dynoff Tab (Spalten-Layout) ───────────────────────────────────────── */

  _renderDynoffTab(container) {
    // Obere Felder: Aktivierung + Stabw.-Fenster
    const topWrap = document.createElement("div");
    this._appendFields(topWrap, DYNOFF_TOP, "dyn_offset_enabled");
    container.appendChild(topWrap);

    // Spalten-Grid
    const dynOn = this._effectiveValue("dyn_offset_enabled");
    const grid = document.createElement("div");
    grid.className = "col-grid";
    grid.id = "dynoff-col-grid";
    grid.style.opacity = dynOn ? "1" : "0.4";
    grid.style.pointerEvents = dynOn ? "" : "none";

    for (const col of DYNOFF_COLS) {
      const card = document.createElement("div");
      card.className = "col-card";
      const hdr = document.createElement("div");
      hdr.className = "col-header";
      hdr.style.background = col.color;
      hdr.innerHTML = `${col.icon} ${col.title}`;
      card.appendChild(hdr);
      const body = document.createElement("div");
      body.className = "col-body";
      this._appendFields(body, col.fields, null);
      card.appendChild(body);
      grid.appendChild(card);
    }

    container.appendChild(grid);

    // Wenn dyn_offset_enabled geändert wird: Grid-Opacity anpassen
    const toggleEl = topWrap.querySelector(`input[data-key="dyn_offset_enabled"]`);
    if (toggleEl) {
      toggleEl.addEventListener("change", (e) => {
        grid.style.opacity = e.target.checked ? "1" : "0.4";
        grid.style.pointerEvents = e.target.checked ? "" : "none";
      });
    }
  }

  /* ── Field Rendering ───────────────────────────────────────────────────── */

  _renderFields(container, fields) {
    container.innerHTML = "";
    const tabId = this._activeTab;
    const enabledKey = this._getTabEnabledKey(tabId);
    this._appendFields(container, fields, enabledKey);
  }

  _appendFields(container, fields, enabledKey) {
    for (const f of fields) {
      const cur = this._effectiveValue(f.k);
      const div = document.createElement("div");
      div.className = "field";

      // Bedingte Sichtbarkeit: Felder außer dem Toggle selbst ausblenden
      if (enabledKey && f.k !== enabledKey) {
        const moduleOn = this._effectiveValue(enabledKey);
        if (!moduleOn) div.style.display = "none";
        div.dataset.conditional = enabledKey;
      }

      if (f.t === "bool") {
        div.innerHTML = `<label class="toggle"><input type="checkbox" data-key="${f.k}" ${cur ? "checked" : ""}/> ${f.l}</label>
          <div class="desc">${f.d || ""}</div>`;
        div.querySelector("input").addEventListener("change", (e) => {
          this._dirty[f.k] = e.target.checked;
          this._updateSaveBar();
          if (f.k === enabledKey) {
            // Alle konditionalen Felder in diesem Container ein-/ausblenden
            container.querySelectorAll(`[data-conditional="${f.k}"]`).forEach(el => {
              el.style.display = e.target.checked ? "" : "none";
            });
          }
        });
      } else if (f.t === "num") {
        div.innerHTML = `<label>${f.l}</label><div class="desc">${f.d || ""}</div>
          <input type="number" min="${f.min}" max="${f.max}" step="${f.step}" value="${cur ?? f.min}"/>`;
        div.querySelector("input").addEventListener("change", (e) => {
          this._dirty[f.k] = parseFloat(e.target.value);
          this._updateSaveBar();
        });
      } else if (f.t === "entity") {
        const eid = `ep_${f.k}`;
        div.innerHTML = `<label>${f.l}</label><div class="desc">${f.d || ""}</div>
          <input type="text" list="${eid}_list" value="${cur || ""}" placeholder="sensor.xxx"/>
          <datalist id="${eid}_list"></datalist>`;
        const inp = div.querySelector("input");
        const dl = div.querySelector("datalist");
        if (this._hass?.states) {
          const domain = f.domain || "";
          Object.keys(this._hass.states)
            .filter(e => !domain || e.startsWith(domain + "."))
            .sort()
            .forEach(e => {
              const opt = document.createElement("option");
              opt.value = e;
              const name = this._hass.states[e]?.attributes?.friendly_name || "";
              if (name) opt.label = name;
              dl.appendChild(opt);
            });
        }
        inp.addEventListener("change", () => {
          this._dirty[f.k] = inp.value;
          this._updateSaveBar();
        });
      } else if (f.t === "text") {
        div.innerHTML = `<label>${f.l}</label><div class="desc">${f.d || ""}</div>
          <input type="text" value="${cur || ""}"/>`;
        div.querySelector("input").addEventListener("change", (e) => {
          this._dirty[f.k] = e.target.value;
          this._updateSaveBar();
        });
      }

      container.appendChild(div);
    }
  }

  /* ── Helpers ───────────────────────────────────────────────────────────── */

  _effectiveValue(key) {
    return key in this._dirty ? this._dirty[key] : this._settings[key];
  }

  _getTabEnabledKey(tabId) {
    const map = {
      surplus: "surplus_enabled",
      ac: "ac_enabled",
      tariff: "tariff_enabled",
      night: "night_enabled",
    };
    return map[tabId] || null;
  }

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
