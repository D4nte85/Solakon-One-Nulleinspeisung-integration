/**
 * Solakon ONE Nulleinspeisung — Sidebar Panel (Komplett)
 * Alle Blueprint-Parameter, farbiges Aktivierungs-Banner, Integral-Reset.
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
  { id: "night",   label: "Nacht",      icon: "🌙" },
];

/* ── Field definitions per tab ─────────────────────────────────────────────── */

const FIELDS = {
  pi: [
    { k: "p_factor",  l: "P-Faktor (Proportional)", d: "Reagiert auf aktuelle Abweichung. Höher = aggressiver. Typisch: 0.8–1.5", t: "num", min: 0.1, max: 5, step: 0.1 },
    { k: "i_factor",  l: "I-Faktor (Integral)",      d: "Eliminiert bleibende Abweichungen. Typisch: 0.03–0.08", t: "num", min: 0, max: 0.5, step: 0.01 },
    { k: "tolerance", l: "Toleranzbereich (W)",       d: "Totband um Regelziel — keine Korrektur innerhalb dieses Bereichs", t: "num", min: 0, max: 200, step: 1 },
    { k: "wait_time", l: "Wartezeit (s)",             d: "Verzögerung nach Leistungsänderung. Gibt WR und Sensoren Zeit.", t: "num", min: 0, max: 30, step: 1 },
  ],
  zones: [
    { k: "zone1_limit",    l: "Zone 1 SOC-Schwelle (%)", d: "SOC über diesem Wert → Zone 1 (aggressiv)", t: "num", min: 1, max: 99, step: 1 },
    { k: "zone3_limit",    l: "Zone 3 SOC-Schwelle (%)", d: "SOC unter diesem Wert → Zone 3 (Stopp)", t: "num", min: 1, max: 49, step: 1 },
    { k: "discharge_max",  l: "Max. Entladestrom Zone 1 (A)", d: "In Zone 2 automatisch 0 A", t: "num", min: 0, max: 100, step: 1 },
    { k: "hard_limit",     l: "Hard Limit (W)",          d: "Maximale Ausgangsleistung in Zone 1 und Zone 0", t: "num", min: 100, max: 2000, step: 50 },
    { k: "offset_1",       l: "Zone 1 Offset (W)",       d: "Statischer Zielwert. Positiv = leichter Bezug, Negativ = leichte Einspeisung", t: "num", min: -200, max: 500, step: 1 },
    { k: "offset_2",       l: "Zone 2 Offset (W)",       d: "Statischer Zielwert für batterieschonenden Betrieb", t: "num", min: -200, max: 500, step: 1 },
    { k: "pv_reserve",     l: "PV-Ladereserve (W)",      d: "Watt die für Batterie-Laden reserviert bleiben (Zone 2 Limit)", t: "num", min: 0, max: 500, step: 10 },
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
    { k: "ac_offset",      l: "Regel-Offset (W)",         d: "Zielwert für PI während AC Laden (typisch negativ)", t: "num", min: -500, max: 200, step: 5 },
    { k: "ac_p_factor",    l: "AC P-Faktor",              d: "Klein halten (~0.3–0.5) wegen langer Hardware-Flanke", t: "num", min: 0.1, max: 3, step: 0.1 },
    { k: "ac_i_factor",    l: "AC I-Faktor",              d: "I macht bei AC Laden die eigentliche Regelarbeit", t: "num", min: 0, max: 0.5, step: 0.01 },
  ],
  tariff: [
    { k: "tariff_enabled",         l: "Tarif-Steuerung aktivieren",   d: "Laden bei günstigem Stromtarif", t: "bool" },
    { k: "tariff_price_sensor",    l: "Preis-Sensor (Entity-ID)",     d: "z.B. sensor.tibber_price oder sensor.awattar_price", t: "text" },
    { k: "tariff_cheap_threshold", l: "Günstig-Schwelle (ct/kWh)",    d: "Unter diesem Preis → Laden", t: "num", min: 0, max: 100, step: 0.5 },
    { k: "tariff_exp_threshold",   l: "Teuer-Schwelle (ct/kWh)",      d: "Über diesem Preis → normale SOC-Logik", t: "num", min: 0, max: 100, step: 0.5 },
    { k: "tariff_soc_target",      l: "Ladeziel SOC (%)",             d: "Tarif-Laden stoppt bei diesem SOC", t: "num", min: 50, max: 100, step: 1 },
    { k: "tariff_power",           l: "Ladeleistung (W)",             d: "Feste Leistung während Tarif-Laden", t: "num", min: 100, max: 2000, step: 50 },
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
      this._showToast(on ? "✅ Regelung AKTIVIERT" : "⛔ Regelung DEAKTIVIERT");
    } catch (e) { this._showToast("❌ " + e.message, true); }
  }

  async _resetIntegral() {
    try {
      await this._ws("reset_integral");
      this._showToast("🔄 Integral zurückgesetzt");
    } catch (e) { this._showToast("❌ " + e.message, true); }
  }

  /* ── Layout ────────────────────────────────────────────────────────────── */

  _build() {
    const root = this.shadowRoot;
    root.innerHTML = `
    <style>
      :host { display:block; font-family:var(--paper-font-body1_-_font-family, sans-serif);
              color:var(--primary-text-color); background:var(--primary-background-color); min-height:100vh; }
      .layout { display:flex; height:100vh; }

      /* ── Nav ── */
      .nav { width:200px; background:var(--card-background-color); border-right:1px solid var(--divider-color);
             display:flex; flex-direction:column; flex-shrink:0; overflow-y:auto; }
      .nav-header { padding:16px 20px; font-weight:700; font-size:1.1rem; color:var(--primary-color);
                     border-bottom:1px solid var(--divider-color); }
      .nav-item { padding:11px 20px; cursor:pointer; display:flex; align-items:center; gap:10px;
                  transition:background .15s; font-size:.95rem; }
      .nav-item:hover { background:var(--secondary-background-color); }
      .nav-item.active { background:var(--primary-color); color:#fff; border-radius:0; }

      /* ── Content ── */
      .content { flex:1; padding:20px 28px; overflow-y:auto; position:relative; }

      /* ── Regulation Banner ── */
      .reg-banner { padding:14px 20px; border-radius:10px; margin-bottom:18px; color:#fff;
                    display:flex; align-items:center; justify-content:space-between; font-weight:600;
                    transition:background .4s; }
      .reg-banner.off { background:linear-gradient(135deg,#dc2626,#b91c1c); }
      .reg-banner.on  { background:linear-gradient(135deg,#16a34a,#15803d); }
      .reg-btn { padding:8px 18px; border-radius:6px; border:2px solid rgba(255,255,255,.6);
                 background:rgba(255,255,255,.15); color:#fff; cursor:pointer; font-weight:700;
                 font-size:.9rem; transition:background .2s; }
      .reg-btn:hover { background:rgba(255,255,255,.3); }

      /* ── Cards ── */
      .card { background:var(--card-background-color); border-radius:12px; padding:20px;
              margin-bottom:16px; box-shadow:var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.08)); }
      .card h3 { margin:0 0 14px; font-size:1rem; color:var(--primary-color); }

      /* ── Zone Banner ── */
      .zone-banner { padding:16px 20px; border-radius:10px; margin-bottom:18px; color:#fff;
                     display:flex; align-items:center; gap:16px; transition:background .5s; }
      .zone-icon { font-size:2rem; }
      .zone-text-main { font-weight:700; font-size:1.1rem; }
      .zone-text-sub  { opacity:.9; font-size:.9rem; }

      /* ── Stat Grid ── */
      .stat-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:14px; }
      .stat-item { background:var(--secondary-background-color); padding:12px; border-radius:8px; }
      .stat-label { font-size:.78rem; color:var(--secondary-text-color); margin-bottom:2px; }
      .stat-value { font-size:1.15rem; font-weight:700; }

      /* ── Flags ── */
      .flag-row { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
      .flag { padding:4px 12px; border-radius:16px; font-size:.8rem; font-weight:600; }
      .flag.on  { background:#dcfce7; color:#166534; }
      .flag.off { background:var(--secondary-background-color); color:var(--secondary-text-color); }

      /* ── Form ── */
      .form-group { margin-bottom:18px; }
      .form-group label { display:block; margin-bottom:3px; font-weight:600; font-size:.92rem; }
      .form-group .desc { font-size:.8rem; color:var(--secondary-text-color); margin-bottom:6px; }
      input[type="number"], input[type="text"] {
        width:100%; padding:9px 10px; border-radius:6px; box-sizing:border-box;
        border:1px solid var(--divider-color); background:var(--card-background-color);
        color:var(--primary-text-color); font-size:.95rem; }
      input:focus { outline:2px solid var(--primary-color); outline-offset:-1px; }
      .cb-row { display:flex; align-items:center; gap:8px; }
      .cb-row input[type="checkbox"] { width:18px; height:18px; accent-color:var(--primary-color); }

      /* ── Save Bar ── */
      .save-bar { position:sticky; bottom:0; background:var(--primary-color); color:#fff;
                  padding:12px 24px; display:none; justify-content:space-between; align-items:center;
                  border-radius:10px 10px 0 0; z-index:10; }
      .btn { padding:8px 18px; border-radius:6px; border:none; cursor:pointer; font-weight:700; font-size:.9rem; }
      .btn-white { background:#fff; color:var(--primary-color); }
      .btn-ghost { background:var(--secondary-background-color); color:var(--primary-text-color); }

      /* ── Toast ── */
      .toast { position:fixed; bottom:24px; right:24px; padding:12px 22px; border-radius:8px;
               color:#fff; z-index:1000; display:none; font-weight:600; font-size:.9rem;
               box-shadow:0 4px 12px rgba(0,0,0,.2); }

      /* ── Mobile ── */
      @media(max-width:700px){
        .layout { flex-direction:column; height:auto; }
        .nav { width:100%; flex-direction:row; overflow-x:auto; border-right:none; border-bottom:1px solid var(--divider-color); }
        .nav-header { display:none; }
        .nav-item { padding:10px 14px; white-space:nowrap; font-size:.85rem; }
        .content { padding:14px; }
      }
    </style>

    <div class="layout">
      <div class="nav">
        <div class="nav-header">⚡ Solakon ONE</div>
        ${TABS.map(t => `<div class="nav-item" data-tab="${t.id}">${t.icon} ${t.label}</div>`).join("")}
      </div>
      <div class="content">
        <div class="reg-banner off" id="reg-banner">
          <span id="reg-text">⛔ Schreibteil INAKTIV — Regelung deaktiviert</span>
          <button class="reg-btn" id="reg-btn">Aktivieren</button>
        </div>
        <div id="tab-content"></div>
        <div class="save-bar" id="save-bar">
          <span>Ungespeicherte Änderungen</span>
          <button class="btn btn-white" id="btn-save">Speichern</button>
        </div>
      </div>
    </div>
    <div id="toast" class="toast"></div>`;

    root.querySelectorAll(".nav-item").forEach(el => {
      el.onclick = () => { this._activeTab = el.dataset.tab; this._renderActiveTab(); };
    });
    root.getElementById("btn-save").onclick = () => this._saveSettings();
    root.getElementById("reg-btn").onclick = () => this._toggleRegulation();
    this._activeTab = "status";
  }

  /* ── Regulation Banner Update ──────────────────────────────────────────── */

  _updateRegBanner() {
    const root = this.shadowRoot;
    const banner = root.getElementById("reg-banner");
    const text = root.getElementById("reg-text");
    const btn = root.getElementById("reg-btn");
    const on = this._settings.regulation_enabled;
    banner.className = "reg-banner " + (on ? "on" : "off");
    text.textContent = on
      ? "✅ Regelung AKTIV — Schreibbefehle werden gesendet"
      : "⛔ Schreibteil INAKTIV — Berechnung läuft, aber keine Modbus-Befehle";
    btn.textContent = on ? "Deaktivieren" : "Aktivieren";
  }

  /* ── Tab Rendering ─────────────────────────────────────────────────────── */

  _renderActiveTab() {
    const root = this.shadowRoot;
    root.querySelectorAll(".nav-item").forEach(el =>
      el.classList.toggle("active", el.dataset.tab === this._activeTab)
    );
    this._updateRegBanner();

    const c = root.getElementById("tab-content");
    const s = this._settings;

    if (this._activeTab === "status") {
      c.innerHTML = `
        <div class="zone-banner" id="zone-banner" style="background:grey">
          <div class="zone-icon" id="zone-icon">❓</div>
          <div>
            <div class="zone-text-main" id="zone-label">Lade…</div>
            <div class="zone-text-sub" id="mode-label"></div>
          </div>
        </div>
        <div class="card">
          <div class="stat-grid">
            <div class="stat-item"><div class="stat-label">Netz</div><div class="stat-value" id="val-grid">--</div></div>
            <div class="stat-item"><div class="stat-label">Solar</div><div class="stat-value" id="val-solar">--</div></div>
            <div class="stat-item"><div class="stat-label">Batterie</div><div class="stat-value" id="val-soc">--</div></div>
            <div class="stat-item"><div class="stat-label">Ausgang</div><div class="stat-value" id="val-actual">--</div></div>
            <div class="stat-item"><div class="stat-label">Integral</div><div class="stat-value" id="val-integral">--</div></div>
          </div>
          <div class="flag-row" id="flag-row"></div>
        </div>
        <div class="card">
          <div class="stat-label">Letzte Aktion</div>
          <div id="val-action" style="margin-top:6px;font-weight:500;">--</div>
          <div id="val-error" style="margin-top:4px;color:#dc2626;font-size:.85rem;"></div>
          <button class="btn btn-ghost" style="margin-top:14px;" id="btn-rst">🔄 Integral Reset</button>
        </div>`;
      root.getElementById("btn-rst").onclick = () => this._resetIntegral();
      this._loadStatus();
    } else {
      const fields = FIELDS[this._activeTab] || [];
      const tabMeta = TABS.find(t => t.id === this._activeTab);
      c.innerHTML = `<div class="card"><h3>${tabMeta.icon} ${tabMeta.label}</h3><div id="fields"></div></div>`;
      const fc = c.querySelector("#fields");

      fields.forEach(f => {
        const val = this._dirty[f.k] !== undefined ? this._dirty[f.k] : s[f.k];
        const grp = document.createElement("div");
        grp.className = "form-group";

        if (f.t === "bool") {
          grp.innerHTML = `<div class="cb-row">
            <input type="checkbox" data-key="${f.k}" ${val ? "checked" : ""}>
            <label>${f.l}</label></div>
            <div class="desc">${f.d}</div>`;
        } else if (f.t === "text") {
          grp.innerHTML = `<label>${f.l}</label><div class="desc">${f.d}</div>
            <input type="text" data-key="${f.k}" value="${val || ""}">`;
        } else {
          grp.innerHTML = `<label>${f.l}</label><div class="desc">${f.d}</div>
            <input type="number" data-key="${f.k}" value="${val ?? 0}"
              ${f.min != null ? `min="${f.min}"` : ""} ${f.max != null ? `max="${f.max}"` : ""}
              ${f.step != null ? `step="${f.step}"` : ""}>`;
        }
        fc.appendChild(grp);
      });

      fc.querySelectorAll("input").forEach(inp => {
        inp.onchange = () => {
          const key = inp.dataset.key;
          let v;
          if (inp.type === "checkbox") v = inp.checked;
          else if (inp.type === "number") v = parseFloat(inp.value);
          else v = inp.value;
          this._dirty[key] = v;
          this._updateSaveBar();
        };
      });
    }
    this._updateSaveBar();
  }

  /* ── Status View ───────────────────────────────────────────────────────── */

  _updateStatusView() {
    const root = this.shadowRoot;
    const st = this._status;
    if (!st || this._activeTab !== "status") return;

    const z = ZONE_CFG[st.zone] || { label: "Unbekannt", color: "grey", icon: "❓" };
    const banner = root.getElementById("zone-banner");
    if (banner) {
      banner.style.background = z.color;
      root.getElementById("zone-icon").textContent = z.icon;
      root.getElementById("zone-label").textContent = st.zone_label || z.label;
      root.getElementById("mode-label").textContent = st.mode_label || "";
    }

    const set = (id, v) => { const el = root.getElementById(id); if (el) el.textContent = v; };
    set("val-grid", st.grid_w + " W");
    set("val-solar", st.solar_w + " W");
    set("val-soc", st.soc_pct + " %");
    set("val-actual", st.actual_w + " W");
    set("val-integral", st.integral);
    set("val-action", st.last_action);
    set("val-error", st.last_error || "");

    const fr = root.getElementById("flag-row");
    if (fr) {
      const flags = [
        ["Zyklus", st.cycle_active],
        ["Surplus", st.surplus_active],
        ["AC Laden", st.ac_charge_active],
        ["Tarif", st.tariff_charge_active],
      ];
      fr.innerHTML = flags.map(([n, v]) =>
        `<span class="flag ${v ? "on" : "off"}">${v ? "●" : "○"} ${n}</span>`
      ).join("");
    }
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
