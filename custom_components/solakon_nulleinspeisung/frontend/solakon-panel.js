/**
 * Solakon ONE Nulleinspeisung — Sidebar Panel (Komplett)
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

/* ── Field definitions per tab ─────────────────────────────────────────────── */

const FIELDS = {
  pi: [
    { k: "p_factor",    l: "P-Faktor (Proportional)", d: "Reagiert auf aktuelle Abweichung. Höher = aggressiver. Typisch: 0.8–1.5", t: "num", min: 0.1, max: 5, step: 0.1 },
    { k: "i_factor",    l: "I-Faktor (Integral)",      d: "Eliminiert bleibende Abweichungen. Typisch: 0.03–0.08", t: "num", min: 0, max: 0.5, step: 0.01 },
    { k: "tolerance",   l: "Toleranzbereich (W)",       d: "Totband um Regelziel — keine Korrektur innerhalb dieses Bereichs", t: "num", min: 0, max: 200, step: 1 },
    { k: "wait_time",   l: "Wartezeit (s)",             d: "Verzögerung nach Leistungsänderung. Gibt WR und Sensoren Zeit.", t: "num", min: 0, max: 30, step: 1 },
    { k: "stddev_window", l: "Stabw.-Fenster (s)",      d: "Zeitfenster für internen Standardabweichungs-Sensor (30–300 s)", t: "num", min: 30, max: 300, step: 10 },
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
  dynoff: [
    { k: "dyn_offset_enabled", l: "Dynamischer Offset aktivieren", d: "Offset automatisch aus Netz-Volatilität berechnen. Überschreibt statische Offsets", t: "bool" },
    { k: "_hdr_z1", l: "── Zone 1 ──", t: "header" },
    { k: "dyn_z1_min",      l: "Min. Offset Zone 1 (W)",     d: "Grundpuffer bei ruhigem Netz", t: "num", min: 0, max: 500, step: 1 },
    { k: "dyn_z1_max",      l: "Max. Offset Zone 1 (W)",     d: "Obergrenze bei unruhigem Netz", t: "num", min: 50, max: 1000, step: 10 },
    { k: "dyn_z1_noise",    l: "Rausch-Schwelle Zone 1 (W)", d: "StdDev darunter = Messrauschen", t: "num", min: 0, max: 100, step: 1 },
    { k: "dyn_z1_factor",   l: "Volatilitäts-Faktor Zone 1", d: "Verstärkung oberhalb Rausch-Schwelle", t: "num", min: 0.5, max: 5, step: 0.1 },
    { k: "dyn_z1_negative", l: "Negativer Offset Zone 1",    d: "Offset negieren (Regelziel < 0 W)", t: "bool" },
    { k: "_hdr_z2", l: "── Zone 2 ──", t: "header" },
    { k: "dyn_z2_min",      l: "Min. Offset Zone 2 (W)",     d: "Grundpuffer bei ruhigem Netz", t: "num", min: 0, max: 500, step: 1 },
    { k: "dyn_z2_max",      l: "Max. Offset Zone 2 (W)",     d: "Obergrenze bei unruhigem Netz", t: "num", min: 50, max: 1000, step: 10 },
    { k: "dyn_z2_noise",    l: "Rausch-Schwelle Zone 2 (W)", d: "StdDev darunter = Messrauschen", t: "num", min: 0, max: 100, step: 1 },
    { k: "dyn_z2_factor",   l: "Volatilitäts-Faktor Zone 2", d: "Verstärkung oberhalb Rausch-Schwelle", t: "num", min: 0.5, max: 5, step: 0.1 },
    { k: "dyn_z2_negative", l: "Negativer Offset Zone 2",    d: "Offset negieren (Regelziel < 0 W)", t: "bool" },
    { k: "_hdr_ac", l: "── Zone AC ──", t: "header" },
    { k: "dyn_ac_min",      l: "Min. Offset AC (W)",         d: "Grundpuffer bei ruhigem Netz", t: "num", min: 0, max: 500, step: 1 },
    { k: "dyn_ac_max",      l: "Max. Offset AC (W)",         d: "Obergrenze bei unruhigem Netz", t: "num", min: 50, max: 1000, step: 10 },
    { k: "dyn_ac_noise",    l: "Rausch-Schwelle AC (W)",     d: "StdDev darunter = Messrauschen", t: "num", min: 0, max: 100, step: 1 },
    { k: "dyn_ac_factor",   l: "Volatilitäts-Faktor AC",     d: "Verstärkung oberhalb Rausch-Schwelle", t: "num", min: 0.5, max: 5, step: 0.1 },
    { k: "dyn_ac_negative", l: "Negativer Offset AC",        d: "Offset negieren (Regelziel < 0 W)", t: "bool" },
  ],
  night: [
    { k: "night_enabled", l: "Nachtabschaltung aktivieren", d: "Zone 2 bei PV < Reserve deaktivieren (Zone 1 + AC läuft weiter)", t: "bool" },
  ],
};

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
        .wrap { max-width:820px; margin:0 auto; padding:16px; }
        h1 { margin:0 0 8px; font-size:1.5em; }
        /* Regulation banner */
        .reg-bar { display:flex; align-items:center; gap:12px; padding:10px 16px; border-radius:10px; margin-bottom:12px; cursor:pointer; user-select:none; transition:background .2s; }
        .reg-bar.on  { background:#16a34a22; border:1px solid #16a34a; }
        .reg-bar.off { background:#dc262622; border:1px solid #dc2626; }
        .reg-dot { width:12px; height:12px; border-radius:50%; }
        .reg-bar.on .reg-dot  { background:#16a34a; }
        .reg-bar.off .reg-dot { background:#dc2626; }
        /* Tabs */
        .tabs { display:flex; gap:2px; flex-wrap:wrap; margin-bottom:12px; }
        .tab { padding:7px 12px; border-radius:8px 8px 0 0; cursor:pointer; background:var(--card-background-color,#f5f5f5); border:1px solid var(--divider-color,#ddd); border-bottom:none; font-size:.85em; transition:background .15s; white-space:nowrap; }
        .tab.active { background:var(--primary-color,#03a9f4); color:#fff; }
        /* Content area */
        .content { background:var(--card-background-color,#fff); border:1px solid var(--divider-color,#ddd); border-radius:0 8px 8px 8px; padding:16px; min-height:200px; }
        /* Form fields */
        .field { margin-bottom:14px; }
        .field label { display:block; font-weight:500; margin-bottom:2px; font-size:.92em; }
        .field .desc { font-size:.8em; color:var(--secondary-text-color,#888); margin-bottom:4px; }
        .field input[type=number], .field input[type=text] { width:100%; max-width:300px; padding:6px 10px; border:1px solid var(--divider-color,#ccc); border-radius:6px; font-size:.95em; box-sizing:border-box; background:var(--card-background-color,#fff); color:var(--primary-text-color,#333); }
        .field select { width:100%; max-width:300px; padding:6px 10px; border:1px solid var(--divider-color,#ccc); border-radius:6px; font-size:.95em; background:var(--card-background-color,#fff); color:var(--primary-text-color,#333); }
        .field .toggle { display:inline-flex; align-items:center; gap:8px; cursor:pointer; }
        .field .toggle input { width:18px; height:18px; }
        .header-row { font-weight:600; font-size:.95em; margin:18px 0 6px; padding:4px 0; border-bottom:1px solid var(--divider-color,#ddd); color:var(--primary-color,#03a9f4); }
        /* Status */
        .zone-banner { padding:12px; border-radius:8px; color:#fff; font-weight:600; font-size:1.1em; margin-bottom:12px; text-align:center; }
        .stat-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
        .stat { padding:8px 12px; border-radius:6px; background:var(--secondary-background-color,#f0f0f0); }
        .stat .val { font-size:1.2em; font-weight:600; }
        .stat .lbl { font-size:.78em; color:var(--secondary-text-color,#888); }
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

    // Regulation toggle
    this.shadowRoot.getElementById("reg-bar").addEventListener("click", () => this._toggleRegulation());

    // Tabs
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
    } else {
      this._renderFields(c, FIELDS[this._activeTab] || []);
    }
    this._updateSaveBar();
  }

  _renderStatus(c) {
    c.innerHTML = `
      <div class="zone-banner" id="zone-banner">Lade…</div>
      <div class="stat-grid">
        <div class="stat"><div class="lbl">Netzleistung</div><div class="val" id="st-grid">—</div></div>
        <div class="stat"><div class="lbl">Solarleistung</div><div class="val" id="st-solar">—</div></div>
        <div class="stat"><div class="lbl">SOC</div><div class="val" id="st-soc">—</div></div>
        <div class="stat"><div class="lbl">PI Integral</div><div class="val" id="st-int">—</div></div>
        <div class="stat"><div class="lbl">Netz-StdDev</div><div class="val" id="st-stddev">—</div></div>
        <div class="stat"><div class="lbl">Dyn. Offset Z1 / Z2</div><div class="val" id="st-dynoff">—</div></div>
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
    set("st-solar", `${st.solar ?? "—"} W`);
    set("st-soc", `${st.soc ?? "—"} %`);
    set("st-int", `${(st.integral ?? 0).toFixed(2)}`);
    set("st-stddev", `${(st.stddev ?? 0).toFixed(1)} W`);
    set("st-dynoff", st.dyn_offset_enabled ? `${st.dyn_z1?.toFixed(0) ?? "—"} / ${st.dyn_z2?.toFixed(0) ?? "—"} W` : "inaktiv");
    set("st-action", st.last_action || "—");
    set("st-error", st.last_error || "Keine");

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

  /* ── Field Rendering ───────────────────────────────────────────────────── */

  _renderFields(container, fields) {
    container.innerHTML = "";

    // Conditional visibility: check if the master toggle is active
    const tabId = this._activeTab;
    const enabledKey = this._getTabEnabledKey(tabId);

    for (const f of fields) {
      // Header separator
      if (f.t === "header") {
        const hdr = document.createElement("div");
        hdr.className = "header-row";
        hdr.textContent = f.l;
        container.appendChild(hdr);
        continue;
      }

      const cur = f.k in this._dirty ? this._dirty[f.k] : this._settings[f.k];
      const div = document.createElement("div");
      div.className = "field";

      // Hide non-toggle fields if module is disabled (except the toggle itself)
      if (enabledKey && f.k !== enabledKey) {
        const moduleOn = this._dirty[enabledKey] !== undefined ? this._dirty[enabledKey] : this._settings[enabledKey];
        if (!moduleOn) {
          div.style.display = "none";
        }
        div.dataset.conditional = enabledKey;
      }

      if (f.t === "bool") {
        div.innerHTML = `<label class="toggle"><input type="checkbox" ${cur ? "checked" : ""}/> ${f.l}</label>
          <div class="desc">${f.d || ""}</div>`;
        div.querySelector("input").addEventListener("change", (e) => {
          this._dirty[f.k] = e.target.checked;
          this._updateSaveBar();
          // Toggle conditional fields
          if (f.k === enabledKey) this._toggleConditional(container, enabledKey, e.target.checked);
        });
      } else if (f.t === "num") {
        div.innerHTML = `<label>${f.l}</label><div class="desc">${f.d || ""}</div>
          <input type="number" min="${f.min}" max="${f.max}" step="${f.step}" value="${cur ?? f.min}"/>`;
        div.querySelector("input").addEventListener("change", (e) => {
          this._dirty[f.k] = parseFloat(e.target.value);
          this._updateSaveBar();
        });
      } else if (f.t === "entity") {
        // Entity picker with datalist
        const eid = `ep_${f.k}`;
        div.innerHTML = `<label>${f.l}</label><div class="desc">${f.d || ""}</div>
          <input type="text" list="${eid}_list" value="${cur || ""}" placeholder="sensor.xxx"/>
          <datalist id="${eid}_list"></datalist>`;
        const inp = div.querySelector("input");
        const dl = div.querySelector("datalist");
        // Populate datalist with matching entities
        if (this._hass && this._hass.states) {
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

  _getTabEnabledKey(tabId) {
    const map = {
      surplus: "surplus_enabled",
      ac: "ac_enabled",
      tariff: "tariff_enabled",
      dynoff: "dyn_offset_enabled",
      night: "night_enabled",
    };
    return map[tabId] || null;
  }

  _toggleConditional(container, key, on) {
    container.querySelectorAll(`[data-conditional="${key}"]`).forEach(el => {
      el.style.display = on ? "" : "none";
    });
  }

  /* ── Helpers ───────────────────────────────────────────────────────────── */

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
