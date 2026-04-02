/**
 * Solakon ONE Nulleinspeisung — Sidebar Panel
 * Vollständige Konfiguration + Live-Status im Sidebar.
 */

const ZONE_CFG = {
  0: { label: "Zone 0 — Überschuss-Einspeisung", color: "#f59e0b", icon: "☀️" },
  1: { label: "Zone 1 — Aggressive Entladung",   color: "#16a34a", icon: "⚡" },
  2: { label: "Zone 2 — Batterieschonend",       color: "#0891b2", icon: "🔋" },
  3: { label: "Zone 3 — Sicherheitsstopp",       color: "#dc2626", icon: "⛔" },
};

const TABS = [
  { id: "status",   label: "Status",      icon: "📊" },
  { id: "pi",       label: "PI-Regler",   icon: "🎛️" },
  { id: "zones",    label: "Zonen",       icon: "🔋" },
  { id: "surplus",  label: "Überschuss",  icon: "☀️" },
  { id: "ac",       label: "AC Laden",    icon: "⚡" },
  { id: "tariff",   label: "Tarif",       icon: "💹" },
  { id: "night",    label: "Nacht",       icon: "🌙" },
];

class SolakonPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._initialized = false;
  }

  // WICHTIG: Home Assistant ruft dies auf, wenn das Panel geladen wird
  set panel(val) {
    this._panel = val;
    if (val && val.config && val.config.entry_id) {
      this._entryId = val.config.entry_id;
      this._checkInit();
    }
  }

  set hass(val) {
    this._hass = val;
    this._checkInit();
  }

  _checkInit() {
    // Starte erst, wenn BEIDE (hass und entryId) vorhanden sind
    if (this._hass && this._entryId && !this._initialized) {
      this._initialized = true;
      this._renderLayout();
      this._loadConfig();
      // Polling für Status alle 5 Sek
      this._statusInterval = setInterval(() => this._loadStatus(), 5000);
    }
  }

  async _loadConfig() {
    try {
      const config = await this._hass.callWS({
        type: "solakon_nulleinspeisung/get_config",
        entry_id: this._entryId
      });
      this._settings = config;
      this._renderActiveTab();
    } catch (err) {
      console.error("Solakon: load config failed", err);
    }
  }

  async _loadStatus() {
    try {
      this._status = await this._ws("solakon_nulleinspeisung/get_status");
      this._updateStatusView();
    } catch (e) { /* ignore polling errors */ }
  }

  async _saveSettings() {
    if (!Object.keys(this._dirty).length) return;
    try {
      await this._ws("solakon_nulleinspeisung/save_config", {
        changes: this._dirty,
      });
      // Merge dirty into settings and clear
      this._settings = { ...this._settings, ...this._dirty };
      this._dirty = {};
      this._showToast("✅ Einstellungen gespeichert");
      this._renderActiveTab();
    } catch (e) {
      this._showToast("❌ Fehler: " + e.message, true);
    }
  }

  async _resetIntegral() {
    try {
      await this._ws("solakon_nulleinspeisung/reset_integral");
      this._showToast("🔄 Integral zurückgesetzt");
    } catch (e) {
      this._showToast("❌ Fehler", true);
    }
  }

  _startPolling() {
    if (this._polling) return;
    this._loadStatus();
    this._polling = setInterval(() => this._loadStatus(), 3000);
  }

  _stopPolling() {
    if (this._polling) { clearInterval(this._polling); this._polling = null; }
  }

  // --- UI BUILDER ---
  _build() {
    this.shadowRoot.innerHTML = `
    <style>
      :host { display: block; font-family: sans-serif; color: var(--primary-text-color); background: var(--primary-background-color); min-height: 100vh; }
      .layout { display: flex; height: 100vh; }
      .nav { width: 200px; background: var(--card-background-color); border-right: 1px solid var(--divider-color); display: flex; flex-direction: column; }
      .nav-header { padding: 20px; font-weight: bold; color: var(--primary-color); border-bottom: 1px solid var(--divider-color); }
      .nav-item { padding: 12px 20px; cursor: pointer; transition: background 0.2s; display: flex; align-items: center; gap: 10px; }
      .nav-item:hover { background: var(--secondary-background-color); }
      .nav-item.active { background: var(--primary-color); color: white; }
      .content { flex: 1; padding: 24px; overflow-y: auto; position: relative; }
      .card { background: var(--card-background-color); border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: var(--ha-card-box-shadow, 0 2px 5px rgba(0,0,0,0.1)); }
      .zone-banner { padding: 15px; border-radius: 8px; margin-bottom: 20px; color: white; display: flex; align-items: center; gap: 15px; transition: background 0.5s; }
      .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 15px; }
      .stat-item { background: var(--secondary-background-color); padding: 10px; border-radius: 8px; }
      .stat-label { font-size: 0.8rem; color: var(--secondary-text-color); }
      .stat-value { font-size: 1.2rem; font-weight: bold; }
      .form-group { margin-bottom: 15px; }
      label { display: block; margin-bottom: 5px; font-weight: 500; }
      input[type="number"], input[type="text"] { width: 100%; padding: 8px; border-radius: 4px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
      .save-bar { position: sticky; bottom: 0; left: 0; right: 0; background: var(--primary-color); color: white; padding: 12px 24px; display: none; justify-content: space-between; align-items: center; border-radius: 8px 8px 0 0; }
      .btn { padding: 8px 16px; border-radius: 4px; border: none; cursor: pointer; font-weight: bold; }
      .btn-primary { background: white; color: var(--primary-color); }
      .toast { position: fixed; bottom: 20px; right: 20px; padding: 12px 20px; border-radius: 4px; color: white; z-index: 1000; display: none; }
    </style>
    <div class="layout">
      <div class="nav">
        <div class="nav-header">Solakon ONE</div>
        ${TABS.map(t => `<div class="nav-item" data-tab="${t.id}">${t.icon} ${t.label}</div>`).join('')}
      </div>
      <div class="content">
        <div id="tab-content"></div>
        <div class="save-bar" id="save-bar">
          <span>Ungespeicherte Änderungen</span>
          <button class="btn btn-primary" id="btn-save">Speichern</button>
        </div>
      </div>
    </div>
    <div id="toast" class="toast"></div>
    `;

    this.shadowRoot.querySelectorAll(".nav-item").forEach(el => {
      el.onclick = () => {
        this._activeTab = el.dataset.tab;
        this._renderActiveTab();
      };
    });
    this.shadowRoot.getElementById("btn-save").onclick = () => this._saveSettings();
  }

  _renderActiveTab() {
    const root = this.shadowRoot;
    root.querySelectorAll(".nav-item").forEach(el => el.classList.toggle("active", el.dataset.tab === this._activeTab));
    
    const container = root.getElementById("tab-content");
    const s = this._settings;

    if (this._activeTab === "status") {
      container.innerHTML = `
        <div class="zone-banner" id="zone-banner">
          <div id="zone-icon" style="font-size: 2rem;"></div>
          <div>
            <div id="zone-label" style="font-weight:bold; font-size: 1.1rem;"></div>
            <div id="mode-label" style="opacity: 0.9;"></div>
          </div>
        </div>
        <div class="card">
          <div class="stat-grid">
            <div class="stat-item"><div class="stat-label">Netz</div><div class="stat-value" id="val-grid">--</div></div>
            <div class="stat-item"><div class="stat-label">Solar</div><div class="stat-value" id="val-solar">--</div></div>
            <div class="stat-item"><div class="stat-label">Batterie</div><div class="stat-value" id="val-soc">--</div></div>
          </div>
        </div>
        <div class="card">
          <div class="stat-label">Letzte Aktion</div>
          <div id="val-action" style="margin-top:5px;">--</div>
          <button class="btn" style="margin-top:15px; background: var(--secondary-background-color);" id="btn-reset-int">Integral Reset</button>
        </div>
      `;
      root.getElementById("btn-reset-int").onclick = () => this._resetIntegral();
      this._updateStatusView();
    } else {
      // Vereinfachtes Rendering der Einstellungs-Tabs
      container.innerHTML = `<div class="card"><h2>${TABS.find(t => t.id === this._activeTab).label}</h2><div id="fields"></div></div>`;
      const fields = container.querySelector("#fields");
      
      // Hier generieren wir die Inputs basierend auf dem Tab
      const configMap = {
        pi: [ {k: "p_factor", l: "P-Faktor (Verstärkung)"}, {k: "i_factor", l: "I-Faktor (Integral)"} ],
        zones: [ {k: "zone1_limit", l: "Zone 1 SOC Limit (%)"}, {k: "zone3_limit", l: "Zone 3 SOC Limit (%)"} ],
        surplus: [ {k: "surplus_enabled", l: "Aktivieren", t: "check"}, {k: "surplus_soc_threshold", l: "SOC Schwelle"} ],
        ac: [ {k: "ac_enabled", l: "AC Laden aktiv", t: "check"}, {k: "ac_soc_target", l: "Ziel SOC"} ],
        night: [ {k: "night_enabled", l: "Nachtmodus aktiv", t: "check"} ]
      };

      (configMap[this._activeTab] || []).forEach(f => {
        const val = this._dirty[f.k] !== undefined ? this._dirty[f.k] : s[f.k];
        const group = document.createElement("div");
        group.className = "form-group";
        if (f.t === "check") {
          group.innerHTML = `<label><input type="checkbox" data-key="${f.k}" ${val ? 'checked' : ''}> ${f.l}</label>`;
        } else {
          group.innerHTML = `<label>${f.l}</label><input type="number" data-key="${f.k}" value="${val || 0}">`;
        }
        fields.appendChild(group);
      });

      fields.querySelectorAll("input").forEach(inp => {
        inp.onchange = () => {
          const key = inp.dataset.key;
          this._dirty[key] = inp.type === "checkbox" ? inp.checked : parseFloat(inp.value);
          this._updateSaveBar();
        };
      });
    }
  }

  _updateStatusView() {
    const root = this.shadowRoot;
    const st = this._status;
    if (this._activeTab !== "status" || !st) return;

    const z = ZONE_CFG[st.zone] || { label: "Unbekannt", color: "grey", icon: "❓" };
    const banner = root.getElementById("zone-banner");
    if (banner) {
      banner.style.background = z.color;
      root.getElementById("zone-icon").textContent = z.icon;
      root.getElementById("zone-label").textContent = st.zone_label || z.label;
      root.getElementById("mode-label").textContent = st.mode_label || "";
    }
    
    if (root.getElementById("val-grid")) root.getElementById("val-grid").textContent = st.grid_w + " W";
    if (root.getElementById("val-solar")) root.getElementById("val-solar").textContent = st.solar_w + " W";
    if (root.getElementById("val-soc")) root.getElementById("val-soc").textContent = st.soc_pct + " %";
    if (root.getElementById("val-action")) root.getElementById("val-action").textContent = st.last_action;
  }

  _updateSaveBar() {
    this.shadowRoot.getElementById("save-bar").style.display = Object.keys(this._dirty).length ? "flex" : "none";
  }

  _showToast(msg, err = false) {
    const t = this.shadowRoot.getElementById("toast");
    t.textContent = msg;
    t.style.background = err ? "#dc2626" : "#16a34a";
    t.style.display = "block";
    setTimeout(() => { t.style.display = "none"; }, 3000);
  }
}
customElements.define("solakon-panel", SolakonPanel);
