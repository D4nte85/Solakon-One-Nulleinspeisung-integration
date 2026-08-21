# Changelog

Alle nennenswerten Änderungen an der Solakon-ONE-Nulleinspeisung-Integration.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [Unreleased]

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
