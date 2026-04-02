/**
 * Solakon ONE Nulleinspeisung — Sidebar Panel
 * Vollständige Konfiguration + Live-Status im Sidebar.
 */

const ZONE_CFG = {
  0: { label: "Zone 0 — Überschuss-Einspeisung", color: "#f59e0b", icon: "☀️" },
  1: { label: "Zone 1 — Aggressive Entladung",   color: "#16a34a", icon: "⚡" },
  2: { label: "Zone 2 — Batterieschonend",        color: "#0891b2", icon: "🔋" },
  3: { label: "Zone 3 — Sicherheitsstopp",        color: "#dc2626", icon: "⛔" },
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

// Vollständige Feldkonfiguration für alle Tabs
const CONFIG_MAP = {
  pi: [
    { k: "p_factor",       l: "P-Faktor (Proportional-Verstärkung)",   t: "number", step: 0.01, min: 0, max: 5 },
    { k: "i_factor",       l: "I-Faktor (Integral-Verstärkung)",        t: "number", step: 0.01, min: 0, max: 2 },
    { k: "tolerance",      l: "Toleranzbereich / Totband (W)",          t: "number", step: 1,    min: 0, max: 200 },
    { k: "wait_time",      l: "Wartezeit nach Leistungsänderung (s)",   t: "number", step: 1,    min: 1, max: 60 },
    { k: "stddev_window",  l: "Standardabweichungs-Fenster (s)",        t: "number", step: 10,   min: 10, max: 600 },
  ],
  zones: [
    { k: "zone1_limit",       l: "Zone-1-Schwelle — SOC (%)",               t: "number", step: 1, min: 0, max: 100 },
    { k: "zone3_limit",       l: "Zone-3-Schwelle / Sicherheitsstopp (%)",   t: "number", step: 1, min: 0, max: 100 },
    { k: "discharge_max",     l: "Max. Entladestrom Zone 1 (A)",             t: "number", step: 1, min: 0, max: 80 },
    { k: "offset_1",          l: "Nullpunkt-Offset Zone 1 statisch (W)",     t: "number", step: 1, min: -200, max: 200 },
    { k: "offset_2",          l: "Nullpunkt-Offset Zone 2 statisch (W)",     t: "number", step: 1, min: -200, max: 200 },
    { k: "pv_reserve",        l: "PV-Ladereserve / Nacht-Schwelle (W)",      t: "number", step: 1, min: 0, max: 500 },
    { k: "hard_limit",        l: "Maximale Ausgangsleistung — Hard Limit (W)", t: "number", step: 1, min: 0, max: 800 },
  ],
  surplus: [
    { k: "surplus_enabled",        l: "Überschuss-Einspeisung aktivieren",  t: "check" },
    { k: "surplus_soc_threshold",  l: "SOC-Schwelle Überschuss (%)",         t: "number", step: 1, min: 50, max: 100 },
    { k: "surplus_soc_hyst",       l: "Hysterese Überschuss-Austritt SOC (%)", t: "number", step: 1, min: 0, max: 20 },
    { k: "surplus_pv_hyst",        l: "Hysterese PV-Überschuss (W)",          t: "number", step: 1, min: 0, max: 300 },
  ],
  ac: [
    { k: "ac_enabled",       l: "AC Laden aktivieren",                  t: "check" },
    { k: "ac_soc_target",    l: "SOC-Ladeziel (%)",                     t: "number", step: 1, min: 50, max: 100 },
    { k: "ac_power_limit",   l: "Max. Ladeleistung (W)",                t: "number", step: 1, min: 0, max: 800 },
    { k: "ac_hysteresis",    l: "Hysterese (W)",                        t: "number", step: 1, min: 0, max: 300 },
    { k: "ac_offset",        l: "Nullpunkt-Offset statisch (W)",        t: "number", step: 1, min: -200, max: 200 },
    { k: "ac_p_factor",      l: "AC Laden — P-Faktor",                  t: "number", step: 0.01, min: 0, max: 5 },
    { k: "ac_i_factor",      l: "AC Laden — I-Faktor",                  t: "number", step: 0.01, min: 0, max: 2 },
  ],
  tariff: [
    { k: "tariff_enabled",         l: "Tarif-Arbitrage aktivieren",          t: "check" },
    { k: "tariff_cheap_threshold", l: "Günstig-Schwelle — Laden + Sperre (ct/kWh)", t: "number", step: 0.1, min: 0, max: 100 },
    { k: "tariff_exp_threshold",   l: "Teuer-Schwelle — Sperre aufheben (ct/kWh)",  t: "number", step: 0.1, min: 0, max: 100 },
    { k: "tariff_soc_target",      l: "SOC-Ladeziel Tarif-Laden (%)",         t: "number", step: 1, min: 50, max: 100 },
    { k: "tariff_power",           l: "Ladeleistung Tarif-Laden (W)",          t: "number", step: 1, min: 0, max: 800 },
  ],
  night: [
    { k: "night_enabled", l: "Nachtabschaltung Zone 2 aktivieren", t: "check" },
  ],
};

class SolakonPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    // BUG FIX: Alle State-Variablen im Constructor initialisieren
    this._initialized = false;
    this._settings    = {};
    this._dirty       = {};
    this._status      = null;
    this._activeTab   = "status";
    this._entryId     = null;
    this._hass        = null;
    this._polling     = null;
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
      // BUG FIX: _renderLayout() war nicht definiert — _build() umbenannt
      this._renderLayout();
      this._loadConfig();
      // BUG FIX: Einheitlich this._polling verwenden
      this._polling = setInterval(() => this._loadStatus(), 5000);
    }
  }

  // BUG FIX: _ws() Hilfsmethode war komplett fehlend
  async _ws(type, extra = {}) {
    return this._hass.callWS({
      type: `solakon_nulleinspeisung/${type}`,
      entry_id: this._entryId,
      ...extra,
    });
  }

  async _loadConfig() {
    try {
      this._settings = await this._ws("get_config");
      this._renderActiveTab();
    } catch (err) {
      console.error("Solakon: Konfiguration laden fehlgeschlagen", err);
    }
  }

  async _loadStatus() {
    try {
      this._status = await this._ws("get_status");
      this._updateStatusView();
    } catch (_e) { /* Polling-Fehler ignorieren */ }
  }

  async _saveSettings() {
    if (!Object.keys(this._dirty).length) return;
    try {
      await this._ws("save_config", { changes: this._dirty });
      this._settings = { ...this._settings, ...this._dirty };
      this._dirty = {};
      this._showSaveBar(false);
      this._showToast("✅ Einstellungen gespeichert");
      this._renderActiveTab();
    } catch (e) {
      this._showToast("❌ Fehler: " + e.message, true);
    }
  }

  async _resetIntegral() {
    try {
      await this._ws("reset_integral");
      this._showToast("🔄 Integral zurückgesetzt");
    } catch (e) {
      this._showToast("❌ Fehler: " + e.message, true);
    }
  }

  // BUG FIX: Methode war als _build() definiert, aber _renderLayout() wurde aufgerufen
  _renderLayout() {
    this.shadowRoot.innerHTML = `
    <style>
      :host {
        display: block; font-family: sans-serif;
        color: var(--primary-text-color);
        background: var(--primary-background-color);
        min-height: 100vh;
      }
      .layout { display: flex; height: 100vh; }
      .nav {
        width: 190px; background: var(--card-background-color);
        border-right: 1px solid var(--divider-color);
        display: flex; flex-direction: column;
        flex-shrink: 0;
      }
      .nav-header {
        padding: 18px 20px; font-weight: bold;
        color: var(--primary-color);
        border-bottom: 1px solid var(--divider-color);
        font-size: 0.95rem;
      }
      .nav-item {
        padding: 12px 20px; cursor: pointer;
        transition: background 0.15s;
        display: flex; align-items: center; gap: 10px;
        font-size: 0.9rem;
      }
      .nav-item:hover { background: var(--secondary-background-color); }
      .nav-item.active { background: var(--primary-color); color: white; }
      .content { flex: 1; padding: 24px; overflow-y: auto; position: relative; }
      .card {
        background: var(--card-background-color); border-radius: 12px;
        padding: 20px; margin-bottom: 16px;
        box-shadow: var(--ha-card-box-shadow, 0 2px 5px rgba(0,0,0,0.1));
      }
      h2 { margin: 0 0 16px 0; font-size: 1.1rem; color: var(--primary-color); }
      .zone-banner {
        padding: 15px; border-radius: 8px; margin-bottom: 20px;
        color: white; display: flex; align-items: center; gap: 15px;
      }
      .stat-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        gap: 12px;
      }
      .stat-item { background: var(--secondary-background-color); padding: 12px; border-radius: 8px; }
      .stat-label { font-size: 0.78rem; color: var(--secondary-text-color); margin-bottom: 4px; }
      .stat-value { font-size: 1.2rem; font-weight: bold; }
      .form-group { margin-bottom: 14px; }
      .form-group label { display: block; margin-bottom: 5px; font-weight: 500; font-size: 0.9rem; }
      .form-group input[type="number"] {
        width: 100%; padding: 8px; border-radius: 6px;
        border: 1px solid var(--divider-color);
        background: var(--secondary-background-color);
        color: var(--primary-text-color);
        box-sizing: border-box; font-size: 0.95rem;
      }
      .form-group input[type="number"]:focus {
        outline: none; border-color: var(--primary-color);
      }
      .check-row { display: flex; align-items: center; gap: 10px; padding: 10px 0; }
      .check-row input[type="checkbox"] { width: 18px; height: 18px; cursor: pointer; }
      .check-row label { margin: 0; cursor: pointer; font-weight: 500; }
      .section-hint {
        font-size: 0.8rem; color: var(--secondary-text-color);
        margin: -8px 0 14px 0; font-style: italic;
      }
      .save-bar {
        position: sticky; bottom: 0;
        background: var(--primary-color); color: white;
        padding: 12px 24px; display: none;
        justify-content: space-between; align-items: center;
        border-radius: 8px 8px 0 0;
      }
      .btn {
        padding: 8px 18px; border-radius: 6px;
        border: none; cursor: pointer; font-weight: bold; font-size: 0.9rem;
      }
      .btn-primary { background: white; color: var(--primary-color); }
      .btn-secondary {
        background: var(--secondary-background-color);
        color: var(--primary-text-color); border: 1px solid var(--divider-color);
      }
      .toast {
        position: fixed; bottom: 20px; right: 20px;
        padding: 12px 20px; border-radius: 6px;
        color: white; z-index: 1000; display: none; font-weight: 500;
      }
    </style>
    <div class="layout">
      <div class="nav">
        <div class="nav-header">☀️ Solakon ONE</div>
        ${TABS.map(t => `<div class="nav-item" data-tab="${t.id}">${t.icon} ${t.label}</div>`).join("")}
      </div>
      <div class="content">
        <div id="tab-content"></div>
        <div class="save-bar" id="save-bar">
          <span>⚠️ Ungespeicherte Änderungen</span>
          <button class="btn btn-primary" id="btn-save">💾 Speichern</button>
        </div>
      </div>
    </div>
    <div id="toast" class="toast"></div>
    `;

    this.shadowRoot.querySelectorAll(".nav-item").forEach(el => {
      el.addEventListener("click", () => {
        this._activeTab = el.dataset.tab;
        this._renderActiveTab();
      });
    });
    this.shadowRoot.getElementById("btn-save").addEventListener("click", () => this._saveSettings());

    // Direkt ersten Tab aktiv rendern (Status-Tab braucht kein _settings)
    this._renderActiveTab();
  }

  _renderActiveTab() {
    const root = this.shadowRoot;
    if (!root) return;

    root.querySelectorAll(".nav-item").forEach(el =>
      el.classList.toggle("active", el.dataset.tab === this._activeTab)
    );

    const container = root.getElementById("tab-content");
    if (!container) return;

    if (this._activeTab === "status") {
      this._renderStatusTab(container);
    } else {
      this._renderSettingsTab(container);
    }
  }

  _renderStatusTab(container) {
    container.innerHTML = `
      <div class="zone-banner" id="zone-banner" style="background: #6b7280;">
        <div id="zone-icon" style="font-size: 2.2rem;">⏳</div>
        <div>
          <div id="zone-label" style="font-weight: bold; font-size: 1.1rem;">Lade Daten…</div>
          <div id="mode-label" style="opacity: 0.85; font-size: 0.9rem;"></div>
        </div>
      </div>
      <div class="card">
        <div class="stat-grid">
          <div class="stat-item">
            <div class="stat-label">🔌 Netzleistung</div>
            <div class="stat-value" id="val-grid">—</div>
          </div>
          <div class="stat-item">
            <div class="stat-label">☀️ Solar</div>
            <div class="stat-value" id="val-solar">—</div>
          </div>
          <div class="stat-item">
            <div class="stat-label">🔋 Batterie SOC</div>
            <div class="stat-value" id="val-soc">—</div>
          </div>
          <div class="stat-item">
            <div class="stat-label">📊 Netz-Stabw.</div>
            <div class="stat-value" id="val-stddev">—</div>
          </div>
          <div class="stat-item">
            <div class="stat-label">∫ Integral</div>
            <div class="stat-value" id="val-integral">—</div>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="stat-label" style="margin-bottom: 6px;">⚡ Letzte Aktion</div>
        <div id="val-action" style="font-size: 0.95rem;">—</div>
        <div id="val-error" style="color: #dc2626; font-size: 0.85rem; margin-top: 4px;"></div>
        <button class="btn btn-secondary" style="margin-top: 16px;" id="btn-reset-int">🔄 Integral zurücksetzen</button>
      </div>
    `;
    this.shadowRoot.getElementById("btn-reset-int").addEventListener("click", () => this._resetIntegral());
    this._loadStatus();
  }

  _renderSettingsTab(container) {
    const tab = TABS.find(t => t.id === this._activeTab);
    const fields = CONFIG_MAP[this._activeTab] || [];
    const s = this._settings;

    container.innerHTML = `
      <div class="card">
        <h2>${tab?.icon || ""} ${tab?.label || ""}</h2>
        <div id="fields"></div>
      </div>
    `;

    const fieldsEl = container.querySelector("#fields");

    if (fields.length === 0) {
      fieldsEl.innerHTML = `<div class="section-hint">Keine Einstellungen für diesen Tab.</div>`;
      return;
    }

    if (!Object.keys(s).length) {
      fieldsEl.innerHTML = `<div class="section-hint">Lade Einstellungen…</div>`;
      return;
    }

    fields.forEach(f => {
      const val = this._dirty[f.k] !== undefined ? this._dirty[f.k] : s[f.k];
      const group = document.createElement("div");

      if (f.t === "check") {
        group.className = "check-row";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.id = `inp_${f.k}`;
        cb.checked = !!val;
        cb.dataset.key = f.k;
        const lbl = document.createElement("label");
        lbl.htmlFor = `inp_${f.k}`;
        lbl.textContent = f.l;
        group.appendChild(cb);
        group.appendChild(lbl);
        cb.addEventListener("change", () => this._markDirty(f.k, cb.checked));
      } else {
        group.className = "form-group";
        const lbl = document.createElement("label");
        lbl.htmlFor = `inp_${f.k}`;
        lbl.textContent = f.l;
        const inp = document.createElement("input");
        inp.type = "number";
        inp.id = `inp_${f.k}`;
        inp.dataset.key = f.k;
        inp.value = (val !== undefined && val !== null) ? val : 0;
        if (f.step !== undefined) inp.step = f.step;
        if (f.min  !== undefined) inp.min  = f.min;
        if (f.max  !== undefined) inp.max  = f.max;
        group.appendChild(lbl);
        group.appendChild(inp);
        inp.addEventListener("change", () => this._markDirty(f.k, parseFloat(inp.value)));
      }

      fieldsEl.appendChild(group);
    });
  }

  _updateStatusView() {
    const root = this.shadowRoot;
    const st = this._status;
    if (this._activeTab !== "status" || !st || !root) return;

    const z = ZONE_CFG[st.zone] ?? { label: "Unbekannt", color: "#6b7280", icon: "❓" };
    const banner = root.getElementById("zone-banner");
    if (banner) {
      banner.style.background = z.color;
      root.getElementById("zone-icon").textContent  = z.icon;
      root.getElementById("zone-label").textContent = st.zone_label || z.label;
      root.getElementById("mode-label").textContent = st.mode_label || "";
    }

    const set = (id, val) => { const el = root.getElementById(id); if (el) el.textContent = val; };
    set("val-grid",     st.grid_w    !== undefined ? `${st.grid_w} W`   : "—");
    set("val-solar",    st.solar_w   !== undefined ? `${st.solar_w} W`  : "—");
    set("val-soc",      st.soc_pct   !== undefined ? `${st.soc_pct} %`  : "—");
    set("val-stddev",   st.stddev    !== undefined ? `${st.stddev} W`   : "—");
    set("val-integral", st.integral  !== undefined ? `${st.integral}`   : "—");
    set("val-action",   st.last_action || "—");
    set("val-error",    st.last_error  || "");
  }

  _markDirty(key, value) {
    this._dirty[key] = value;
    this._showSaveBar(true);
  }

  _showSaveBar(visible) {
    const bar = this.shadowRoot.getElementById("save-bar");
    if (bar) bar.style.display = visible ? "flex" : "none";
  }

  _showToast(msg, err = false) {
    const t = this.shadowRoot.getElementById("toast");
    if (!t) return;
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
