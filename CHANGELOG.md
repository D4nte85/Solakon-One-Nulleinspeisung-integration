# Changelog

Alle nennenswerten Änderungen an der Solakon-ONE-Nulleinspeisung-Integration.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [Unreleased]

### Behoben
- Warnhinweis und Hilfetext zu **Ruhezustand in Modus 1** sowie die README-Tabelle
  sagten noch, das Gerät verlasse die Fernsteuerung nie mehr. Seit `3.0.0-beta.2`
  verlässt es sie bei ausgeschalteter Regelung
- Bei ungültigen SOC-Grenzen schrieb der Zyklus noch das Export-Limit, bevor er
  abbrach. Der Abgleich läuft jetzt erst nach der Validierung
- Fiel ein Kernsensor (Netz, PV, Ist-Leistung, SOC) aus, übersprang der Zyklus ohne
  Meldung. Lieferte er Text statt einer Zahl, regelte die Integration mit 0 weiter —
  ein SOC-Sensor im Fehlerzustand löste so den Sicherheitsstopp aus. Beides überspringt
  jetzt den Zyklus mit der Meldung „Sensor … nicht verfügbar oder ohne Zahlenwert“
- Die Ruhe in Modus `'0'` (Falls B, C, F, Tarifsperre) setzte den Entladestrom auf 0 A,
  weil sie für den Abgleich wie Zone 2 zählte. Verließ das Gerät die Fernsteuerung, blieb
  es geklemmt. Ohne Zyklus gilt 0 A jetzt nur noch in Modus `'1'`, sonst der Max-Entladestrom
- Lag der Output-Sollwert über dem dynamischen Limit (Zone 2: PV − Reserve), der
  Netzfehler aber in der Toleranz, blieb er stehen und die Batterie deckte den Verbrauch.
  Der PI-Schritt läuft jetzt auch dann und begrenzt auf das Limit
- Mehrere Instanzen: Entlud genau eine Schwester, ließ die Summe der Ist-Leistungen sie
  weg und zählte nur die eigene Instanz. Eine ruhende Instanz startete so AC-Laden aus der
  Entladung der Schwester. Die Summe zählt jetzt die eigene Instanz plus alle Schwestern im Pool


## [3.0.0-beta.2] – 2026-09-14

> **Beta-Release.** Folgestand zu `3.0.0-beta.1`: Regelung aus verlässt den Ruhezustand in Modus 1, Nachtabschaltung mit Hysterese. Erscheint in HACS nur bei aktivierten Beta-Versionen.

### Hinzugefügt
- Nachtabschaltung: Einstellung **Hysterese Einschalten** (W, Standard 0). Die Nacht
  beginnt weiter bei PV < PV-Ladereserve und endet erst bei PV ≥ PV-Ladereserve +
  Hysterese — verhindert Flattern zwischen Fall F und E in der Dämmerung

### Geändert
- Regelung ausschalten schreibt immer Modus `'0'`, auch mit aktivem Schalter
  **Ruhezustand in Modus 1** — das Gerät verlässt die Fernsteuerung, wenn die
  Integration nicht mehr regelt. Der Betriebsmodus-Zustand
  `rest_discharge_regulation_off` entfällt

## [3.0.0-beta.1] – 2026-09-13

> **Beta-Release.** Umfangreicher interner Umbau von Coordinator, WebSocket-Handlern, Sensoren, Config-Flow und Panel, dazu der zentrale Ruhezustand. Verhaltensänderung gegenüber `2.4.x`: Zahlenwerte kommen nur noch aus Entitäten der Domains `sensor`, `input_number` und `number`. Erscheint in HACS nur bei aktivierten Beta-Versionen.

### Hinzugefügt
- Schalter **Ruhezustand in Modus 1** im Debug-Tab (Standard aus, nicht empfohlen): die
  Regelung ruht in Modus `'1'` mit 0 W statt in Modus `'0'`. Für Geräte, die in Modus
  `'0'` nicht laden. Alle Ruhe-Übergänge laufen über einen gemeinsamen Ruhezustand;
  Modus `'0'` wird nur noch dort geschrieben, mit aktivem Schalter nie. Das Gerät
  verlässt die Fernsteuerung dann nie mehr, auch nicht bei ausgeschalteter Regelung.

### Geändert
- Zahlenwerte werden nur noch aus Entitäten der Domains `sensor`, `input_number` und
  `number` gelesen. Eine Entität anderer Domain gilt als ungültig: Tarifschwellen fallen
  auf den Panel-Wert zurück, sensorgebundene Funktionen melden die falsche Domain
- Einheiten beim Sensorlesen werden ohne Rücksicht auf Groß-/Kleinschreibung erkannt,
  `MWh` eingeschlossen
- Status-Tab und Übersicht zeigen Offset und Batteriekapazität aus dem gespeicherten
  Stand der Regelung statt aus ungespeicherten Panel-Eingaben; die Kapazität wird mit
  denselben Einheiten wie im Backend umgerechnet
- Panel: alle Entity-Eingaben nutzen die volle Breite, die Speicherleiste der Verteilung
  hat denselben Abstand wie die der Instanz-Tabs
- Intern: Refactoring von Coordinator, WebSocket-Handlern, Sensoren, Config-Flow und Panel —
  wiederholte Logik auf gemeinsame Funktionen zurückgeführt, Verhalten gegen
  Charakterisierungstests und Render-Vergleich des Panels geprüft

## [2.4.1-beta.1] – 2026-09-12

> **Beta-Release.** Fehlerbehebungen und ein interner Umbau der Textquellen; keine Breaking Changes gegenüber `2.4.0`. Erscheint in HACS nur bei aktivierten Beta-Versionen.

### Behoben
- Das Panel trug 76 englische Texte ein zweites Mal als Inline-Fallback im JavaScript
  (`s.solar_lbl || "Solar"`). Jeder dieser Schlüssel existiert in `panel.en.json`, und
  46 der Fallbacks wichen vom dortigen Wert ab — sie hätten im Ernstfall „Solar" statt
  „Solar Power", „📈" statt „📈 Control State" und „Save" statt „💾 Save" angezeigt,
  unbemerkt, weil der Zweig nur bei fehlender Sprachdatei greift. Die Sprachdateien
  werden jetzt übereinandergelegt: `panel.en.json` ist die Basis, die Landessprache
  liegt darüber — ein Schlüssel, der nur in einer der beiden Dateien steht, kommt damit
  aus der anderen, und kein Text muss im Code stehen. Lässt sich die Basis gar nicht
  laden, sagt das Panel das jetzt sichtbar, statt 76 halbaktuelle Wörter anzuzeigen
- Zustandstexte und Entitätsnamen standen mehrfach: die zehn Betriebszustände und die
  vierzehn Fall-Bezeichnungen in `panel.de.json`/`panel.en.json` **und** in
  `translations/*.json`, die sechs Modus-Texte zusätzlich in `i18n.py`, vier
  Entitätsnamen noch einmal als Panel-Beschriftung. Nichts hielt die Kopien
  zusammen — die englischen Fall-Bezeichnungen waren dadurch bereits in allen
  vierzehn Fällen auseinandergelaufen (Panel Title Case, Entität Sentence Case), und
  `strings.json` trug einen deutschen Config-Flow-Teil, obwohl es die englische
  Quelle ist. Einzige Quelle ist jetzt `translations/<lang>.json`, weil Home
  Assistant Entitätszustände nur von dort liest: das Panel lädt sie über die neuen
  Static-Paths `/<domain>/entity.<lang>.json` und löst Zustandstexte und Namen daraus
  auf, `i18n.py` liest die Modus-Texte beim Import von dort ein, und `strings.json`
  ist wieder englisch und deckungsgleich mit `translations/en.json`. Der bisher
  parametrisierte Text „Unbekannter Modus: {mode}" setzt den Rohwert jetzt im Code an,
  weil ein Entitätszustand keine Parameter tragen kann. Die Kurzform der Zonen im
  Panel-Kopf bleibt bewusst ein eigener Text
- Die beiden kWh-Schwellen der Forecast-Features standen bei Neuinstallation auf `5000.0` (`const.py`) — ein W-Wert aus der Zeit vor der Umstellung auf `_flt_kwh_normalized()`. Verglichen wird gegen kWh Tagesertrag, die Panel-Felder reichen bis 100 bzw. 50 kWh: Surplus-Forecast-Erzwingung und Tarif-Lock-Unterdrückung waren damit bis zur manuellen Korrektur wirkungslos. Beide Vorgaben jetzt `15.0`, wie die Zone-1-Nacht-Forcierung. Bestehende Installationen behalten ihren gespeicherten Wert und müssen die Schwelle einmal prüfen
- Doku: `README.md` beschrieb die Forecast-Schwelle als „Basiseinheit (W bzw. Wh), Standard 5000 Wh" — das war das Verhalten von `_flt_kilo_normalized()`. Richtig ist kWh mit automatischer Wh/MWh-Normalisierung. Panel-Label „Mindest-Ertrag für Surplus" trägt die Einheit jetzt ebenfalls, und die Überschuss-Parametertabelle im README listet die Forecast-Erzwingung überhaupt erst
- Die Gerätegrenze von 1200 W war nur im Panel hinterlegt, nicht in der Regelung: die vier Leistungsfelder (`hard_limit_z0`, `hard_limit_z1`, `ac_power_limit`, `tariff_power`) tragen `max: 1200` als Eingabeattribut, `save_config` nimmt jedoch jeden Wert entgegen (`changes: dict`, keine Wertevalidierung), und Werte aus der Zeit vor der Slider-Korrektur stehen unverändert im Store. Ein Sollwert darüber wird je nach Einbindung von `number.set_value` abgewiesen — dann verfällt der Schreibvorgang und hinterlässt nur eine Exception im Log — oder angenommen und vom Gerät nicht erreicht, womit der Regler in stille Sättigung läuft, weil `at_max_limit` unter `dynamic_max` bleibt. Die Gerätegrenze wird jetzt an drei Stellen berücksichtigt: in der Limitbildung (`effective_hard`, `effective_hard_z1`, AC-Zweig von `dynamic_max`), in `_pi_calculate`, damit Klemmung und Back-Calculation gegen die real erreichbare Grenze rechnen, und als letzte Klemme in `_set_output`/`_set_output_and_wait`, die auch die nicht über `dynamic_max` laufende Tarif-Ladeleistung erfasst. Maßgeblich ist die Konstante `DEVICE_MAX_POWER` mit der Datenblattgrenze des Solakon ONE von 1200 W. Das `max`-Attribut der Ausgangs-Entität wird dafür nicht herangezogen — Modbus-Einbindungen deklarieren dort die Registergrenze (gemessen: 100000), nicht die Gerätegrenze. Der Blueprint deckelt seit jeher über `inverter_entity_max` und `effective_max` (`coordinator.py`, `README.md`)

## [2.4.0] – 2026-09-12

> **Enthält Breaking Changes und die erste echte Store-Migration.** Beide Stores steigen von Version 1 auf 2; ein Rückschritt auf 2.3.2 ist danach nicht vorgesehen — die alte Codebasis kennt das neue Format nicht. Vor der Installation ein Backup der Konfiguration anlegen.
>
> Diese Version fasst die Vorabversionen `2.4.0-beta.1` und `2.4.0-beta.2` zusammen. Wer eine der beiden installiert hat, findet die seither umbenannten Zustandswerte unter *Für Tester der Betas* am Ende dieses Abschnitts.

### Hinzugefügt
- Neuer Sensor „Betriebszustand" fasst zusammen, was eine Instanz gerade tut — bisher war das nur aus neun Binärsensoren, Zone und Betriebsmodus in der richtigen Rangfolge zu erschließen. Zehn Zustände, abgeleitet aus den Zustandsflags statt aus dem zuletzt ausgeführten Fall, mit Zone, Gerätemodus, letztem Fall, letzter Aktion, Fehler und Zeitpunkt des letzten Wechsels als Attribute. Als übersetzter Enum-Sensor angelegt (Schlüssel sprachneutral, Anzeige in Deutsch und Englisch), damit Automationen unabhängig von Anzeigetexten bleiben. Dazu neu das Flag `discharge_locked`: die Tarifsperre war bisher von außen nicht von Bereitschaft zu unterscheiden, weil Fall TM nur beim Übergang feuert und kein Flag setzt. Die Panel-Übersicht zeigt den Zustand anstelle des aktiven Falls; der Status-Tab führt den Fall weiterhin (Discussion [#34](https://github.com/D4nte85/Solakon-One-Nulleinspeisung-integration/discussions/34), `coordinator.py`, `sensor.py`, `const.py`, `__init__.py`, `strings.json`, `translations/`, `solakon-panel.js`, `panel.de.json`, `panel.en.json`, `README.md`)

### Geändert (Breaking)
- Alle 17 erzeugten Entitäten tragen jetzt übersetzte Namen statt hartcodierter deutscher, und die Freitextfelder der Regelung erscheinen in der Sprache der Home-Assistant-Instanz. Das Panel war seit jeher zweisprachig, die Entitäten waren es nicht — ein englischsprachiges Home Assistant zeigte „Aktuelle Zone", „Überschussleistung" und deutsche Fehlermeldungen. **Was bricht:** „Aktiver Fall" und „Betriebsmodus" sind jetzt Enum-Sensoren; ihr Zustandswert ist der sprachneutrale Schlüssel (`0A` … `TM` bzw. `waiting`/`disabled`/`discharge`/`ac_charge`/`disabled_regulation_off`/`unknown`), nicht mehr der deutsche Klartext. Automationen, die auf den Anzeigetext dieser beiden Sensoren prüfen, müssen auf den Schlüssel umgestellt werden — danach sind sie von Anzeigetexten unabhängig. Die Zustandswerte aller übrigen Sensoren bleiben unverändert, „Aktuelle Zone" bleibt numerisch mit `state_class: measurement`. Das Attribut `fall_id` entfällt, es ist mit dem Zustandswert wortgleich; „Letzte Aktion" bekommt dafür `action_key` plus die Werte der Meldung als Attribute, damit sie sprachneutral auswertbar bleibt. Bestehende `entity_id`s ändern sich **nicht**; nur bei Neuinstallationen leitet Home Assistant sie aus dem übersetzten Namen ab. Zonen-Label, Modustext, letzte Aktion und Fehlermeldungen kann Home Assistant nicht übersetzen (Attribute und Panel-Payload) — sie rendert die Integration über `hass.config.language` und folgen damit der Instanzsprache, nicht der persönlichen Sprache eines Benutzers (Discussion [#21](https://github.com/D4nte85/Solakon-One-Nulleinspeisung-integration/discussions/21), `i18n.py` neu, `coordinator.py`, `sensor.py`, `binary_sensor.py`, `switch.py`, `const.py`, `strings.json`, `translations/`, `README.md`)
- Die fünf einmaligen Konversionen laufen nicht mehr bei jedem Start bzw. jedem Storelesen mit, sondern genau einmal beim Update: beide Stores tragen jetzt Version 2 und migrieren über `_async_migrate_func`. Betroffen sind die Aufspaltung `hard_limit` → `hard_limit_z0`/`_z1`, die Umbenennung `surplus_forecast_sensor` → `pv_forecast_sensor`, die Auflösung des alten `capacity_weighting`-Bools in den Drei-Wert-`distribution_mode` und die Verschachtelung des flachen Verteilungs-Stores nach Netzsensor. Damit entfallen die vier `s.get(S_HARD_LIMIT_Z0, s.get(S_HARD_LIMIT, 800))`-Kaskaden im Regelzyklus und in der Verteilung, die den alten Schlüssel wie einen gleichberechtigten aussehen ließen, sowie zwei `async_save()`-Aufrufe mitten im Ladepfad. Die Konstanten `S_HARD_LIMIT` und `S_SURPLUS_FORECAST_SENSOR` sind entfallen. Ein Zwischenschritt ist nicht nötig: die Migration deckt alle vier Altformen ab, ein Update von jeder bisherigen Version läuft direkt durch (`coordinator.py`, `__init__.py`, `const.py`)

### Geändert
- Ein Preis-Sensor in €/kWh statt der erwarteten ct/kWh blieb unbemerkt: der Preis liegt dann dauerhaft unter der Günstig-Schwelle, die Integration lädt durchgehend aus dem Netz und sperrt über den Discharge-Lock zusätzlich Zone 1 und Zone 2. Neue Prüfung `_tariff_unit_warning()` meldet den Verdacht als Fehlermeldung im Panel. Kriterium ist der Wert, nicht die Einheit — Preiseinheiten sind in Home Assistant nicht normiert und fehlen bei Template-Sensoren oft ganz: ein Preis zwischen 0 und 1 bei einer Günstig-Schwelle ab 3 muss dafür sechs Stunden ununterbrochen anliegen, womit negative Börsenpreise und einzelne Nulltarif-Stunden ausgenommen sind. `unit_of_measurement` wirkt nur bestätigend (€/EUR meldet sofort, ct/Cent/öre unterdrückt). Umgerechnet wird nichts (Discussion [#34](https://github.com/D4nte85/Solakon-One-Nulleinspeisung-integration/discussions/34), `coordinator.py`, `const.py`, `README.md`)
- Netzgruppen werden in Panel und Übersicht jetzt nach dem Home-Assistant-Bereich ihres Netzsensors benannt (direkt zugewiesen oder über das Gerät geerbt), mit Rückfall auf den Anzeigenamen des Sensors und dessen Entity-ID. Bei der von Home Assistant empfohlenen Entitätsbenennung (Bereich, Gerät, Entität) trugen alle Gruppen denselben Namen, etwa „Netz Leistung". Die Beschriftung heißt entsprechend „Bereich" statt „Gruppe"; die Gruppenzuordnung selbst bleibt an der Sensor-Entität (Discussion [#21](https://github.com/D4nte85/Solakon-One-Nulleinspeisung-integration/discussions/21), `solakon-panel.js`, `panel.de.json`, `panel.en.json`, `README.md`)
- Instanz-Karten der Übersicht kennzeichnen zwei Zustände zusätzlich zur Zonenfarbe: inaktive Regelung als ausgegraute Karte, anliegende Fehlermeldung als roter Rahmen mit ⚠️ und der Meldung als Tooltip (Discussion [#21](https://github.com/D4nte85/Solakon-One-Nulleinspeisung-integration/discussions/21), `solakon-panel.js`, `README.md`)
- Die vier schreibenden WebSocket-Commands (`save_config`, `set_cycle`, `reset_integral`, `save_distribution_config`) verlangen jetzt `@websocket_api.require_admin` — zuvor konnte jeder angemeldete Home-Assistant-Benutzer die Reglerkonfiguration ändern, da keiner der acht Commands eine Rechteprüfung trug. Die vier lesenden Commands bleiben offen, damit das Panel für alle Benutzer sichtbar bleibt; README um einen Hinweis ergänzt (Issue [#35](https://github.com/D4nte85/Solakon-One-Nulleinspeisung-integration/issues/35), `__init__.py`, `README.md`)
- Die Zustände des Sensors „Betriebsmodus" tragen jetzt den Herstellerwortlaut des Registers **und** eine Erklärung in der Anzeigesprache: `disabled` → „Disabled (Fernsteuerung abgegeben)" bzw. „Disabled (remote control released)", `discharge` → „INV Discharge PV Priority (Entladen mit PV-Vorrang)" bzw. „(PV-first discharge)". „Disabled" allein las sich wie ein ausgeschaltetes Gerät, gemeint ist aber Modus `'0'`: die Fernsteuerung ist abgegeben, Zeitplan und Easy Mode der Solakon-App greifen wieder. Der Zustandswert bleibt der sprachneutrale Schlüssel, Automationen sind nicht betroffen. `mode_unknown` im Panel heißt jetzt „Unbekannter Modus: {mode}" statt „Modus: {mode}" und deckt sich damit mit dem Entitätstext (`i18n.py`, `strings.json`, `translations/`)

### Behoben
- `_pi_calculate` nahm einen Parameter `tolerance` entgegen, benutzte ihn im Rumpf aber nicht — die Toleranz gatet ausschließlich den Aufruf (`coordinator.py:1290` und `:1315`). Der durchgereichte Wert ließ die Rechnung so aussehen, als trüge sie ein eigenes Totband. Parameter entfernt, an beiden Aufrufstellen nicht mehr übergeben; das Regelverhalten ändert sich nicht (`coordinator.py`)
- Zone 3 griff erst **unter** der eingestellten Schwelle statt auf ihr: die Fälle B und C prüften `soc < zone3`, während Zonenanzeige, Zone-2-Eintritt und README die Schwelle als zu Zone 3 gehörend behandeln. Bei ganzzahligem SOC vom Wechselrichter — also ständig — wurde bei genau der eingestellten Schwelle weiter entladen, bis der SOC einen Punkt darunter fiel; das Panel zeigte dabei Zone 1 und „Entladen", weil die Zonenanzeige `cycle_active` vor dem SOC prüfte. Stand der Zyklus gerade nicht, griff überhaupt kein Fall: Fall C verlangte `soc < zone3`, Fall E `zone3 < soc` — die Anzeige meldete „Sicherheitsstopp", ohne dass der Wechselrichter je auf Modus `'0'` gesetzt wurde. Beide Fälle prüfen jetzt `soc <= zone3`, und die Zonenanzeige prüft den SOC vor den Zyklusflags (`coordinator.py`, `README.md`)
- Beim Entfernen der **letzten** Instanz blieben die beiden instanzübergreifenden Stores `solakon_nulleinspeisung_distribution` und `solakon_nulleinspeisung_soc_switch_state` in `.storage` liegen: `async_remove_entry` räumte nur die Einstellungsdatei der jeweiligen Instanz weg. Sie werden jetzt mitgelöscht, sobald kein Config-Entry der Integration mehr vorhanden ist — bei weiteren Instanzen bleiben sie unangetastet, da sie dort weiterhin gebraucht werden. Home Assistant trägt den Entry vor dem Aufruf aus der Registrierung aus (`config_entries.py:2280` vor `:2281`), die Prüfung auf verbleibende Entries ist damit ohne Sonderfall korrekt (`__init__.py`)

### Für Tester der Betas

Nur relevant für alle, die `2.4.0-beta.1` oder `2.4.0-beta.2` installiert hatten — die betroffenen Zustände gibt es erst seit dieser Beta-Reihe.

- Der Betriebszustand `discharging` heißt jetzt `battery_supply` („Batteriebetrieb" / „Battery supply"). Die Zustände benennen damit durchgängig, **welche Quelle den Hausverbrauch gerade deckt**, statt einmal die Zone und einmal die Wirkung: `pv_direct` die PV, `battery_supply` die Batterie. Das Kriterium bleibt unverändert `cycle_active` — der Zustand gilt also weiterhin auch in den Minuten, in denen der PI-Ausgang auf 0 steht, weil die PV den Verbrauch allein trägt. **Was bricht:** Automationen auf den Zustandswert `discharging` müssen auf `battery_supply` umgestellt werden; der Zustand existiert erst seit 2.4.0-beta.1 (`const.py`, `coordinator.py`, `sensor.py`, `strings.json`, `translations/`, `panel.de.json`, `panel.en.json`, `README.md`)
- Der Betriebszustand `idle` heißt jetzt `pv_direct` („PV-Direktnutzung" / „PV direct use", Icon `mdi:solar-power-variant`). Der Zustand gilt in Zone 2 bei Tag, wenn Fall E den Wechselrichter auf PV-Vorrang gestellt hat und die Ausgangsleistung 0 beträgt: die PV deckt den Hausverbrauch direkt, die Batterie bleibt unangetastet. Das ist ein aktiver Betriebsfall, „Bereitschaft"/„Standby" beschrieb ihn als Warten. **Was bricht:** Automationen, die auf den Zustandswert `idle` prüfen, müssen auf `pv_direct` umgestellt werden — der Zustand existiert erst seit 2.4.0-beta.1 (`const.py`, `coordinator.py`, `sensor.py`, `strings.json`, `translations/`, `panel.de.json`, `panel.en.json`, `README.md`)
- Drei weitere Betriebszustände heißen präziser: `blocked` → „Regelung blockiert" / „Control blocked" statt „Gestört" / „Fault" — der Zustand entsteht ausschließlich aus fehlenden Kernsensoren oder unplausiblen SOC-Grenzen, nie aus einer Störung des Wechselrichters; der Grund steht in der Fehlermeldung. `ac_charging` heißt in Deutsch „AC-Laden" statt „AC Laden", passend zu „Tarif-Laden". `safety_stop` nennt den Anlass: „Sicherheitsstopp (SOC-Minimum)" / „Safety stop (SOC minimum)" — der Zustand liest sich sonst wie ein Defekt, tatsächlich steht der SOC auf der Zone-3-Schwelle und die Regelung hat die Fernsteuerung abgegeben. Die Zustandswerte bleiben unverändert (`strings.json`, `translations/`, `panel.de.json`, `panel.en.json`, `README.md`)

## [2.3.2] – 2026-09-02

### Geändert
- README für die Aufnahme in den HACS-Standardstore überarbeitet: Hinweisblock vorangestellt, dass die offizielle Solakon-ONE-Integration Voraussetzung ist und selbst nicht im Standardstore liegt ([hacs/default#9184](https://github.com/hacs/default/pull/9184))
- FAQ um den Betrieb ohne eigene Panels am Gerät erweitert — Zone 0 ist dort unerreichbar und blockiert damit AC Laden, die Nachtabschaltung ist bei PV = 0 dauerhaft aktiv und sperrt Zone 2, und von den vier Trigger-Quellen bleibt praktisch nur der Netzsensor. Dazu drei kleinere Einträge: Vorzeichen des Offsets als Zielwert am Netzzähler, getrennte Offsets und P/I-Faktoren für AC Laden, Ampere gegen Watt. Ausgelöst durch Discussion [#31](https://github.com/D4nte85/Solakon-One-Nulleinspeisung-integration/discussions/31), Fehlerbehebungs-Eintrag zum `device_class: power`-Filter des Selectors aus Discussion [#30](https://github.com/D4nte85/Solakon-One-Nulleinspeisung-integration/discussions/30) (`README.md`)
- Beschreibung des periodischen Triggers nannte als Anwendungsfall nur „stabile Haushalte" und verschwieg den zweiten Fall — ein Setup ohne geeignete Trigger-Quelle, in dem der periodische Trigger der einzige Taktgeber ist (`panel.de.json`, `panel.en.json`, `README.md`)

### Behoben
- Der Regler konnte im gesättigten Zustand dauerhaft verstummen: steht der Sollwert des Standard-PI am oberen Limit und besteht der Netzfehler in dieselbe Richtung fort, ist der `at_max_limit`-Guard dauerhaft erfüllt und es wird nie wieder geschrieben. Bleibt der Wechselrichter in genau diesem Zustand stehen, ohne das Modus-Register zu ändern, erreicht ihn kein Befehl mehr — auch Fall D greift nicht, da er einen Modus außerhalb `'1'`/`'3'` voraussetzt. Da es keinen Schreibversuch gab, konnte auch nichts fehlschlagen und gemeldet werden. Neue Methode `_check_output_stall()` prüft ausschließlich in diesem Zweig die tatsächliche Ausgangsleistung gegen das Limit: mehr als 5 % Abweichung bei einem seit über 300 s unveränderten Messwert löst einen Sollwert-Rewrite aus; bleibt die Abweichung bestehen, wird der Wechselrichter aus dem Regelmodus genommen (Output 0, Timer-Toggle, Modus `'0'`) und im Folgezyklus von Fall D regulär zurückgeholt. Die übrigen drei PI-Pfade sind ausgenommen — Zone 0, Tarif-Laden und die Totbänder halten den Ausgang bewusst unterhalb ihres Limits. Feldbeleg: 19 h Ausgang 0 W bei aktivem Entladezyklus, Erholung erst nach Hardware-Neustart des Wechselrichters (Issue [#32](https://github.com/D4nte85/Solakon-One-Nulleinspeisung-integration/issues/32), `coordinator.py`, `const.py`)
- `sensor.py`: Docstring von `SurplusPowerSensor` beschrieb den Wert als „Maximum aus Hard-Limit und aktueller PV-Leistung" — berechnet wird das Maximum der beiden Hard-Limits Z0 und Z1

## [2.3.1] – 2026-08-27

### Behoben
- Fall-H-Austritt (AC Laden Ende): Vergleich `eigener Output ≤ 0 W` (aus V309, in v2.2.7 von exaktem `== 0` gelockert) auf `abs(actual) <= S_SELF_ADJUST_TOL` (Standard 2 W, dieselbe Toleranz wie die PI-Konvergenzprüfung) geändert. Feldbeleg (27.08., Kumpel-Installation, reine AC-Anbindung ohne PV, Fehler unter v2.2.8) per Verlaufsdiagramm ausgewertet: der als `actual_power_sensor` hinterlegte Sensor folgt derselben Vorzeichenkonvention wie der Netzsensor (positiv = Bezug, negativ = Einspeisung/Verbrauch von Überschuss) — während aktivem AC-Laden ist er durchgehend deutlich negativ (im Feldbeleg bis −400 W), nicht nur nahe 0. Der einseitige `≤ 0`-Vergleich war dadurch praktisch die gesamte Ladedauer über erfüllt, unabhängig von der tatsächlichen Ladeleistung — übrig blieb effektiv nur noch die Grid-Bedingung (`Grid ≥ Offset + Hysterese`). Da das Laden selbst den gemessenen Netzüberschuss verringert, erreicht die Regelung diese Schwelle regelmäßig als direkte Folge ihrer eigenen Arbeit — Fall H feuerte dann sofort, auch bei laufender substanzieller Ladeleistung (Feldbeleg: Reset bei ~300 W kommandierter Leistung), gefolgt vom sofortigen Wiedereintritt über Fall G, da das Netzdefizit nach dem Reset weiterbesteht — periodischer Moduswechsel 3↔1 alle ~15–20 s mit hartem Output-Reset auf 0 W. Fix: `abs(actual) <= Toleranz` verlangt jetzt, dass die Ladeleistung tatsächlich auf nahe null heruntergeregelt ist, bevor der Grid-Zweig greift — ein laufender Ladevorgang mit spürbarer Leistung erfüllt die Bedingung nicht mehr (`coordinator.py`)
- `_confirm_zero_output()` loggte WARNING/ERROR ("Output-Nullung nicht bestätigt") auch dann, wenn `CONF_ACTUAL_SENSOR` seit unserem letzten Schreibbefehl schlicht noch nicht neu gepollt hatte — dieser Sensor stammt aus einer fremden Integration mit eigenem, deutlich langsamerem Poll-Intervall (1–300 s, Standard 30 s) als unser Warte-/Retry-Fenster. Ein solcher Read sagt nichts über Erfolg oder Fehlschlag aus, wurde aber als Fehlschlag gewertet (Feldbeleg: Kreuzbefund aus Batterie-Register + Hardware-Shelly in Issue #27 zeigte, dass das Gerät real bereits genullt hatte, während unser Read noch einen alten Spike-Wert zeigte). Schreib-/Retry-Verhalten unverändert — WARNING/ERROR werden jetzt nur noch geloggt, wenn der zugrundeliegende Read nachweislich (`state.last_updated` ≥ letzter eigener Schreibzeitpunkt) aussagekräftig ist (`coordinator.py`)

## [2.3.0] – 2026-08-26

### Behoben
- Regelzyklus (`_run_regulation_cycle`): `CONF_ACTIVE_POWER` wurde bis zu dreimal pro Zyklus gelesen (Zyklusstart, nach den Falls, unmittelbar vor der PI-Entscheidung), dazwischen liegen `await`s (u. a. Timer-Toggle) — Gate-Prüfung (`at_max_limit`/`at_min_limit`/`above_dynamic_max`), PI-Basisberechnung und die angezeigte Statuszeile ("PI: … → … W") konnten dadurch je nach Zykluszeitpunkt auf unterschiedlichen Momentaufnahmen des Ausgangswerts stehen. Jetzt genau eine Lesung nach dem letzten Await vor der PI-Entscheidung, von Gate, PI-Basis und Statusanzeige gemeinsam verwendet (`coordinator.py`)
- `_total_actual_power()` (Grundlage für Überschuss-Ein-/Austritt und Fall G) las im Einzelbetrieb `CONF_ACTUAL_SENSOR` unabhängig von der bereits am Zyklusanfang erfassten `actual`-Variable ein zweites Mal — mit einem `await` (Exportlimit-Sync) dazwischen. Beide potenziell abweichenden Lesungen desselben Sensors flossen in dieselbe Überschuss-Bedingung ein (`total_actual` aus der zweiten Lesung neben direkten `actual`-Vergleichen aus der ersten). Übernimmt jetzt die bereits gelesene eigene `actual`-Snapshot statt erneut zu lesen (`coordinator.py`)
- Multi-Instanz-Verteilung (`_all_shares()`/`_soc_switch_shares()`, Modi "SOC-gewichtet"/"Kapazitätsgewichtet"/"SOC-Umschaltung"): las den eigenen SOC für die Gewichtsberechnung unabhängig vom bereits am Zyklusanfang erfassten `soc` erneut aus `CONF_SOC_SENSOR` — mit demselben Exportlimit-Sync-`await` dazwischen wie oben. `error_share` konnte dadurch auf einem anderen eigenen SOC-Stand beruhen als die Zonen-/Fall-Entscheidungen desselben Zyklus. Übernimmt jetzt den Zyklus-Snapshot für die eigene Instanz, Fremdinstanzen werden weiterhin live gelesen (`coordinator.py`)
- Falls (`_execute_falls()`, z. B. Fall H: AC-Laden-Ende): `_set_output(0)` rief `number.set_value` ohne `blocking=True` auf und kehrte zurück, bevor `CONF_ACTIVE_POWER` den neuen Wert widerspiegelte. Lief im selben Zyklus direkt danach das PI-Gate (z. B. weil der Fall den Modus auf "Discharge" zurückgesetzt hat), konnte dessen `current_power`-Lesung noch den alten, vor-dem-Fall-Wert zeigen — die PI-Basis rechnete dann auf einer stale Ausgangsleistung weiter, statt vom gerade gesetzten Nullpunkt. Feldbeleg: eingefrorener Zone-1-Output nach Fall H über 16 min trotz gesättigtem PI-Integral (Issue #27). Neue Methode `_set_output_and_wait()` bündelt `_set_output()` mit dem bereits vorhandenen `_wait_for_target()`-Konvergenz-Poll (analog zum entsprechenden `wait_template`-Muster im Blueprint) — ersetzt jetzt alle Fall-eigenen `_set_output(...)`-Aufrufe sowie die bisher nur in den regulären PI-Pfaden genutzten Set+Wait-Paare (`coordinator.py`)
- Output-Nullung (Fall-Übergänge, PI-Ziel 0) war rein "fire and forget" — ein verlorener/abgelehnter Schreibbefehl blieb unbemerkt, der Zyklus lief mit dem tatsächlich weiterhin anliegenden alten Output einfach weiter. Neue Methode `_confirm_zero_output()` (aufgerufen aus `_set_output_and_wait()` immer wenn `value == 0`) verifiziert die reale Konvergenz gegen `CONF_ACTUAL_SENSOR` unabhängig von der Einstellung "Selbstjustierung" (die `_wait_for_target()` sonst voraussetzt), schreibt bei Nichtkonvergenz bis zu zweimal erneut und meldet nach Ausschöpfung einen sichtbaren Fehler über den neuen Warnkanal `_output_warning` (Panel-Fehleranzeige, analog zu `_dist_warning`) statt stillschweigend weiterzulaufen (`coordinator.py`)
- Tarif-Laden-Fortsetzung (`elif self.tariff_charge_active`) schrieb `tariff_power` bislang in jedem Zyklus unbedingt neu, ohne Prüfung ob der Ist-Wert schon übereinstimmt — seit dem `_set_output_and_wait()`-Fix oben bedeutete das eine feste `wait_time`-Verzögerung in **jedem** Regelzyklus während der gesamten Ladedauer, statt wie bei den übrigen Pfaden nur bei tatsächlicher Abweichung. Guard `if abs(current_power - tariff_power) > 0.5` ergänzt, analog zum bestehenden Zone-0-Guard (`coordinator.py`)

## [2.2.8] – 2026-08-24

### Hinzugefügt
- Dynamischer Offset: neue Einstellung `stddev_trim_count` (Dyn.-Offset-Tab, Standard 0) — schließt die N höchsten UND die N niedrigsten Einzelmesswerte im Stabw.-Fenster vor der Berechnung aus (pro Seite, nicht insgesamt — N=5 → 10 Samples ausgeschlossen). Trennt kurze, seltene Lastspitzen (z. B. Kompressor-/Pumpen-Anlaufstrom) von echter Dauerunruhe anhand des betroffenen Fensteranteils statt der Ereignisdauer — ein Puls, der nur eine Minderheit der Samples füllt, fällt komplett raus, eine Schwankung über den Großteil des Fensters bewegt den Offset weiterhin. Als Anzahl Samples konfigurierbar, nicht als Prozent (`coordinator.py`, `const.py`)
- Netz-Stabw.-Sensor: neues Attribut `stddev_raw` (ungetrimmter Wert) und `trim_count`, Panel zeigt getrimmten und rohen Wert direkt nebeneinander zum Vergleich beim Tunen (`sensor.py`, `__init__.py`, `panel.*.json`, `solakon-panel.js`)

## [2.2.7] – 2026-08-23

### Behoben
- Surplus-Forecast-Erzwingung, Tarif-Lock-PV-Vorhersage und Zone-1-Nacht-Forcierung verglichen den PV-Ertrag-Sensor (dokumentiert in kWh) über `_flt_kilo_normalized()` gegen ihre jeweilige Schwelle — bei einem Sensor mit Einheit `kWh` normalisiert diese Funktion den Wert automatisch ×1000 auf Wh, während die drei Schwellenfelder unverändert in kWh eingegeben werden. Die Schwelle griff dadurch praktisch nie (jeder reale kWh-Ertrag lag nach der ×1000-Normalisierung weit über jedem im Panel sinnvoll einstellbaren Wert). Neue Funktion `_flt_kwh_normalized()` (Wh ÷1000, MWh ×1000, kWh/ohne Einheit unverändert) ersetzt `_flt_kilo_normalized()` an allen drei Stellen — normalisiert jetzt unabhängig davon korrekt, ob der konfigurierte Sensor in Wh, kWh oder MWh meldet. `surplus_lock_sensor` (Leistungs-Vorhersage in W) bleibt unverändert bei `_flt_kilo_normalized()`, da dort tatsächlich in Watt verglichen wird (`coordinator.py`)
- Fall H (AC Laden Ende): Vergleich `eigener Output = 0 W` auf `eigener Output ≤ 0 W` geändert — robuster gegen isolierte Ein-Sekunden-Nullwerte durch Modbus-Rauschen in Leistungssensoren (`coordinator.py`, analog zum entsprechenden Blueprint-Fix)

## [2.2.6] – 2026-08-21

### Behoben
- Coordinator: `_on_periodic()` (periodischer Fallback-Trigger) rief `hass.async_create_task()` ohne `@callback`-Decorator auf — Home Assistant führt undekorierte Trigger-Callbacks im Executor-Thread aus, von dort ist `async_create_task` nicht thread-safe. Betraf ausschließlich Installationen mit aktiviertem periodischen Trigger (ab Werk deaktiviert). `@callback` ergänzt, analog zur bereits korrekten Schwester-Methode `_on_state_change()`

## [2.2.5] – 2026-08-20

### Behoben
- Live-Vorschau (`index.html`): fehlendes `<meta charset="utf-8">` — Umlaute, Gedankenstriche und Emoji (z. B. in der neuen Verteilungs-Modus-Zeile) konnten je nach Browser-/Locale-Fallback als Mojibake dargestellt werden, da weder der HTTP-Header noch die HTML-Datei eine Zeichenkodierung deklarierten. Betrifft nur die Vorschau, nicht die echte Integration — deren Panel läuft im bereits UTF-8-deklarierten Home-Assistant-Frontend-Dokument
- Live-Vorschau (`index.html`): der angezeigte Verteilungs-Modus (`dist_mode_effective`) war beim Seitenaufbau einmalig hartkodiert statt bei jeder Statusabfrage neu aus der Demo-Konfiguration berechnet — Modusänderungen im Verteilungs-Tab spiegelten sich dadurch nicht in der Übersicht wider. Neue Funktion `computeDistModeEffective()` bildet die Backend-Degradationslogik nach und wird bei jedem `get_status`-Aufruf neu ausgewertet
- Übersichtsseite: die Gesamt-Karte verglich den konfigurierten Verteilungs-Modus (`distModeConfigured`) inklusive ungespeicherter Änderungen im Verteilungs-Tab-Formular mit dem tatsächlich angewandten Modus (`dist_mode_effective`, immer der gespeicherte Backend-Zustand) — eine ungespeicherte Dropdown-Änderung erschien dadurch fälschlich als Degradations-Warnung, obwohl das Backend weiterhin im gespeicherten Modus regelte. `distModeConfigured` liest jetzt ausschließlich den gespeicherten Verteilungs-Config-Stand (`_distConfig`), nicht mehr ungespeicherte Edits (`_distDirty`)
- Geräteansicht: nach dem Wechsel von einem anderen Gerät blieb im Tab-Balken (Status/Einstellungen/Debug/…) der zuletzt angeklickte Tab des vorherigen Geräts eingefärbt, obwohl bereits der Status-Tab angezeigt wurde — die `.active`-Klasse im Tab-Balken wurde nur beim Tab-Klick selbst aktualisiert, nicht beim programmatischen Geräte-Wechsel
- Übersichtsseite: bei mehreren Instanzen konnte ein Klick auf ein Gerät während des laufenden 1-Sekunden-Pollings sporadisch wieder von der Übersicht überschrieben werden — die Statusabfrage aller Instanzen prüfte nur zu Beginn, ob die Übersicht noch aktiv ist, nicht mehr nach der (bei mehreren Geräten spürbar dauernden) Abfrageschleife
- Geräteansicht: dieselbe Race Condition steckte noch an vier weiteren Stellen, die alle ungeprüft nach einem `await` in geräteübergreifend geteilten Zustand (`_settings`, `_status`) schrieben — wechselte der Nutzer währenddessen auf ein anderes Gerät, konnten veraltete oder falsche Messwerte/Einstellungen des vorherigen Geräts im Status-/Einstellungs-Tab des neuen erscheinen: der reguläre Statuspoll pro Einzelgerät (`_loadStatus()`), das Nachladen der Einstellungen beim Geräte-Wechsel (`_loadConfig()`), das Speichern der Einstellungen (`_saveSettings()`) sowie das Umschalten der Regelung (`_toggleRegulation()`) und der Zone-Debug-Schalter (`_toggleCycle()`). Alle fünf Stellen halten die Geräte-ID jetzt vor dem `await` fest und verwerfen die Antwort, wenn der Nutzer inzwischen gewechselt hat

## [2.2.4] – 2026-08-20

### Hinzugefügt
- Übersichtsseite: Gesamt-Karte je Netzgruppe zeigt jetzt zusätzlich den SOC-Mittelwert (kapazitätsgewichtet, mit Fallback auf ungewichteten Mittelwert bei fehlendem/ungültigem Kapazitätssensor — Kennzeichnung „⌀") und den aktuell angewandten Verteilungs-Modus, inkl. Anzeige einer Degradation wenn dieser vom konfigurierten Modus abweicht (`Kapazitätsgewichtet → SOC-gewichtet ⚠️`). Neues Coordinator-Attribut `dist_mode_effective`, im `get_status`-WS-Payload exponiert. Gesamt-Karte erscheint jetzt außerdem bereits ab zwei Instanzen **innerhalb einer** Netzgruppe, nicht mehr erst ab zwei Netzgruppen (Discussion #21)

### Geändert
- Übersichtsseite: die Gesamtwerte je Netzgruppe (Ausgangsleistung, Netzleistung) erscheinen jetzt als eigene Karte im selben Zeilen-Layout wie die Einzelgeräte-Karten (Bezeichnung, Wert je eigener Zeile) statt als eine zusammengedrängte Kopfzeile (Discussion #21)
- Live-Vorschau (`index.html`): Szenario-Schalter unten rechts, um zwischen den drei strukturell unterschiedlichen Panel-Zuständen zu wechseln — 1 Instanz, 2 Instanzen/1 Netzgruppe, 3 Instanzen/2 Netzgruppen. Auch per `?scenario=single|single-group|multi-group` direkt verlinkbar; `?multigroup=1` bleibt als Alias auf `multi-group` erhalten
- Live-Vorschau: Verteilungs-Config aller Netzgruppen wird jetzt beim Verbinden vorab geladen statt erst beim Öffnen des Verteilungs-Tabs — Voraussetzung für den SOC-Mittelwert/Verteilungs-Modus auf der Übersicht

### Behoben
- Übersichtsseite: beim Wechsel zu „Übersicht" blieb bei mehreren Netzgruppen der zuletzt aktive Gruppen-Tab weiterhin optisch markiert und die zugehörige Verteilungs-/Instanzen-Unterleiste sichtbar (Discussion #21). `_switchInstance()` setzt die aktive Gruppe jetzt beim Wechsel zur Übersicht zurück
- Übersichtsseite: der Netzleistungswert im Gruppen-Gesamtwert stammte von einer beliebigen Instanz der Gruppe statt vom gemeinsamen Netzsensor selbst — je nach Render-Zeitpunkt der unabhängig pollenden Instanzen zeigte er dadurch inkonsistente, unterschiedlich alte Werte (Discussion #21). Wird jetzt direkt aus dem HA-State des Netzsensors gelesen
- Verteilungs-Tab: die Speicherleiste bei den globalen Sensoren zeigte dauerhaft „ungespeicherte Änderungen", auch direkt nach dem Speichern (Discussion #21). Die Sichtbarkeitsprüfung zählte fälschlich alle jemals geladenen Gruppen statt der tatsächlich geänderten Felder der aktiven Gruppe
- Live-Vorschau (`index.html`): Demo-Verteilungs-Config nutzte den ungültigen Wert `distribution_mode: "weighted"` mit einer nicht existierenden `capacity_weighting`-Eigenschaft — entsprach nicht dem echten Schema (`equal`/`soc`/`capacity`/`soc_switch`). Korrigiert auf `"capacity"`

## [2.2.3] – 2026-08-20

### Behoben
- Dynamischer Offset: bei mehreren Instanzen am selben Netzsensor berechnete jede Instanz unabhängig ihre eigene StdDev aus einem eigenen Ringpuffer — leicht phasenversetzt zueinander, da nicht synchronisiert. Die Korrekturen einer Instanz sahen dadurch für die andere wie externe Netzunruhe aus und hielten den Offset gegenseitig oben, auch ohne reale Störung (Issue #24, gemeldet von `dbatosc`). `_update_stddev()` läuft jetzt nur noch beim deterministisch bestimmten Gruppen-Leader (kleinste entry_id unter den aktiv regelnden Instanzen der Netzgruppe, neue Methode `_group_leader()`), alle anderen Instanzen der Gruppe übernehmen dessen `grid_stddev`. Einzelbetrieb unverändert (Instanz ist immer ihr eigener Leader). Feldverifikation durch den Reporter steht aus

## [2.2.2] – 2026-08-20

### Behoben
- Übersicht/Verteilungsseite konnte durch verzögerte Config-/Save-Antworten (`_loadConfig`, `_saveSettings`, `_saveDistConfig`, `_loadDistConfig`) mit der zuletzt aktiven Instanz-Detailansicht überschrieben werden, wenn der Nutzer währenddessen zur Übersicht oder Verteilung wechselte — Tab-Leiste zeigte weiterhin „Übersicht"/„Verteilung" als aktiv, der Inhalt aber die alte Instanzansicht (Discussion #21, gemeldet von `githubalf`). `_renderActiveTab()` und `_rerenderDist()` prüfen jetzt vor dem Schreiben in `#content`, ob die jeweilige View noch aktiv ist
- Panel-JavaScript wurde nach einem Update im Browser nicht zuverlässig neu geladen — `module_url` zeigte immer auf dieselbe URL (`/solakon_nulleinspeisung/panel.js`), unabhängig von der installierten Version, sodass Browser sie über Neuladen und HA-Neustart hinweg als unverändert behandeln konnten (mutmaßliche Hauptursache für „keine Änderung sichtbar" trotz Update in Discussion #21 — Tab-Leiste des Reporters entsprach exakt der v2.2.0-Struktur ohne Verteilungs-Tab). `module_url` trägt jetzt die Integrationsversion als Query-Parameter (`?v={VERSION}`), erzwingt damit bei jedem Versions-Sprung eine neue URL und garantiert einen frischen Fetch

## [2.2.1] – 2026-08-19

### Hinzugefügt
- Netzgruppen (Discussion #21): Instanzen werden automatisch nach ihrem konfigurierten Netz-Leistungssensor gruppiert — Fehleraufteilung und Leistungsverteilung (`_compute_distribution`, `_compute_ac_distribution`, `_total_actual_power`, `_total_commanded_power`, `_total_commanded_ac_power`) laufen ab sofort nur noch innerhalb einer Gruppe statt über alle installierten Instanzen hinweg. Die Verteilungs-Konfiguration (Limit, Verteilungs-Modus, Kapazitätssensoren, globale Sensor-Vorgaben) ist jetzt pro Gruppe unabhängig einstellbar. Bei nur einer Gruppe (Normalfall) rechnerisch identisch zum bisherigen Verhalten. Panel: Verteilung ist jetzt ein eigener Tab (statt Teil der Übersichtsseite); bei mehreren Gruppen ersetzt eine Gruppen-Tab-Ebene die Instanz-Tabs, jede Gruppe öffnet darunter „Verteilung" + ihre Instanzen. Übersichtsseite zeigt Instanzen jetzt nach Gruppe sortiert mit Gesamt-Leistungsanzeige je Gruppe. Bestehende Verteilungs-Einstellungen werden beim Update automatisch auf alle zu diesem Zeitpunkt bekannten Gruppen übertragen (kein Reset)
- Neuer Sensor `sensor.solakon_one_uberschussleistung` (Discussion #22): verwertbarer PV-Überschuss in W — `min(aktuell geltendes Hard-Limit, PV-Leistung) − Ausgangsleistung`, geklemmt auf ≥0. Für Automationen gedacht (z. B. Zusatzverbraucher bei Überschuss schalten), keine Diagnose-Entität

## [2.2.0] – 2026-08-11

### Hinzugefügt
- Neuer Verteilungs-Modus „SOC-Umschaltung" (Issue #14): Statt alle Instanzen parallel gewichtet zu entladen, entlädt immer nur eine Instanz exklusiv, bis ihr SOC seit Übernahme um eine einstellbare Divergenz-Schwelle (Prozentpunkte, Standard 5) gefallen ist — dann übernimmt die Instanz mit dem höchsten verbleibenden SOC. Baut auf der in v2.1.9 gefixten Gruppen-Sollwert-PI-Basis (Issue #19) auf, die harte Anteilswechsel (0 % ↔ 100 %) sauber und ohne Nachlauf verarbeitet. Aktive Instanz + ihr Start-SOC sind Pool-weit über einen eigenen Store persistiert, unabhängig vom `_dist_config`-Store der Nutzereinstellungen, und überstehen HA-Neustarts. Zone-3-Sicherheitsstopp (Fall B/C) übergibt automatisch an die nächste Instanz, da die gestoppte Instanz den Modus-1-Pool verlässt. Zone 0 (Überschuss-Einspeisung) hat absoluten Vorrang vor der regulären Entladung anderer Instanzen — konsistent mit dem bestehenden Zone-0-Vorrang gegenüber AC-/Tarif-Laden derselben Instanz: eine einzelne Zone-0-Instanz übernimmt bedingungslos und sofort die Führung; sind mehrere Instanzen gleichzeitig in Zone 0, teilen sie sich den Anteil gleichmäßig statt exklusiv (Wechselrichterverlust bei diesen kleinen Leistungen vernachlässigbar, vermeidet eine 0-W-Zwangslage mit Abschaltrisiko). Das gemeinsame Leistungslimit (`global_max_power`) bleibt dabei unverändert über die reguläre `_compute_distribution`-Formel gewahrt

### Behoben
- SOC-Umschaltung: Verlässt die aktive Instanz Zone 0 und geht in die reguläre Rotation über, wurde die Divergenz-Baseline (`start_soc`) nicht zurückgesetzt, sondern blieb auf dem SOC-Wert beim Zone-0-Eintritt stehen. Da Zone 0 selbst spürbar SOC verbraucht (Ausgabe auf `effective_hard`, nicht nur den 2-A-Puffer), war beim Rückkehr in die Rotation bereits ein Teil des Divergenz-Budgets „verbraucht" — die nächste Rotation löste dadurch früher aus als die konfigurierte Schwelle vorsieht. Neues `was_zone0`-Flag im Store-Zustand erkennt den Übergang und verankert `start_soc` beim Verlassen von Zone 0 neu, unabhängig davon ob die zurückkehrende Instanz zuvor alleiniger oder einer von mehreren Zone-0-Teilnehmern war
- Verteilungs-Degradation war für den Nutzer unsichtbar: fiel bei `soc`/`capacity`/`soc_switch`-Modus der SOC- oder Kapazitätssensor einer *fremden* Instanz kurzzeitig auf `unknown`/`unavailable`, degradierte der gesamte Pool für diesen Zyklus stillschweigend auf Gleichverteilung (bzw. Capacity→SOC-Gewichtung) — ohne Log-Eintrag oder Panel-Hinweis. `_all_shares()` (vormals `_weighted_share()`) setzt bei Degradation jetzt einen Warnkanal (`_dist_warning`), der in `_run_regulation_cycle()` in die bestehende `last_error`-Sammelmeldung übernommen wird, für beide Pools (Nulleinspeisung und AC-Laden)
- Heterogene Hard-Limits (`hard_limit_z0`/`hard_limit_z1`) zwischen Instanzen führten dazu, dass eine kapp-limitierte Instanz (z. B. schwächerer Wechselrichter) ihren rechnerischen Anteil an `global_max_power` nicht ausschöpfen konnte — der ungenutzte Rest verfiel, statt an Instanzen mit Reserve weiterzureichen. Bei gemischter Hardware erreichte der Pool `global_max_power` dadurch strukturell nie, selbst wenn andere Instanzen noch Kapazität gehabt hätten. `_compute_distribution()` verteilt jetzt über ein Wasserfüllverfahren (`_waterfill_allocate()`): kapp-limitierte Instanzen werden auf ihr Hard-Limit gesetzt, der Rest wird unter den verbleibenden Instanzen proportional zu ihrem Anteil neu aufgeteilt (iterativ, bis kein Rest mehr verteilbar ist). Bei gleich dimensionierten Instanzen (Normalfall) identisches Ergebnis wie zuvor

## [2.1.9] – 2026-08-11

### Behoben
- Fall 0B (Surplus Ende) setzte den Output anders als alle übrigen Zonenwechsel-Falls (B/C/F/G/H) nicht explizit auf 0 zurück — der Zone-0-Wert (nahe Hard-Limit-Z0) blieb bis zur nächsten PI-Korrektur stehen. Im Multi-Instanz-Betrieb ein Einstiegspunkt für die in Issue #19 gemeldete Verteilungs-Drift (Fall-G/#16 hatte dasselbe Muster). `_set_output(0)` ergänzt
- Latch-Flag `_solar_zero_entry_armed` (Zone-0-`PV = 0`-Entprellung, Issue #17) war reiner In-Memory-Zustand und wurde bei jedem HA-Neustart wieder auf `True` initialisiert, unabhängig vom tatsächlichen PV-Zustand — konnte den in #17 gefixten nächtlichen Oszillations-Loop einmalig zurückbringen, wenn ein Neustart ins Beobachtungsfenster fiel (Issue #20). Flag wird jetzt über die bestehende `Store`-Infrastruktur persistiert; dafür auch in den bisher auf die vier Haupt-Flags beschränkten Speicher-Trigger-Vergleich (`_prev_flags`) aufgenommen, da es sich unabhängig von `cycle_active`/`surplus_active`/etc. ändern kann
- Multi-Instanz-Verteilungs-Drift (Issue #19): Der normale Nulleinspeisungs-PI baute die Korrektur bisher auf dem eigenen zuletzt kommandierten Wert der Instanz auf — rein inkrementell, ohne jeden Abgleich gegen den tatsächlichen Soll-Anteil. Eine einmal entstandene Asymmetrie zwischen Instanzen (z. B. durch zeitversetzte Rückkehr aus einem Zonenwechsel) pflanzte sich dadurch beliebig lange fort. Neue Ausgangsbasis: `(Σ kommandierte Leistung aller Instanzen im Pool) × eigener Fehler-Anteil` statt des eigenen Werts — gleicht die Aufteilung bei jedem Stelleingriff automatisch wieder an die Gewichtung an. Neue Hilfsfunktion `_total_commanded_power()` (analog zur bestehenden `_total_actual_power()`, aber auf dem kommandierten statt dem gemessenen Wert, um keine Sensor-Latenz/kein -Rauschen in die PI-Basis einzuschleusen). Im Einzelbetrieb ohne Wirkung (Ausgangsbasis identisch zum bisherigen Wert)
- Dieselbe Verteilungs-Drift wie Issue #19, aber im AC-Lade-Pool (Pool 2, mehrere gleichzeitig ladende Instanzen) — beim systematischen Durchgehen aller Falls gefunden, bisher ungemeldet. Gleicher Fix, eigene Hilfsfunktion `_total_commanded_ac_power()` (Pool nach `ac_charge_active` statt Modus `'1'`)

## [2.1.8] – 2026-07-29

### Hinzugefügt
- Neues Setting `zone1_force_min_soc`: eigener, unabhängig einstellbarer Sicherheits-Floor für die Zone-1-Nacht-Forcierung (Default 20 %). Bisher wurde dafür die Zone-3-Schwelle wiederverwendet — die aber als Austritts-/Sicherheitsstopp-Schwelle eine andere Rolle hat und frei von 1–49 % einstellbar ist, wodurch der Forcierungs-Floor im Extremfall bei 1 % SOC gelegen hätte (Bereich, in dem die SOC-Schätzung unzuverlässig wird). Validierung: muss strikt zwischen Zone-3- und Zone-1-Schwelle liegen, sonst Fehlermeldung analog zu den bestehenden SOC-Limit-Checks

### Behoben
- `zone1_force_threshold` hatte Default `5000.0`, während der zugehörige UI-Slider nur 0–50 kWh zulässt (Wert außerhalb des eigenen Wertebereichs, blind von `pv_forecast_threshold`/`surplus_forecast_threshold` übernommen) — Feature blieb bei Werkseinstellung und aktiviertem Enable-Flag wirkungslos, da kein realer Vorhersage-Sensor je ≥5000 kWh meldet. Default auf `15.0` korrigiert
- SOC-Zahlenfelder (`zone1_limit`, `zone3_limit`, `zone1_force_min_soc`, `surplus_soc_threshold`, `ac_soc_target`, `tariff_soc_target`) hatten uneinheitliche, willkürlich enge UI-Slider-Bereiche (z. B. `zone3_limit`/`zone1_force_min_soc` nur bis 49 %, `surplus_soc_threshold`/`ac_soc_target`/`tariff_soc_target` erst ab 50 %) — Restriktion gehörte in die bestehende gegenseitige Validierung (`zone1_limit`/`zone3_limit`/`surplus_soc_threshold` in `coordinator.py`), nicht ins UI. Alle sechs Felder jetzt einheitlich 0–100 %, Abhängigkeiten weiterhin ausschließlich über die Coordinator-Validierung erzwungen. `surplus_soc_hyst` unverändert (Hysterese-Differenz, kein absoluter SOC-Wert)
- README (Zone-0-Abschnitt): Behauptung „Batterie bleibt während einer Wolke unangetastet" korrigiert — widersprach dem bereits dokumentierten 2-A-Stabilitätspuffer, der die Batterie unabhängig von PV kontinuierlich entlädt

### Geändert
- README (Zone-0-Abschnitt): Klarstellung ergänzt, warum die 2-A-Entladefreigabe (Obergrenze, kein fester Sollwert) existiert und nicht 0 sein darf — bei vollem Akku kann kein Strom mehr hineinfließen, der Solakon kann PV aber nur regeln solange Batteriestrom fließt; ohne diesen Stromfluss schaltet das Gerät komplett ab, die 2 A sind bewusst niedrig gewählt um die Batterie dabei minimal zu belasten

## [2.1.7] – 2026-07-29

### Hinzugefügt
- Zone-1-Nacht-Forcierung (Issue #80): erlaubt den Zone-1-Entladezyklus auch unter der normalen Zone-1-Schwelle, wenn die PV-Vorhersage für den Zieltag zeigt, dass die Nacht ohnehin wieder aufgefüllt wird — verhindert ungenutzt liegen gebliebene Kapazität nach einem wolkigen Tag mit gutem Folgetag. Neue Settings `zone1_force_enabled`/`zone1_force_sensor`/`zone1_force_threshold`, neuer Fall-A-Zusatzpfad, neuer Diagnose-Binärsensor. Der Vorhersage-Sensor wechselt an der Mitternachtsgrenze automatisch zwischen "morgen" und "heute" (derselbe Zieltag — der "morgen"-Sensor würde nach Mitternacht sonst auf den übernächsten Tag zeigen), Mittag als Umschaltpunkt.
- Instanzübergreifende globale Sensor-Vorgaben im Verteilungs-Tab (Multi-Instanz): PV-Vorhersage heute/morgen, Leistungs-Vorhersage jetzt, Strompreis-Sensor, dynamische Preisschwellen — jede Instanz kann optional lokal überschreiben, sonst gilt der globale Wert. Reduziert Konfigurationsaufwand bei mehreren Instanzen desselben Haushalts (ein Wetter-/Tarif-Sensor statt N identischer Einzelkonfigurationen).
- Neues Panel-Tab „Entitäten" bündelt alle optionalen Entity-Picker-Felder dieser Instanz (`pv_forecast_sensor`, `zone1_force_sensor`, `surplus_lock_sensor`, `tariff_price_sensor`, `tariff_cheap_entity`, `tariff_exp_entity`) an einer Stelle, statt sie über Zonen-, Überschuss- und Tarif-Tab verstreut zu pflegen — flache Liste analog zur „Globale Sensoren"-Karte im Verteilungs-Tab, nicht nach Feature gruppiert. Enable-Flags und Zahlen-Schwellen bleiben in ihrem jeweiligen Feature-Tab, die dortigen Felder verweisen nur noch auf das neue Tab.

### Geändert
- `surplus_forecast_sensor` und `pv_forecast_sensor` zu einem gemeinsamen Feld verschmolzen (beide lasen denselben Werttyp — PV-Ertrag heute in kWh — für zwei unterschiedliche Features). Bestehende `surplus_forecast_sensor`-Werte werden beim ersten Start nach dem Update automatisch übernommen, sofern `pv_forecast_sensor` noch leer ist.
- Sichtbare Fehlermeldung bei fehlendem/ungültigem Sensor auf Surplus-Forecast-Erzwingung, Austritts-Sperre und PV-Vorhersage ausgeweitet — bisher scheiterten diese drei Features bei aktivem Enable-Flag, aber leerem oder nicht verfügbarem Sensor, still (Flag einfach wirkungslos, kein Hinweis). Bisher galt das nur für den Tarif-Preis-Sensor. Da `last_error` ein einzelner String ist, werden mehrere gleichzeitig zutreffende Fehler jetzt mit „ • " verkettet statt sich gegenseitig zu überschreiben — so bleibt sichtbar, dass es sich um mehrere getrennte Probleme handelt
- Entitäten-Tab-Feldbeschreibungen auf „speist Feature X (Tab)" gekürzt, ausführliche Verhaltenserklärungen bleiben im jeweiligen Feature-Tab. Verweis-Hinweise auf den Feature-Tabs (Zonen/Surplus/Tarif) nennen jetzt explizit den exakten Feldnamen aus dem Entitäten-Tab und was ohne Zuweisung passiert (z. B. „Ohne Entität „PV-Vorhersage morgen“ (Entitäten-Tab) bleibt diese Funktion inaktiv.") statt nur unspezifisch auf „einen Sensor“ zu verweisen. Überschuss-Tab, Sektion „PV-Vorhersage" (`surplus_forecast_enabled`) hatte gar keinen solchen Verweis und referenzierte in der eigenen Beschreibung noch das veraltete „siehe Tarif-Tab" (Sensor lag dort vor der Entitäten-Tab-Umstellung) — beides korrigiert
- Tab-Leiste (`.tab-bar`) bleibt jetzt einzeilig mit horizontalem Scroll statt bei zehn Tabs umzubrechen (`flex-wrap: nowrap` + `overflow-x: auto`); Scrollbar reserviert per `scrollbar-gutter: stable` eigenen Platz statt als Overlay zu überlappen, und ist per `::-webkit-scrollbar`/`scrollbar-width` dauerhaft sichtbar statt automatisch auszublenden
- `pv_forecast_sensor`-Beschreibung (lokal und global im Verteilungs-Tab) ergänzt um den dritten Consumer Zone-1-Nacht-Forcierung (0–12 Uhr) — fehlte in beiden Varianten

### Behoben
- Fall-G-Eintritt (AC Laden Start) im Multi-Instanz-Betrieb: Bedingung `(grid + actual) < −ac_hysteresis` verglich den eigenen Output der prüfenden Instanz statt der Summe aller Instanzen im Entlademodus (Issue #16). Dadurch konnte eine Instanz die Entladung einer Schwester-Instanz als externen Netzüberschuss werten und daraufhin genau diese Menge aus dem Netz nachladen — Batterie-zu-Batterie-Umpumpen mit doppelten Wandlungsverlusten, sowohl nachts (reale Schwester-Entladung) als auch tagsüber bei Lasttransienten (kurzzeitiger eigener Regel-Nachlauf nach Lastabwurf). Fix: `actual` durch `self._total_actual_power()` ersetzt, analog zur bereits korrekten Zone-0-Referenz. Die Fall-H-Abbruchbedingung bleibt unverändert auf den eigenen Output bezogen (prüft das Ende der eigenen Ladesession)
- Zone-0-Eintritt oszillierte nachts bei vollem Akku im Sekundentakt (Issue #17): Der `PV = 0`-Sonderzweig (deckt PV-Hardwaredrosselung bei vollem Akku ab, Issue #11) nutzte eine reine Zwei-Zyklen-Entprellung über `Output = 0`, die nachts nicht ausreichte — nach einem Austritt genügte ein einzelner erneuter Nullwert der Ausgangsleistung, um sofort wieder einzutreten. Fix: Zusätzlicher Latch — der Zweig bleibt nach jedem Austritt bei `PV = 0` gesperrt, bis erneut echtes `PV > 0` gemessen wurde (tagsüber sofort der Fall, nachts erst bei Sonnenaufgang). SOC- und Verbrauchs-Austritt bleiben unverändert

### Entfernt
- Einmalige Migration des alten Zonen-Tab-Kapazitätssensors (`battery_capacity_sensor`) ins Verteilungs-Tab: seit v2.1.5 überflüssig, jede seitdem aktualisierte Installation hat sie bereits durchlaufen

## [2.1.6] – 2026-07-22

### Behoben
- Race Condition beim parallelen Setup mehrerer Instanzen (Issue #15): `hass.data[..._dist_config]` entstand erst nach einem `await store.async_load()`, während der Store-Guard schon vorher gesetzt wurde. Startete eine zweite Instanz in diesem Zeitfenster (z. B. HA-Neustart, Stromausfall-Wiederanlauf), sah sie den Guard bereits gesetzt, übersprang die Initialisierung und griff auf den noch nicht existierenden Key zu → `KeyError`, Setup schlug mit `setup_error` fehl. Fix: `_dist_config` wird jetzt synchron mit Defaults angelegt, bevor der `await` den Event-Loop abgibt

## [2.1.5] – 2026-07-20

### Behoben
- Verteilungs-Tab: „Kapazitätsausgleich"-Checkbox war unabhängig vom Verteilungs-Modus-Dropdown, steuerte im Backend aber nichts eigenständig — bei Modus „SOC-gewichtet" wurden konfigurierte Kapazitätssensoren immer mitverwendet, auch mit deaktivierter Checkbox (gefunden bei der Analyse von Issue #14 — behebt die Ursache dieses Konfigurations-Widerspruchs, nicht notwendigerweise die im Issue beschriebene SOC-Divergenz selbst)
- `_weighted_share()`: Kapazitätssensor-Unit-Vergleich war ein exakter String-Match auf `"kWh"` — jede Abweichung (Groß-/Kleinschreibung, `"Wh"`, kein Unit gesetzt) führte zu einer stillen 1000×-Fehlinterpretation. Jetzt toleranter: Unit wird vor dem Vergleich kleingeschrieben (daher Vergleich gegen `"wh"`, nicht `"Wh"`), nur bei erkanntem `"wh"` wird umgerechnet, alles andere als bereits-kWh behandelt
- `_weighted_share()`: SOC-Read anderer Instanzen prüfte anders als jeder sonstige Sensor-Zugriff im Coordinator nicht auf `unknown`/`unavailable` — eine unsichere Fremdinstanz-SOC fällt jetzt auf Gleichverteilung zurück statt mit einer falschen 0 weiterzurechnen

### Geändert
- Verteilungs-Modus ist jetzt ein einzelnes Dropdown mit drei sich gegenseitig ausschließenden Optionen: Gleichverteilung / SOC-gewichtet (reine Prozentpunkte, keine Kapazitätssensoren) / Kapazitätsgewichtet (zusätzlich × Batteriekapazität). Ersetzt die bisherige Kombination aus Zwei-Optionen-Dropdown + separater Checkbox. Kapazitätssensor-Felder sind nur noch bei „Kapazitätsgewichtet" aktiv, sonst ausgegraut. Bestehende Configs werden beim Start automatisch migriert.

## [2.1.4] – 2026-07-14

### Behoben
- `manifest.json`: `http`-Komponente als Dependency ergänzt — Panel nutzt `hass.http.async_register_static_paths` direkt, ohne dass `http` explizit deklariert war (Hassfest-Validierungsfehler, aufgefallen bei der Aufnahme ins HACS-Default-Repository)
- `manifest.json`: Reihenfolge der Schlüssel alphabetisch sortiert (nach `domain`/`name`), wie von Hassfest gefordert

## [2.1.3] – 2026-07-14

### Behoben
- Übersichtsseite wurde bei jedem 1-s-Poll komplett neu gerendert — Eingabefelder im Verteilungsblock verloren dadurch sekündlich den Fokus, sobald die Übersicht sichtbar war. Live-Werte (Zone, SOC, Output, Grid, Fall) werden jetzt gezielt in bestehende Elemente gepatcht, statt das DOM neu aufzubauen (Issue #13)
- Instanz-übergreifende Übersichtsseite zeigte weiterhin den Titel-/Regelungs-Block ("Regelung aktiv", Info-Accordion) und die Config-Tab-Leiste (Status/PI-Regler/Zonen/...) der zuletzt aktiven Einzelinstanz — beides bezieht sich auf eine einzelne Instanz und ist auf der Übersicht bedeutungslos bzw. irreführend. `_switchInstance()` blendet beide Blöcke jetzt beim Wechsel auf "Übersicht" aus und beim Zurückwechseln auf eine Instanz wieder ein

### Hinzugefügt
- Surplus-Austritts-Sperre (optional, Issue #11): Solange eine PV-Leistungs-Vorhersage ≥ Sperr-Faktor × Hard Limit Z0 (Standard 1,5, einstellbar) UND SOC > Zone-3-Schwelle, ist nur der PV-Austritt aus Zone 0 gesperrt — kurze PV-Einbrüche (Wolken) werden durchgeritten statt auszutreten. Hintergrund: Der Austritt bei vollem Akku führt in einen Zustand, in dem die Hardware die PV auf den Eigenbedarf drosselt und der Überschuss nicht mehr messbar ist; der Wiedereintritt verzögert sich dann um Minuten. Der SOC-Austritt bleibt ungesperrt, bei nicht verfügbarem Sensor ist die Sperre inaktiv. Neue Panel-Felder (Schalter, Sensor mit Validierungspunkt, Faktor), Status-Flag und Diagnose-Binärsensor
- Live-Validierungspunkte an allen Entity-Eingabefeldern (Config-Tabs und Kapazitätssensoren im Verteilungs-Tab): grün = Entity liefert einen Wert, gelb = existiert, aber `unknown`/`unavailable`, rot = existiert nicht. Aktualisieren beim Tippen und im Polling — macht Tippfehler in Entity-IDs sofort sichtbar (Issue #13). In der Live-Vorschau (`index.html`) mit allen drei Zuständen abgebildet

### Geändert
- README/Panel: Empfehlung für die Surplus-SOC-Schwelle präzisiert — ~5 % unter der App-Ladeobergrenze (z. B. 95 % bei Max 100 %) statt pauschal 90–98 %, mit Begründung (Eintritt nur messbar solange der Akku lädt; am Vollladepunkt drosselt die Hardware die PV auf den Eigenbedarf)
- Batteriekapazitätssensor war doppelt konfigurierbar: einmal pro Instanz im Zonen-Tab (`battery_capacity_sensor`), einmal pro Instanz im Verteilungs-Tab — mit Fallback auf den Instanz-Wert, aber ohne Vorbefüllung. Ein Tippfehler in nur einem der beiden Felder brach die Kapazitätsgewichtung unbemerkt. Feld aus dem Zonen-Tab entfernt; einziger Konfigurationsort ist jetzt das Verteilungs-Tab. Bereits gesetzte Zonen-Tab-Werte werden beim ersten Start nach dem Update automatisch ins Verteilungs-Tab übernommen, sofern dort noch kein Wert hinterlegt ist

## [2.1.2] – 2026-07-08

### Behoben
- AC-Lade-Fehler-Anteil von der Nulleinspeisungs-Verteilung entkoppelt: bisher galt eine Instanz im Modus `'3'` für die Multi-Instanz-Verteilung als „inaktiv" und bekam `error_share = 0` — der AC-Lade-PI-Regler fror dadurch bei 0 W ein, sobald die Leistungsverteilung aktiv war. Jetzt eigener Pool, der nur unter gleichzeitig AC-ladenden Instanzen aufgeteilt wird (`_compute_ac_distribution`)
- Aktiv-Kriterium der Nulleinspeisungs-Verteilung korrigiert: `_compute_distribution`/`_total_actual_power` prüften bisher nur `regulation_enabled`, nicht den tatsächlichen Modus — eine Sekundärinstanz in Modus `'0'` oder `'3'` verwässerte dadurch fälschlich den `error_share` der echten Modus-`'1'`-Teilnehmer. Jetzt zusätzlich `mode == '1'` erforderlich, analog zum Blueprint
- Panel-Eingabefelder (`hard_limit_z0`, `hard_limit_z1`, `ac_power_limit`, `tariff_power`) erlaubten bis zu 2000 W — reale AC-Hardwaregrenze des Solakon ONE ist 1200 W in beide Richtungen. Slider-Obergrenzen entsprechend korrigiert
- Fall-D-Recovery erfordert bei aktiver AC-/Tarif-Lade-Session keine Zone-3-Schwelle mehr — vorher blieb der Modus bei niedrigem SOC dauerhaft auf `'0'` hängen, obwohl `ac_charge_active`/`tariff_charge_active` noch `True` waren (z. B. nach Deaktivieren/Reaktivieren der Regelung während laufendem Laden), und keine der übrigen Falls konnte den Zustand auflösen
- Entladestrom wird in der Deaktivierungs-Sequenz (`Regelung aktiv = Aus`) explizit auf Max-Entladestrom zurückgesetzt — verhindert, dass ein während AC-/Tarif-Laden auf 0 A geklemmter Wert nach dem Deaktivieren dauerhaft stehen bleibt (Issue #10)
- Zone 0 als Overlay über Zone 1 erzwungen: Fall 0A aktiviert `cycle_active`, Fall 0B leitet die Zone beim Austritt aus dem SOC neu ab — schließt hängende Zustände, in denen Surplus aktiv war, aber weder Nachtabschaltung (Fall F) noch Recovery (Fall D) den Zustand kannten
- Forecast-Forcierung an SOC > Zone-3-Schwelle gekoppelt — beendet das Modus-Flattern 0A ↔ C, wenn die Forcierung bei tiefentladener Batterie gegen den Zone-3-Sicherheitsstopp ankämpfte
- Neue Validierung: Export-Schwelle (Surplus) muss über der Zone-1-Schwelle liegen, analog zur bestehenden Zone1-/Zone3-Prüfung
- Tarif-Lock der Fall-D-Recovery verschont aktiven Surplus (konsistent zu Fall TM) — Modus-Wiederherstellung in Zone 0 wird nicht mehr durch mittlere Strompreise blockiert

### Geändert
- Einstellungsänderungen (Hauptschalter, Panel-Save) stoßen sofort einen Regelzyklus an, statt auf das nächste Sensor-Event zu warten — gleiche Mechanik wie beim manuellen Zonenwechsel und beim Verteilungs-Save
- Zone 0 schreibt den Output nur noch bei Abweichung vom Sollwert — vorher identischer Modbus-Schreibbefehl plus Wartezeit bei jedem Regelzyklus, solange Surplus aktiv war
- AC-Lade-Pfad wartet nur noch nach einem tatsächlichen Stelleingriff (wie der normale PI-Pfad) und baut das Integral in Toleranzphasen per Decay ab
- Timeout-Reset (Schritt 9) entfällt, wenn ein Fall im selben Zyklus bereits einen Timer-Toggle ausgeführt hat — kein Doppel-Toggle mit stalem Countdown-Wert mehr
- HACS-Validierungs-Workflow nach `.github/workflows/` verschoben (lag im Repo-Root und wurde von GitHub Actions nie ausgeführt); Brands-Prüfung ausgenommen
- `manifest.json` (documentation, issue_tracker) und Config-Flow-Hinweis verlinken jetzt auf das Integrations-Repo statt auf das Blueprint-Repo
- `.gitignore` ergänzt (`__pycache__/`, `*.pyc`)
- Kapazitätsgewichtung (Multi-Instanz): fehlt der Kapazitätssensor bei irgendeiner aktiven Instanz, zählen alle neutral 1.0 — vorher dominierte eine sensorlose Instanz mit 100-kWh-Fallback die Leistungsverteilung
- OptionsFlow verweigert doppelte `mode_select`-Zuweisung (gleiche Prüfung wie beim Anlegen) — verhindert zwei Instanzen auf demselben Inverter
- Geräteversion aus `manifest.json` gelesen (`sw_version`) statt hartkodiert im Modellnamen
- Tote Symbole entfernt (`S_DIST_*`-Konstanten, `_static_registered`-Aufräumzeile)

## [2.1.1] – 2026-07-03

### Behoben
- Timer-Toggle vor jedem Moduswechsel zu `'0'` erzwungen — alle Falls (B/C/F/H/HT/I/TM) und manuelles Ausschalten (Issue #10)
- Race Condition beim Deaktivieren geschlossen: Regelzyklus prüft `Regelung aktiv` als Erstes und bricht sofort ab
- Disable-Cleanup zentral in `async_update_settings`: auch der Panel-Button setzt jetzt Output 0 → Timer-Toggle → Modus Disabled
- Zone-2-PI: Overshoot am Hard-Limit behoben, sinkende PV wird nachgeführt
- PI-Anti-Windup via Back-Calculation
- Tarif: Discharge-Lock greift auch bei günstigem Preis (#6), Tarif-Logik ohne Preis-Sensor deaktiviert (#5)
- OptionsFlow: Entitäten nach `entry.data` + Reload-Listener, Deprecation-Fix
- Weitere Bugfixes: Forecast-Listener, Flag-Persistenz, Listener-Leak, tote Parameter & Code

### Geändert
- Leistungsverteilung vereinfacht: PV-Gewichtung entfernt, Kapazitätsausgleich ergänzt
- Surplus stabilisiert: gemeinsame Hausverbrauchs-Referenz (Σactual) für Eintritt/Austritt, Entprellung gegen Eintritt-Cycling, PV-Hysterese auf Instanz-Lastanteil skaliert, Forecast-Forcierung ans PV-Hard-Limit gekoppelt
- Entladestrom zentral aus dem Regelzustand abgeleitet statt verstreut gesetzt
- AC-I-Faktor-Default auf 0.0 (sicherer Startwert)
- Doku und Panel-Texte (DE/EN) umfassend an den Code angeglichen

### Hinzugefügt
- Zonen-spezifische Hard-Limits (Zone 0 Surplus / Zone 1+2 Entladung)
- Optionaler periodischer Regelzyklus-Trigger
- Export-Limit-Sync mit Hard Limit

## [2.1.0] – 2026-05-16
- Leistungsverteilungs-Logik aus dem Multi-Instanz-Blueprint nativ implementiert
- `allocated_power` als Sensor-Attribut, Status-Endpoint und Panel-Anzeige
- Panel und README an die neue Verteilungslogik angepasst

## [2.0.2] – 2026-05-15
- kWh-Kapazitätsgewichtung für Multi-Instancing
- Proportionale Fehleraufteilung bei Multi-Instanz-Betrieb
- Panel-Internationalisierung (DE/EN) + Static-Path-Fix

## [2.0.1] – 2026-04-20
- 25 Bugfixes aus vollständigem Code-Review, Deprecation-Fixes, README-Korrekturen
- Live-Demo (`index.html`) ergänzt

## [2.0.0] – 2026-04-10
- Vollständige Steuer-Falls-Architektur mit Prioritätensystem: Überschuss-Einspeisung, Tarif-Laden (GT/TM/Discharge-Lock), AC Laden, Nachtabschaltung
- SOC-Zonen mit Modus-Steuerung und zonenspezifischem Entladestrom (Zone 0 Surplus 2 A, Zone 1 Maximalwert, Zone 2 0 A, Zone 3 Stopp)
- Self-Adjusting Wait: wartet auf die tatsächliche WR-Ausgangsleistung statt fester Wartezeit
- Binary-Sensor-Plattform ergänzt, Number-Plattform entfernt
- Übersetzungen (DE/EN), HACS-Validate-Workflow, Icon/Branding

## [1.1.0] – 2026-04-02
- Dynamischer Offset: Netz-Standardabweichung intern berechnet (`GridStdDevSensor`), zonenspezifische dynamische Offsets

## [1.0.0] – 2026-04-02
- Erstveröffentlichung: PI-Regler mit SOC-Zonen, Sidebar-Panel (Lit-Element), WebSocket-API, Config Flow
