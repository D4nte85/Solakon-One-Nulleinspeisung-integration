/**
 * Solakon ONE Nulleinspeisung — Sidebar Panel
 * Vollständige Konfiguration + Live-Status im Sidebar.
 * Kommuniziert via WebSocket mit dem HA-Backend.
 */

// ── Zone / Mode display data ──────────────────────────────────────────────────
const ZONE_CFG = {
  0: { label: "Zone 0 — Überschuss-Einspeisung", color: "#f59e0b", icon: "☀️" },
  1: { label: "Zone 1 — Aggressive Entladung",   color: "#16a34a", icon: "⚡" },
  2: { label: "Zone 2 — Batterieschonend",       color: "#0891b2", icon: "🔋" },
  3: { label: "Zone 3 — Sicherheitsstopp",       color: "#dc2626", icon: "⛔" },
};

// ── Settings tab definitions ──────────────────────────────────────────────────
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
    this._hass      = null;
    this._entryId   = null;
    this._settings  = {};
    this._status    = {};
    this._dirty     = {};        // tracks unsaved changes
    this._activeTab = "status";
    this._polling   = null;
    this._wsConn    = null;
  }

  setConfig(config) {
    this._entryId = config?.entry_id ?? null;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._build();
      this._loadConfig();
      this._startPolling();
    }
  }

  connectedCallback()    { this._startPolling(); }
  disconnectedCallback() { this._stopPolling(); }

  // ── WebSocket helpers ─────────────────────────────────────────────────────
  async _ws(type, extra = {}) {
    return new Promise((resolve, reject) => {
      if (!this._hass) return reject("no hass");
      this._hass.connection.sendMessagePromise({ type, entry_id: this._entryId, ...extra })
        .then(resolve)
        .catch(reject);
    });
  }

  async _loadConfig() {
    try {
      const res = await this._ws("solakon_nulleinspeisung/get_config");
      this._settings = res.settings ?? {};
      this._dirty = {};
      this._renderActiveTab();
    } catch (e) {
      console.error("Solakon: load config failed", e);
    }
  }

  async _loadStatus() {
    try {
      const res = await this._ws("solakon_nulleinspeisung/get_status");
      this._status = res;
      this._updateStatusView();
    } catch (e) { /* ignore polling errors */ }
  }

  async _saveSettings() {
    if (!Object.keys(this._dirty).length) return;
    try {
      const res = await this._ws("solakon_nulleinspeisung/save_config", {
        settings: this._dirty,
      });
      this._settings = res.settings ?? this._settings;
      this._dirty = {};
      this._showToast("✅ Einstellungen gespeichert");
      this._renderActiveTab();
    } catch (e) {
      this._showToast("❌ Fehler beim Speichern: " + e, true);
    }
  }

  async _resetIntegral() {
    await this._ws("solakon_nulleinspeisung/reset_integral");
    this._showToast("🔄 Integral zurückgesetzt");
  }

  // ── Polling ───────────────────────────────────────────────────────────────
  _startPolling() {
    if (this._polling) return;
    this._polling = setInterval(() => this._loadStatus(), 2000);
  }
  _stopPolling() {
    if (this._polling) { clearInterval(this._polling); this._polling = null; }
  }

  // ── Full DOM build ────────────────────────────────────────────────────────
  _build() {
    this.shadowRoot.innerHTML = `
<style>
  :host {
    display: block;
    font-family: var(--paper-font-body1_-_font-family, -apple-system, sans-serif);
    font-size: 14px;
    color: var(--primary-text-color);
  }
  * { box-sizing: border-box; }

  .layout { display: flex; height: 100vh; overflow: hidden; }

  /* ── Sidebar nav ── */
  .nav {
    width: 180px;
    flex-shrink: 0;
    background: var(--sidebar-background-color, var(--card-background-color));
    border-right: 1px solid var(--divider-color);
    display: flex;
    flex-direction: column;
    padding: 0;
    overflow-y: auto;
  }
  .nav-header {
    padding: 20px 16px 12px;
    font-size: 1rem;
    font-weight: 700;
    color: var(--primary-color);
    letter-spacing: -.01em;
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid var(--divider-color);
    margin-bottom: 8px;
  }
  .nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 16px;
    cursor: pointer;
    border-radius: 0 24px 24px 0;
    margin: 2px 8px 2px 0;
    font-size: 0.9rem;
    transition: background .12s;
    user-select: none;
  }
  .nav-item:hover { background: var(--secondary-background-color); }
  .nav-item.active {
    background: var(--primary-color);
    color: var(--text-primary-color, #fff);
    font-weight: 600;
  }
  .nav-icon { width: 20px; text-align: center; }
  .nav-bottom {
    margin-top: auto;
    padding: 12px 8px;
    border-top: 1px solid var(--divider-color);
  }

  /* ── Main content ── */
  .content {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
    max-width: 720px;
  }

  /* ── Cards ── */
  .card {
    background: var(--card-background-color, #fff);
    border-radius: 12px;
    box-shadow: var(--ha-card-box-shadow, 0 1px 4px rgba(0,0,0,.12));
    padding: 20px;
    margin-bottom: 16px;
  }
  .card-title {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .08em;
    color: var(--secondary-text-color);
    margin: 0 0 14px;
  }

  /* ── Zone banner ── */
  .zone-banner {
    border-radius: 10px;
    padding: 16px 20px;
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 16px;
    transition: background .3s;
  }
  .zone-icon { font-size: 2rem; }
  .zone-name { font-size: 1.05rem; font-weight: 700; color: #fff; }
  .zone-sub  { font-size: 0.8rem; color: rgba(255,255,255,.85); margin-top: 2px; }

  /* ── Status grid ── */
  .stat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 10px;
  }
  .stat {
    background: var(--secondary-background-color);
    border-radius: 8px;
    padding: 10px 12px;
  }
  .stat-label { font-size: 0.68rem; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .04em; }
  .stat-value { font-size: 1.1rem; font-weight: 600; margin-top: 2px; }

  /* ── Pills ── */
  .pills { display: flex; flex-wrap: wrap; gap: 6px; }
  .pill {
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    transition: background .2s;
  }
  .pill-on  { background: #16a34a; color: #fff; }
  .pill-off { background: var(--secondary-background-color); color: var(--secondary-text-color); }

  /* ── Form ── */
  .form-row {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid var(--divider-color);
  }
  .form-row:last-child { border-bottom: none; }
  .form-label {
    flex: 1;
    min-width: 0;
  }
  .form-label-text {
    font-size: 0.88rem;
    font-weight: 500;
    color: var(--primary-text-color);
  }
  .form-label-hint {
    font-size: 0.75rem;
    color: var(--secondary-text-color);
    margin-top: 2px;
  }
  .form-control { flex-shrink: 0; }

  input[type="number"], input[type="text"] {
    width: 100px;
    padding: 6px 8px;
    border: 1px solid var(--divider-color);
    border-radius: 6px;
    background: var(--secondary-background-color);
    color: var(--primary-text-color);
    font-size: 0.9rem;
    text-align: right;
  }
  input[type="number"]:focus, input[type="text"]:focus {
    outline: none;
    border-color: var(--primary-color);
  }
  .input-wide { width: 200px; text-align: left; }

  input[type="checkbox"] {
    width: 18px; height: 18px; cursor: pointer;
    accent-color: var(--primary-color);
  }

  select {
    padding: 6px 8px;
    border: 1px solid var(--divider-color);
    border-radius: 6px;
    background: var(--secondary-background-color);
    color: var(--primary-text-color);
    font-size: 0.9rem;
    cursor: pointer;
  }

  /* ── Section header inside a tab ── */
  .section-header {
    font-size: 0.78rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .07em;
    color: var(--primary-color);
    margin: 18px 0 6px;
    padding-bottom: 4px;
    border-bottom: 2px solid var(--primary-color);
  }
  .section-header:first-child { margin-top: 0; }

  /* ── Buttons ── */
  .btn {
    padding: 8px 16px;
    border: none;
    border-radius: 8px;
    font-size: 0.88rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity .15s;
  }
  .btn:hover { opacity: .85; }
  .btn-primary { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .btn-secondary { background: var(--secondary-background-color); color: var(--primary-text-color); }
  .btn-danger { background: #dc2626; color: #fff; }
  .btn-sm { padding: 5px 10px; font-size: 0.8rem; }

  .save-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 0 0;
    margin-top: 8px;
    border-top: 1px solid var(--divider-color);
  }
  .dirty-badge {
    background: #f59e0b;
    color: #fff;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.75rem;
    font-weight: 700;
  }

  /* ── Toast ── */
  .toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%) translateY(80px);
    background: var(--card-background-color);
    box-shadow: 0 4px 16px rgba(0,0,0,.25);
    padding: 10px 20px;
    border-radius: 24px;
    font-weight: 600;
    font-size: 0.9rem;
    z-index: 999;
    transition: transform .25s ease;
    pointer-events: none;
  }
  .toast.show { transform: translateX(-50%) translateY(0); }

  /* ── Disabled overlay for optional sections ── */
  .optional-disabled { opacity: .45; pointer-events: none; }

  /* ── Responsive ── */
  @media (max-width: 500px) {
    .nav { width: 56px; }
    .nav-item span:last-child { display: none; }
    .nav-header span:last-child { display: none; }
    .content { padding: 16px; }
  }
</style>

<div class="layout">
  <nav class="nav">
    <div class="nav-header">
      <span>⚡</span>
      <span>Solakon ONE</span>
    </div>
    <div id="nav-items"></div>
    <div class="nav-bottom">
      <button class="btn btn-secondary btn-sm" id="btn-reload" style="width:100%">⟳ Neu laden</button>
    </div>
  </nav>

  <main class="content" id="content">
    <div id="tab-content"></div>
  </main>
</div>

<div class="toast" id="toast"></div>
`;

    // Build nav items
    const navEl = this.shadowRoot.getElementById("nav-items");
    TABS.forEach(tab => {
      const el = document.createElement("div");
      el.className = "nav-item" + (tab.id === this._activeTab ? " active" : "");
      el.dataset.tab = tab.id;
      el.innerHTML = `<span class="nav-icon">${tab.icon}</span><span>${tab.label}</span>`;
      el.addEventListener("click", () => this._switchTab(tab.id));
      navEl.appendChild(el);
    });

    this.shadowRoot.getElementById("btn-reload").addEventListener("click", () => this._loadConfig());
  }

  // ── Tab switching ─────────────────────────────────────────────────────────
  _switchTab(id) {
    this._activeTab = id;
    this.shadowRoot.querySelectorAll(".nav-item").forEach(el => {
      el.classList.toggle("active", el.dataset.tab === id);
    });
    this._renderActiveTab();
  }

  _renderActiveTab() {
    const el = this.shadowRoot.getElementById("tab-content");
    switch (this._activeTab) {
      case "status":  el.innerHTML = this._buildStatusTab();  this._bindStatusTab();  break;
      case "pi":      el.innerHTML = this._buildPiTab();      this._bindFormTab("pi"); break;
      case "zones":   el.innerHTML = this._buildZonesTab();   this._bindFormTab("zones"); break;
      case "surplus": el.innerHTML = this._buildSurplusTab(); this._bindFormTab("surplus"); break;
      case "ac":      el.innerHTML = this._buildAcTab();      this._bindFormTab("ac"); break;
      case "tariff":  el.innerHTML = this._buildTariffTab();  this._bindFormTab("tariff"); break;
      case "night":   el.innerHTML = this._buildNightTab();   this._bindFormTab("night"); break;
    }
    if (this._activeTab !== "status") {
      this._updateSaveBar();
    }
  }

  // ── Status tab ────────────────────────────────────────────────────────────
  _buildStatusTab() {
    const s = this._status;
    const zone = s.zone ?? 3;
    const zc = ZONE_CFG[zone] ?? ZONE_CFG[3];

    return `
<div class="zone-banner" id="zone-banner" style="background:linear-gradient(135deg,${zc.color}dd,${zc.color}88)">
  <div class="zone-icon">${zc.icon}</div>
  <div>
    <div class="zone-name" id="zone-name">${s.zone_label ?? zc.label}</div>
    <div class="zone-sub" id="mode-label">${s.mode_label ?? "—"}</div>
  </div>
</div>

<div class="card">
  <div class="card-title">Leistung</div>
  <div class="stat-grid">
    <div class="stat"><div class="stat-label">Netz</div><div class="stat-value" id="sv-grid">${this._watt(s.grid_w)}</div></div>
    <div class="stat"><div class="stat-label">PV</div><div class="stat-value" id="sv-solar">${this._watt(s.solar_w)}</div></div>
    <div class="stat"><div class="stat-label">WR-Ausgang</div><div class="stat-value" id="sv-output">${this._watt(s.output_w)}</div></div>
    <div class="stat"><div class="stat-label">SOC</div><div class="stat-value" id="sv-soc">${this._pct(s.soc_pct)}</div></div>
  </div>
</div>

<div class="card">
  <div class="card-title">Regler-Zustand</div>
  <div class="stat-grid" style="margin-bottom:14px">
    <div class="stat"><div class="stat-label">Integral</div><div class="stat-value" id="sv-integral">${s.integral ?? "—"}</div></div>
  </div>
  <div class="pills" id="sv-pills">
    ${this._pill("Zyklus aktiv",   s.cycle_active,      "#16a34a")}
    ${this._pill("Überschuss",     s.surplus_active,    "#d97706")}
    ${this._pill("AC Laden",       s.ac_charge_active,  "#2563eb")}
    ${this._pill("Tarif-Laden",    s.tariff_active,     "#059669")}
  </div>
</div>

<div class="card">
  <div class="card-title">Letzte Aktion</div>
  <div id="sv-last-action" style="font-size:.9rem;font-style:italic">${s.last_action ?? "—"}</div>
  ${s.last_error ? `<div style="color:#dc2626;margin-top:8px;font-size:.85rem">⚠️ ${s.last_error}</div>` : ""}
</div>

<div style="display:flex;gap:10px">
  <button class="btn btn-secondary btn-sm" id="btn-reset-int">🔄 Integral reset</button>
</div>
`;
  }

  _bindStatusTab() {
    this.shadowRoot.getElementById("btn-reset-int")?.addEventListener("click", () => this._resetIntegral());
  }

  _updateStatusView() {
    if (this._activeTab !== "status") return;
    const s = this._status;
    if (!s || !Object.keys(s).length) return;

    const zone = s.zone ?? 3;
    const zc = ZONE_CFG[zone] ?? ZONE_CFG[3];

    const banner = this.shadowRoot.getElementById("zone-banner");
    if (banner) banner.style.background = `linear-gradient(135deg,${zc.color}dd,${zc.color}88)`;

    const setText = (id, val) => {
      const el = this.shadowRoot.getElementById(id);
      if (el) el.textContent = val;
    };

    setText("zone-name",      s.zone_label ?? zc.label);
    setText("mode-label",     s.mode_label ?? "—");
    setText("sv-grid",        this._watt(s.grid_w));
    setText("sv-solar",       this._watt(s.solar_w));
    setText("sv-output",      this._watt(s.output_w));
    setText("sv-soc",         this._pct(s.soc_pct));
    setText("sv-integral",    s.integral ?? "—");
    setText("sv-last-action", s.last_action ?? "—");

    const pills = this.shadowRoot.getElementById("sv-pills");
    if (pills) pills.innerHTML = [
      this._pill("Zyklus aktiv",  s.cycle_active,     "#16a34a"),
      this._pill("Überschuss",    s.surplus_active,   "#d97706"),
      this._pill("AC Laden",      s.ac_charge_active, "#2563eb"),
      this._pill("Tarif-Laden",   s.tariff_active,    "#059669"),
    ].join("");
  }

  // ── PI tab ────────────────────────────────────────────────────────────────
  _buildPiTab() {
    return `
<h2 style="margin:0 0 16px;font-size:1.1rem">🎛️ PI-Regler Parameter</h2>
<div class="card">
  <div class="section-header">Proportional / Integral</div>
  ${this._numRow("p_factor",  "P-Faktor",  "Proportional-Verstärkung. Startpunkt: 0.3, schrittweise erhöhen.", 0.1, 5.0, 0.1)}
  ${this._numRow("i_factor",  "I-Faktor",  "Integral-Verstärkung. Beginne mit 0 — erst erhöhen wenn P stabil.", 0.0, 0.2, 0.01)}
  ${this._numRow("tolerance", "Toleranz",  "Totband in Watt. Kein PI-Eingriff innerhalb ±Toleranz.", 0, 200, 5, "W")}
  ${this._numRow("wait_time", "Wartezeit", "Sekunden nach Leistungsänderung (Reaktionszeit WR).", 0, 30, 1, "s")}
</div>
${this._saveBar()}`;
  }

  // ── Zones tab ─────────────────────────────────────────────────────────────
  _buildZonesTab() {
    return `
<h2 style="margin:0 0 16px;font-size:1.1rem">🔋 SOC-Zonen & Offsets</h2>
<div class="card">
  <div class="section-header">SOC-Schwellen</div>
  ${this._numRow("zone1_limit",        "Zone 1 Start (%)",     "Überschreiten → Aggressive Entladung.", 1, 99, 1, "%")}
  ${this._numRow("zone3_limit",        "Zone 3 Stopp (%)",     "Unterschreiten → Sicherheitsstopp. Muss < Zone 1.", 1, 49, 1, "%")}
  ${this._numRow("discharge_current_max", "Max. Entladestrom Zone 1", "Ampere. Zone 2 und AC/Tarif-Laden → immer 0 A.", 0, 40, 1, "A")}
</div>

<div class="card">
  <div class="section-header">Zone 1 — Offset</div>
  ${this._numRow("offset_1", "Statischer Offset", "Ziel-Netzleistung in Zone 1 (W). Fallback wenn kein dyn. Offset.", -100, 100, 5, "W")}
  <div class="section-header" style="margin-top:12px">Dynamischer Offset Zone 1</div>
  ${this._checkRow("dyn_offset_1_enabled", "Dynamischer Offset aktiv", "StdDev-basierter Volatilitäts-Offset.")}
  <div id="dyn1-fields" class="${this._s("dyn_offset_1_enabled") ? "" : "optional-disabled"}">
    ${this._textRow("dyn_offset_1_stddev_sensor", "StdDev-Sensor Entity ID", "z.B. sensor.solakon_grid_stddev_60s")}
    ${this._numRow("dyn_offset_1_min",    "Min. Offset (W)", "Puffer bei ruhigem Netz.", 0, 200, 5, "W")}
    ${this._numRow("dyn_offset_1_max",    "Max. Offset (W)", "Obergrenze bei unruhigem Netz.", 50, 1000, 10, "W")}
    ${this._numRow("dyn_offset_1_noise_floor", "Rausch-Schwelle (W)", "StdDev darunter = Grundrauschen.", 0, 100, 5, "W")}
    ${this._numRow("dyn_offset_1_factor", "Volatilitäts-Faktor", "Verstärkung über Rauschschwelle.", 0.5, 5.0, 0.1)}
    ${this._checkRow("dyn_offset_1_negative", "Negativer Offset", "Offset negieren → leichte Einspeisung als Ziel.")}
  </div>
</div>

<div class="card">
  <div class="section-header">Zone 2 — Offset</div>
  ${this._numRow("offset_2",     "Statischer Offset",      "Ziel-Netzleistung in Zone 2 (W).", -100, 100, 5, "W")}
  ${this._numRow("pv_charge_reserve", "PV-Ladereserve (W)", "Dynamisches Limit Zone 2: Max(0, PV − Reserve). Auch PV-Schwelle für Nachtabschaltung.", 0, 1000, 10, "W")}
  <div class="section-header" style="margin-top:12px">Dynamischer Offset Zone 2</div>
  ${this._checkRow("dyn_offset_2_enabled", "Dynamischer Offset aktiv", "")}
  <div id="dyn2-fields" class="${this._s("dyn_offset_2_enabled") ? "" : "optional-disabled"}">
    ${this._textRow("dyn_offset_2_stddev_sensor", "StdDev-Sensor Entity ID", "")}
    ${this._numRow("dyn_offset_2_min",    "Min. Offset (W)", "", 0, 200, 5, "W")}
    ${this._numRow("dyn_offset_2_max",    "Max. Offset (W)", "", 50, 1000, 10, "W")}
    ${this._numRow("dyn_offset_2_noise_floor", "Rausch-Schwelle (W)", "", 0, 100, 5, "W")}
    ${this._numRow("dyn_offset_2_factor", "Volatilitäts-Faktor", "", 0.5, 5.0, 0.1)}
    ${this._checkRow("dyn_offset_2_negative", "Negativer Offset", "")}
  </div>
</div>

<div class="card">
  <div class="section-header">Hard Limit</div>
  ${this._numRow("hard_limit", "Maximale Ausgangsleistung (W)", "Absolute Obergrenze. Gilt für Zone 0 und Zone 1.", 0, 1200, 10, "W")}
</div>
${this._saveBar()}`;
  }

  // ── Surplus tab ───────────────────────────────────────────────────────────
  _buildSurplusTab() {
    const enabled = this._s("surplus_enabled");
    return `
<h2 style="margin:0 0 16px;font-size:1.1rem">☀️ Überschuss-Einspeisung (Zone 0)</h2>
<div class="card">
  ${this._checkRow("surplus_enabled", "Überschuss-Einspeisung aktivieren",
    "Wenn SOC ≥ Schwelle UND PV > Verbrauch + Hysterese → Output auf Hard Limit. Integral wird eingefroren.")}
</div>
<div class="${enabled ? "" : "optional-disabled"}">
  <div class="card">
    <div class="section-header">Bedingungen</div>
    ${this._numRow("surplus_soc_threshold", "SOC-Schwelle (%)",      "Ab diesem SOC wird eingespeist.", 50, 99, 1, "%")}
    ${this._numRow("surplus_soc_hysteresis","Hysterese SOC (%)",     "SOC muss um diesen Wert unter Schwelle fallen.", 1, 20, 1, "%")}
    ${this._numRow("surplus_pv_hysteresis", "Hysterese PV (W)",      "Totband um Hausverbrauch (Ein/Aus).", 10, 200, 10, "W")}
  </div>
</div>
${this._saveBar()}`;
  }

  // ── AC tab ────────────────────────────────────────────────────────────────
  _buildAcTab() {
    const enabled = this._s("ac_charge_enabled");
    return `
<h2 style="margin:0 0 16px;font-size:1.1rem">⚡ AC Laden</h2>
<div class="card">
  ${this._checkRow("ac_charge_enabled", "AC Laden aktivieren",
    "Erkennung: (Grid + Ausgang) < −Hysterese. Typischer Fall: externe PV-Anlage speist ins Netz.")}
</div>
<div class="${enabled ? "" : "optional-disabled"}">
  <div class="card">
    <div class="section-header">Bedingungen & Grenzen</div>
    ${this._numRow("ac_charge_soc_target",  "SOC-Ladeziel (%)",     "Laden stoppt wenn SOC erreicht.", 10, 99, 1, "%")}
    ${this._numRow("ac_charge_power_limit", "Max. Ladeleistung (W)","Obergrenze für PI-Regler.", 50, 1200, 50, "W")}
    ${this._numRow("ac_charge_hysteresis",  "Hysterese (W)",        "Totband für Ein- und Austritt.", 0, 300, 10, "W")}
    ${this._numRow("ac_charge_offset",      "Offset (W)",           "Ziel-Netzleistung im AC-Lade-Modus. Negativ = Einspeisung angestrebt.", -100, 100, 5, "W")}
  </div>
  <div class="card">
    <div class="section-header">PI-Faktoren AC-Laden (separat)</div>
    ${this._numRow("ac_charge_p_factor", "P-Faktor AC", "Klein halten (~0.3–0.5) wegen langer Hardware-Flanke.", 0.1, 5.0, 0.1)}
    ${this._numRow("ac_charge_i_factor", "I-Faktor AC", "Macht die eigentliche Regelarbeit.", 0.0, 0.2, 0.01)}
  </div>
  <div class="card">
    <div class="section-header">Dynamischer Offset AC</div>
    ${this._checkRow("dyn_offset_ac_enabled", "Dynamischer Offset aktiv", "")}
    <div id="dynac-fields" class="${this._s("dyn_offset_ac_enabled") ? "" : "optional-disabled"}">
      ${this._textRow("dyn_offset_ac_stddev_sensor", "StdDev-Sensor Entity ID", "")}
      ${this._numRow("dyn_offset_ac_min",    "Min. Offset (W)", "", 0, 200, 5, "W")}
      ${this._numRow("dyn_offset_ac_max",    "Max. Offset (W)", "", 50, 1000, 10, "W")}
      ${this._numRow("dyn_offset_ac_noise_floor", "Rausch-Schwelle (W)", "", 0, 100, 5, "W")}
      ${this._numRow("dyn_offset_ac_factor", "Volatilitäts-Faktor", "", 0.5, 5.0, 0.1)}
      ${this._checkRow("dyn_offset_ac_negative", "Negativer Offset", "")}
    </div>
  </div>
</div>
${this._saveBar()}`;
  }

  // ── Tariff tab ────────────────────────────────────────────────────────────
  _buildTariffTab() {
    const enabled = this._s("tariff_enabled");
    return `
<h2 style="margin:0 0 16px;font-size:1.1rem">💹 Tarif-Arbitrage</h2>
<div class="card">
  ${this._checkRow("tariff_enabled", "Tarif-Arbitrage aktivieren",
    "Laden bei günstigem Tarif, Entladesperre bei günstigem/neutralem Preis. Ohne gültigen Sensor → kein Eingriff.")}
</div>
<div class="${enabled ? "" : "optional-disabled"}">
  <div class="card">
    <div class="section-header">Preissensor</div>
    ${this._textRow("tariff_price_sensor", "Entity ID Strompreis-Sensor",
      "Tibber, Awattar, input_number — oder leer lassen. Kein Sensor → Feature schlummert. Einheit muss zu den Schwellwerten passen.")}
  </div>
  <div class="card">
    <div class="section-header">Preiszonen</div>
    ${this._numRow("tariff_cheap_threshold",     "Günstig-Schwelle",      "Unter diesem Wert: Laden + Entladesperre.", -100, 100, 0.5)}
    ${this._numRow("tariff_expensive_threshold", "Teuer-Schwelle",        "Ab diesem Wert: Entladesperre aufgehoben.", -100, 100, 0.5)}
  </div>
  <div class="card">
    <div class="section-header">Laden</div>
    ${this._numRow("tariff_soc_target", "SOC-Ladeziel (%)",  "Tarif-Laden stoppt hier.", 10, 99, 1, "%")}
    ${this._numRow("tariff_charge_power", "Ladeleistung (W)", "Direkt gesetzt — kein PI.", 50, 1200, 50, "W")}
  </div>
</div>
${this._saveBar()}`;
  }

  // ── Night shutdown tab ────────────────────────────────────────────────────
  _buildNightTab() {
    const enabled = this._s("night_shutdown_enabled");
    return `
<h2 style="margin:0 0 16px;font-size:1.1rem">🌙 Nachtabschaltung</h2>
<div class="card">
  ${this._checkRow("night_shutdown_enabled", "Nachtabschaltung aktivieren",
    "Betrifft nur Zone 2. Zone 1 und AC Laden laufen weiter. Schwelle = PV-Ladereserve aus Zonen-Einstellungen.")}
</div>
<div class="${enabled ? "" : "optional-disabled"}">
  <div class="card" style="color:var(--secondary-text-color);font-size:.88rem">
    Wenn PV-Leistung &lt; PV-Ladereserve (aus Zonen-Tab): Zone 2 → Modus 0, Output 0 W.<br><br>
    Reaktivierung: Sobald PV wieder über die PV-Ladereserve steigt.
  </div>
</div>
${this._saveBar()}`;
  }

  // ── Form helpers ──────────────────────────────────────────────────────────
  _s(key) {
    // return current value (dirty override or saved)
    return key in this._dirty ? this._dirty[key] : (this._settings[key] ?? "");
  }

  _numRow(key, label, hint, min, max, step, unit = "") {
    const val = this._s(key);
    return `
<div class="form-row" data-key="${key}">
  <div class="form-label">
    <div class="form-label-text">${label}${unit ? ` <small>(${unit})</small>` : ""}</div>
    ${hint ? `<div class="form-label-hint">${hint}</div>` : ""}
  </div>
  <div class="form-control">
    <input type="number" class="setting-input" data-key="${key}"
      min="${min}" max="${max}" step="${step}" value="${val}">
  </div>
</div>`;
  }

  _textRow(key, label, hint) {
    const val = this._s(key);
    return `
<div class="form-row" data-key="${key}">
  <div class="form-label">
    <div class="form-label-text">${label}</div>
    ${hint ? `<div class="form-label-hint">${hint}</div>` : ""}
  </div>
  <div class="form-control">
    <input type="text" class="setting-input input-wide" data-key="${key}" value="${val}"
      placeholder="entity_id oder leer">
  </div>
</div>`;
  }

  _checkRow(key, label, hint) {
    const val = this._s(key);
    return `
<div class="form-row" data-key="${key}">
  <div class="form-label">
    <div class="form-label-text">${label}</div>
    ${hint ? `<div class="form-label-hint">${hint}</div>` : ""}
  </div>
  <div class="form-control">
    <input type="checkbox" class="setting-input" data-key="${key}" ${val ? "checked" : ""}>
  </div>
</div>`;
  }

  _saveBar() {
    return `<div class="save-bar" id="save-bar">
      <button class="btn btn-primary" id="btn-save">💾 Speichern</button>
      <span class="dirty-badge" id="dirty-badge" style="display:none">Ungespeichert</span>
    </div>`;
  }

  _updateSaveBar() {
    const badge = this.shadowRoot.getElementById("dirty-badge");
    if (badge) badge.style.display = Object.keys(this._dirty).length ? "" : "none";
  }

  // ── Bind form inputs ──────────────────────────────────────────────────────
  _bindFormTab(_tabId) {
    const root = this.shadowRoot;

    root.querySelectorAll(".setting-input").forEach(inp => {
      inp.addEventListener("change", () => {
        const key = inp.dataset.key;
        const val = inp.type === "checkbox" ? inp.checked
                  : inp.type === "number"   ? parseFloat(inp.value)
                  : inp.value;
        this._dirty[key] = val;
        this._updateSaveBar();

        // Re-render optional section visibility immediately
        if (key.endsWith("_enabled") || key === "surplus_enabled") {
          this._renderActiveTab();
        }
      });
    });

    root.getElementById("btn-save")?.addEventListener("click", () => this._saveSettings());
  }

  // ── Utility ───────────────────────────────────────────────────────────────
  _watt(v) {
    if (v === null || v === undefined || v === "—") return "—";
    const n = parseFloat(v);
    return isNaN(n) ? v : `${n.toFixed(0)} W`;
  }
  _pct(v) {
    if (v === null || v === undefined || v === "—") return "—";
    const n = parseFloat(v);
    return isNaN(n) ? v : `${n.toFixed(0)} %`;
  }
  _pill(label, active, color) {
    return `<span class="pill ${active ? "pill-on" : "pill-off"}" style="${active ? `background:${color}` : ""}">${label}</span>`;
  }

  _showToast(msg, err = false) {
    const el = this.shadowRoot.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    el.style.borderLeft = err ? "4px solid #dc2626" : "4px solid #16a34a";
    el.classList.add("show");
    setTimeout(() => el.classList.remove("show"), 2800);
  }
}

customElements.define("solakon-panel", SolakonPanel);
