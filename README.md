# ⚡ Solakon ONE Nulleinspeisung

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue)](https://www.home-assistant.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Vollautomatische **Nulleinspeisung** für den **Solakon ONE** Wechselrichter als native Home Assistant Integration — kein Blueprint, keine Helfer-Entitäten, keine manuelle YAML-Pflege.

Die Integration regelt die Ausgangsleistung des Wechselrichters über einen **PI-Regler** so, dass der Netzbezug möglichst bei 0 W gehalten wird. Alle Parameter werden über ein **Sidebar-Panel** direkt in der HA-Oberfläche konfiguriert und persistent gespeichert.

> **Unterschied zur Blueprint-Variante:** Diese Integration ersetzt Automation-Blueprint, PI-Script-Blueprint und alle manuell zu erstellenden Helfer durch eine einzige, nativ installierbare Komponente. Keine `input_boolean`-, `input_number`- oder Script-Helper erforderlich — der gesamte Regelzustand wird intern im Coordinator gehalten.

---

## Funktionsübersicht

### Kernfunktion — Nulleinspeisung mit PI-Regler

Die Netzleistung ist die Regelgröße, die Wechselrichterausgangsleistung die Stellgröße. Der P-Anteil reagiert sofort auf Abweichungen, der I-Anteil gleicht dauerhaften Offset aus. Ein konfigurierbares Totband verhindert unnötige Stelleingriffe bei kleinen Schwankungen. Optional wartet der Regler auf die tatsächliche Leistungsübernahme des Wechselrichters statt auf eine feste Wartezeit (Self-Adjusting Wait).

### SOC-Zonenverwaltung

Das Verhalten wird abhängig vom Batterie-Ladestand in vier Zonen eingeteilt:

| Zone | Bedingung | Modus | Max. Entladestrom | Regelziel | Besonderheiten |
|------|-----------|-------|-------------------|-----------|----------------|
| **Zone 0** | SOC ≥ Export-Schwelle UND PV-Überschuss | `'1'` | 2 A (Stabilitätspuffer) | Hard Limit | Optional. PI-Integral eingefroren. SOC- und PV-Hysterese verhindern Flackern. |
| **Zone 1** | SOC > Zone-1-Schwelle | `'1'` | Konfigurierter Maximalwert | 0 W + Offset 1 | Läuft bis Zone-3-Schwelle — kein Yo-Yo-Effekt. Auch nachts aktiv. |
| **Zone 2** | Zone-3 < SOC ≤ Zone-1 | `'1'` | 0 A | 0 W + Offset 2 | Output-Limit: `max(0, PV − Reserve)`. Optional: Nachtabschaltung. |
| **Zone 3** | SOC ≤ Zone-3-Schwelle | `'0'` (Disabled) | 0 A | — | Output = 0 W. Vollständiger Batterieschutz. AC Laden bleibt möglich. |

### Optionale Module

**☀️ Überschuss-Einspeisung (Zone 0)** — Wenn PV-Erzeugung den Eigenbedarf um mehr als eine konfigurierbare Hysterese übersteigt und der SOC eine Zielschwelle erreicht hat, wird der Wechselrichter über den Nullpunkt hinaus angesteuert. Ein SOC-Hysterese-Band und eine PV-Hysterese verhindern Flackern beim Ein- und Ausschalten.

**⚡ AC-Laden** — Steuert den Wechselrichter in den Lademodus, wenn der SOC unter ein Ziel fällt und externer Überschuss erkannt wird (`Grid + Output < −Hysterese`). Eigener PI-Regler mit separaten P/I-Faktoren, eigenem Offset und konfigurierbarer Leistungsobergrenze.

**💹 Tarif-Arbitrage** — Wertet einen externen Strompreis-Sensor aus und lädt bei günstigem Tarif automatisch auf, sperrt die Entladung bei mittlerem Tarif und gibt sie bei teurem Tarif wieder frei.

**📈 Dynamischer Offset** — Berechnet den Nullpunkt-Offset automatisch aus der Netz-Volatilität (Standardabweichung). Ersetzt den separaten Dynamic-Offset-Blueprint — alle Parameter sind pro Zone (Zone 1, Zone 2, Zone AC) einzeln konfigurierbar, inklusive optionalem negativem Offset.

**🌙 Nachtabschaltung** — Unterdrückt in Zone 2 den Entladebetrieb unterhalb einer konfigurierbaren PV-Erzeugungsschwelle. Zone 1 und AC Laden laufen auch nachts weiter.

---

## Voraussetzungen

- Home Assistant 2024.1 oder neuer
- [HACS](https://hacs.xyz) installiert
- Solakon ONE Wechselrichter mit Modbus-Integration in HA
- Sensor für die Netzleistung (z. B. Shelly 3EM, Shelly PM) — **positiv = Bezug, negativ = Einspeisung**

**Wichtig:** Die Implementierung der Fernsteuerung in der Solakon-Integration kennt kein echtes „Disabled" als Fernsteuerbefehl — `'0'` schaltet die Fernsteuerung ab und die App-Standardeinstellungen greifen. Damit die Nulleinspeisung wie gewünscht funktioniert, sollte entweder ein **0-W-Zeitplan für 24 Stunden** aktiv sein oder die **Standard-Ausgangsleistung auf 0 W** gestellt werden.

Die folgenden Solakon-Entitäten müssen in HA vorhanden sein und werden beim Einrichten zugewiesen:

| Typ | Beschreibung |
|-----|-------------|
| `sensor` (power) | Netzleistung |
| `sensor` (power) | Tatsächliche WR-Ausgangsleistung |
| `sensor` (power) | PV-Erzeugungsleistung |
| `sensor` (battery) | Batterieladestand (SOC) |
| `sensor` | Remote-Timeout-Countdown |
| `number` | Ausgangsleistungsregler |
| `number` | Maximaler Entladestrom |
| `number` | Modus-Reset-Timer |
| `select` | Betriebsmodus |

---

## Installation

### Über HACS (empfohlen)

1. HACS öffnen → **Integrationen** → drei Punkte oben rechts → **Benutzerdefiniertes Repository hinzufügen**
2. URL eintragen: `https://github.com/D4nte85/Solakon-One-Nulleinspeisung-Blueprint-homeassistant`
3. Kategorie: **Integration** → **Hinzufügen**
4. Die Integration **Solakon ONE Nulleinspeisung** erscheint in der Liste → **Herunterladen**
5. Home Assistant neu starten

### Manuell

Repository klonen oder als ZIP herunterladen und den Ordner `custom_components/solakon_nulleinspeisung` in das Verzeichnis `config/custom_components/` der HA-Installation kopieren, dann HA neu starten.

---

## Einrichtung

Nach dem Neustart unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach *Solakon* suchen.

Im Einrichtungsformular werden die neun Pflichtentitäten zugewiesen. Alle weiteren Parameter (PI-Regler, SOC-Zonen, optionale Module) werden **nicht** im Config-Flow konfiguriert, sondern ausschließlich über das **Sidebar-Panel**.

> Die Regelung startet nach der Einrichtung mit deaktiviertem Schreibteil (`Regelung aktiv = Aus`). Erst nach Prüfung der Konfiguration im Panel sollte die Regelung aktiviert werden.

---

## Konfiguration im Sidebar-Panel

Nach der Einrichtung erscheint in der HA-Seitenleiste der Eintrag **Solakon ONE**. Das Panel ist in acht Tabs gegliedert. Änderungen werden erst nach Klick auf **💾 Speichern** übernommen — die Speicherleiste erscheint automatisch sobald ein Wert geändert wurde.

---

### 📊 Status

Echtzeit-Übersicht aller Regelzustände:

- Aktive Zone mit farblichem Banner (Zone 0–3)
- Netzleistung, Solarleistung, Ausgangsleistung, SOC
- Netz-Standardabweichung (Stabilitätsindikator)
- PI-Integral-Wert
- Aktiver Offset (Zone 1 / Zone 2 / Zone AC) mit Quelle (dynamisch / statisch)
- Zeitabstand seit letzter Regelaktion und seit letztem Moduswechsel
- Letzte Aktion und etwaige Fehlermeldungen
- Status-Flags: Zyklus, Surplus, AC Laden, Tarif-Laden
- Schaltfläche zum manuellen Zurücksetzen des PI-Integrals

---

### 🎛️ PI-Regler

Kern des Regelkreises. Vollständige Einstellhilfe → [PI-Regler Einstellung](#pi-regler-einstellung).

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| P-Faktor | Proportionale Verstärkung — sofortige Reaktion auf Abweichung | 0,8–1,5 |
| I-Faktor | Integrale Verstärkung — gleicht dauerhaften Offset aus | 0,03–0,08 |
| Totband (W) | Abweichungen innerhalb dieses Bereichs lösen keinen Stelleingriff aus | 10–30 |
| Wartezeit (s) | Feste Pause (ohne Self-Adjust) oder maximales Timeout als Sicherheitsnetz (mit Self-Adjust) | 1–5 |
| Stabw.-Fenster (s) | Zeitfenster für den internen Standardabweichungs-Sensor | 30–300 |
| Self-Adjusting Wait | Wartet auf die tatsächliche WR-Ausgangsleistung statt fester Wartezeit | Empfohlen |
| Zielwert-Toleranz (W) | Abweichung, ab der der Zielwert als erreicht gilt (nur bei Self-Adjust) | 2–5 |

**PI-Verhalten intern:**
- Anti-Windup: Integral begrenzt auf ±1000
- Integral-Reset bei jedem Zonenwechsel
- Toleranz-Decay: Integral um 5 % pro Zyklus abgebaut, wenn Fehler ≤ Totband und `|Integral| > 10`
- Zone 0: Integral eingefroren (kein Decay, kein PI-Aufruf)

---

### 🔋 Zonen

SOC-Zonenlogik mit allen Leistungs- und Offset-Parametern.

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Zone 1 SOC-Schwelle (%) | SOC über diesem Wert → Zone 1 (aggressiv) | 40–60 |
| Zone 3 SOC-Schwelle (%) | SOC unter diesem Wert → Zone 3 (Stopp) | 15–25 |
| Max. Entladestrom (A) | Entladestrom in Zone 1 (Zone 2 = 0 A, Surplus = 2 A) | 25–40 |
| Hard Limit (W) | Absolute Obergrenze der Ausgangsleistung in Zone 0 und Zone 1 | 800 |
| Zone 1 Offset (W) | Statischer Zielwert in Zone 1. Bei aktivem Dyn. Offset überschrieben | 20–50 |
| Zone 2 Offset (W) | Statischer Zielwert in Zone 2 | 10–30 |
| PV-Ladereserve (W) | Zone-2-Output-Limit: `max(0, PV − Reserve)`. Dient auch als Schwelle für Nachtabschaltung | 30–100 |

**Zum Nullpunkt-Offset:** Ein positiver Wert von z. B. 30 W lässt den Regler auf 30 W Netzbezug regeln (Sicherheitspuffer gegen versehentliche Einspeisung). Ein negativer Wert lässt den Regler gezielt leicht einspeisen.

**Wichtig:** Zone-1-Schwelle muss größer als Zone-3-Schwelle sein. Die Integration prüft dies beim Start.

---

### ☀️ Überschuss

Optionale Überschuss-Einspeisung (Zone 0).

**Eintritts-Bedingung:** SOC ≥ Export-Schwelle UND (PV > Output + Grid + PV-Hysterese ODER PV = 0)

> Der `PV = 0`-Zweig deckt den Fall ab, dass das MPPT die PV bei vollem Akku auf 0 W drosselt.

**Austritts-Bedingung:** SOC < (Export-Schwelle − SOC-Hysterese) ODER PV ≤ Output + Grid − PV-Hysterese

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Aktivieren | Ein/Aus-Schalter | — |
| SOC-Schwelle (%) | Ab diesem SOC wird Überschuss eingespeist | 90–98 |
| SOC-Hysterese (%) | Austritt erst bei SOC < (Schwelle − Hysterese) | 3–5 |
| PV-Hysterese (W) | Mindestüberschuss über Eigenbedarf für Eintritt und Austritt | 30–80 |

---

### ⚡ AC Laden

Optionales Laden bei erkanntem externem Überschuss. Aktiv in Zone 1 und Zone 2.

**Eintritts-Bedingung:** SOC < Ladeziel UND Modus ≠ `'3'` UND (Grid + Output) < −Hysterese

> Der Modus-Guard `≠ '3'` verhindert einen Re-Eintritt wenn AC Laden bereits aktiv ist.

**Abbruch-Bedingung:** SOC ≥ Ladeziel ODER (Grid ≥ ac_offset + Hysterese UND Output = 0 W)

> Der `Output = 0 W`-Guard verhindert Fehlauslösung während der PI noch aktiv regelt.

Der Lademodus verwendet einen **eigenen invertierten PI-Regler**: `raw_error = ac_offset − grid`. Ein positiver Fehler (Grid zu negativ → zu viel Einspeisung) erhöht die Ladeleistung.

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Aktivieren | Ein/Aus-Schalter | — |
| Ladeziel SOC (%) | Laden stoppt bei diesem SOC | 80–95 |
| Max. Ladeleistung (W) | Obergrenze der AC-Ladeleistung | 400–800 |
| Eintritts-Hysterese (W) | (Grid + Output) muss unter −Hysterese liegen | 30–80 |
| Regel-Offset (W) | Zielwert während AC Laden (typisch negativ) | −80 bis −30 |
| AC P-Faktor | Klein halten wegen langer Hardware-Flanke (~25 s) | 0,3–0,5 |
| AC I-Faktor | Macht bei AC Laden die eigentliche Regelarbeit | 0,05–0,1 |

---

### 💹 Tarif

Optionale Tarif-Arbitrage für dynamische Stromtarife (Tibber, aWATTar …).

Drei Preisstufen:
- **Günstig** (Preis < Günstig-Schwelle): AC-Laden mit fester Leistung bis SOC-Ziel
- **Mittel** (Günstig ≤ Preis < Teuer): Discharge-Lock in Zone 2 — Entladung gesperrt. Zone 1 läuft weiter.
- **Teuer** (Preis ≥ Teuer-Schwelle): normale SOC-Logik, keine Einschränkung

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Aktivieren | Ein/Aus-Schalter | — |
| Preis-Sensor | Sensor-Entität mit aktuellem Strompreis in ct/kWh | — |
| Günstig-Schwelle (ct/kWh) | Unter diesem Preis → Laden | 5–15 |
| Teuer-Schwelle (ct/kWh) | Über diesem Preis → normale SOC-Logik | 20–35 |
| Ladeziel SOC (%) | Tarif-Laden stoppt bei diesem SOC | 85–95 |
| Ladeleistung (W) | Feste Leistung während Tarif-Laden | 400–800 |

---

### 📈 Dyn. Offset

Optionaler dynamischer Offset. Ersetzt den separaten Dynamic-Offset-Blueprint vollständig.

**Offset-Formel:**
```
volatility_buffer = max(0, (StdDev − Rausch-Schwelle) × Faktor)
offset_abs        = clamp(min_offset + volatility_buffer, min_offset, max_offset)
offset_out        = +offset_abs  (Negativer Offset: Aus)
offset_out        = −offset_abs  (Negativer Offset: Ein)
```

| Netz-Zustand | StdDev | Ergebnis (min=30, noise=15, factor=1.5) |
|:------------|:------:|:---------------------------------------:|
| Sehr ruhig | 5 W | 30 W *(Minimum)* |
| Normal | 30 W | 53 W |
| Unruhig | 80 W | 128 W |
| Sehr unruhig | 160 W | 228 W |
| Extrem | 250 W+ | 250 W *(Maximum)* |

Jede Zone (Zone 1, Zone 2, Zone AC) hat einen eigenen Parameterblock:

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Aktivieren | Dyn. Offset für diese Zone verwenden. Überschreibt den statischen Offset. | — |
| Min. Offset (W) | Grundpuffer bei ruhigem Netz | 20–40 |
| Max. Offset (W) | Obergrenze bei unruhigem Netz | 150–300 |
| Rausch-Schwelle (W) | StdDev darunter = Messrauschen, kein Anstieg | 10–20 |
| Volatilitäts-Faktor | Verstärkung oberhalb der Rausch-Schwelle | 1,0–2,0 |
| Negativer Offset | Offset negieren (Regelziel < 0 W) | Aus |

---

### 🌙 Nacht

Optionale Nachtabschaltung. Deaktiviert **nur Zone 2** wenn PV < PV-Ladereserve (aus den Zonen-Einstellungen — kein separater Parameter). Zone 1 (aggressive Entladung) und AC Laden laufen auch nachts weiter.

---

## SOC-Zonen und Steuerlogik (Falls)

Die Regellogik arbeitet mit einer geordneten Liste von Falls (ähnlich einem `choose`-Block). Die Reihenfolge ist entscheidend — der erste zutreffende Fall wird ausgeführt.

| Fall | Bedingung | Aktion |
|:-----|:----------|:-------|
| **0A** — Surplus Start | `surplus_enabled` UND `new_surplus = True` UND `surplus_active = False` | `surplus_active → True`. Integral eingefroren. |
| **0B** — Surplus Ende | `surplus_enabled` UND `surplus_active = True` UND Austritts-Bedingung erfüllt | `surplus_active → False`. Integral = 0. |
| **A** — Zone 1 Start | SOC > Zone-1-Schwelle UND `cycle_active = False` UND kein AC Laden | `cycle_active → True`. Integral = 0. Timer-Toggle. Modus → `'1'`. |
| **B** — Zone 3 Stop | SOC < Zone-3-Schwelle UND `cycle_active = True` UND kein AC Laden | `cycle_active → False`. Integral = 0. Output → 0 W. Modus → `'0'`. |
| **C** — Zone 3 Absicherung | SOC < Zone-3-Schwelle UND `cycle_active = False` UND Modus ≠ `'0'` UND kein AC Laden | Output → 0 W. Modus → `'0'`. Kein Integral-Reset. |
| **D** — Recovery | `(cycle_active = True ODER ac_charge_active = True)` UND Modus ∉ `{'1','3'}` UND SOC > Zone-3-Schwelle | Timer-Toggle. Modus → `'3'` (wenn `ac_charge_active`) sonst `'1'`. Kein Integral-Reset. |
| **GT** — Tarif-Laden Start | Tarif aktiv UND Preis < Günstig-Schwelle UND SOC < Tarif-SOC-Ziel UND Modus ≠ `'3'` | `tariff_charge_active → True`. `cycle_active → True`. Timer-Toggle. Output → 0 W. Modus → `'3'`. |
| **HT** — Tarif-Laden Ende | `tariff_charge_active = True` UND (Preis ≥ Günstig-Schwelle ODER SOC ≥ Tarif-SOC-Ziel) | `tariff_charge_active → False`. Integral = 0. Zone 1 → `'1'` / Zone 2 → `'0'` + 0 W. |
| **TM** — Discharge-Lock | Tarif aktiv UND Günstig ≤ Preis < Teuer-Schwelle UND kein AC/Tarif-Laden UND Modus = `'1'` UND `cycle_active = False` | Integral = 0. Output → 0 W. Modus → `'0'`. |
| **G** — AC Laden Start | AC aktiv UND SOC < Ladeziel UND **Modus ≠ `'3'`** UND (Grid + Output) < −Hysterese | `ac_charge_active → True`. Timer-Toggle. Output → 0 W. Modus → `'3'`. |
| **H** — AC Laden Ende | Modus = `'3'` UND (SOC ≥ Ladeziel ODER (Grid ≥ ac_offset + Hysterese UND Output = 0)) | `ac_charge_active → False`. Integral = 0. Zone 1 → `'1'` / Zone 2 → `'0'` + 0 W. |
| **I** — Safety | Modus = `'3'` UND kein aktives AC Laden UND kein Tarif-Laden | Integral = 0. Zone 1 → Timer-Toggle + `'1'` / Zone 2 → `'0'` + 0 W. |
| **E** — Zone 2 Start | Zone-3 < SOC ≤ Zone-1 UND `cycle_active = False` UND Modus = `'0'` UND kein AC Laden UND kein Nacht | Integral = 0. Timer-Toggle. Modus → `'1'`. |
| **F** — Nachtabschaltung | Nacht aktiv UND `cycle_active = False` UND Modus ≠ `'0'` UND kein AC Laden | Integral = 0. Output → 0 W. Modus → `'0'`. |

**Reihenfolge-Begründungen:**
- Fall D liegt vor Falls G/H, damit Recovery nur Modus ∉ `{'1','3'}` prüft — der AC-Lade-Modus `'3'` wird durch Recovery nie überschrieben.
- Fall I fängt jeden `'3'`-Zustand ohne legitime Lade-Session auf — egal ob durch externe Modussetzung oder Fehlzustand entstanden.

---

## PI-Regler Einstellung

Der Regler wird in drei Schritten eingestellt. Ziel: schnelle, präzise Reaktion ohne dauerhaftes Schwingen. **Grundprinzip: klein anfangen, langsam steigern, beim ersten stabilen Zittern stoppen und einen Schritt zurückgehen.**

### Schritt 1: Wartezeit bestimmen (P = 1, I = 0)

Die Wartezeit deckt die Gesamtverzögerung zwischen dem Schreibbefehl an den Wechselrichter und dem stabilen Messwert ab:

```
number.set_value gesendet
  + 0,5–2,0 s   Modbus-Schreiben + Bestätigung (automatisch, zählt NICHT zur Wartezeit)
  + 0,5–1,5 s   Wechselrichter passt Ausgangsleistung an (Hardware-Flanke)       ┐
  + 0,5–1,5 s   Shelly + Solakon-Integration lesen neue Werte per Polling        ┘ → Wartezeit
─────────────────────────────────────────────────────────────────────────────────
  Sinnvolle Wartezeit: 1–5 s (je nach Bus-Last und Polling-Intervall)
```

> Mit aktiviertem **Self-Adjusting Wait** wird die Wartezeit zum Max-Timeout — der Regler geht automatisch weiter sobald die Ausgangsleistung den Zielwert erreicht. Das ist die empfohlene Einstellung.

### Schritt 2: P-Faktor finden (I = 0, Startpunkt: P = 0,5)

| Beobachtung | Bedeutung | Aktion |
|:------------|:----------|:-------|
| Output reagiert kaum, Netz weit vom Ziel | P zu klein | P erhöhen (+0,2 pro Schritt) |
| Output schwingt kurz, pendelt sich aber ein | Guter Bereich | Halten oder minimal erhöhen |
| Output und Netz pendeln dauerhaft ohne Einpendeln | P zu groß | Einen Schritt zurück |

**Ziel:** Den Punkt finden, wo das System gerade eben anfängt leicht zu zittern — dann P um einen Schritt zurücknehmen. Typischer Arbeitsbereich nach diesem Verfahren: **0,8–1,5**.

> Das Schwingen sieht man am besten in einem Verlaufsgraph der Netzleistung (HA Verlaufsgraph für den Shelly-Sensor). Stabiles Pendeln mit kleiner Amplitude um den Zielwert ist normal. Erst wenn der Output dauerhaft auf und ab fährt ohne Tendenz zum Einpendeln ist es zu viel.

### Schritt 3: I-Faktor hinzufügen (Startpunkt: I = 0,02)

Mit P allein verbleibt eine bleibende Regelabweichung bei Lastwechseln. Der I-Anteil korrigiert diese langsam aber sicher.

| Beobachtung | Bedeutung | Aktion |
|:------------|:----------|:-------|
| Regler trifft Zielwert nicht dauerhaft | I zu klein | I erhöhen (+0,01 pro Schritt) |
| Zielwert wird zuverlässig gehalten | Optimal | Fertig |
| Langsames, lang-periodisches Schwingen (Minuten) | I zu groß | Leicht reduzieren |

Typischer Arbeitsbereich: **0,03–0,08**. Zeichen für zu hohes I: langsame Schwingungen mit langer Periode. Der Anti-Windup (±1000) und der Toleranz-Decay (5 %/Zyklus) begrenzen Windup-Effekte automatisch.

**AC Laden separat tunen:** Wegen der langen Hardware-Flanke des Wechselrichters (~25 s von Minimum auf Maximum) P-Faktor besonders klein halten (~0,3–0,5) und den I-Anteil die eigentliche Regelarbeit machen lassen.

---

## Technische Details

### Timer-Toggle Mechanismus

Moduswechsel werden durch einen Toggle zwischen den Werten **3598 und 3599** am Modus-Reset-Timer erzwungen — nicht durch einen festen Wert. Dies erzeugt eine Zustandsänderung, die den Solakon ONE zur stabilen Modus-Übernahme veranlasst.

```
Aktueller Timer-Wert = 3599 → schreibe 3598
Aktueller Timer-Wert < 3599 → schreibe 3599
→ anschließend: Modus setzen
```

Der Toggle wird bei jedem Moduswechsel (Falls A, D, E, G, GT, H-Zone1, HT-Zone1, I-Zone1) direkt vor dem `select.select_option`-Aufruf durchgeführt. Zusätzlich: Wenn der Timeout-Countdown unter 120 s fällt, wird ebenfalls ein Toggle ausgeführt um den Remote-Betrieb aufrechtzuerhalten.

**Modbus-Befehlsreihenfolge:** Bei allen Wechseln in Modus `'0'` (Disabled) muss immer zuerst `Output → 0 W` und dann `Modus → '0'` gesetzt werden, da der Solakon ONE Output-Befehle ignoriert wenn er bereits in Modus `'0'` ist.

### PI-Regler Formeln

**Fehlerberechnung (modusabhängig):**
```
Normal (ac_charge_mode = false):
  raw_error = grid_power − target_offset

AC Laden (ac_charge_mode = true):
  raw_error = target_offset − grid_power   ← invertiert
```

**Kapazitäts-Clamping:**
```
raw_error > 0: error = min(raw_error, max_power − current_power)
raw_error < 0: error = max(raw_error, 0 − current_power)
```

**Integral und Korrektur:**
```
integral_new = clamp(integral_old + error, −1000, 1000)
correction   = error × P_Faktor + integral_new × I_Faktor
new_power    = current_power + correction
final_power  = clamp(new_power, 0, max_power)
```

**Dynamisches Power-Limit (max_power):**
```
Modus '3' (AC Laden):   max_power = ac_power_limit
Zone 1 (cycle = True):  max_power = hard_limit
Zone 2 (cycle = False): max_power = max(0, PV − pv_reserve)
```

### Recovery-Mechanismus (Fall D)

Falls der Modus des Wechselrichters extern zurückgesetzt wird (z. B. durch einen Neustart der Integration) während `cycle_active = True` gilt, erkennt die Integration diesen Zustand automatisch und reaktiviert den Modus über den Timer-Toggle — ohne Zonenwechsel oder Integral-Reset. Der wiederhergestellte Modus richtet sich nach dem internen Zustand: `ac_charge_active = True` → `'3'`, sonst `'1'`.

### Safety-Mechanismus (Fall I)

Fängt den Zustand ab, in dem der Wechselrichter Modus `'3'` hat, aber weder `ac_charge_active` noch `tariff_charge_active` gesetzt ist. Tritt auf bei externer Modussetzung oder nach einem Neustart. Aktion: Integral = 0, anschließend Zone 1 → Timer-Toggle + Modus `'1'`, Zone 2 → Output 0 W + Modus `'0'`.

### Entladestrom-Steuerung

| Zustand | Entladestrom | Bedingung |
|:--------|:------------|:----------|
| Surplus aktiv (Zone 0) | 2 A | Stabilitätspuffer |
| Zone 1 (cycle aktiv) | Konfigurierter Maximalwert | Nur wenn nicht Surplus, nicht AC Laden |
| Zone 2 / AC Laden / Tarif-Laden | 0 A | — |

Stromänderungen werden nur geschrieben wenn der aktuelle Wert um mehr als 0,5 A abweicht.

---

## Wichtige Hinweise

1. **Schreibteil erst nach Konfigurationsprüfung aktivieren.** Die Regelung startet mit `Regelung aktiv = Aus`. Nach Einrichtung im Panel den Schreibteil erst dann einschalten wenn alle Parameter geprüft sind.
2. **Zone-1-Schwelle > Zone-3-Schwelle.** Die Integration prüft dies und gibt im Status-Tab einen Fehler aus falls die Limits ungültig sind.
3. **Netzleistungssensor-Polarität.** Positiv = Bezug, negativ = Einspeisung — abweichende Polarität führt zu umgekehrtem Regelverhalten.
4. **AC Laden Eintritts-Guard.** Eintritt in AC Laden ist nur möglich wenn Modus ≠ `'3'`. Das verhindert einen Re-Eintritt wenn AC Laden bereits aktiv ist (Ausgangsleistung = 0 W während PI noch hochregelt würde sonst als Eintritts-Bedingung interpretiert).
5. **AC Laden P/I-Tuning.** Separates Tuning erforderlich — P klein halten (~0,3–0,5) wegen der langen Hardware-Flanke des Solakon ONE im AC-Lade-Modus (~25 s). I-Faktor macht die eigentliche Regelarbeit. Standard I-Faktor: 0,0 als sicherer Startpunkt.
6. **at_max_limit-Guard.** Greift nur am absoluten Hard Limit (800 W), nicht am dynamischen `max_power`. Dadurch kein Deadlock wenn das dynamic ceiling sinkt (z. B. weil PV nachlässt).
7. **at_max/at_min-Guards im AC-Lade-Modus.** Beide Guards sind während AC Laden deaktiviert — Fall I übernimmt die Safety-Funktion für unlegitimierte `'3'`-Zustände.
8. **Tarif-Discharge-Lock.** Der Lock gilt für mittlere UND günstige Preiszonen (alles unterhalb der Teuer-Schwelle), nicht nur für die mittlere Zone. Zone 1 läuft in allen Tarifstufen weiter.
9. **Dynamischer Offset.** Jede Zone wird einzeln aktiviert. Die Netz-Standardabweichung wird intern berechnet — kein externer Statistik-Sensor erforderlich. Nach dem ersten Start einige Minuten warten bis genug Samples gesammelt sind.
10. **Self-Adjusting Wait.** Polls die tatsächliche Ausgangsleistung nach einem Setpoint-Befehl statt einer festen Wartezeit zu schlafen. Die konfigurierte Wartezeit wird zum maximalen Timeout als Sicherheitsnetz.

---

## Erzeugte Entitäten

Die Integration erzeugt automatisch folgende Entitäten unter dem Gerät **Solakon ONE**:

| Entität | Typ | Beschreibung |
|---------|-----|-------------|
| `sensor.solakon_one_aktuelle_zone` | Sensor | Aktive Zone (0–3) mit Zusatzattributen |
| `sensor.solakon_one_betriebsmodus` | Sensor | Lesbarer Modustext |
| `sensor.solakon_one_letzte_aktion` | Sensor | Letzter Logeintrag der Steuerlogik |
| `sensor.solakon_one_netz_standardabweichung` | Sensor | Netz-Stabw. in W über das konfigurierte Fenster |
| `number.solakon_one_pi_integral` | Number | Aktueller I-Anteil (schreibgeschützt, nur zur Anzeige) |
| `switch.solakon_one_regelung_aktiv` | Switch | Hauptschalter — aktiviert/deaktiviert den Schreibteil |
| `switch.solakon_one_entladezyklus_aktiv` | Switch | Internes Flag Entladezyklus (read-only) |
| `switch.solakon_one_uberschuss_modus` | Switch | Flag Überschuss-Modus aktiv (read-only) |
| `switch.solakon_one_ac_laden_aktiv` | Switch | Flag AC-Laden aktiv (read-only) |
| `switch.solakon_one_tarif_laden_aktiv` | Switch | Flag Tarif-Laden aktiv (read-only) |

Die Diagnose-Switch-Entitäten sind schreibgeschützt — sie spiegeln interne Zustände wider und können nicht manuell geschaltet werden.

---

## Fehlerbehebung

**Panel öffnet sich, zeigt aber keine Werte an**
Integration neu laden (Einstellungen → Geräte & Dienste → Solakon → drei Punkte → Neu laden). Falls das Problem bleibt, HA-Protokoll auf Fehler der Domain `solakon_nulleinspeisung` prüfen.

**Werte werden nicht gespeichert**
Im Browser-Konsolenfenster (F12) nach WebSocket-Fehlern schauen. Häufige Ursache: Integration wurde noch nicht vollständig geladen.

**Status-Tab zeigt Fehlermeldung „SOC-Limits ungültig"**
Zone-1-Schwelle muss größer als Zone-3-Schwelle sein. Im Zonen-Tab prüfen und korrigieren.

**Regler schwingt (Leistung pendelt stark)**
P-Faktor reduzieren oder Wartezeit erhöhen. Der Standardabweichungs-Sensor im Status-Tab zeigt die Netzstabilität — bei hohem Wert (> 50 W) größeres Totband setzen.

**Zone 3 aktiv, obwohl Batterie nicht leer**
Zone-3-Schwelle im Zonen-Tab prüfen. Wert muss kleiner als Zone-1-Schwelle sein.

**AC Laden startet nicht trotz Überschuss**
Prüfen ob AC Laden im Tab aktiviert ist. (Grid + Output) muss unter −Hysterese liegen. SOC muss unter Ladeziel sein. Status-Flag „AC Laden aktiv" im Status-Tab beobachten.

**AC Laden bricht sofort wieder ab**
Eintritts-Hysterese zu klein — Grid-Wert schwankt bereits über der Abbruch-Schwelle. Hysterese erhöhen oder P/I kleiner setzen damit der Regler nicht zu aggressiv hochregelt.

**Tarif-Laden reagiert nicht auf Preisänderungen**
Preis-Sensor im Tarif-Tab prüfen — muss eine gültige Sensor-Entität mit numerischem Wert in ct/kWh sein. Günstig-Schwelle muss über dem aktuellen Preis liegen.

**Dynamischer Offset bleibt auf Minimum**
Stabw.-Sensor im Status-Tab prüfen. Nach dem ersten Start braucht der Sensor einige Minuten bis genug Samples gesammelt sind. Volatilitäts-Faktor erhöhen oder Rausch-Schwelle senken falls der Offset zu träge reagiert.

**Integration taucht nach Installation nicht auf**
Home Assistant vollständig neu starten (nicht nur neu laden). HACS-Download-Status überprüfen.

**Recovery (Fall D) greift zu oft**
Der Modus-Reset-Timer läuft ab bevor der Regler ihn zurücksetzen kann. Solakon-Integration auf Polling-Intervall prüfen — der Timeout-Countdown-Sensor muss zuverlässig in HA ankommen.

---

## Lizenz

MIT — siehe [LICENSE](LICENSE)

---

## Autor

[@D4nte85](https://github.com/D4nte85)
