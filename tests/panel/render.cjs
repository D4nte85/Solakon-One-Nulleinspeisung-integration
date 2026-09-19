// Rendert das Panel mit den Mock-Daten aus index.html über eine feste Aktionsfolge und
// schreibt je Schritt das normalisierte Shadow-DOM:  node render.cjs <panel.js> <out.json> [textwurzel]
// Textwurzel: Verzeichnis, aus dem fetch Panel- und Entity-Texte lädt (Standard: Repo).
// Abgedeckt: 3 Szenarien × 2 Sprachen, alle Tabs, Eingaben, Speichern, Debug-Schalter,
// Verteilung, Wettläufe mit Instanzwechsel, Fehlerpfade. Poll-Timer und Toast-Timer sind
// abgeschaltet, WS-Antworten im Wettlauf laufen über eine Warteschlange — deterministisch.
const fs = require("fs"), path = require("path");
const { JSDOM } = require(__dirname + "/node_modules/jsdom");
const REPO = path.resolve(__dirname, "..", "..");
const DOMAIN = "solakon_nulleinspeisung";
const TEXTE = path.resolve(process.argv[4] || REPO);
const panelSrc = fs.readFileSync(process.argv[2], "utf8");
const html = fs.readFileSync(REPO + "/index.html", "utf8")
  .replace(/<script src="custom_components[^"]*"><\/script>/, () => `<script>${panelSrc}</script>`);
const tick = (ms = 0) => new Promise(r => setTimeout(r, ms));

function norm(root, win) {
  const live = [...root.querySelectorAll("input,select")];
  live.forEach(el => el.setAttribute("data-live", el.type === "checkbox" ? String(el.checked) : el.value));
  const clone = win.document.createElement("div");
  clone.innerHTML = root.innerHTML;
  live.forEach(el => el.removeAttribute("data-live"));
  const walk = n => {
    for (const ch of [...n.childNodes]) {
      if (ch.nodeType === 3) {
        if (ch.parentNode.nodeName === "STYLE") { ch.textContent = ch.textContent.replace(/\s+/g, " ").trim(); continue; }
        const t = ch.textContent.replace(/\s+/g, " ");
        if (!t.trim()) ch.remove(); else ch.textContent = t.trim();
      } else if (ch.nodeType === 1) {
        if (ch.hasAttribute("style")) ch.setAttribute("style", ch.style.cssText);
        const attrs = [...ch.attributes].map(a => [a.name, a.value]).sort();
        for (const [a] of attrs) ch.removeAttribute(a);
        for (const [a, v] of attrs) ch.setAttribute(a, v);
        walk(ch);
      }
    }
  };
  walk(clone);
  return clone.innerHTML.replace(/></g, ">\n<");
}

async function run(scenario, lang) {
  const shots = [];
  const dom = new JSDOM(html, {
    url: `http://localhost/?scenario=${scenario}&lang=${lang}`, runScripts: "dangerously", pretendToBeVisual: true,
    beforeParse(win) {
      win.Date.now = () => 1_800_000_000_000;
      win.setInterval = () => 0;
      const st = win.setTimeout.bind(win); win.setTimeout = (fn, ms, ...a) => ms === 3000 ? 0 : st(fn, ms, ...a);
      win.fetch = async (url) => {
        let rel = url.replace(/^\//, "");
        const f = path.join(TEXTE, rel);
        if (!fs.existsSync(f)) return { ok: false, status: 404, json: async () => ({}) };
        const txt = fs.readFileSync(f, "utf8");
        return { ok: true, status: 200, json: async () => JSON.parse(txt), text: async () => txt };
      };
    },
  });
  const win = dom.window;
  await tick(50);
  const p = win.document.getElementById("panel");
  const sr = p.shadowRoot;
  const settle = async () => { for (let i = 0; i < 5; i++) await tick(5); };
  const shot = async (name) => { await settle(); const tst = sr.getElementById("toast"); shots.push([`${scenario}/${lang}/${name}`, norm(sr, win)]); if (tst) tst.textContent = ""; };
  const poll = async () => { await p._loadStatus(); await settle(); };
  const fire = (el, type) => el && el.dispatchEvent(new win.Event(type, { bubbles: true }));
  const click = el => el && el.click();
  const instTabs = () => [...sr.querySelectorAll(".inst-tab")];
  await settle(); clearInterval(p._polling);
  // Validierungspunkt: je ein Zustand mit Text; fehlende Entity und "unavailable" liefert der Mock
  p._hass.states["sensor.panel_test_text"] = { state: "an", attributes: {} };
  await shot("start"); await poll(); await shot("start+poll");

  const tabRound = async (prefix) => {
    for (const tab of [...sr.querySelectorAll(".tab")]) {
      const id = tab.dataset.id;
      click(tab); await poll(); await shot(`${prefix}/tab-${id}`);
      if (id === "pi") {
        const inp = sr.querySelector('#content input[type="number"]');
        if (inp) { inp.value = "2.5"; fire(inp, "change"); await shot(`${prefix}/pi-dirty`); }
        click(sr.querySelector("#save-bar button")); await shot(`${prefix}/pi-saved`);
      }
      if (id === "surplus") {
        const cb = sr.querySelector('#content input[data-key="surplus_enabled"]');
        if (cb) { cb.checked = !cb.checked; fire(cb, "change"); await shot(`${prefix}/surplus-toggle`); }
      }
      if (id === "entities") {
        const inp = sr.querySelector("#content .entity-row input");
        if (inp) {
          for (const [wert, name] of [["sensor.solakon_one_leistung", "zahl"], ["sensor.panel_test_text", "text"],
                                      ["sensor.gibt_es_nicht", "fehlt"]]) {
            inp.value = wert; fire(inp, "input"); await shot(`${prefix}/entity-dot-${name}`);
          }
          inp.value = "sensor.solcast_prognose"; fire(inp, "input"); fire(inp, "change"); await shot(`${prefix}/entity-input`);
        }
      }
      if (id === "debug") {
        const btns = [...sr.querySelectorAll("#content button")];
        click(btns[1]); await shot(`${prefix}/debug-zone1`);
        click(btns[0]); await shot(`${prefix}/debug-reset`);
        const rc = sr.getElementById("dbg-rest-discharge");
        if (rc) { rc.checked = true; fire(rc, "change"); await shot(`${prefix}/debug-rest`); }
        await poll(); await shot(`${prefix}/debug-poll`);
      }
    }
    const reg = sr.querySelector("#reg-bar button, #reg-bar");
    if (reg) { click(reg); await poll(); await shot(`${prefix}/reg-toggle`); }
  };
  await tabRound("i0");

  let names = instTabs().map(t => t.textContent);
  for (const name of names) {
    const t = instTabs().find(x => x.textContent === name);
    if (!t) continue;
    click(t); await shot(`inst-${name}/vor-poll`); await poll(); await shot(`inst-${name}`);
    for (const sub of instTabs().map(x => x.textContent).filter(n => !names.includes(n))) {
      click(instTabs().find(x => x.textContent === sub)); await poll(); await shot(`inst-${name}/sub-${sub}`);
    }
    if (sr.querySelector('#content select[data-dist-key="distribution_mode"]')) {
      const sel = sr.querySelector('#content select[data-dist-key="distribution_mode"]');
      sel.value = "soc_switch"; fire(sel, "change"); await shot(`inst-${name}/dist-mode`);
      const cap = sr.querySelector('#content input[data-dist-key="capacity_sensor"]');
      if (cap) { cap.value = "sensor.solakon_one_batteriekapazitat"; fire(cap, "input"); await shot(`inst-${name}/dist-cap-input`); fire(cap, "change"); await shot(`inst-${name}/dist-cap-change`); }
      const g = sr.querySelector('#content input[data-dist-key="global_pv_forecast_today_sensor"]');
      if (g) { g.value = "sensor.solcast_prognose"; fire(g, "input"); await shot(`inst-${name}/dist-global-input`); }
      const btn = [...sr.querySelectorAll("#content button")].pop();
      click(btn); await shot(`inst-${name}/dist-saved`);
    }
  }
  const last = instTabs().filter(t => !t.textContent.includes(":")).pop();
  if (last && names.length) { click(last); await poll(); await tabRound("ilast"); }
  // Wettlauf: Antworten warten in einer Warteschlange, dazwischen Instanzwechsel
  const plain = instTabs().filter(t => !t.textContent.includes(":") && !t.textContent.includes("⚖") && t.textContent !== instTabs()[0].textContent);
  if (plain.length >= 2) {
    const realWS = p._hass.callWS.bind(p._hass);
    let pending = [];
    p._hass.callWS = (msg) => new Promise((res, rej) => pending.push(() => realWS(msg).then(res, rej)));
    const flush = async () => { for (let i = 0; i < 8; i++) { const q = pending; pending = []; q.forEach(f => f()); await settle(); } };
    const tabBtn = id => [...sr.querySelectorAll(".tab")].find(t => t.dataset.id === id);
    click(plain[1]); click(plain[0]); await flush(); await shot("race/load");
    click(tabBtn("pi")); await flush();
    const inp = sr.querySelector('#content input[type="number"]'); inp.value = "4"; fire(inp, "change");
    click(sr.querySelector("#save-bar button")); click(plain[1]); await flush(); await shot("race/save");
    click(sr.getElementById("reg-bar")); click(plain[0]); await flush(); await shot("race/reg");
    click(tabBtn("debug")); await flush();
    click([...sr.querySelectorAll("#content button")][1]); click(plain[1]); await flush();
    click(tabBtn("debug")); await flush(); await shot("race/cycle");
    p._loadStatus(); click(plain[0]); await flush(); await shot("race/poll");
    p._hass.callWS = realWS;
  }

  // Fehlerpfade: jeder WS-Aufruf schlägt fehl
  const okWS = p._hass.callWS;
  p._hass.callWS = () => Promise.reject(new Error("WS kaputt"));
  const dbg = [...sr.querySelectorAll(".tab")].find(t => t.dataset.id === "debug");
  if (dbg) {
    click(dbg); await shot("err/debug");
    const btns = [...sr.querySelectorAll("#content button")];
    click(btns[0]); await shot("err/reset"); click(btns[1]); await shot("err/zone1");
    const rc = sr.getElementById("dbg-rest-discharge");
    if (rc) { rc.checked = !rc.checked; fire(rc, "change"); await shot("err/rest"); }
  }
  click(sr.getElementById("reg-bar")); await shot("err/reg");
  const pi = [...sr.querySelectorAll(".tab")].find(t => t.dataset.id === "pi");
  if (pi) { click(pi); const inp = sr.querySelector('#content input[type="number"]'); inp.value = "3"; fire(inp, "change"); click(sr.querySelector("#save-bar button")); await shot("err/pi-save"); }
  // Abgewiesene Settings: Befunde als JSON im Fehlertext
  const kaputtWS = p._hass.callWS;
  p._hass.callWS = () => Promise.reject(Object.assign(new Error(JSON.stringify([
    { key: "hard_limit_z0", reason: "range", min: 100, max: 1200 },
    { key: "zone1_limit", reason: "integer", min: 0, max: 100 },
    { key: "soc_switch_divergence", reason: "range", min: 1, max: 50 },
    { key: "gibt_es_nicht", reason: "unknown", min: null, max: null }])), { code: "invalid_settings" }));
  if (pi) { click(sr.querySelector("#save-bar button")); await shot("err/pi-invalid"); }
  p._hass.callWS = kaputtWS;
  const dist = instTabs().find(t => t.textContent.includes("⚖"));
  if (dist) { click(dist); await settle(); const sel = sr.querySelector('#content select'); if (sel) { sel.value = "soc"; fire(sel, "change"); await settle(); click([...sr.querySelectorAll("#content button")].pop()); await shot("err/dist-save"); } }
  p._hass.callWS = okWS;
  win.close();
  return shots;
}

(async () => {
  const all = [];
  for (const sc of ["single", "single-group", "multi-group"]) for (const lang of ["de", "en"]) all.push(...await run(sc, lang));
  fs.writeFileSync(process.argv[3], JSON.stringify(all, null, 1));
  console.log(`${all.length} Schnappschüsse`);
  process.exit(0);
})().catch(e => { console.error(e); process.exit(2); });
