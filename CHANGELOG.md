# Changelog

Alle nennenswerten Änderungen an der Solakon-ONE-Nulleinspeisung-Integration.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [Unreleased]

### Behoben
- Fall 0B (Surplus Ende) setzte den Output anders als alle übrigen Zonenwechsel-Falls (B/C/F/G/H) nicht explizit auf 0 zurück — der Zone-0-Wert (nahe Hard-Limit-Z0) blieb bis zur nächsten PI-Korrektur stehen. Im Multi-Instanz-Betrieb ein Einstiegspunkt für die in Issue #19 gemeldete Verteilungs-Drift (Fall-G/#16 hatte dasselbe Muster). `_set_output(0)` ergänzt
- Latch-Flag `_solar_zero_entry_armed` (Zone-0-`PV = 0`-Entprellung, Issue #17) war reiner In-Memory-Zustand und wurde bei jedem HA-Neustart wieder auf `True` initialisiert, unabhängig vom tatsächlichen PV-Zustand — konnte den in #17 gefixten nächtlichen Oszillations-Loop einmalig zurückbringen, wenn ein Neustart ins Beobachtungsfenster fiel (Issue #20). Flag wird jetzt über die bestehende `Store`-Infrastruktur persistiert; dafür auch in den bisher auf die vier Haupt-Flags beschränkten Speicher-Trigger-Vergleich (`_prev_flags`) aufgenommen, da es sich unabhängig von `cycle_active`/`surplus_active`/etc. ändern kann

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
