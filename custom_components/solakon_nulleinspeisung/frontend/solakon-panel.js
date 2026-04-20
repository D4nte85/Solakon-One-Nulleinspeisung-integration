/**
 * Solakon ONE Nulleinspeisung — Sidebar Panel
 */

const DOMAIN = "solakon_nulleinspeisung";

// Zone colors and icons — not translated
const ZONE_STYLE = {
  0: { color: "#f59e0b", icon: "☀️" },
  1: { color: "#16a34a", icon: "⚡" },
  2: { color: "#0891b2", icon: "🔋" },
  3: { color: "#dc2626", icon: "⛔" },
};

const TABS = [
  { id: "status"  },
  { id: "pi"      },
  { id: "zones"   },
  { id: "surplus" },
  { id: "ac"      },
  { id: "tariff"  },
  { id: "dynoff"  },
  { id: "night"   },
  { id: "debug"   },
];

// Tab icons — not translated
const TAB_ICONS = {
  status:  "📊",
  pi:      "🎛️",
  zones:   "🔋",
  surplus: "☀️",
  ac:      "⚡",
  tariff:  "💹",
  dynoff:  "📈",
  night:   "🌙",
  debug:   "🔧",
};

// Layout: field keys + numeric constraints only — labels/descriptions in translation files
const TAB_LAYOUT = {
  pi: {
    cols: [
      {
        tk: "pi_ctrl", icon: "🎛️", color: "#0891b2",
        fields: [
          { k: "p_factor",  t: "num", min: 0.1, max: 5,   step: 0.1  },
          { k: "i_factor",  t: "num", min: 0,   max: 0.5, step: 0.01 },
          { k: "tolerance", t: "num", min: 0,   max: 200, step: 1    },
          { k: "wait_time", t: "num", min: 0,   max: 30,  step: 1    },
        ],
      },
      {
        tk: "pi_saw", icon: "🎯", color: "#7c3aed",
        fields: [
          { k: "self_adjust_enabled",   t: "bool" },
          { k: "self_adjust_tolerance", t: "num", min: 1, max: 50, step: 1 },
        ],
      },
    ],
  },

  zones: {
    cols: [
      {
        tk: "zones_soc", icon: "🔋", color: "#0891b2",
        fields: [
          { k: "zone1_limit", t: "num", min: 1,  max: 99,  step: 1  },
          { k: "zone3_limit", t: "num", min: 1,  max: 49,  step: 1  },
          { k: "pv_reserve",  t: "num", min: 0,  max: 500, step: 10 },
        ],
      },
      {
        tk: "zones_power", icon: "⚙️", color: "#b45309",
        fields: [
          { k: "hard_limit",    t: "num", min: 100, max: 2000, step: 50 },
          { k: "discharge_max", t: "num", min: 1,   max: 100,  step: 1  },
        ],
      },
      {
        tk: "zones_offsets", icon: "🎯", color: "#7c3aed",
        fields: [
          { k: "offset_1", t: "num", min: -200, max: 300, step: 1 },
          { k: "offset_2", t: "num", min: -200, max: 300, step: 1 },
        ],
      },
    ],
  },

  surplus: {
    top: [
      { k: "surplus_enabled", t: "bool" },
    ],
    enabledKey: "surplus_enabled",
    cols: [
      {
        tk: "surplus_soc", icon: "🔋", color: "#0891b2",
        fields: [
          { k: "surplus_soc_threshold", t: "num", min: 50,  max: 100, step: 1 },
          { k: "surplus_soc_hyst",      t: "num", min: 1,   max: 20,  step: 1 },
        ],
      },
      {
        tk: "surplus_pv", icon: "☀️", color: "#f59e0b",
        fields: [
          { k: "surplus_pv_hyst", t: "num", min: 10, max: 200, step: 10 },
        ],
      },
      {
        tk: "surplus_forecast", icon: "🌤️", color: "#65a30d",
        fields: [
          { k: "surplus_forecast_enabled",   t: "bool" },
          { k: "surplus_forecast_sensor",    t: "entity" },
          { k: "surplus_forecast_threshold", t: "num", min: 0, max: 100, step: 0.5 },
        ],
      },
    ],
  },

  ac: {
    top: [
      { k: "ac_enabled", t: "bool" },
    ],
    enabledKey: "ac_enabled",
    cols: [
      {
        tk: "ac_entry", icon: "⚡", color: "#7c3aed",
        fields: [
          { k: "ac_soc_target",  t: "num", min: 50,  max: 100,  step: 1   },
          { k: "ac_power_limit", t: "num", min: 100, max: 2000, step: 50  },
          { k: "ac_hysteresis",  t: "num", min: 10,  max: 500,  step: 10  },
          { k: "ac_offset",      t: "num", min: -500,max: 200,  step: 5   },
        ],
      },
      {
        tk: "ac_pi", icon: "🎛️", color: "#0891b2",
        fields: [
          { k: "ac_p_factor", t: "num", min: 0.1, max: 3,   step: 0.1  },
          { k: "ac_i_factor", t: "num", min: 0,   max: 0.5, step: 0.01 },
        ],
      },
    ],
  },

  tariff: {
    top: [
      { k: "tariff_enabled",      t: "bool" },
      { k: "tariff_price_sensor", t: "entity", domain: "sensor" },
    ],
    enabledKey: "tariff_enabled",
    cols: [
      {
        tk: "tariff_thresholds", icon: "💹", color: "#0891b2",
        fields: [
          { k: "tariff_cheap_threshold", t: "num",    min: 0, max: 100, step: 0.5 },
          { k: "tariff_cheap_entity",    t: "entity", domain: "input_number" },
          { k: "tariff_exp_threshold",   t: "num",    min: 0, max: 100, step: 0.5 },
          { k: "tariff_exp_entity",      t: "entity", domain: "input_number" },
        ],
      },
      {
        tk: "tariff_charge", icon: "🔋", color: "#16a34a",
        fields: [
          { k: "tariff_soc_target", t: "num", min: 50,  max: 100,  step: 1  },
          { k: "tariff_power",      t: "num", min: 100, max: 2000, step: 50 },
        ],
      },
      {
        tk: "tariff_forecast", icon: "☀️", color: "#f59e0b",
        fields: [
          { k: "pv_forecast_enabled",   t: "bool" },
          { k: "pv_forecast_sensor",    t: "entity" },
          { k: "pv_forecast_threshold", t: "num", min: 0, max: 50, step: 0.5 },
        ],
      },
    ],
  },

  dynoff: {
    top: [
      { k: "stddev_window", t: "num", min: 30, max: 300, step: 10 },
    ],
    cols: [
      {
        tk: "dynoff_z1", icon: "⚡", color: "#16a34a",
        fields: [
          { k: "dyn_z1_enabled",  t: "bool" },
          { k: "dyn_z1_min",      t: "num", min: 0,   max: 500,  step: 1   },
          { k: "dyn_z1_max",      t: "num", min: 50,  max: 1000, step: 10  },
          { k: "dyn_z1_noise",    t: "num", min: 0,   max: 100,  step: 1   },
          { k: "dyn_z1_factor",   t: "num", min: 0.5, max: 5,    step: 0.1 },
          { k: "dyn_z1_negative", t: "bool" },
        ],
      },
      {
        tk: "dynoff_z2", icon: "🔋", color: "#0891b2",
        fields: [
          { k: "dyn_z2_enabled",  t: "bool" },
          { k: "dyn_z2_min",      t: "num", min: 0,   max: 500,  step: 1   },
          { k: "dyn_z2_max",      t: "num", min: 50,  max: 1000, step: 10  },
          { k: "dyn_z2_noise",    t: "num", min: 0,   max: 100,  step: 1   },
          { k: "dyn_z2_factor",   t: "num", min: 0.5, max: 5,    step: 0.1 },
          { k: "dyn_z2_negative", t: "bool" },
        ],
      },
      {
        tk: "dynoff_ac", icon: "⚡", color: "#7c3aed",
        fields: [
          { k: "dyn_ac_enabled",  t: "bool" },
          { k: "dyn_ac_min",      t: "num", min: 0,   max: 500,  step: 1   },
          { k: "dyn_ac_max",      t: "num", min: 50,  max: 1000, step: 10  },
          { k: "dyn_ac_noise",    t: "num", min: 0,   max: 100,  step: 1   },
          { k: "dyn_ac_factor",   t: "num", min: 0.5, max: 5,    step: 0.1 },
          { k: "dyn_ac_negative", t: "bool" },
        ],
      },
    ],
  },

  night: {
    top: [
      { k: "night_enabled", t: "bool" },
    ],
  },
};

// ── Multi-Instance State ─────────────────────────────────────────────────────

class SolakonPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._initialized    = false;
    this._settings       = {};
    this._dirty          = {};
    this._status         = null;
    this._activeTab      = "status";
    this._polling        = null;
    this._t              = {};
    // Multi-Instance
    this._instances      = [];
    this._activeInstance = null;
    this._allStatuses    = {};
    this._distConfig     = {};
    this._distDirty      = {};
  }

  set panel(val) {
    this._panel = val;
    if (val?.config?.entry_id) { this._entryId = val.config.entry_id; }
    if (val?.config !== undefined) { this._checkInit(); }
  }

  set hass(val) { this._hass = val; this._checkInit(); }

  _checkInit() {
    if (this._hass && !this._initialized) {
      this._initialized = true;
      this._loadTranslations().then(() => {
        this._build();
        this._loadInstances();
        this._polling = setInterval(() => this._loadStatus(), 1000);
      });
    }
  }

  async _loadTranslations() {
    const lang = (this._hass.language || "en").split("-")[0].toLowerCase();
    const supported = ["de", "en"];
    const locale = supported.includes(lang) ? lang : "en";
    try {
      const res = await fetch(`/${DOMAIN}/panel.${locale}.json`);
      if (!res.ok) throw new Error("fetch failed");
      this._t = await res.json();
    } catch (_) {
      if (locale !== "en") {
        try {
          const res = await fetch(`/${DOMAIN}/panel.en.json`);
          this._t = await res.json();
        } catch (_) { this._t = {}; }
      } else {
        this._t = {};
      }
    }
  }

  // Shorthand: look up a field's label or description
  _fl(key) { return this._t.fields?.[key]?.l || key; }
  _fd(key) { return this._t.fields?.[key]?.d || ""; }

  async _ws(cmd, extra = {}) {
    return this._hass.callWS({ type: `${DOMAIN}/${cmd}`, entry_id: this._entryId, ...extra });
  }

  // ── Multi-Instance Methoden ───────────────────────────────────────────────

  async _loadInstances() {
    try {
      const res = await this._hass.callWS({ type: `${DOMAIN}/get_all_instances` });
      this._instances = res.instances || [];
    } catch (_) {
      this._instances = this._entryId
        ? [{ entry_id: this._entryId, instance_name: "Solakon ONE" }]
        : [];
    }
    if (this._instances.length > 0 && !this._activeInstance) {
      this._activeInstance = this._instances[0].entry_id;
      this._entryId        = this._instances[0].entry_id;
    }
    this._renderInstBar();
    await this._loadConfig();
  }

  _renderInstBar() {
    const bar = this.shadowRoot.getElementById("inst-bar");
    if (!bar) return;
    bar.innerHTML = "";
    if (this._instances.length <= 1) return;

    const mkTab = (id, label) => {
      const el = document.createElement("div");
      el.className = "inst-tab" + (this._activeInstance === id ? " active" : "");
      el.textContent = label;
      el.addEventListener("click", () => this._switchInstance(id));
      bar.appendChild(el);
    };

    mkTab("__overview__", this._t.ov?.btn || "Overview");
    for (const inst of this._instances) mkTab(inst.entry_id, inst.instance_name);
  }

  _switchInstance(id) {
    this._activeInstance = id;
    this._renderInstBar();
    if (id === "__overview__") {
      const c = this.shadowRoot.getElementById("content");
      if (c) this._renderOverview(c);
      const bar = this.shadowRoot.getElementById("save-bar");
      if (bar) bar.style.display = "none";
      return;
    }
    this._entryId   = id;
    this._settings  = {};
    this._dirty     = {};
    this._status    = null;
    this._activeTab = "status";
    this._loadConfig();
  }

  _renderOverview(c) {
    const ov = this._t.ov || {};
    const html = this._instances.map(inst => {
      const st = this._allStatuses[inst.entry_id] || {};
      const zs = ZONE_STYLE[st.zone] ?? ZONE_STYLE[2];
      const zLabel = this._t.zone_cfg?.[st.zone] ?? `Zone ${st.zone}`;
      const fl = this._t.fall_labels?.[st.active_fall] || st.active_fall || "—";
      return `<div class="ov-card" data-eid="${inst.entry_id}">
        <div class="ov-hdr" style="background:${zs.color}">${zs.icon} ${inst.instance_name}</div>
        <div class="ov-body">
          <div class="ov-row"><span>${ov.soc    || "SOC"}</span><strong>${st.soc ?? "—"} %</strong></div>
          <div class="ov-row"><span>${ov.output || "Output"}</span><strong>${st.actual_power != null ? st.actual_power + " W" : "—"}</strong></div>
          <div class="ov-row"><span>${ov.grid   || "Grid"}</span><strong>${st.grid != null ? st.grid.toFixed(0) + " W" : "—"}</strong></div>
          <div class="ov-row"><span>${ov.fall   || "Case"}</span><strong>${fl}</strong></div>
        </div>
      </div>`;
    }).join("");
    c.innerHTML = `<div class="ov-grid">${html}</div>`;
    c.querySelectorAll(".ov-card").forEach(card => {
      card.addEventListener("click", () => this._switchInstance(card.dataset.eid));
    });

    const distContainer = document.createElement("div");
    distContainer.style.marginTop = "16px";
    c.appendChild(distContainer);
    this._renderVerteilung(distContainer);
  }

  // ── Config / Status Laden ─────────────────────────────────────────────────

  async _loadConfig() {
    try { this._settings = await this._ws("get_config"); this._renderActiveTab(); }
    catch (e) { console.error("Solakon: config load failed", e); }
  }

  async _loadStatus() {
    if (this._activeInstance === "__overview__") {
      for (const inst of this._instances) {
        try {
          this._allStatuses[inst.entry_id] = await this._hass.callWS(
            { type: `${DOMAIN}/get_status`, entry_id: inst.entry_id }
          );
        } catch (_) {}
      }
      const c = this.shadowRoot.getElementById("content");
      if (c) this._renderOverview(c);
      return;
    }
    try {
      this._status = await this._ws("get_status");
      if (this._activeTab === "status") this._updateStatusView();
      if (this._activeTab === "debug") {
        const el = this.shadowRoot.getElementById("dbg-zone-state");
        if (el) el.textContent = this._status.cycle_active
          ? (this._t.debug?.zone1_state || "Zone 1")
          : (this._t.debug?.zone2_state || "Zone 2");
      }
      this._updateRegBanner();
    } catch (e) { /* ignore polling errors */ }
  }

  // ── Build ─────────────────────────────────────────────────────────────────

  _build() {
    const tc  = this._t.top_card   || {};
    const sb  = this._t.save_bar   || {};
    const reg = this._t.regulation || {};

    const prioRows = (tc.prio_rows || []).map(([p, m, b]) =>
      `<tr><td>${p}</td><td>${m}</td><td>${b}</td></tr>`
    ).join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
          color: var(--primary-text-color, #333);
          background-color: var(--primary-background-color, #fafafa);
        }
        .wrap { max-width: 940px; margin: 0 auto; padding: 16px; }

        /* ── App bar ─────────────────────────────────────────────────────── */
        .app-bar {
          position: sticky; top: 0; z-index: 20;
          background: var(--app-header-background-color, var(--primary-color, #03a9f4));
          color: var(--app-header-text-color, #fff);
          display: flex; align-items: center; height: 56px; padding: 0 4px;
        }
        .menu-btn { background: none; border: none; color: inherit; cursor: pointer; padding: 10px 12px; border-radius: 50%; font-size: 1.4em; line-height: 1; display: flex; align-items: center; }
        .menu-btn:hover { background: rgba(255,255,255,0.12); }
        .app-bar-title { font-size: 1.05em; font-weight: 500; flex: 1; padding-left: 4px; }

        /* ── Instanz-Leiste (Multi-Instance) ─────────────────────────────── */
        .inst-bar { display: flex; flex-wrap: wrap; gap: 4px; padding: 8px 16px 0;
          background: var(--secondary-background-color, #f0f0f0);
          border-bottom: 1px solid var(--divider-color, #ddd); }
        .inst-bar:empty { display: none; }
        .inst-tab { padding: 7px 13px; border-radius: 8px 8px 0 0; cursor: pointer;
          background: var(--card-background-color, #fff);
          border: 1px solid var(--divider-color, #ddd);
          border-bottom: 2px solid var(--card-background-color, #fff);
          font-size: .82em; white-space: nowrap; position: relative; bottom: -1px;
          transition: background .15s; }
        .inst-tab:hover:not(.active) { background: var(--secondary-background-color, #f5f5f5); }
        .inst-tab.active { background: var(--primary-color, #03a9f4); color: #fff;
          border-color: var(--primary-color, #03a9f4);
          border-bottom-color: var(--primary-color, #03a9f4); font-weight: 600; }

        /* ── Übersichts-Karten ───────────────────────────────────────────── */
        .ov-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
        .ov-card { border: 1px solid var(--divider-color, #ddd); border-radius: 10px;
          overflow: hidden; cursor: pointer; transition: box-shadow .15s; }
        .ov-card:hover { box-shadow: 0 2px 10px rgba(0,0,0,.12); }
        .ov-hdr  { padding: 10px 14px; color: #fff; font-weight: 600; font-size: .92em; }
        .ov-body { padding: 10px 14px; background: var(--card-background-color, #fff);
          display: flex; flex-direction: column; gap: 6px; }
        .ov-row  { display: flex; justify-content: space-between; font-size: .85em; }
        .ov-row span   { color: var(--secondary-text-color, #666); }
        .ov-row strong { color: var(--primary-text-color, #333); }

        /* ── Top card ────────────────────────────────────────────────────── */
        .top-card { border: 1px solid var(--divider-color, #ddd); border-radius: 10px; overflow: hidden; margin-bottom: 14px; }
        .top-card-hdr { background: var(--primary-color, #03a9f4); color: #fff; padding: 12px 16px; font-size: 1.1em; font-weight: 600; display: flex; align-items: center; gap: 8px; }
        .top-card-body { padding: 12px 16px; background: var(--card-background-color, #fff); display: flex; flex-direction: column; gap: 10px; }

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
        .prio-table { width: 100%; border-collapse: collapse; font-size: .82em; margin-top: 4px; }
        .prio-table th { background: var(--secondary-background-color, #f0f0f0); padding: 5px 8px; text-align: left; font-weight: 600; border-bottom: 1px solid var(--divider-color, #ddd); }
        .prio-table td { padding: 4px 8px; border-bottom: 1px solid var(--divider-color, #eee); }
        .prio-table tr:last-child td { border-bottom: none; }

        /* ── Tab panel ───────────────────────────────────────────────────── */
        .tab-panel { border: 1px solid var(--divider-color, #ddd); border-radius: 10px; overflow: hidden; margin-bottom: 14px; }
        .tab-bar { background: var(--secondary-background-color, #f0f0f0); border-bottom: 2px solid var(--divider-color, #ddd); display: flex; flex-wrap: wrap; padding: 8px 8px 0; gap: 2px; }
        .tab { padding: 7px 11px; border-radius: 8px 8px 0 0; cursor: pointer; background: var(--card-background-color, #fff); border: 1px solid var(--divider-color, #ddd); border-bottom: 2px solid var(--card-background-color, #fff); font-size: .82em; white-space: nowrap; position: relative; bottom: -2px; transition: background .15s; }
        .tab:hover:not(.active) { background: var(--secondary-background-color, #f5f5f5); }
        .tab.active { background: var(--primary-color, #03a9f4); color: #fff; border-color: var(--primary-color, #03a9f4); border-bottom-color: var(--primary-color, #03a9f4); font-weight: 600; }
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
        @media (max-width: 700px) { .col-grid.cols-2, .col-grid.cols-3 { grid-template-columns: 1fr; } }
        .col-grid.disabled { opacity: .45; pointer-events: none; }
        .col-card { border: 1px solid var(--divider-color, #ddd); border-radius: 10px; overflow: hidden; }
        .col-card.top-item { margin-bottom: 12px; }
        .col-header { padding: 8px 14px; color: #fff; font-weight: 600; font-size: .88em; }
        .col-body { padding: 12px 14px; background: var(--card-background-color, #fff); display: flex; flex-direction: column; gap: 10px; }

        /* ── Fields ──────────────────────────────────────────────────────── */
        .field { display: flex; flex-direction: column; gap: 4px; }
        .field label { display: flex; align-items: center; gap: 8px; font-size: .9em; font-weight: 500; cursor: pointer; }
        .field input[type="number"], .field input[type="text"] { padding: 6px 10px; border: 1px solid var(--divider-color, #ddd); border-radius: 6px; background: var(--secondary-background-color, #f5f5f5); color: var(--primary-text-color, #333); font-size: .9em; width: 100%; box-sizing: border-box; }
        .field input[type="checkbox"] { width: 16px; height: 16px; cursor: pointer; accent-color: var(--primary-color, #03a9f4); }
        .desc { font-size: .78em; color: var(--secondary-text-color, #888); line-height: 1.5; }

        /* ── Status tab ──────────────────────────────────────────────────── */
        .zone-banner { padding: 12px; border-radius: 8px; color: #fff; font-weight: 600; font-size: 1.1em; margin-bottom: 12px; text-align: center; }
        .stat-col-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
        .stat-col-card { border: 1px solid var(--divider-color, #ddd); border-radius: 10px; overflow: hidden; }
        .stat-col-header { padding: 8px 14px; color: #fff; font-weight: 600; font-size: .88em; }
        .stat-col-body { padding: 12px 14px; background: var(--card-background-color, #fff); display: flex; flex-direction: column; gap: 8px; }
        .stat-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .stat { padding: 7px 10px; border-radius: 6px; background: var(--secondary-background-color, #f0f0f0); }
        .stat .val { font-size: 1.15em; font-weight: 600; }
        .stat .lbl { font-size: .76em; color: var(--secondary-text-color, #888); margin-top: 2px; }
        .stat-full { padding: 7px 10px; border-radius: 6px; background: var(--secondary-background-color, #f0f0f0); }
        .stat-full .val { font-size: 1.15em; font-weight: 600; }
        .stat-full .lbl { font-size: .76em; color: var(--secondary-text-color, #888); margin-top: 2px; }
        .stat-full .lbl-src { font-size: .76em; color: var(--secondary-text-color, #888); margin-top: 1px; font-style: italic; }
        .offset-src-tag { display: inline-block; padding: 2px 7px; border-radius: 10px; font-size: .75em; font-style: normal; margin-right: 4px; font-weight: 500; }
        .offset-src-tag.active   { background: #16a34a22; color: #16a34a; }
        .offset-src-tag.inactive { background: #6b728022; color: #6b7280; }

        /* ── Flags ───────────────────────────────────────────────────────── */
        .flag-row { display: flex; flex-wrap: wrap; gap: 5px; }
        .flag { padding: 3px 9px; border-radius: 12px; font-size: .8em; font-weight: 500; }
        .flag.on  { background: #16a34a22; color: #16a34a; }
        .flag.off { background: #6b728022; color: #6b7280; }

        /* ── Mode labels ─────────────────────────────────────────────────── */
        .mode-lbl { color: var(--secondary-text-color, #888); margin-bottom: 2px; font-size: .85em; }
        .mode-val { font-size: .88em; color: var(--primary-text-color, #333); }
        .mode-err { font-size: .88em; color: #dc2626; }

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
      <div id="inst-bar" class="inst-bar"></div>
      <div class="wrap">

        <div class="top-card">
          <div class="top-card-hdr">${tc.title || "⚡ Solakon ONE"}</div>
          <div class="top-card-body">
            <div class="reg-bar off" id="reg-bar">
              <div class="reg-dot"></div>
              <span id="reg-text">${reg.inactive || ""}</span>
            </div>
            <details class="global-info">
              <summary>${tc.info_summary || "ℹ️"}</summary>
              <div class="global-body">
                <p>${tc.p1 || ""}</p>
                <p>${tc.p2 || ""}</p>
                <p>${tc.p3 || ""}</p>
                <p><strong>${tc.prio_heading || ""}</strong></p>
                <table class="prio-table">
                  <tr>
                    <th>${tc.prio_priority || ""}</th>
                    <th>${tc.prio_module   || ""}</th>
                    <th>${tc.prio_blocks   || ""}</th>
                  </tr>
                  ${prioRows}
                </table>
                <p style="margin-top:4px">${tc.prio_note || ""}</p>
              </div>
            </details>
          </div>
        </div>

        <div class="tab-panel">
          <div class="tab-bar" id="tabs"></div>
          <div class="tab-content" id="content"></div>
        </div>

        <div id="save-bar">
          <span>${sb.unsaved || ""}</span>
          <button onclick="this.getRootNode().host._saveSettings()">${sb.save || "Save"}</button>
        </div>
      </div>
      <div id="toast"></div>
    `;

    this.shadowRoot.getElementById("reg-bar").addEventListener("click", () => this._toggleRegulation());
    this.shadowRoot.getElementById("menu-btn").addEventListener("click", () => {
      this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }));
    });

    const tabWrap = this.shadowRoot.getElementById("tabs");
    for (const t of TABS) {
      const el = document.createElement("div");
      el.className = "tab" + (t.id === this._activeTab ? " active" : "");
      el.textContent = `${TAB_ICONS[t.id] || ""} ${this._t.tabs?.[t.id] || t.id}`;
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

    const doc = this._t.tab_docs?.[this._activeTab];
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

    if (layout.top?.length) {
      const topCard = document.createElement("div");
      topCard.className = "col-card top-item";
      const topHdr = document.createElement("div");
      topHdr.className = "col-header";
      topHdr.style.background = "#475569";
      topHdr.textContent = this._t.general_section || "⚙️ General";
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
      hdr.textContent = `${col.icon} ${this._t.col_titles?.[col.tk] || col.tk}`;
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
    const label = this._fl(f.k);
    const desc  = this._fd(f.k);

    if (f.t === "bool") {
      div.innerHTML = `<label class="toggle"><input type="checkbox" data-key="${f.k}" ${cur ? "checked" : ""}/> ${label}</label><div class="desc">${desc}</div>`;
      div.querySelector("input").addEventListener("change", (e) => {
        this._dirty[f.k] = e.target.checked;
        this._updateSaveBar();
      });
    } else if (f.t === "num") {
      div.innerHTML = `<label>${label}</label><div class="desc">${desc}</div><input type="number" min="${f.min}" max="${f.max}" step="${f.step}" value="${cur ?? f.min}"/>`;
      div.querySelector("input").addEventListener("change", (e) => {
        this._dirty[f.k] = parseFloat(e.target.value);
        this._updateSaveBar();
      });
    } else if (f.t === "entity") {
      const eid = `ep_${f.k}`;
      div.innerHTML = `<label>${label}</label><div class="desc">${desc}</div><input type="text" list="${eid}_list" value="${cur || ""}" placeholder="sensor.xxx"/><datalist id="${eid}_list"></datalist>`;
      const inp = div.querySelector("input");
      const dl  = div.querySelector("datalist");
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
    const s = this._t.status || {};
    c.innerHTML = `
      <div class="zone-banner" id="zone-banner">${s.loading || "…"}</div>
      <div class="stat-col-grid">

        <div class="stat-col-card">
          <div class="stat-col-header" style="background:#0891b2">${s.measurements_hdr || "⚡"}</div>
          <div class="stat-col-body">
            <div class="stat-row">
              <div class="stat"><div class="val" id="st-grid">—</div><div class="lbl">${s.grid_lbl   || "Grid"}</div></div>
              <div class="stat"><div class="val" id="st-soc">—</div> <div class="lbl">${s.soc_lbl    || "SOC"}</div></div>
            </div>
            <div class="stat-row">
              <div class="stat"><div class="val" id="st-actual">—</div><div class="lbl">${s.output_lbl || "Output"}</div></div>
              <div class="stat"><div class="val" id="st-solar">—</div> <div class="lbl">${s.solar_lbl  || "Solar"}</div></div>
            </div>
          </div>
        </div>

        <div class="stat-col-card">
          <div class="stat-col-header" style="background:#7c3aed">${s.ctrl_hdr || "📈"}</div>
          <div class="stat-col-body">
            <div class="stat-row">
              <div class="stat"><div class="val" id="st-int">—</div>   <div class="lbl">${s.integral_lbl || "Integral"}</div></div>
              <div class="stat"><div class="val" id="st-stddev">—</div><div class="lbl">${s.stddev_lbl   || "StdDev"}</div></div>
            </div>
            <div class="stat-full">
              <div class="val" id="st-offset-val">—</div>
              <div class="lbl" id="st-offset-lbl">${s.offset_lbl || "Offset"}</div>
              <div class="lbl-src" id="st-offset-src">—</div>
            </div>
            <div class="stat-row">
              <div class="stat"><div class="val" id="st-elapsed">—</div>     <div class="lbl">${s.elapsed_lbl      || ""}</div></div>
              <div class="stat"><div class="val" id="st-mode-elapsed">—</div><div class="lbl">${s.mode_elapsed_lbl || ""}</div></div>
            </div>
          </div>
        </div>

        <div class="stat-col-card">
          <div class="stat-col-header" style="background:#b45309">${s.modules_hdr || "🚦"}</div>
          <div class="stat-col-body">
            <div>
              <div class="mode-lbl">${s.active_modules_lbl || ""}</div>
              <div class="flag-row" id="st-flags"></div>
            </div>
            <div>
              <div class="mode-lbl">${s.active_fall_lbl || ""}</div>
              <div class="mode-val" id="st-active-fall">—</div>
            </div>
            <div>
              <div class="mode-lbl">${s.mode_lbl || ""}</div>
              <div class="mode-val" id="st-mode">—</div>
            </div>
            <div>
              <div class="mode-lbl">${s.last_action_lbl || ""}</div>
              <div class="mode-val" id="st-action">—</div>
            </div>
            <div>
              <div class="mode-lbl">${s.error_lbl || ""}</div>
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
    const s  = this._t.status || {};

    const zs    = ZONE_STYLE[st.zone] || ZONE_STYLE[2];
    const zLabel = this._t.zone_cfg?.[st.zone] ?? `Zone ${st.zone}`;
    const b = this.shadowRoot.getElementById("zone-banner");
    if (b) { b.textContent = `${zs.icon} ${zLabel}`; b.style.background = zs.color; }

    const set = (id, v) => { const e = this.shadowRoot.getElementById(id); if (e) e.textContent = v; };
    const fl = this.shadowRoot.getElementById("st-flags");
    if (fl) fl.innerHTML = [
      [s.flag_cycle       || "Cycle",         st.cycle_active],
      [s.flag_surplus     || "Surplus",        st.surplus_active],
      [s.flag_ac          || "AC",             st.ac_charge],
      [s.flag_tariff      || "Tariff",         st.tariff_charge],
      [s.flag_night       || "Night",          st.is_night],
      [s.flag_pv_tariff   || "PV→Tariff",      st.forecast_tariff_suppressed],
      [s.flag_pv_surplus  || "PV→Surplus",     st.forecast_surplus_forced],
    ].map(([n, v]) => `<span class="flag ${v ? "on" : "off"}">${v ? "●" : "○"} ${n}</span>`).join("");

    set("st-active-fall", this._t.fall_labels?.[st.active_fall] || st.active_fall || "—");
    set("st-grid",         `${(st.grid ?? 0).toFixed(0)} W`);
    set("st-actual",       `${st.actual_power ?? "—"} W`);
    set("st-solar",        `${st.solar ?? "—"} W`);
    set("st-soc",          `${st.soc ?? "—"} %`);
    set("st-int",          `${(st.integral ?? 0).toFixed(2)}`);
    set("st-stddev",       `${(st.stddev ?? 0).toFixed(1)} W`);
    set("st-elapsed",      this._fmt_elapsed(st.last_output_ts));
    set("st-mode-elapsed", this._fmt_elapsed(st.mode_label_ts));
    set("st-mode",         st.mode_label  || "—");
    set("st-action",       st.last_action || "—");
    set("st-error",        st.last_error  || (s.no_error || "—"));

    let offsetZoneKey, isDyn, offsetStatic;
    if (st.ac_charge) {
      offsetZoneKey = "offset_zone_ac";
      isDyn         = !!st.dyn_ac_enabled;
      offsetStatic  = this._settings.ac_offset ?? "—";
    } else if (st.cycle_active) {
      offsetZoneKey = "offset_zone_1";
      isDyn         = !!st.dyn_z1_enabled;
      offsetStatic  = this._settings.offset_1 ?? "—";
    } else {
      offsetZoneKey = "offset_zone_2";
      isDyn         = !!st.dyn_z2_enabled;
      offsetStatic  = this._settings.offset_2 ?? "—";
    }
    const dynVal      = isDyn ? (st[`dyn_${offsetZoneKey === "offset_zone_ac" ? "ac" : offsetZoneKey === "offset_zone_1" ? "z1" : "z2"}`] ?? 0).toFixed(0) : offsetStatic;
    const offsetLabel = s[offsetZoneKey] || offsetZoneKey;
    set("st-offset-val", `${dynVal} W`);
    set("st-offset-lbl", `${s.offset_lbl || "Offset"} — ${offsetLabel}`);
    const srcEl = this.shadowRoot.getElementById("st-offset-src");
    const staticLbl = `${s.static_tag || "static"}: ${offsetStatic} W`;
    if (srcEl) srcEl.innerHTML = isDyn
      ? `<span class="offset-src-tag active">${s.dyn_tag || "dynamic"}</span><span class="offset-src-tag inactive">${staticLbl}</span>`
      : `<span class="offset-src-tag inactive">${s.dyn_inactive || "dyn. off"}</span><span class="offset-src-tag active">${staticLbl}</span>`;
  }

  // ── Debug tab ─────────────────────────────────────────────────────────────

  _renderDebug() {
    const c  = this.shadowRoot.getElementById("content");
    const d  = this._t.debug || {};
    const zoneState = this._status
      ? (this._status.cycle_active ? (d.zone1_state || "Zone 1") : (d.zone2_state || "Zone 2"))
      : "—";

    c.innerHTML = `
      <div class="col-grid cols-2">

        <div class="col-card">
          <div class="col-header" style="background:#7c3aed">${d.pi_hdr || "PI Integral"}</div>
          <div class="col-body">
            <p style="font-size:.85em;color:var(--secondary-text-color,#888);margin:0 0 12px">
              ${d.pi_desc || ""}
            </p>
            <button class="btn btn-secondary"
              onclick="this.getRootNode().host._resetIntegral()">
              ${d.reset_btn || "Reset"}
            </button>
          </div>
        </div>

        <div class="col-card">
          <div class="col-header" style="background:#0891b2">${d.zone_hdr || "Zone"}</div>
          <div class="col-body">
            <p style="font-size:.85em;color:var(--secondary-text-color,#888);margin:0 0 4px">
              ${d.zone_desc || ""}
            </p>
            <p style="font-size:.85em;margin:0 0 12px">
              ${d.zone_current || ""}<strong id="dbg-zone-state">${zoneState}</strong>
            </p>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <button class="btn" style="background:#16a34a;color:#fff"
                onclick="this.getRootNode().host._toggleCycle(true)">
                ${d.zone1_btn || "Zone 1"}
              </button>
              <button class="btn" style="background:#0891b2;color:#fff"
                onclick="this.getRootNode().host._toggleCycle(false)">
                ${d.zone2_btn || "Zone 2"}
              </button>
            </div>
          </div>
        </div>

      </div>
    `;
  }

  // ── Shared helpers ────────────────────────────────────────────────────────

  _updateRegBanner() {
    const on  = this._settings.regulation_enabled;
    const reg = this._t.regulation || {};
    const bar = this.shadowRoot.getElementById("reg-bar");
    const txt = this.shadowRoot.getElementById("reg-text");
    if (bar) bar.className = `reg-bar ${on ? "on" : "off"}`;
    if (txt) txt.textContent = on ? (reg.active || "") : (reg.inactive || "");
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

  async _saveSettings() {
    if (!Object.keys(this._dirty).length) return;
    const toast = this._t.toast || {};
    try {
      await this._ws("save_config", { changes: this._dirty });
      this._settings = { ...this._settings, ...this._dirty };
      this._dirty = {};
      this._showToast(toast.settings_saved || "✅");
      this._renderActiveTab();
    } catch (e) { this._showToast("❌ " + e.message, true); }
  }

  async _toggleRegulation() {
    const on    = !this._settings.regulation_enabled;
    const toast = this._t.toast || {};
    try {
      await this._ws("save_config", { changes: { regulation_enabled: on } });
      this._settings.regulation_enabled = on;
      this._updateRegBanner();
      this._showToast(on ? (toast.regulation_on || "✅") : (toast.regulation_off || "⏸️"));
    } catch (e) { this._showToast("❌ " + e.message, true); }
  }

  async _resetIntegral() {
    const toast = this._t.toast || {};
    try {
      await this._ws("reset_integral");
      this._showToast(toast.integral_reset || "🔄");
    } catch (e) { this._showToast("❌ " + e.message, true); }
  }

  async _toggleCycle(activate) {
    const toast = this._t.toast || {};
    const d     = this._t.debug || {};
    try {
      await this._ws("set_cycle", { active: activate });
      this._showToast(activate ? (toast.zone1_activated || "⚡") : (toast.zone2_activated || "🔋"));
      this._status = await this._ws("get_status");
      const el = this.shadowRoot.getElementById("dbg-zone-state");
      if (el) el.textContent = this._status.cycle_active
        ? (d.zone1_state || "Zone 1")
        : (d.zone2_state || "Zone 2");
    } catch (e) { this._showToast("❌ " + e.message, true); }
  }

  // ── Verteilung ───────────────────────────────────────────────────────────

  async _loadDistConfig() {
    try {
      const res = await this._hass.callWS({ type: `${DOMAIN}/get_distribution_config` });
      this._distConfig = res.distribution || {};
    } catch (_) { this._distConfig = {}; }
    this._distDirty = {};
  }

  async _saveDistConfig() {
    const merged = { ...this._distConfig, ...this._distDirty };
    const toast  = this._t.toast || {};
    try {
      await this._hass.callWS({ type: `${DOMAIN}/save_distribution_config`, distribution: merged });
      this._distConfig = merged;
      this._distDirty  = {};
      this._showToast(toast.dist_saved || "✅");
      this._renderActiveTab();
    } catch (e) { this._showToast("❌ " + e.message, true); }
  }

  _distVal(key) {
    return key in this._distDirty ? this._distDirty[key] : this._distConfig[key];
  }

  _setDistVal(key, value) {
    this._distDirty[key] = value;
    this._renderActiveTab();
  }

  _distInstVal(entry_id, key) {
    const k = `inst_${entry_id}_${key}`;
    return k in this._distDirty ? this._distDirty[k]
         : (this._distConfig[k] ?? "");
  }

  _setDistInstVal(entry_id, key, value) {
    this._distDirty[`inst_${entry_id}_${key}`] = value;
    this._renderActiveTab();
  }

  _renderVerteilung(c) {
    const dt = this._t.dist || {};

    if (this._instances.length <= 1) {
      c.innerHTML = `<p style="font-size:.88em;color:var(--secondary-text-color,#888);padding:12px 0">
        ${dt.single_instance_note || ""}</p>`;
      return;
    }

    const distLoaded = Object.keys(this._distConfig).length > 0 || Object.keys(this._distDirty).length > 0;
    if (!distLoaded) {
      this._loadDistConfig().then(() => this._renderActiveTab());
      c.innerHTML = `<p style="font-size:.88em;color:var(--secondary-text-color,#888);padding:12px 0">${dt.loading || "…"}</p>`;
      return;
    }

    const mode      = this._distVal("distribution_mode") ?? "equal";
    const globalMax = this._distVal("global_max_power")  ?? 800;
    const interval  = this._distVal("interval_seconds")  ?? "30";
    const balance   = this._distVal("soc_pv_balance")    ?? 0.5;

    const manualRows = this._instances.map(inst => {
      const val = this._distInstVal(inst.entry_id, "manual_power") ?? 800;
      return `<div class="field">
        <label>${inst.instance_name} ${dt.manual_inst_lbl || "(W)"}</label>
        <input type="number" min="0" max="9600" step="10" value="${val}"
          data-dist-inst="${inst.entry_id}" data-dist-key="manual_power"/>
      </div>`;
    }).join("");

    const manualSum = this._instances.reduce((s, inst) => {
      return s + (parseFloat(this._distInstVal(inst.entry_id, "manual_power")) || 0);
    }, 0);
    const warnTpl = dt.manual_warn || "⚠️ Sum ({sum} W) exceeds global max";
    const manualWarn = manualSum > globalMax
      ? `<p style="font-size:.8em;color:#dc2626;margin-top:4px">${warnTpl.replace("{sum}", manualSum)}</p>`
      : "";

    const intervalOptions = ["10","30","60","120","300"].map(v =>
      `<option value="${v}"${v === String(interval) ? " selected" : ""}>${v} s${v === "30" ? (dt.interval_recommended || "") : ""}</option>`
    ).join("");

    c.innerHTML = `
      <div class="col-card top-item">
        <div class="col-header" style="background:#0891b2">${dt.global_hdr || "🌐"}</div>
        <div class="col-body">
          <div class="field">
            <label>${dt.global_max_lbl || ""}</label>
            <div class="desc">${dt.global_max_desc || ""}</div>
            <input type="number" min="0" max="9600" step="10" value="${globalMax}" data-dist-key="global_max_power"/>
          </div>
          <div class="field">
            <label>${dt.interval_lbl || ""}</label>
            <div class="desc">${dt.interval_desc || ""}</div>
            <select data-dist-key="interval_seconds">${intervalOptions}</select>
          </div>
        </div>
      </div>

      <div class="col-card top-item">
        <div class="col-header" style="background:#7c3aed">${dt.mode_hdr || "⚖️"}</div>
        <div class="col-body">
          <div class="field">
            <label>${dt.mode_lbl || ""}</label>
            <div class="desc">${(dt.mode_desc || "").replace(/\n/g, "<br>")}</div>
            <select data-dist-key="distribution_mode" id="dist-mode-select">
              <option value="equal"${mode === "equal" ? " selected" : ""}>${dt.mode_equal || "Equal"}</option>
              <option value="weighted"${mode === "weighted" ? " selected" : ""}>${dt.mode_weighted || "Weighted"}</option>
              <option value="manual"${mode === "manual" ? " selected" : ""}>${dt.mode_manual || "Manual"}</option>
            </select>
          </div>
          <div class="field" style="${mode !== "weighted" ? "opacity:.4;pointer-events:none" : ""}">
            <label>${dt.balance_lbl || ""}</label>
            <div class="desc">${dt.balance_desc || ""}</div>
            <input type="number" min="0" max="1" step="0.05" value="${balance}" data-dist-key="soc_pv_balance"/>
          </div>
        </div>
      </div>

      <div class="col-card top-item" style="${mode !== "manual" ? "opacity:.4;pointer-events:none" : ""}">
        <div class="col-header" style="background:#b45309">${dt.manual_hdr || "🔧"}</div>
        <div class="col-body">
          ${manualRows}
          ${manualWarn}
        </div>
      </div>

      <div id="dist-save-bar" style="position:sticky;bottom:0;background:var(--primary-color,#03a9f4);color:#fff;padding:10px 16px;border-radius:8px;margin-top:4px;align-items:center;justify-content:space-between;display:${Object.keys(this._distDirty).length ? "flex" : "none"}">
        <span>${dt.unsaved || ""}</span>
        <button onclick="this.getRootNode().host._saveDistConfig()" style="background:#fff;color:var(--primary-color,#03a9f4);border:none;padding:6px 16px;border-radius:6px;cursor:pointer;font-weight:600">${dt.save || "Save"}</button>
      </div>
    `;

    c.querySelectorAll("[data-dist-key]").forEach(el => {
      const key  = el.dataset.distKey;
      const inst = el.dataset.distInst;
      el.addEventListener("change", () => {
        const val = el.type === "number" ? parseFloat(el.value) : el.value;
        if (inst) this._setDistInstVal(inst, key, val);
        else      this._setDistVal(key, val);
      });
    });
  }

  disconnectedCallback() {
    if (this._polling) { clearInterval(this._polling); this._polling = null; }
  }
}

customElements.define("solakon-panel", SolakonPanel);
