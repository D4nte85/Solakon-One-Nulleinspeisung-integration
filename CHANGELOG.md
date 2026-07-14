# Changelog

Alle nennenswerten Änderungen an der Solakon-ONE-Nulleinspeisung-Integration.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

## [Unreleased]

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
