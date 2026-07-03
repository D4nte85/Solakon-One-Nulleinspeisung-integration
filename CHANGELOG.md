# Changelog

Alle nennenswerten Änderungen an der Solakon-ONE-Nulleinspeisung-Integration.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

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
