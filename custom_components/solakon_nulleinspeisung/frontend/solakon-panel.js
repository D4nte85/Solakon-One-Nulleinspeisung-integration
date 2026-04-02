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
    { k: "p_factor",       l: "P-Faktor",                               t: "number", step: 0.1, min: 0, max: 5 },
    { k: "i_factor",       l: "I-Faktor",                               t: "number", step: 0.01, min: 0, max: 1 },
    { k: "tolerance",      l: "Toleranz / Totband (W)",                 t: "number", step: 1, min: 0, max: 100 },
    { k: "wait_time",      l: "Wartezeit zw. Zyklen (Sekunden)",        t: "number", step: 1, min: 1, max: 60 },
    { k: "stddev_window",  l: "Zeitfenster StdDev (Sekunden)",          t: "number", step: 1, min: 10, max: 300 },
  ],
  zones: [
    { k: "zone1_limit",       l: "Zone-1-Schwelle — SOC (%)",               t: "number", step: 1, min: 0, max: 100 },
    { k: "zone3_limit",       l: "Zone-3-Schwelle / Sicherheitsstopp (%)",   t: "number", step: 1, min: 0, max: 100 },
    { k: "discharge_max",     l: "Max. Entladestrom Zone 1 (A)",             t: "number", step: 1, min: 0, max: 80 },
    
    // Zone 1
    { k: "offset_1",          l: "Nullpunkt-Offset Zone 1 statisch (W)",     t: "number", step: 1, min: -200, max: 200 },
    { k: "dyn_offset_1_enabled", l: "Dyn. Offset Zone 1 aktivieren",         t: "check" },
    { k: "dyn_offset_1_min",  l: "Zone 1 Min. Offset (W)",                   t: "number", step: 1, min: 0, max: 200 },
    { k: "dyn_offset_1_max",  l: "Zone 1 Max. Offset (W)",                   t: "number", step: 1, min: 50, max: 1000 },
    { k: "dyn_offset_1_noise_floor", l: "Zone 1 Rausch-Schwelle (W)",        t: "number", step: 1, min: 0, max: 100 },
    { k: "dyn_offset_1_factor", l: "Zone 1 Volatilitäts-Faktor",             t: "number", step: 0.1, min: 0, max: 5 },
    { k: "dyn_offset_1_negative", l: "Zone 1 Negativer Offset",              t: "check" },

    // Zone 2
    { k: "offset_2",          l: "Nullpunkt-Offset Zone 2 statisch (W)",     t: "number", step: 1, min: -200, max: 200 },
    { k: "dyn_offset_2_enabled", l: "Dyn. Offset Zone 2 aktivieren",         t: "check" },
    { k: "dyn_offset_2_min",  l: "Zone 2 Min. Offset (W)",                   t: "number", step: 1, min: 0, max: 200 },
    { k: "dyn_offset_2_max",  l: "Zone 2 Max. Offset (W)",                   t: "number", step: 1, min: 50, max: 1000 },
    { k: "dyn_offset_2_noise_floor", l: "Zone 2 Rausch-Schwelle (W)",        t: "number", step: 1, min: 0, max: 100 },
    { k: "dyn_offset_2_factor", l: "Zone 2 Volatilitäts-Faktor",             t: "number", step: 0.1, min: 0, max: 5 },
    { k: "dyn_offset_2_negative", l: "Zone 2 Negativer Offset",              t: "check" },

    { k: "pv_reserve",        l: "PV-Ladereserve / Nacht-Schwelle (W)",      t: "number", step: 1, min: 0, max: 500 },
    { k: "hard_limit",        l: "Maximale Ausgangsleistung — Hard Limit (W)", t: "number", step: 1, min: 0, max: 800 },
  ],
  surplus: [
    { k: "surplus_enabled",       l: "Überschuss-Einspeisung aktivieren",   t: "check" },
    { k: "surplus_soc_threshold", l: "SOC Export-Schwelle (%)",             t: "number", step: 1, min: 50, max: 100 },
    { k: "surplus_soc_hyst",      l: "SOC Hysterese (%)",                   t: "number", step: 1, min: 1, max: 20 },
    { k: "surplus_pv_hyst",       l: "PV Hysterese (W)",                    t: "number", step: 1, min: 0, max: 300 },
  ],
  ac: [
    { k: "ac_enabled",       l: "AC Laden aktivieren",                  t: "check" },
    { k: "ac_soc_target",    l: "SOC-Ladeziel (%)",                     t: "number", step: 1, min: 50, max: 100 },
    { k: "ac_power_limit",   l: "Max. Ladeleistung (W)",                t: "number", step: 1, min: 0, max: 800 },
    { k: "ac_hysteresis",    l: "Hysterese (W)",                        t: "number", step: 1, min: 0, max: 300 },
    
    // AC Offset
    { k: "ac_offset",        l: "Nullpunkt-Offset statisch (W)",        t: "number", step: 1, min: -200, max: 200 },
    { k: "dyn_offset_ac_enabled", l: "Dyn. Offset AC aktivieren",       t: "check" },
    { k: "dyn_offset_ac_min",  l: "AC Min. Offset (W)",                 t: "number", step: 1, min: 0, max: 200 },
    { k: "dyn_offset_ac_max",  l: "AC Max. Offset (W)",                 t: "number", step: 1, min: 50, max: 1000 },
    { k: "dyn_offset_ac_noise_floor", l: "AC Rausch-Schwelle (W)",      t: "number", step: 1, min: 0, max: 100 },
    { k: "dyn_offset_ac_factor", l: "AC Volatilitäts-Faktor",           t: "number", step: 0.1, min: 0, max: 5 },
    { k: "dyn_offset_ac_negative", l: "AC Negativer Offset",            t: "check" },

    { k: "ac_p_factor",      l: "AC Laden — P-Faktor",                  t: "number", step: 0.01, min: 0, max: 5 },
    { k: "ac_i_factor",      l: "AC Laden — I-Faktor",                  t: "number", step: 0.01, min: 0, max: 2 },
  ],
  tariff: [
    { k: "tariff_enabled",         l: "Dynamischen Stromtarif nutzen",      t: "check" },
    { k: "tariff_price_sensor",    l: "Preissensor (Entity ID)",            t: "text" },
    { k: "tariff_cheap_threshold", l: "Günstig-Schwelle (ct/kWh)",          t: "number", step: 0.1 },
    { k: "tariff_exp_threshold",   l: "Teuer-Schwelle (ct/kWh)",            t: "number", step: 0.1 },
    { k: "tariff_soc_target",      l: "SOC Ziel bei günstigem Strom (%)",   t: "number", step: 1, min: 0, max: 100 },
    { k: "tariff_power",           l: "Ladeleistung bei günstigem Strom (W)",t: "number", step: 1, min: 0, max: 800 },
  ],
  night: [
    { k: "night_enabled",    l: "Nachtladung aktivieren",               t: "check" },
  ],
};

class SolakonPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._settings = {};
    this._status = {};
    this._activeTab = "status";
    this._dirty = {};
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config && hass.panels && hass.panels["solakon_nulleinspeisung"]) {
      this._config = hass.panels["solakon_nulleinspeisung"].config;
      this._loadData();
    }
  }

  async _loadData() {
    if (!this._hass || !this._config) return;
    const eid = this._config.entry_id;
    try {
      this._settings = await this._hass.callWS({ type: "solakon_nulleinspeisung/get_config", entry_id: eid });
      this._status = await this._hass.callWS({ type: "solakon_nulleinspeisung/get_status", entry_id: eid });
      this._render();
    } catch (e) {
      console.error("WS Error:", e);
    }
  }

  _render() {
    if (!this.shadowRoot.innerHTML) {
      this.shadowRoot.innerHTML = this._renderLayout();
      this._attachEvents();
    }
    this._updateStatus();
    this._renderActiveTab();
  }

  _renderLayout() {
    return `
      <style>
        :host { --primary-color: #10b981; --bg-color: var(--primary-background-color, #f8fafc); font-family: system-ui, sans-serif; }
        .wrapper { max-width: 900px; margin: 0 auto; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .tabs { display: flex; gap: 8px; border-bottom: 2px solid var(--divider-color); padding-bottom: 10px; margin-bottom: 20px; overflow-x: auto; }
        .tab { padding: 8px 16px; border-radius: 6px; cursor: pointer; background: var(--card-background-color); border: 1px solid var(--divider-color); white-space: nowrap; }
        .tab.active { background: var(--primary-color); color: white; border-color: var(--primary-color); }
        .content { background: var(--card-background-color); padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; font-weight: 500; margin-bottom: 5px; font-size: 0.95rem; }
        .form-group input[type="number"], .form-group input[type="text"] { width: 100%; padding: 8px; border-radius: 6px; border: 1px solid var(--divider-color); background: var(--secondary-background-color); color: var(--primary-text-color); box-sizing: border-box; }
        .form-group input:focus { outline: none; border-color: var(--primary-color); }
        .form-group.checkbox { display: flex; align-items: center; gap: 10px; }
        .form-group.checkbox input { width: 18px; height: 18px; cursor: pointer; }
        
        /* Status Dashboard Styles */
        .dashboard { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-top: 15px; }
        .card { background: var(--secondary-background-color); padding: 15px; border-radius: 8px; text-align: center; border: 1px solid var(--divider-color); }
        .card .label { font-size: 0.85rem; color: var(--secondary-text-color); margin-bottom: 5px; }
        .card .value { font-size: 1.4rem; font-weight: 700; color: var(--primary-text-color); }
        .status-header { display: flex; align-items: center; gap: 15px; padding: 15px; background: var(--secondary-background-color); border-radius: 8px; margin-bottom: 15px; border-left: 5px solid #ccc; }
        
        /* Action Bar */
        #save-bar { display: none; position: sticky; bottom: 0; left: 0; right: 0; background: var(--card-background-color); padding: 15px; border-top: 1px solid var(--divider-color); justify-content: flex-end; gap: 10px; }
        .btn { padding: 10px 20px; border-radius: 6px; border: none; cursor: pointer; font-weight: 600; }
        .btn-primary { background: var(--primary-color); color: white; }
        .btn-secondary { background: var(--secondary-background-color); border: 1px solid var(--divider-color); }
      </style>
      <div class="wrapper">
        <div class="header">
          <h2>Solakon ONE Regelung</h2>
          <button class="btn btn-secondary" id="btn-refresh">🔄 Aktualisieren</button>
        </div>
        
        <div class="tabs">
          ${TABS.map(t => `<div class="tab ${t.id === this._activeTab ? "active" : ""}" data-id="${t.id}">${t.icon} ${t.label}</div>`).join("")}
        </div>
        
        <div class="content" id="tab-content"></div>
      </div>
      
      <div id="save-bar">
        <button class="btn btn-secondary" id="btn-discard">Verwerfen</button>
        <button class="btn btn-primary" id="btn-save">Speichern</button>
      </div>
    `;
  }

  _attachEvents() {
    const root = this.shadowRoot;
    root.querySelectorAll(".tab").forEach(tab => {
      tab.addEventListener("click", () => {
        root.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        this._activeTab = tab.dataset.id;
        this._renderActiveTab();
      });
    });

    root.getElementById("btn-refresh").addEventListener("click", () => this._loadData());
    root.getElementById("btn-discard").addEventListener("click", () => { this._dirty = {}; this._showSaveBar(false); this._loadData(); });
    root.getElementById("btn-save").addEventListener("click", () => this._saveSettings());
  }

  _renderActiveTab() {
    const container = this.shadowRoot.getElementById("tab-content");
    container.innerHTML = "";

    if (this._activeTab === "status") {
      this._renderStatusTab(container);
    } else {
      this._renderSettingsTab(container);
    }
  }

  _renderStatusTab(container) {
    container.innerHTML = `
      <div class="status-header" id="status-hdr">
        <div style="font-size: 2rem;" id="zone-icon">🤖</div>
        <div>
          <div id="zone-label" style="font-weight: 700; font-size: 1.1rem;">Lade Status...</div>
          <div id="mode-label" style="color: var(--secondary-text-color); font-size: 0.9rem;">...</div>
        </div>
      </div>
      
      <div class="dashboard">
        <div class="card"><div class="label">Netzleistung</div><div class="value" id="val-grid">—</div></div>
        <div class="card"><div class="label">PV Leistung</div><div class="value" id="val-solar">—</div></div>
        <div class="card"><div class="label">SOC Batterie</div><div class="value" id="val-soc">—</div></div>
        <div class="card"><div class="label">StdDev (Volatilität)</div><div class="value" id="val-stddev">—</div></div>
        <div class="card"><div class="label">I-Anteil</div><div class="value" id="val-integral">—</div></div>
      </div>
      <div style="margin-top: 15px; font-size: 0.9rem;">
        <strong>Letzte Aktion:</strong> <span id="val-action">—</span>
      </div>
    `;
    this._updateStatus();
  }

  _renderSettingsTab(container) {
    const fields = CONFIG_MAP[this._activeTab];
    if (!fields) return;

    fields.forEach(f => {
      const group = document.createElement("div");
      const val = this._dirty[f.k] !== undefined ? this._dirty[f.k] : this._settings[f.k];

      if (f.t === "check") {
        group.className = "form-group checkbox";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.id = `inp_${f.k}`;
        cb.checked = !!val;
        const lbl = document.createElement("label");
        lbl.htmlFor = `inp_${f.k}`;
        lbl.textContent = f.l;
        group.appendChild(cb);
        group.appendChild(lbl);
        cb.addEventListener("change", () => this._markDirty(f.k, cb.checked));
      } else if (f.t === "text") {
        group.className = "form-group";
        const lbl = document.createElement("label");
        lbl.htmlFor = `inp_${f.k}`;
        lbl.textContent = f.l;
        const inp = document.createElement("input");
        inp.type = "text";
        inp.id = `inp_${f.k}`;
        inp.value = val !== undefined ? val : "";
        group.appendChild(lbl);
        group.appendChild(inp);
        inp.addEventListener("change", () => this._markDirty(f.k, inp.value));
      } else {
        group.className = "form-group";
        const lbl = document.createElement("label");
        lbl.htmlFor = `inp_${f.k}`;
        lbl.textContent = f.l;
        const inp = document.createElement("input");
        inp.type = "number";
        inp.id = `inp_${f.k}`;
        if (f.step) inp.step = f.step;
        if (f.min !== undefined) inp.min = f.min;
        if (f.max !== undefined) inp.max = f.max;
        inp.value = val !== undefined ? val : "";
        group.appendChild(lbl);
        group.appendChild(inp);
        inp.addEventListener("change", () => this._markDirty(f.k, parseFloat(inp.value)));
      }
      container.appendChild(group);
    });
  }

  _updateStatus() {
    const root = this.shadowRoot;
    const st = this._status;
    const hdr = root.getElementById("status-hdr");
    if (!hdr) return;

    const z = ZONE_CFG[st.zone] || { label: "Unbekannte Zone", color: "#ccc", icon: "❓" };
    hdr.style.borderLeftColor = z.color;
    root.getElementById("zone-icon").textContent = z.icon;
    root.getElementById("zone-label").textContent = z.label;
    root.getElementById("mode-label").textContent = st.mode_label || "";
    
    const set = (id, val) => { const el = root.getElementById(id); if (el) el.textContent = val; };
    set("val-grid",     st.grid_w    !== undefined ? `${st.grid_w} W`   : "—");
    set("val-solar",    st.solar_w   !== undefined ? `${st.solar_w} W`  : "—");
    set("val-soc",      st.soc_pct   !== undefined ? `${st.soc_pct} %`  : "—");
    set("val-stddev",   st.stddev    !== undefined ? `${st.stddev} W`   : "—");
    set("val-integral", st.integral  !== undefined ? `${st.integral}`   : "—");
    set("val-action",   st.last_action || "—");
  }

  _markDirty(key, value) {
    this._dirty[key] = value;
    this._showSaveBar(true);
  }

  _showSaveBar(visible) {
    const bar = this.shadowRoot.getElementById("save-bar");
    if (bar) bar.style.display = visible ? "flex" : "none";
  }

  async _saveSettings() {
    if (!this._config) return;
    try {
      await this._hass.callWS({
        type: "solakon_nulleinspeisung/save_config",
        entry_id: this._config.entry_id,
        changes: this._dirty
      });
      this._settings = { ...this._settings, ...this._dirty };
      this._dirty = {};
      this._showSaveBar(false);
      this._loadData();
    } catch (e) {
      console.error("Save failed:", e);
    }
  }
}

customElements.define("solakon-panel", SolakonPanel);
