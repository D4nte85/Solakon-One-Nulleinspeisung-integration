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

const FALL_LABELS = {
  "0A": "Zone 0: Überschuss Start",
  "0B": "Zone 0: Überschuss Ende",
  "A":  "Zone 1: Entladezyklus Start",
  "B":  "Zone 3: Stopp (Zyklus aktiv)",
  "C":  "Zone 3: Stopp",
  "D":  "Recovery: Modus wiederhergestellt",
  "E":  "Zone 2: Regelung aktiv",
  "F":  "Nacht: Abschaltung",
  "G":  "AC Laden: Start",
  "H":  "AC Laden: Ende",
  "I":  "Safety: Modus-Korrektur",
  "GT": "Tarif-Laden: Start",
  "HT": "Tarif-Laden: Ende",
  "TM": "Discharge-Lock: Preis zu hoch",
};

const TABS = [
  { id: "status",     label: "Status",      icon: "📊" },
  { id: "pi",         label: "PI-Regler",   icon: "🎛️" },
  { id: "zones",      label: "Zonen",       icon: "🔋" },
  { id: "surplus",    label: "Überschuss",  icon: "☀️" },
  { id: "ac",         label: "AC Laden",    icon: "⚡" },
  { id: "tariff",     label: "Tarif",       icon: "💹" },
  { id: "dynoff",     label: "Dyn. Offset", icon: "📈" },
  { id: "night",      label: "Nacht",       icon: "🌙" },
  { id: "debug",      label: "Debug",       icon: "🔧" },
];

const TAB_DOCS = {
  pi: {
    summary: "PI-Regler — Kern des Regelkreises",
    text: "Regelgröße: Netzleistung (positiv = Bezug, negativ = Einspeisung). Stellgröße: AC-Ausgangsleistung des Wechselrichters.\n\nP-Anteil: reagiert sofort auf die aktuelle Abweichung (Grid − Offset).\nI-Anteil: summiert Abweichungen über die Zeit auf, eliminiert bleibende Regelabweichungen.\nAnti-Windup: Integral auf ±1000 begrenzt.\nIntegral-Reset: bei jedem Zonenwechsel auf 0.\nToleranz-Decay: −5 %/Zyklus wenn Fehler ≤ Totband und |Integral| > 10.\nZone 0: Integral eingefroren, kein PI-Aufruf.\n\nFehlerberechnung modusabhängig:\n• Normal: raw_error = Grid − Offset\n• AC Laden: raw_error = Offset − Grid (invertiert)\n\nSelf-Adjusting Wait: Nach einem Stelleingriff wird auf die tatsächliche WR-Ausgangsleistung gewartet statt einer fixen Pause. Sobald actual_power den Sollwert ±Toleranz erreicht, geht der Regler weiter. Die konfigurierte Wartezeit wirkt als maximales Timeout.\n\nEinstieg: P = 0.5, I = 0. P schrittweise erhöhen bis Output zu pendeln beginnt, dann einen Schritt zurück. I erst einführen wenn P-Regelung stabil ist.",
  },
  zones: {
    summary: "SOC-Zonenlogik — Verhalten abhängig vom Batterieladestand",
    text: "Zone 0 (Überschuss, optional): SOC ≥ Export-Schwelle UND PV-Überschuss → Output auf Hard Limit. Entladestrom 2 A. PI-Integral eingefroren.\n\nZone 1 (aggressiv): SOC > Zone-1-Schwelle → hoher Entladestrom, Offset 1. Läuft durch bis SOC ≤ Zone-3-Schwelle — kein Yo-Yo-Effekt.\n\nZone 2 (schonend): Zone-3 < SOC ≤ Zone-1 → 0 A Entladestrom, dynamisches Output-Limit (max PV − Reserve), Offset 2.\n\nZone 3 (Sicherheitsstopp): SOC ≤ Zone-3-Schwelle → Output 0 W, Modus Disabled. AC Laden bleibt trotzdem möglich.",
  },
  surplus: {
    summary: "Überschuss-Einspeisung — Zone 0 aktivieren",
    text: "Höchste Priorität — blockiert Tarif-Laden, Discharge-Lock und AC Laden solange Zone 0 aktiv.\n\nNormaler Eintritt: SOC ≥ SOC-Schwelle UND (PV > Output + Grid + PV-Hysterese ODER PV = 0 ODER Output = 0).\nForecast-Eintritt: Vorhersage ≥ Schwelle UND PV > Hard Limit (kein SOC-Gate).\n\nAustritt (nur ohne Forecast): SOC < (Schwelle − SOC-Hysterese) ODER PV ≤ Output + Grid − PV-Hysterese (wenn PV ≠ 0 und Output ≠ 0).\nBei aktivem Forecast: Exit komplett blockiert — nur Zone 3 (Safety) beendet Surplus. Sobald Forecast-Sensor unter Schwelle fällt, greift die normale Exit-Logik.\n\nOutput wird auf Hard Limit gesetzt. Integral eingefroren (kein PI-Aufruf).",
  },
  ac: {
    summary: "AC Laden — Netz lädt die Batterie",
    text: "Eintritt (Fall G): SOC < Ladeziel UND kein Überschuss aktiv UND kein AC/Tarif-Laden aktiv UND Modus ≠ '3' UND (Grid + Output) < −Hysterese.\nAbbruch (Fall H): Modus = '3' UND ac_charge_active UND kein Tarif-Laden UND (SOC ≥ Ladeziel ODER (Grid ≥ Offset + Hysterese UND Output = 0 W)).\n\nPI-Regler läuft invertiert — Positiver Fehler → Ladeleistung erhöhen.\nat_max/at_min-Guards entfallen — Fall I übernimmt die Safety-Funktion.\n\nRückkehr: Zone 1 → Timer-Toggle + Modus '1'. Zone 2 → Output 0 W + Modus '0'. Integral = 0.\n\nSOC-Schutz (Zone 3) bleibt vollständig aktiv.\n\nWegen der Hardware-Flanke des Solakon ONE (~25 s von Min auf Max) P-Faktor klein halten. Der I-Anteil macht die eigentliche Regelarbeit.\n\nPriorität: AC Laden startet nicht wenn Überschuss-Einspeisung (Zone 0) aktiv ist. AC Laden und Tarif-Laden blockieren sich gegenseitig über den Modus-Guard (Modus ≠ '3').",
  },
  tariff: {
    summary: "Tarif-Arbitrage (Tibber, aWATTar …) — drei Preisstufen",
    text: "Günstig (Preis < Günstig-Schwelle): Tarif-Laden startet — feste Ladeleistung bis SOC-Ziel. Kein PI-Regler.\nMittel (Günstig ≤ Preis < Teuer-Schwelle): Discharge-Lock — Zone 1 und Zone 2 gesperrt (Output 0 W, Modus Disabled). Sobald der Preis die Teuer-Schwelle überschreitet, wird der Betrieb automatisch wiederhergestellt.\nTeuer (Preis ≥ Teuer-Schwelle): normale SOC-Logik, keine Einschränkung.\n\nTarif-Laden und AC-Laden sind voneinander unabhängige Module und blockieren sich gegenseitig über den Modus-Guard.\n\nPriorität: Tarif-Laden und Discharge-Lock werden blockiert solange Überschuss-Einspeisung (Zone 0) aktiv ist.\n\nErfordert Preis-Sensor mit numerischem Wert in ct/kWh.",
  },
  dynoff: {
    summary: "Dynamischer Offset — automatisch aus Netz-Volatilität berechnet",
    text: "Berechnet den Nullpunkt-Offset aus der Standardabweichung der Netzleistung über das konfigurierte Zeitfenster.\n\nFormel: offset = clamp(min + max(0, (StdDev − Rausch) × Faktor), min, max)\n\nBeispiel (min=30, noise=15, factor=1.5):\n• StdDev 5 W → 30 W (Minimum)\n• StdDev 30 W → 53 W\n• StdDev 80 W → 128 W\n• StdDev 160 W → 228 W\n• StdDev 250 W+ → 250 W (Maximum)\n\nJede Zone (Zone 1, Zone 2, Zone AC) ist einzeln aktivierbar und überschreibt den statischen Offset der jeweiligen Zone.\n\nDer StdDev-Sensor wird intern berechnet — kein externer Statistik-Sensor erforderlich.",
  },
  night: {
    summary: "Nachtabschaltung — Zone 2 bei PV < PV-Ladereserve deaktivieren",
    text: "Betrifft ausschließlich Zone 2 (Fall F): Modus → Disabled, Output 0 W, Integral-Reset.\nZone 1 und AC Laden laufen auch nachts weiter.\n\nSchwelle: PV-Ladereserve aus den Zonen-Einstellungen — kein separater Parameter.\n\nReaktivierung: Sobald PV wieder über die PV-Ladereserve steigt, greift Fall E (Integral-Reset, Timer-Toggle, Modus → '1') — sofern kein Tarif-Lock aktiv ist.",
  },
  debug: {
    summary: "Debug — manuelle Eingriffe in den Regelzustand",
    text: "Integral zurücksetzen: Setzt den I-Anteil des PI-Reglers auf 0.\n\nZone manuell setzen: Schaltet den internen cycle_active-Flag und setzt das Integral zurück.\n• Zone 1 aktivieren: cycle_active = true → aggressiver Entladebetrieb, voller Entladestrom.\n• Zone 2 aktivieren: cycle_active = false → batterieschonender Betrieb, 0 A Entladestrom, dynamisches Output-Limit.\n\nAlle Aktionen werden unter 'Letzte Aktion' im Status-Tab protokolliert.",
  },
};

const TAB_LAYOUT = {
  pi: {
    cols: [
      {
        title: "Regelparameter", icon: "🎛️", color: "#0891b2",
        fields: [
          { k: "p_factor",  l: "P-Faktor (Proportional)", d: "Reagiert sofort auf die aktuelle Abweichung (Grid − Offset). Höher = aggressiver. Zu groß: Output pendelt dauerhaft. Typisch nach Einstellung: 0.8–1.5", t: "num", min: 0.1, max: 5, step: 0.1 },
          { k: "i_factor",  l: "I-Faktor (Integral)",     d: "Summiert Abweichungen über die Zeit auf, eliminiert bleibende Regelabweichungen. Anti-Windup auf ±1000 begrenzt. Startwert: 0 — erst erhöhen wenn P-Regelung stabil ist. Typisch: 0.03–0.08", t: "num", min: 0, max: 0.5, step: 0.01 },
          { k: "tolerance", l: "Toleranzbereich / Totband (W)", d: "Abweichungen innerhalb dieses Bereichs lösen keinen PI-Eingriff aus. Stattdessen greift der Integral-Decay (−5 %/Zyklus wenn |Integral| > 10).", t: "num", min: 0, max: 200, step: 1 },
          { k: "wait_time", l: "Wartezeit / Max-Timeout (s)", d: "Kompensiert Hardware-Flanke + Sensor-Polling-Latenz nach einem Stelleingriff. Ohne Self-Adjust: feste Pause. Mit Self-Adjust: maximales Timeout als Sicherheitsnetz.", t: "num", min: 0, max: 30, step: 1 },
        ],
      },
      {
        title: "Self-Adjusting Wait", icon: "🎯", color: "#7c3aed",
        fields: [
          { k: "self_adjust_enabled",   l: "Self-Adjusting Wait aktivieren", d: "Wartet nach jedem Stelleingriff auf die tatsächliche WR-Ausgangsleistung. Sobald actual_power den Sollwert ±Toleranz erreicht, geht der Regler weiter. Die Wartezeit wirkt als maximales Timeout.", t: "bool" },
          { k: "self_adjust_tolerance", l: "Zielwert-Toleranz (W)", d: "Abweichung zwischen actual_power und Sollwert in Watt, ab der der Zielwert als erreicht gilt und die Wartezeit endet. Typisch: 2–5 W.", t: "num", min: 1, max: 50, step: 1 },
        ],
      },
    ],
  },

  zones: {
    cols: [
      {
        title: "SOC-Grenzen", icon: "🔋", color: "#0891b2",
        fields: [
          { k: "zone1_limit", l: "Zone 1 SOC-Schwelle (%)", d: "SOC überschreitet diesen Wert → Zone 1 startet. Zone 1 läuft durch bis SOC ≤ Zone-3-Schwelle — kein Yo-Yo-Effekt. Auch nachts aktiv.", t: "num", min: 1, max: 99, step: 1 },
          { k: "zone3_limit", l: "Zone 3 SOC-Schwelle (%)", d: "SOC unterschreitet diesen Wert → Zone 3 (Sicherheitsstopp): Output 0 W, Modus Disabled. Muss kleiner als Zone-1-Schwelle sein. AC Laden bleibt trotz Zone 3 möglich.", t: "num", min: 1, max: 49, step: 1 },
          { k: "pv_reserve",  l: "PV-Ladereserve (W)", d: "Zone-2-Output-Limit: max(0, PV − Reserve). Gleichzeitig Schwelle für Nachtabschaltung: Zone 2 deaktiviert wenn PV < Reserve.", t: "num", min: 0, max: 500, step: 10 },
        ],
      },
      {
        title: "Leistungsgrenzen", icon: "⚙️", color: "#b45309",
        fields: [
          { k: "hard_limit",    l: "Hard Limit (W)", d: "Absolute Ausgangsleistungs-Obergrenze in Zone 0 und Zone 1. Der at_max_limit-Guard greift nur an dieser Grenze, nicht am dynamischen Zone-2-Limit.", t: "num", min: 100, max: 2000, step: 50 },
          { k: "discharge_max", l: "Max. Entladestrom Zone 1 (A)", d: "Entladestrom in Zone 1. Zone 2 und AC Laden setzen automatisch 0 A. Surplus setzt 2 A.", t: "num", min: 1, max: 100, step: 1 },
        ],
      },
      {
        title: "Offsets", icon: "🎯", color: "#7c3aed",
        fields: [
          { k: "offset_1", l: "Offset Zone 1 (W)", d: "Regelziel in Zone 1. Positiv = Regler hält leichten Netzbezug als Sicherheitspuffer. Negativ = Regler speist leicht ein. Wird überschrieben wenn Dyn. Offset für Zone 1 aktiv ist.", t: "num", min: -200, max: 300, step: 1 },
          { k: "offset_2", l: "Offset Zone 2 (W)", d: "Regelziel in Zone 2. Empfohlen: etwas größer als Zone-1-Offset (stärkerer Bezugspuffer wenn Batterie schonend entladen wird). Wird überschrieben wenn Dyn. Offset für Zone 2 aktiv ist.", t: "num", min: -200, max: 300, step: 1 },
        ],
      },
    ],
  },

  surplus: {
    top: [
      { k: "surplus_enabled", l: "Überschuss-Einspeisung aktivieren", d: "Höchste Priorität — blockiert Tarif-Laden, Discharge-Lock und AC Laden solange Zone 0 aktiv. Normal: SOC ≥ Schwelle + PV-Überschuss. Mit Forecast: PV > Hard Limit genügt (kein SOC-Gate), Exit blockiert bis Forecast wegfällt.", t: "bool" },
    ],
    enabledKey: "surplus_enabled",
    cols: [
      {
        title: "SOC-Bedingung", icon: "🔋", color: "#0891b2",
        fields: [
          { k: "surplus_soc_threshold", l: "SOC-Schwelle (%)",  d: "Zone 0 startet erst ab diesem SOC. Empfohlen: > Zone-1-Schwelle. Typisch: 90–98 %.", t: "num", min: 50, max: 100, step: 1 },
          { k: "surplus_soc_hyst",      l: "SOC-Hysterese (%)", d: "Austritt erst wenn SOC < (Schwelle − Hysterese). Verhindert Flackern nahe der Schwelle. Typisch: 3–5 %.", t: "num", min: 1, max: 20, step: 1 },
        ],
      },
      {
        title: "PV-Bedingung", icon: "☀️", color: "#f59e0b",
        fields: [
          { k: "surplus_pv_hyst", l: "PV-Hysterese (W)", d: "Eintritt: PV > Output + Grid + Hysterese. Austritt: PV ≤ Output + Grid − Hysterese.", t: "num", min: 10, max: 200, step: 10 },
        ],
      },
      {
      title: "PV-Vorhersage", icon: "🌤️", color: "#65a30d",
      fields: [
        { k: "surplus_forecast_enabled",   l: "Forecast-Erzwingung aktivieren",  d: "Wenn Vorhersage ≥ Schwelle: Surplus startet sobald PV > Hard Limit (kein SOC-Gate). Exit komplett blockiert — nur Zone 3 (Safety) beendet Surplus. Abends fällt der Forecast-Sensor unter die Schwelle → normale Exit-Logik greift sofort.", t: "bool" },
        { k: "surplus_forecast_sensor",    l: "Vorhersage-Sensor",           d: "Sensor mit dem prognostizierten PV-Ertrag (z. B. Forecast.Solar, Solcast). Einheit muss zur Schwelle passen (z. B. kWh).", t: "entity" },
        { k: "surplus_forecast_threshold", l: "Mindest-Ertrag für Surplus",  d: "PV > Hard Limit + Forecast ≥ Schwelle → Surplus startet ohne SOC-Bedingung und bleibt aktiv bis Forecast unter Schwelle fällt.", t: "num", min: 0, max: 100, step: 0.5 },
      ],
    },
    ],
  },

  ac: {
    top: [
      { k: "ac_enabled", l: "AC Laden aktivieren", d: "Eintritt (Fall G): SOC < Ladeziel UND kein Überschuss aktiv UND kein AC/Tarif-Laden UND Modus ≠ '3' UND (Grid + Output) < −Hysterese. Abbruch (Fall H): Modus = '3' UND ac_charge_active UND kein Tarif-Laden UND (SOC ≥ Ladeziel ODER (Grid ≥ Offset + Hysterese UND Output = 0 W)). SOC-Schutz (Zone 3) bleibt vollständig aktiv. Startet nicht wenn Überschuss-Einspeisung (Zone 0) oder Tarif-Laden aktiv ist.", t: "bool" },
    ],
    enabledKey: "ac_enabled",
    cols: [
      {
        title: "Eintritt & Grenzen", icon: "⚡", color: "#7c3aed",
        fields: [
          { k: "ac_soc_target",  l: "Ladeziel SOC (%)", d: "Laden stoppt wenn SOC diesen Wert erreicht. Empfohlen: > Zone-1-Schwelle — so übernimmt Zone 1 direkt nach dem Laden und fährt Nulleinspeisung.", t: "num", min: 50, max: 100, step: 1 },
          { k: "ac_power_limit", l: "Max. Ladeleistung (W)", d: "Absolute Obergrenze der AC-Ladeleistung. Wird als max_power an den PI-Regler übergeben.", t: "num", min: 100, max: 2000, step: 50 },
          { k: "ac_hysteresis",  l: "Eintritts-Hysterese (W)", d: "Eintritt: (Grid + Output) < −Hysterese. Austritt: Grid ≥ (Offset + Hysterese) UND Output = 0 W. Der Output = 0 W-Guard verhindert Fehlauslösung während der PI noch regelt.", t: "num", min: 10, max: 500, step: 10 },
          { k: "ac_offset",      l: "Regel-Offset (W)", d: "Regelziel für die Netzleistung im AC-Lade-Modus. Negativ = Einspeisung angestrebt → PI erhöht Ladeleistung. Wird überschrieben wenn Dyn. Offset für Zone AC aktiv ist.", t: "num", min: -500, max: 200, step: 5 },
        ],
      },
      {
        title: "PI-Parameter", icon: "🎛️", color: "#0891b2",
        fields: [
          { k: "ac_p_factor", l: "AC P-Faktor", d: "Proportional-Verstärkung im AC-Lade-Modus. Wegen der Hardware-Flanke des Solakon ONE (~25 s von Min auf Max) klein halten (~0.3–0.5). Startwert: 0.3.", t: "num", min: 0.1, max: 3, step: 0.1 },
          { k: "ac_i_factor", l: "AC I-Faktor", d: "Integral-Verstärkung im AC-Lade-Modus. Startwert: 0 — erst erhöhen wenn P allein eine bleibende Regelabweichung hinterlässt. Typisch: 0.05–0.1. Der I-Anteil macht die eigentliche Regelarbeit.", t: "num", min: 0, max: 0.5, step: 0.01 },
        ],
      },
    ],
  },

  tariff: {
    top: [
      { k: "tariff_enabled",      l: "Tarif-Steuerung aktivieren", d: "Günstig (< Günstig-Schwelle): Tarif-Laden. Mittel (dazwischen): Discharge-Lock — Zone 1 und Zone 2 gesperrt. Teuer (≥ Teuer-Schwelle): normale SOC-Logik. Wird blockiert solange Überschuss-Einspeisung (Zone 0) aktiv ist. Unabhängig vom AC-Laden-Modul.", t: "bool" },
      { k: "tariff_price_sensor", l: "Preis-Sensor", d: "Sensor-Entität mit aktuellem Strompreis als numerischem Wert in ct/kWh.", t: "entity", domain: "sensor" },
    ],
    enabledKey: "tariff_enabled",
    cols: [
      {
        title: "Preisschwellen", icon: "💹", color: "#0891b2",
        fields: [
          { k: "tariff_cheap_threshold", l: "Günstig-Schwelle (ct/kWh)", d: "Tarif-Laden startet wenn Preis diese Schwelle unterschreitet UND SOC < Ladeziel. Auch untere Grenze des Discharge-Locks.", t: "num", min: 0, max: 100, step: 0.5 },
          { k: "tariff_cheap_entity",    l: "Günstig-Schwelle dynamisch", d: "Optionale input_number-Entität. Wenn gesetzt und verfügbar, überschreibt sie den statischen Wert.", t: "entity", domain: "input_number" },
          { k: "tariff_exp_threshold",   l: "Teuer-Schwelle (ct/kWh)", d: "Über dieser Schwelle: normale SOC-Logik, Discharge-Lock hebt sich. Dazwischen (Günstig ≤ Preis < Teuer): Discharge-Lock Zone 1 und Zone 2. Muss größer als Günstig-Schwelle sein.", t: "num", min: 0, max: 100, step: 0.5 },
          { k: "tariff_exp_entity",      l: "Teuer-Schwelle dynamisch", d: "Optionale input_number-Entität. Wenn gesetzt und verfügbar, überschreibt sie den statischen Wert.", t: "entity", domain: "input_number" },
        ],
      },
      {
        title: "Laden", icon: "🔋", color: "#16a34a",
        fields: [
          { k: "tariff_soc_target", l: "Ladeziel SOC (%)", d: "Tarif-Laden stoppt wenn dieser SOC erreicht wird. Unabhängig vom SOC-Ladeziel des AC-Lade-Moduls.", t: "num", min: 50, max: 100, step: 1 },
          { k: "tariff_power",      l: "Ladeleistung (W)", d: "Feste Ladeleistung während Tarif-Laden — kein PI-Regler, keine dynamische Anpassung.", t: "num", min: 100, max: 2000, step: 50 },
        ],
      },
      {
        title: "PV-Vorhersage", icon: "☀️", color: "#f59e0b",
        fields: [
          { k: "pv_forecast_enabled",   l: "PV-Vorhersage aktivieren", d: "Wenn aktiv und der Vorhersage-Sensor einen Wert ≥ Schwelle meldet, wird Tarif-Laden und Discharge-Lock unterdrückt. Automatische Flexibilität für gute Wetterlagen.", t: "bool" },
          { k: "pv_forecast_sensor",    l: "Vorhersage-Sensor", d: "input_number- oder sensor-Entität mit einem kWh-Wert (z.B. erwartete Solarproduktion heute). Kann von einer Wetter-Integration oder einem Solcast-Account kommen.", t: "entity" },
          { k: "pv_forecast_threshold", l: "Schwellwert (kWh)", d: "Wenn Vorhersage ≥ diesem Wert, gilt: Tarif-Laden und Discharge-Lock sind gesperrt, normale Nulleinspeisung läuft weiter.", t: "num", min: 0, max: 50, step: 0.5 },
        ],
      },
    ],
  },

  dynoff: {
    top: [
      { k: "stddev_window", l: "Stabw.-Fenster (s)", d: "Zeitfenster für die Standardabweichungs-Berechnung. Gilt für alle Zonen.", t: "num", min: 30, max: 300, step: 10 },
    ],
    cols: [
      {
        title: "Zone 1", icon: "⚡", color: "#16a34a",
        fields: [
          { k: "dyn_z1_enabled",  l: "Aktivieren", d: "Berechnet den Offset dynamisch aus der Netz-StdDev statt des statischen Werts. Überschreibt den statischen Zone-1-Offset.", t: "bool" },
          { k: "dyn_z1_min",      l: "Min. Offset (W)", d: "Grundpuffer bei ruhigem Netz (StdDev ≤ Rausch-Schwelle). Offset sinkt nie unter diesen Wert.", t: "num", min: 0, max: 500, step: 1 },
          { k: "dyn_z1_max",      l: "Max. Offset (W)", d: "Obergrenze des Offsets. Offset steigt nie über diesen Wert, auch bei sehr hoher StdDev.", t: "num", min: 50, max: 1000, step: 10 },
          { k: "dyn_z1_noise",    l: "Rausch-Schwelle (W)", d: "StdDev unterhalb dieser Schwelle wird als Messrauschen gewertet und löst keinen Offset-Anstieg aus.", t: "num", min: 0, max: 100, step: 1 },
          { k: "dyn_z1_factor",   l: "Volatilitäts-Faktor", d: "Verstärkung oberhalb der Rausch-Schwelle. Formel: buffer = (StdDev − Rausch) × Faktor.", t: "num", min: 0.5, max: 5, step: 0.1 },
          { k: "dyn_z1_negative", l: "Negativer Offset", d: "Negiert den berechneten Offset (× −1). Das Regelziel liegt dann unterhalb von 0 W.", t: "bool" },
        ],
      },
      {
        title: "Zone 2", icon: "🔋", color: "#0891b2",
        fields: [
          { k: "dyn_z2_enabled",  l: "Aktivieren", d: "Berechnet den Offset dynamisch aus der Netz-StdDev statt des statischen Werts. Überschreibt den statischen Zone-2-Offset.", t: "bool" },
          { k: "dyn_z2_min",      l: "Min. Offset (W)", d: "Grundpuffer bei ruhigem Netz (StdDev ≤ Rausch-Schwelle). Offset sinkt nie unter diesen Wert.", t: "num", min: 0, max: 500, step: 1 },
          { k: "dyn_z2_max",      l: "Max. Offset (W)", d: "Obergrenze des Offsets. Offset steigt nie über diesen Wert, auch bei sehr hoher StdDev.", t: "num", min: 50, max: 1000, step: 10 },
          { k: "dyn_z2_noise",    l: "Rausch-Schwelle (W)", d: "StdDev unterhalb dieser Schwelle wird als Messrauschen gewertet und löst keinen Offset-Anstieg aus.", t: "num", min: 0, max: 100, step: 1 },
          { k: "dyn_z2_factor",   l: "Volatilitäts-Faktor", d: "Verstärkung oberhalb der Rausch-Schwelle. Formel: buffer = (StdDev − Rausch) × Faktor.", t: "num", min: 0.5, max: 5, step: 0.1 },
          { k: "dyn_z2_negative", l: "Negativer Offset", d: "Negiert den berechneten Offset (× −1). Das Regelziel liegt dann unterhalb von 0 W.", t: "bool" },
        ],
      },
      {
        title: "Zone AC Laden", icon: "⚡", color: "#7c3aed",
        fields: [
          { k: "dyn_ac_enabled",  l: "Aktivieren", d: "Berechnet den AC-Lade-Offset dynamisch aus der Netz-StdDev statt des statischen Werts. Überschreibt den statischen AC-Offset.", t: "bool" },
          { k: "dyn_ac_min",      l: "Min. Offset (W)", d: "Grundpuffer bei ruhigem Netz (StdDev ≤ Rausch-Schwelle). Offset sinkt nie unter diesen Wert.", t: "num", min: 0, max: 500, step: 1 },
          { k: "dyn_ac_max",      l: "Max. Offset (W)", d: "Obergrenze des Offsets. Offset steigt nie über diesen Wert, auch bei sehr hoher StdDev.", t: "num", min: 50, max: 1000, step: 10 },
          { k: "dyn_ac_noise",    l: "Rausch-Schwelle (W)", d: "StdDev unterhalb dieser Schwelle wird als Messrauschen gewertet und löst keinen Offset-Anstieg aus.", t: "num", min: 0, max: 100, step: 1 },
          { k: "dyn_ac_factor",   l: "Volatilitäts-Faktor", d: "Verstärkung oberhalb der Rausch-Schwelle. Formel: buffer = (StdDev − Rausch) × Faktor.", t: "num", min: 0.5, max: 5, step: 0.1 },
          { k: "dyn_ac_negative", l: "Negativer Offset", d: "Negiert den berechneten Offset (× −1). Das Regelziel liegt dann unterhalb von 0 W.", t: "bool" },
        ],
      },
    ],
  },

  night: {
    top: [
      { k: "night_enabled", l: "Nachtabschaltung aktivieren", d: "Zone 2 bei PV < PV-Ladereserve deaktivieren. Zone 1 und AC Laden laufen weiter. Zone 2 wird nicht reaktiviert solange ein Tarif-Lock (mittlerer/günstiger Preis) aktiv ist.", t: "bool" },
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
    // Multi-Instance
    this._instances      = [];    // [{entry_id, instance_name}]
    this._activeInstance = null;  // entry_id oder "__overview__"
    this._allStatuses    = {};    // entry_id → status (für Übersicht)
    this._distConfig     = {};    // globale Verteilungskonfiguration
    this._distDirty      = {};    // ungespeicherte Änderungen Verteilung
  }

  set panel(val) {
    this._panel = val;
    if (val?.config?.entry_id) { this._entryId = val.config.entry_id; }
    if (val?.config !== undefined)  { this._checkInit(); }
  }

  set hass(val) { this._hass = val; this._checkInit(); }

  _checkInit() {
    if (this._hass && !this._initialized) {
      this._initialized = true;
      this._build();
      this._loadInstances();
      this._polling = setInterval(() => this._loadStatus(), 1000);
    }
  }

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

    mkTab("__overview__", "📊 Übersicht");
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
    const html = this._instances.map(inst => {
      const st = this._allStatuses[inst.entry_id] || {};
      const z  = ZONE_CFG[st.zone] ?? ZONE_CFG[2];
      const fl = FALL_LABELS[st.active_fall] || st.active_fall || "—";
      return `<div class="ov-card" data-eid="${inst.entry_id}">
        <div class="ov-hdr" style="background:${z.color}">${z.icon} ${inst.instance_name}</div>
        <div class="ov-body">
          <div class="ov-row"><span>SOC</span><strong>${st.soc ?? "—"} %</strong></div>
          <div class="ov-row"><span>Ausgang</span><strong>${st.actual_power != null ? st.actual_power + " W" : "—"}</strong></div>
          <div class="ov-row"><span>Netz</span><strong>${st.grid != null ? st.grid.toFixed(0) + " W" : "—"}</strong></div>
          <div class="ov-row"><span>Fall</span><strong>${fl}</strong></div>
        </div>
      </div>`;
    }).join("");
    c.innerHTML = `<div class="ov-grid">${html}</div>`;
    c.querySelectorAll(".ov-card").forEach(card => {
      card.addEventListener("click", () => this._switchInstance(card.dataset.eid));
    });

    // Verteilung als zweiter Block
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
          ? "Zone 1 (Zyklus aktiv)" : "Zone 2";
      }
      this._updateRegBanner();
    } catch (e) { /* ignore polling errors */ }
  }

  // ── Build ─────────────────────────────────────────────────────────────────

  _build() {
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
                <p>Optionale Module: <strong>☀️ Überschuss</strong>, <strong>⚡ AC-Laden</strong>, <strong>💹 Tarif-Arbitrage</strong>, <strong>📈 Dynamischer Offset</strong> (pro Zone einzeln), <strong>🌙 Nachtabschaltung</strong>. Alle Parameter werden persistent hier im Panel gespeichert — kein YAML, keine Helfer-Entitäten.</p>
                <p><strong>Priorität und gegenseitige Blockierung der optionalen Module:</strong></p>
                <table class="prio-table">
                  <tr><th>Priorität</th><th>Modul</th><th>Blockiert</th></tr>
                  <tr><td>1 (höchste)</td><td>☀️ Überschuss (Zone 0)</td><td>Tarif-Laden (GT), Discharge-Lock (TM), AC Laden (G)</td></tr>
                  <tr><td>2</td><td>💹 Tarif-Laden (günstig)</td><td>AC Laden (via Modus '3'), Discharge-Lock</td></tr>
                  <tr><td>3</td><td>💹 Discharge-Lock (mittel)</td><td>Zone-1/2-Recovery (D), Zone-2-Start (E)</td></tr>
                  <tr><td>4</td><td>⚡ AC Laden</td><td>Tarif-Laden (via Modus '3'), Discharge-Lock</td></tr>
                  <tr><td>5</td><td>🌙 Nachtabschaltung</td><td>Zone-2-Start (E)</td></tr>
                  <tr><td>6 (niedrigste)</td><td>Zone 1 / Zone 2</td><td>—</td></tr>
                </table>
                <p style="margin-top:4px">AC Laden und Tarif-Laden blockieren sich gegenseitig über den Modus-Guard (Modus ≠ '3'). Überschuss-Einspeisung hat absoluten Vorrang — kein anderes optionales Modul kann während Zone 0 starten.</p>
              </div>
            </details>
          </div>
        </div>

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
      this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }));
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
              <div class="mode-lbl">Aktiver Fall</div>
              <div class="mode-val" id="st-active-fall">—</div>
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
    const fl = this.shadowRoot.getElementById("st-flags");
    if (fl) fl.innerHTML = [
      ["Zyklus",      st.cycle_active],
      ["Surplus",     st.surplus_active],
      ["AC Laden",    st.ac_charge],
      ["Tarif-Laden", st.tariff_charge],
      ["Nacht",       st.is_night],
      ["PV→Tarif",    st.forecast_tariff_suppressed],
      ["PV→Surplus",  st.forecast_surplus_forced],
    ].map(([n, v]) => `<span class="flag ${v ? "on" : "off"}">${v ? "●" : "○"} ${n}</span>`).join("");

    set("st-active-fall", FALL_LABELS[st.active_fall] || st.active_fall || "—");
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
    set("st-error",        st.last_error  || "Keine");

    let offsetLabel, offsetActive, isDyn, offsetStatic;
    if (st.ac_charge) {
      offsetLabel  = "Zone AC Laden";
      isDyn        = !!st.dyn_ac_enabled;
      offsetStatic = this._settings.ac_offset ?? "—";
      offsetActive = isDyn ? (st.dyn_ac ?? 0).toFixed(0) : offsetStatic;
    } else if (st.cycle_active) {
      offsetLabel  = "Zone 1";
      isDyn        = !!st.dyn_z1_enabled;
      offsetStatic = this._settings.offset_1 ?? "—";
      offsetActive = isDyn ? (st.dyn_z1 ?? 0).toFixed(0) : offsetStatic;
    } else {
      offsetLabel  = "Zone 2";
      isDyn        = !!st.dyn_z2_enabled;
      offsetStatic = this._settings.offset_2 ?? "—";
      offsetActive = isDyn ? (st.dyn_z2 ?? 0).toFixed(0) : offsetStatic;
    }
    set("st-offset-val", `${offsetActive} W`);
    set("st-offset-lbl", `Aktiver Offset — ${offsetLabel}`);
    const srcEl = this.shadowRoot.getElementById("st-offset-src");
    if (srcEl) srcEl.innerHTML = isDyn
      ? `<span class="offset-src-tag active">⚡ dynamisch</span><span class="offset-src-tag inactive">statisch: ${offsetStatic} W</span>`
      : `<span class="offset-src-tag inactive">dyn. inaktiv</span><span class="offset-src-tag active">statisch: ${offsetStatic} W</span>`;
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
      if (el) el.textContent = this._status.cycle_active
        ? "Zone 1 (Zyklus aktiv)" : "Zone 2";
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
    try {
      await this._hass.callWS({ type: `${DOMAIN}/save_distribution_config`, distribution: merged });
      this._distConfig = merged;
      this._distDirty  = {};
      this._showToast("✅ Verteilung gespeichert");
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
    if (this._instances.length <= 1) {
      c.innerHTML = `<p style="font-size:.88em;color:var(--secondary-text-color,#888);padding:12px 0">
        Leistungsverteilung wird nur bei mehreren Instanzen benötigt.</p>`;
      return;
    }

    const distLoaded = Object.keys(this._distConfig).length > 0 || Object.keys(this._distDirty).length > 0;
    if (!distLoaded) {
      this._loadDistConfig().then(() => this._renderActiveTab());
      c.innerHTML = `<p style="font-size:.88em;color:var(--secondary-text-color,#888);padding:12px 0">Lade…</p>`;
      return;
    }

    const mode      = this._distVal("distribution_mode") ?? "equal";
    const globalMax = this._distVal("global_max_power")  ?? 800;
    const interval  = this._distVal("interval_seconds")  ?? "30";
    const balance   = this._distVal("soc_pv_balance")    ?? 0.5;

    const manualRows = this._instances.map(inst => {
      const val = this._distInstVal(inst.entry_id, "manual_power") ?? 800;
      return `<div class="field">
        <label>${inst.instance_name} (W)</label>
        <input type="number" min="0" max="9600" step="10" value="${val}"
          data-dist-inst="${inst.entry_id}" data-dist-key="manual_power"/>
      </div>`;
    }).join("");

    const manualSum = this._instances.reduce((s, inst) => {
      return s + (parseFloat(this._distInstVal(inst.entry_id, "manual_power")) || 0);
    }, 0);
    const manualWarn = manualSum > globalMax
      ? `<p style="font-size:.8em;color:#dc2626;margin-top:4px">⚠️ Summe (${manualSum} W) überschreitet Global-Max</p>`
      : "";

    c.innerHTML = `
      <div class="col-card top-item">
        <div class="col-header" style="background:#0891b2">🌐 Globale Einstellungen</div>
        <div class="col-body">
          <div class="field">
            <label>Gesamte Max. Ausgangsleistung (W)</label>
            <div class="desc">Absolute Obergrenze aller Instanzen zusammen — wird nach Gewichtung aufgeteilt. Standard: 800 W (gesetzliches Einspeise-Maximum). Im manuellen Modus wird dieser Wert ignoriert.</div>
            <input type="number" min="0" max="9600" step="10" value="${globalMax}" data-dist-key="global_max_power"/>
          </div>
          <div class="field">
            <label>Aktualisierungsintervall</label>
            <div class="desc">Wie oft die Verteilung neu berechnet und in die Coordinatoren geschrieben wird.</div>
            <select data-dist-key="interval_seconds">
              ${["10","30","60","120","300"].map(v =>
                `<option value="${v}"${v === String(interval) ? " selected" : ""}>${v} s${v === "30" ? " (empfohlen)" : ""}</option>`
              ).join("")}
            </select>
          </div>
        </div>
      </div>

      <div class="col-card top-item">
        <div class="col-header" style="background:#7c3aed">⚖️ Verteilungs-Modus</div>
        <div class="col-body">
          <div class="field">
            <label>Modus</label>
            <div class="desc">
              Gleichverteilung → jede aktive Instanz erhält gleich viel<br>
              Gewichtet → Aufteilung nach SOC-Anteil und/oder PV-Leistung der Instanz<br>
              Manuell → feste Wattzahl pro Instanz, unabhängig von SOC oder PV
            </div>
            <select data-dist-key="distribution_mode" id="dist-mode-select">
              <option value="equal"${mode === "equal" ? " selected" : ""}>Gleichverteilung</option>
              <option value="weighted"${mode === "weighted" ? " selected" : ""}>Gewichtet</option>
              <option value="manual"${mode === "manual" ? " selected" : ""}>Manuell</option>
            </select>
          </div>
          <div class="field" style="${mode !== "weighted" ? "opacity:.4;pointer-events:none" : ""}">
            <label>SOC ←→ PV Gewichtung (0–1)</label>
            <div class="desc">0,0 → ausschließlich nach SOC · 1,0 → ausschließlich nach PV-Leistung der Instanz · 0,5 → 50/50 — Nur wirksam wenn Modus = Gewichtet</div>
            <input type="number" min="0" max="1" step="0.05" value="${balance}" data-dist-key="soc_pv_balance"/>
          </div>
        </div>
      </div>

      <div class="col-card top-item" style="${mode !== "manual" ? "opacity:.4;pointer-events:none" : ""}">
        <div class="col-header" style="background:#b45309">🔧 Manuelle Leistung pro Instanz</div>
        <div class="col-body">
          ${manualRows}
          ${manualWarn}
        </div>
      </div>

      <div id="dist-save-bar" style="position:sticky;bottom:0;background:var(--primary-color,#03a9f4);color:#fff;padding:10px 16px;border-radius:8px;margin-top:4px;align-items:center;justify-content:space-between;display:${Object.keys(this._distDirty).length ? "flex" : "none"}">
        <span>Ungespeicherte Änderungen</span>
        <button onclick="this.getRootNode().host._saveDistConfig()" style="background:#fff;color:var(--primary-color,#03a9f4);border:none;padding:6px 16px;border-radius:6px;cursor:pointer;font-weight:600">💾 Speichern</button>
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
