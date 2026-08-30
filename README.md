# ⚡ Solakon ONE Nulleinspeisung

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue)](https://www.home-assistant.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Vollautomatische **Nulleinspeisung** für den **Solakon ONE** Wechselrichter als native Home Assistant Integration — kein Blueprint, keine Helfer-Entitäten, keine manuelle YAML-Pflege.

Die Integration regelt die Ausgangsleistung des Wechselrichters über einen **PI-Regler** so, dass der Netzbezug möglichst bei 0 W gehalten wird. Alle Parameter werden über ein **Sidebar-Panel** direkt in der HA-Oberfläche konfiguriert und persistent gespeichert.

> [!IMPORTANT]
> **Voraussetzung: die offizielle Solakon-ONE-Integration.**
> Sie liefert per Modbus TCP alle Geräteentitäten — SOC, PV-Leistung, tatsächliche Ausgangsleistung, Betriebsmodus, Entladestrom —, die diese Integration regelt. Ohne sie funktioniert hier nichts.
>
> **Repository:** https://github.com/solakon-de/solakon-one-homeassistant
>
> Sie ist **nicht im HACS-Standardstore** enthalten und muss als benutzerdefiniertes Repository hinzugefügt werden: HACS → Integrationen → ⋮ → *Benutzerdefiniertes Repository hinzufügen* → obige URL, Kategorie **Integration**.
>
> **Danach zwingend:** Die Entität `number.solakon_one_maximaler_entladestrom` ist dort **standardmäßig deaktiviert** und muss von Hand aktiviert werden (Gerät → Entität → Zahnrad → *Aktivieren*). Ohne sie kann der Entladestrom nicht gesteuert werden; im Einrichtungsformular erscheint sie sonst als „unbekannte Entität“.

---

# ☀️ Solakon ONE Dashboard Vorschau

Hier kannst du das Dashboard interaktiv testen:

[![Live Demo](https://img.shields.io/badge/Vorschau-Live%20Demo-03a9f4?style=for-the-badge&logo=google-chrome&logoColor=white)](https://D4nte85.github.io/Solakon-One-Nulleinspeisung-integration/)

> [!NOTE]
> Dies ist eine statische Web-Vorschau zur Demonstration des UI-Designs. Die Werte sind Beispieldaten.

---

## Funktionsübersicht

### Kernfunktion — Nulleinspeisung mit PI-Regler

Die Netzleistung ist die Regelgröße, die Wechselrichterausgangsleistung die Stellgröße. Der P-Anteil reagiert sofort auf Abweichungen, der I-Anteil gleicht dauerhaften Offset aus. Ein konfigurierbares Totband verhindert unnötige Stelleingriffe bei kleinen Schwankungen. Optional wartet der Regler auf die tatsächliche Leistungsübernahme des Wechselrichters statt auf eine feste Wartezeit (Self-Adjusting Wait).

### SOC-Zonenverwaltung

Das Verhalten wird abhängig vom Batterie-Ladestand in vier Zonen eingeteilt:

| Zone | Bedingung | Modus | Max. Entladestrom | Regelziel | Besonderheiten |
|------|-----------|-------|-------------------|-----------|----------------|
| **Zone 0** | SOC ≥ Export-Schwelle UND PV-Überschuss | `'1'` | 2 A (Stabilitätspuffer) | Hard Limit Z0 | Optional. PI-Integral eingefroren. SOC- und PV-Hysterese verhindern Flackern. |
| **Zone 1** | SOC > Zone-1-Schwelle | `'1'` | Konfigurierter Maximalwert | 0 W + Offset 1 | Läuft bis Zone-3-Schwelle — kein Yo-Yo-Effekt. Auch nachts aktiv. |
| **Zone 2** | Zone-3 < SOC ≤ Zone-1 | `'1'` | 0 A | 0 W + Offset 2 | Output-Limit: `min(Hard-Limit Z1, max(0, PV − Reserve))`. Optional: Nachtabschaltung. |
| **Zone 3** | SOC ≤ Zone-3-Schwelle | `'0'` (Disabled), außer AC Laden aktiv → `'3'` | 0 A | — | Output = 0 W. Vollständiger Batterieschutz. AC Laden bleibt möglich. |

### Optionale Module

**☀️ Überschuss-Einspeisung (Zone 0)** — Wenn PV-Erzeugung den Eigenbedarf um mehr als eine konfigurierbare Hysterese übersteigt und der SOC eine Zielschwelle erreicht hat, wird der Wechselrichter über den Nullpunkt hinaus angesteuert. Ein SOC-Hysterese-Band und eine PV-Hysterese verhindern Flackern beim Ein- und Ausschalten.

**⚡ AC-Laden** — Steuert den Wechselrichter in den Lademodus, wenn der SOC unter ein Ziel fällt und externer Überschuss erkannt wird (`Grid + ΣOutput_entladend < −Hysterese`, Σ über alle Instanzen im Entlademodus). Eigener PI-Regler mit separaten P/I-Faktoren, eigenem Offset und konfigurierbarer Leistungsobergrenze.

**💹 Tarif-Arbitrage** — Wertet einen externen Strompreis-Sensor aus und lädt bei günstigem Tarif automatisch auf, sperrt die Entladung unterhalb der Teuer-Schwelle (günstig + mittel) in Zone 1 und Zone 2, und gibt sie bei teurem Tarif wieder frei.

**📈 Dynamischer Offset** — Berechnet den Nullpunkt-Offset automatisch aus der Netz-Volatilität (Standardabweichung). Ersetzt den separaten Dynamic-Offset-Blueprint — alle Parameter sind pro Zone (Zone 1, Zone 2, Zone AC) einzeln konfigurierbar, inklusive optionalem negativem Offset.

**🌙 Nachtabschaltung** — Unterdrückt in Zone 2 den Entladebetrieb unterhalb einer konfigurierbaren PV-Erzeugungsschwelle. Zone 1 und AC Laden laufen auch nachts weiter.

**Priorität und gegenseitige Blockierung der optionalen Module:**

Die Module werden in fest definierter Prioritätsreihenfolge ausgewertet — ein aktives Modul höherer Priorität blockiert den Start niedrigerer Module:

| Priorität | Modul | Blockiert |
|:---------:|-------|-----------|
| 1 (höchste) | ☀️ Überschuss-Einspeisung | Tarif-Laden (GT), Discharge-Lock (TM), AC Laden (G) |
| 2 | 💹 Tarif-Laden (günstig) | AC Laden (via Modus `'3'`), Discharge-Lock |
| 3 | 💹 Discharge-Lock (< Teuer) | Zone-1/2-Recovery (Fall D), Zone-2-Start (Fall E) |
| 4 | ⚡ AC Laden | Tarif-Laden (via Modus `'3'`), Discharge-Lock |
| 5 | 🌙 Nachtabschaltung | Zone-2-Start (Fall E) |
| 6 (niedrigste) | Zone 1 / Zone 2 | — |

AC Laden und Tarif-Laden blockieren sich gegenseitig über den Modus-Guard (`Modus ≠ '3'`). Überschuss-Einspeisung hat absoluten Vorrang — kein anderes optionales Modul kann während Zone 0 starten.

## Multi-Instancing

Bei mehr als einer installierten Instanz zeigt das Sidebar-Panel oben eine **Instanzleiste** sowie eine **Übersichtsseite** mit Echtzeit-Status aller Instanzen und einen eigenen **Verteilungs-Tab**.

### Netzgruppen (mehrere Smartmeter)

Instanzen werden automatisch nach ihrem konfigurierten Netz-Leistungssensor gruppiert — Instanzen mit demselben Sensor bilden eine **Netzgruppe**. Fehleraufteilung und Leistungsverteilung (siehe unten) laufen ausschließlich **innerhalb** einer Gruppe; Instanzen an unterschiedlichen Smartmetern (z. B. zwei getrennte Stromkreise mit je eigenem Zähler) beeinflussen sich nicht gegenseitig.

Bei nur einer Gruppe (Normalfall) ist diese Zuordnung unsichtbar — es gibt genau einen gemeinsamen Verteilungs-Tab. Bei mehreren Gruppen ersetzt die oberste Tab-Ebene die einzelnen Instanz-Tabs durch Gruppen-Tabs (`Gruppe: <Netzsensor>`); jede Gruppe öffnet darunter ihre eigene zweite Tab-Ebene mit „Verteilung" und den zugehörigen Instanzen. Die Übersichtsseite zeigt weiterhin alle Instanzen aller Gruppen, untereinander nach Gruppe sortiert mit einer eigenen **Gesamt-Karte** je Gruppe mit mehr als einer Instanz: SOC-Mittelwert (kapazitätsgewichtet, wenn bei allen Instanzen der Gruppe ein gültiger Kapazitätssensor gesetzt ist, sonst ungewichteter Mittelwert — Kennzeichnung „⌀"), Summe der Ausgangsleistung, Netzleistung (direkt vom gemeinsamen Netzsensor) sowie der aktuelle Verteilungs-Modus. Degradiert der Coordinator den konfigurierten Modus diesen Zyklus mangels gültigem Fremdinstanz-Sensor (siehe unten), zeigt die Karte beide Modi (`Kapazitätsgewichtet → SOC-gewichtet ⚠️`).

### Automatische Fehleraufteilung und Leistungsverteilung

Laufen mehrere Instanzen gleichzeitig, berechnet jeder Coordinator seinen **Gewichts-Anteil** `w_i` und verwendet ihn sowohl für den PI-Regelungsfehler als auch für das zugeteilte Leistungslimit in Zone 1. Das läuft in **zwei vollständig getrennten Pools**, je nachdem welche Rolle eine Instanz gerade einnimmt:

```
# Gewicht w_i je Instanz — abhängig vom Verteilungs-Modus:
Gleichverteilung     w_i = 1 / Anzahl aktiver Instanzen
SOC-gewichtet        w_i = nutzbar_i / Σ nutzbar_j
                     nutzbar_i = (SOC_i − Zone-3-Schwelle_i) / 100
Kapazitätsgewichtet  wie SOC-gewichtet, zusätzlich × Kapazität_kWh_i
SOC-Umschaltung      genau eine Instanz aktiv (w_i = 1), alle anderen 0

# Daraus je Instanz:
allocated_power_i = wasserfüll(total_power, {w_i}, {hard_limit_i})
error_share_i     = w_i        → Anteil am Netzfehler im PI-Regler
```

**Wasserfüllverfahren:** `roh_i = total_power × w_i`. Übersteigt `roh_i` das Hard-Limit einer Instanz, wird sie darauf gekappt und der ungenutzte Rest unter den übrigen erneut nach `w_i` verteilt — iterativ, bis nichts mehr verteilbar ist. Bei gleich dimensionierten Instanzen ohne Wirkung; bei unterschiedlichen verhindert es, dass Spielraum verfällt.

**SOC-Umschaltung:** Die aktive Instanz entlädt exklusiv, bis ihr SOC seit Übernahme um die Divergenz-Schwelle gefallen ist — dann übernimmt die Instanz mit dem höchsten verbleibenden SOC (nie zweimal in Folge dieselbe). Der Zustand übersteht HA-Neustarts. Zone 0 hat Vorrang: eine Instanz in Überschuss-Einspeisung übernimmt sofort die Führung, mehrere teilen sich gleichmäßig. Beim Verlassen von Zone 0 wird die Rotations-Baseline auf den aktuellen SOC neu verankert.

**Zwei getrennte Pools:** Pool 1 sind die Instanzen in Modus `'1'` (Nulleinspeisung), Pool 2 die mit aktivem AC Laden. Pool 2 bekommt nur einen eigenen `error_share`, kein `allocated_power` — die AC-Ladeleistung bleibt unabhängig vom Hard-Limit. Eine Instanz in Modus `'0'` trägt zu keinem Pool bei (`error_share = 0`, `allocated_power = None`, statisches Hard-Limit gilt). Bei nur einer aktiven Instanz je Pool ist `w_i = 1,0`.

> **Batteriekapazität (kWh):** Nur bei Verteilungs-Modus „Kapazitätsgewichtet" relevant. Fehlt der Sensor bei irgendeiner aktiven Instanz, wird die Kapazität für alle neutral (1.0) gewertet — die Gewichtung entspricht dann „SOC-gewichtet". Sinnvoll wenn die Instanzen Batterien unterschiedlicher Kapazität steuern.

> **Degradations-Warnung:** Ist bei Modus „SOC-gewichtet", „Kapazitätsgewichtet" oder „SOC-Umschaltung" der SOC- oder Kapazitätssensor **einer fremden** Instanz gerade `unknown`/`unavailable` (z. B. kurz nach einem HA-Neustart der anderen Instanz), fällt der gesamte Pool für diesen Regelzyklus automatisch auf Gleichverteilung zurück (bzw. „Kapazitätsgewichtet" auf „SOC-gewichtet"). Das erscheint als Meldung im Status-/Fehlerfeld jeder betroffenen Instanz, bis der Sensor wieder verfügbar ist — kein stiller Fallback. Zusätzlich sichtbar in der Übersicht: die Gesamt-Karte zeigt den tatsächlich angewandten Modus, wenn er vom konfigurierten abweicht (siehe [Netzgruppen](#netzgruppen-mehrere-smartmeter)).

**Ausgangsbasis für den PI-Stelleingriff (Pool 1):** Im normalen Nulleinspeisungs-PI baut die Korrektur nicht auf dem eigenen zuletzt kommandierten Wert dieser Instanz auf, sondern auf ihrem proportionalen Anteil am Gruppen-Sollwert:
```
power_base_i = (Σ kommandierte Leistung aller Instanzen in Pool 1) × error_share_i
neuer_output_i = power_base_i + PI-Korrektur
```
Dadurch gleicht sich die Aufteilung zwischen den Instanzen bei jedem Stelleingriff automatisch wieder an die Gewichtung `w_i` an, statt eine einmal entstandene Schieflage (z. B. durch zeitversetzte Rückkehr aus einem Zonenwechsel) über beliebig viele Zyklen fortzuschreiben. Im Einzelbetrieb (`error_share = 1,0`, nur eine Instanz im Pool) ist `power_base_i` identisch zum eigenen kommandierten Wert — kein Unterschied zum bisherigen Verhalten.

### Leistungsverteilung konfigurieren

Im Panel wird bei mehreren Instanzen ein zusätzlicher **Verteilungs-Tab** eingeblendet — bei mehreren Netzgruppen (siehe oben) je Gruppe ein eigener, unabhängig konfigurierbarer Verteilungs-Tab.

| Parameter | Beschreibung |
|-----------|-------------|
| Gesamte Max. Ausgangsleistung (W) | Absolute Obergrenze aller Instanzen zusammen |
| Verteilungs-Modus | Gleichverteilung / SOC-gewichtet / Kapazitätsgewichtet / SOC-Umschaltung — vier sich gegenseitig ausschließende Optionen, siehe Formeln oben |
| Kapazitätssensor (pro Instanz) | Nur bei Modus „Kapazitätsgewichtet" wirksam (Feld sonst ausgegraut). `sensor.solakon_one_batteriekapazitat`. Der Validierungspunkt neben dem Feld zeigt live, ob die Entity existiert und einen Wert liefert (grün/gelb/rot) |
| Divergenz-Schwelle (Prozentpunkte) | Nur bei Modus „SOC-Umschaltung" wirksam. Die aktive Instanz entlädt exklusiv, bis ihr SOC um diesen Wert gefallen ist, dann Übergabe an die Instanz mit dem höchsten verbleibenden SOC. Standard 5 |

**Globale Sensoren:** Zusätzliche Karte im Verteilungs-Tab für Sensoren, die typischerweise für den ganzen Haushalt gelten statt pro Solakon-Instanz zu unterscheiden — eine Wetter-/Solcast-Vorhersage, ein Stromtarif. Jede Instanz kann im jeweiligen Tab (Überschuss/Zonen/Tarif) optional lokal überschreiben; ist dort nichts gesetzt, gilt der globale Wert. Anders als der Kapazitätssensor (real pro Instanz unterschiedlich, keine sinnvolle globale Vorgabe) sind das reine Entity-Picker ohne eigene Enable-Flags oder Schwellen — die bleiben ausschließlich lokal pro Instanz.

| Globaler Sensor | Speist |
|---|---|
| PV-Vorhersage heute (kWh, Wh/MWh automatisch normalisiert) | Surplus-Forecast-Erzwingung (Überschuss-Tab), Tarif-Lock-Unterdrückung (Tarif-Tab), 0–12 Uhr zusätzlich Zone-1-Nacht-Forcierung (Zonen-Tab) |
| PV-Vorhersage morgen (kWh, Wh/MWh automatisch normalisiert) | Zone-1-Nacht-Forcierung (Zonen-Tab) |
| Leistungs-Vorhersage jetzt (W) | Austritts-Sperre (Überschuss-Tab) |
| Strompreis-Sensor | Tarif-Arbitrage (Tarif-Tab) |
| Günstig-/Teuer-Schwelle dynamisch | Tarif-Arbitrage (Tarif-Tab) |

---

> **Unterschied zur Blueprint-Variante:** Diese Integration ersetzt Automation-Blueprint, PI-Script-Blueprint und alle manuell zu erstellenden Helfer durch eine einzige, nativ installierbare Komponente. Keine `input_boolean`-, `input_number`- oder Script-Helper erforderlich — der gesamte Regelzustand wird intern im Coordinator gehalten.

---

## Voraussetzungen

- Home Assistant 2024.1 oder neuer
- [HACS](https://hacs.xyz) installiert
- Solakon ONE Wechselrichter mit der offiziellen [Solakon-ONE-Integration](https://github.com/solakon-de/solakon-one-homeassistant) in HA (siehe Hinweis ganz oben)
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
| `number` *(optional)* | Netz-Ausgangsleistungsgrenze — für Export-Limit-Feature |

> **Hinweis zu Timeout-Countdown & Modus-Reset-Timer:** Die Solakon-Fernsteuerung läuft ab, wenn der Countdown-Sensor abläuft. Die Integration hält sie aktiv, indem sie den Modus-Reset-Timer rechtzeitig togglet (Countdown < 120 s). Derselbe Toggle-Mechanismus erzwingt zusätzlich bei jedem Moduswechsel die sichere Übernahme durch den Solakon (siehe Stichwort „Timer-Toggle" in der Falls-Tabelle weiter unten).

---

## Installation

### Über HACS (empfohlen)

1. HACS öffnen → **Integrationen** → drei Punkte oben rechts → **Benutzerdefiniertes Repository hinzufügen**
2. URL eintragen: `https://github.com/D4nte85/Solakon-One-Nulleinspeisung-integration`
3. Kategorie: **Integration** → **Hinzufügen**
4. Die Integration **Solakon ONE Nulleinspeisung** erscheint in der Liste → **Herunterladen**
5. Home Assistant neu starten

### Manuell

Repository klonen oder als ZIP herunterladen und den Ordner `custom_components/solakon_nulleinspeisung` in das Verzeichnis `config/custom_components/` der HA-Installation kopieren, dann HA neu starten.

---

## Einrichtung

Nach dem Neustart unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** nach *Solakon* suchen.

Im Einrichtungsformular werden zunächst ein **Instanzname** (z. B. „Speicher 1" — wird zum Gerätenamen in HA, relevant bei mehreren Instanzen, siehe [Multi-Instancing](#multi-instancing)) sowie die neun Pflichtentitäten zugewiesen. Alle weiteren Parameter (PI-Regler, SOC-Zonen, optionale Module) werden **nicht** im Config-Flow konfiguriert, sondern ausschließlich über das **Sidebar-Panel**.

> Die Regelung startet nach der Einrichtung mit deaktiviertem Schreibteil (`Regelung aktiv = Aus`). Erst nach Prüfung der Konfiguration im Panel sollte die Regelung aktiviert werden.

---

## Konfiguration im Sidebar-Panel

Nach der Einrichtung erscheint in der HA-Seitenleiste der Eintrag **Solakon ONE**. Jede Instanz ist in zehn Tabs gegliedert. Änderungen werden erst nach Klick auf **💾 Speichern** übernommen — die Speicherleiste erscheint automatisch sobald ein Wert geändert wurde. Bei mehr als einer Instanz kommen zusätzlich eine **Übersichtsseite** und ein **Verteilungs-Tab** hinzu, siehe [Multi-Instancing](#multi-instancing).

Alle Eingabefelder für Entity-IDs (z. B. Kapazitäts-, Vorhersage- und Preis-Sensoren) zeigen rechts einen **Validierungspunkt**, der die eingetragene Entity live gegen Home Assistant prüft: **grün** = Entity liefert einen Wert, **gelb** = Entity existiert, ist aber `unknown`/`unavailable`, **rot** = Entity existiert nicht (Tippfehler prüfen). Der Punkt aktualisiert sich beim Tippen und im laufenden Betrieb.

---

### 📊 Status

Echtzeit-Übersicht aller Regelzustände: aktive Zone mit farblichem Banner (Zone 0–3), Netzleistung, Solarleistung, Ausgangsleistung, SOC, Netz-Standardabweichung (Stabilitätsindikator), PI-Integral-Wert, aktiver Offset (Zone 1 / Zone 2 / Zone AC) mit Quelle (dynamisch / statisch), Zeitabstand seit letzter Regelaktion und seit letztem Moduswechsel, letzte Aktion und etwaige Fehlermeldungen, Status-Flags: Zyklus, Surplus, AC Laden, Tarif-Laden, Nacht, PV→Tarif, PV→Surplus, Austritts-Sperre. Rein lesend — manuelle Eingriffe liegen im **Debug**-Tab.

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
| Periodischer Trigger | Startet die Regelschleife im konfigurierten Intervall neu — auch ohne Sensor-Änderung. Sinnvoll bei stabilen Haushalten, in denen der Netzbezug selten springt. | Aus |
| Trigger-Intervall (s) | Abstand zwischen zwei periodischen Regelläufen. Bereich: 5–300 s. | 10–60 |

---

### 🔋 Zonen

SOC-Zonenlogik mit allen Leistungs- und Offset-Parametern.

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Zone 1 SOC-Schwelle (%) | SOC über diesem Wert → Zone 1 (aggressiv) | 40–60 |
| Zone 3 SOC-Schwelle (%) | SOC unter diesem Wert → Zone 3 (Stopp) | 15–25 |
| Max. Entladestrom (A) | Entladestrom in Zone 1 (Zone 2 = 0 A, Surplus = 2 A) | 25–40 |
| Hard Limit Z0 — Surplus (W) | Ausgangsleistungs-Obergrenze in Zone 0 (Überschuss-Einspeisung). Typisch: gesetzliches Maximum (z. B. 800 W). | 800 |
| Hard Limit Z1 — Entladung (W) | Ausgangsleistungs-Obergrenze in Zone 1 und Zone 2. In Zone 2 gilt `min(Z1, max(0, PV − Reserve))`. Wird als `max(Z0, Z1)` in die optionale Export-Limit-Entität geschrieben. | 800 |
| Zone 1 Offset (W) | Statischer Zielwert in Zone 1. Bei aktivem Dyn. Offset überschrieben | 20–50 |
| Zone 2 Offset (W) | Statischer Zielwert in Zone 2 | 10–30 |
| PV-Ladereserve (W) | Zone-2-Output-Limit: `min(Hard-Limit Z1, max(0, PV − Reserve))`. Dient auch als Schwelle für Nachtabschaltung | 30–100 |

Ein positiver Offset von z. B. 30 W lässt den Regler auf 30 W Netzbezug regeln (Sicherheitspuffer gegen versehentliche Einspeisung). Ein negativer Wert lässt den Regler gezielt leicht einspeisen.

**Wichtig:** Zone-1-Schwelle muss größer als Zone-3-Schwelle sein, und bei aktivierter Überschuss-Einspeisung muss die Export-Schwelle über der Zone-1-Schwelle liegen. Bei aktivierter Nacht-Forcierung muss deren Mindest-SOC strikt zwischen Zone-3- und Zone-1-Schwelle liegen. Die Integration prüft alles in jedem Regelzyklus und pausiert mit Fehlermeldung, solange die Grenzen ungültig sind.

**Nacht-Forcierung (optional):** Erlaubt den Zone-1-Entladezyklus auch unter der normalen Zone-1-Schwelle, wenn die PV-Vorhersage für den Zieltag zeigt, dass die Nacht ohnehin wieder aufgefüllt wird — verhindert ungenutzt liegen gebliebene Kapazität nach einem wolkigen Tag. Bedingung: Vorhersage ≥ Mindest-Ertrag UND PV < PV-Ladereserve (gerade dunkel) UND SOC > eigenes Mindest-SOC. Das Mindest-SOC ist ein eigener, unabhängig einstellbarer Sicherheits-Floor (nicht die Zone-3-Schwelle, die nur den regulären Austritt steuert) — muss strikt zwischen Zone-3- und Zone-1-Schwelle liegen, damit die Forcierung nicht bei SOC-Werten greift, in denen die SOC-Schätzung unzuverlässig wird. Reiner Eintritts-Trigger — der Austritt läuft unverändert ausschließlich über die Zone-3-Schwelle, ein späteres Zurückfallen der Vorhersage beeinflusst einen bereits laufenden Zyklus nicht.

> **Sensor wechselt an der Mitternachtsgrenze:** Vor Mitternacht wird die "PV-Vorhersage morgen" gelesen — das ist der korrekte Zieltag, dessen Ertrag die Nacht auffüllt. Nach Mitternacht (neuer Kalendertag) würde derselbe "morgen"-Sensor auf den *übernächsten* Tag zeigen, deshalb wird automatisch stattdessen die "PV-Vorhersage heute" verwendet — der Zieltag bleibt über die ganze Nacht hinweg derselbe, nur die Quelle wechselt. Kein Sonnenauf-/untergangs-Helper nötig, Mittag (12 Uhr) ist der Umschaltpunkt.

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Aktivieren | Ein/Aus-Schalter | — |
| PV-Vorhersage morgen | 🔌 Sensor wird im **Entitäten**-Tab zugewiesen | — |
| Mindest-Ertrag (kWh) | Forcierung nur ab dieser Vorhersage | abhängig vom Speicher |

---

### 🔌 Entitäten

Bündelt alle optionalen Entity-Picker-Felder dieser Instanz an einer Stelle, statt sie über Zonen-, Überschuss- und Tarif-Tab verstreut zu pflegen. Enable-Flags und Zahlen-Schwellen bleiben in ihrem jeweiligen Feature-Tab — hier wird ausschließlich zugewiesen, **welche** Entität gelesen wird. Bei Multi-Instanz: lokal (hier) überschreibt den globalen Wert aus dem [Verteilungs-Tab](#multi-instancing), sonst gilt dieser. Bleibt ein Feld sowohl hier als auch global leer, ist die jeweilige Funktion inaktiv — auch wenn ihr Enable-Flag gesetzt ist.

| Parameter | Speist |
|-----------|--------|
| PV-Vorhersage heute (optional lokal) | Tarif-Lock-Unterdrückung (Tarif-Tab), Surplus-Forecast-Erzwingung (Überschuss-Tab), 0–12 Uhr zusätzlich Zone-1-Nacht-Forcierung (Zonen-Tab) |
| PV-Vorhersage morgen (optional lokal) | Zone-1-Nacht-Forcierung (Zonen-Tab), gelesen vor Mitternacht — danach automatisch obiges Feld |
| Leistungs-Vorhersage-Sensor (W, optional lokal) | Austritts-Sperre (Überschuss-Tab) |
| Preis-Sensor (optional lokal) | Tarif-Arbitrage (Tarif-Tab) |
| Günstig-Schwelle dynamisch (optional lokal) | Tarif-Arbitrage (Tarif-Tab) |
| Teuer-Schwelle dynamisch (optional lokal) | Tarif-Arbitrage (Tarif-Tab) |

---

### ☀️ Überschuss

Optionale Überschuss-Einspeisung (Zone 0). **Hat absoluten Vorrang vor allen anderen optionalen Modulen** — Tarif-Laden, Discharge-Lock (inkl. dessen Recovery-Sperre) und AC Laden werden blockiert solange Zone 0 aktiv ist.

**Zone 0 ist ein Overlay über Zone 1:** Der Eintritt aktiviert immer auch den Zone-1-Zyklus (`cycle_active`), beim Austritt wird die Zone aus dem SOC neu abgeleitet (SOC > Zone-1-Schwelle → Zone 1 läuft weiter, sonst Zone 2). Deshalb muss die Export-Schwelle über der Zone-1-Schwelle liegen — die Integration prüft das in jedem Zyklus.

**Zum 2-A-Stabilitätspuffer:** Ist der Akku voll, kann kein Strom mehr hineinfließen — der Solakon kann PV aber nur regeln solange Batteriestrom fließt, also muss er in diesem Fall herausfließen. Ohne diesen Stromfluss (0 A) schaltet das Gerät komplett ab. Die 2 A sind deshalb eine Entladefreigabe (Obergrenze, kein fester Sollwert) und bewusst niedrig gewählt, um die Batterie dabei so wenig wie möglich zu belasten.

**Normaler Eintritt:** SOC ≥ Export-Schwelle UND (PV > ((Σ Output aller Instanzen + Grid) × Fehler-Anteil + PV-Hysterese × Fehler-Anteil) ODER (PV = 0 UND Output = 0 im aktuellen *und* vorherigen Zyklus UND seit dem letzten Austritt erneut PV > 0 gemessen))

> Ein- und Austritt nutzen denselben Verbrauchsbezug `(Σ Output + Grid) × Fehler-Anteil` (im Einzelbetrieb = `Output + Grid`). Gleiche Referenz für beide ist zwingend, sonst bricht das Hysterese-Totband zusammen und Zone 0 flackert.

> Der `PV = 0`-Zweig deckt den Fall ab, dass das MPPT die PV bei vollem Akku auf 0 W drosselt. Die Bedingung `Output = 0` über zwei aufeinanderfolgende Zyklen (Entprellung) allein reicht nachts nicht: Nach einem Austritt bleibt PV weiterhin bei 0, und sobald die Ausgangsleistung zwei Zyklen in Folge wieder auf 0 zurückfällt (z. B. während der PI aus Zone 1 erst hochregelt), feuert derselbe Zweig erneut — ein Ein-/Austritts-Loop im Sekundentakt. Zusätzliche Sperre (Latch): Nach jedem Austritt bei `PV = 0` bleibt der Zweig deaktiviert, bis wieder echtes `PV > 0` gemessen wurde — das passiert tagsüber sofort (die Hardware gibt PV nach dem erzwungenen Zone-0-Eintritt wieder frei), nachts erst bei Sonnenaufgang. Der SOC- und Verbrauchs-Austritt bleiben davon unberührt. Der Sperr-Zustand übersteht einen HA-Neustart (persistiert im Store). (Der Blueprint erreicht dasselbe über getaktete Trigger statt Entprellung.)

**Forecast-Eintritt:** PV-Vorhersage ≥ Schwelle UND PV > Hard Limit Z0 UND SOC > Zone-3-Schwelle

> Sensorwerte mit k-Präfix (kW, kWh, kWp …) werden automatisch ×1000 normalisiert — Schwelle immer in der Basiseinheit (W bzw. Wh) angeben. Standard: 5000 Wh.
>
> Der Vorhersage-Sensor ist ein gemergtes Feld ("PV-Vorhersage heute", konfiguriert im Tarif-Tab) — dieselbe Quelle speist auch die Tarif-Lock-Unterdrückung unten, da beide Features denselben Werttyp brauchen. Bei Multi-Instanz kann dieser Sensor zusätzlich global im Verteilungs-Tab hinterlegt werden; jede Instanz überschreibt optional lokal.

> Keine Export-Schwelle — Surplus startet sobald PV die maximale Ausgangsleistung übersteigt, der SOC muss nur über der Zone-3-Schutzgrenze liegen. Gedacht für sonnige Tage: 800 W werden dauerhaft ausgegeben, der Rest lädt die Batterie. Die Forcierung ist an PV > Hard Limit Z0 gekoppelt und endet von selbst, sobald die PV unter das Limit fällt (kein Abregel-Risiko mehr). Die SOC-Untergrenze verhindert, dass die Forcierung gegen den Zone-3-Sicherheitsstopp ankämpft (Modus-Flattern 0A ↔ C).

**Austritts-Bedingung:** PV ≤ ((Σ Output aller Instanzen + Grid) × Fehler-Anteil − PV-Hysterese × Fehler-Anteil) ODER SOC < (Export-Schwelle − SOC-Hysterese)

> Der PV-Term prüft, ob die eigene PV noch den **Anteil dieser Instanz am Hausverbrauch** übersteigt. Der wahre Hausverbrauch ist `Σ Output (alle Wechselrichter) + Grid` — im Einzelbetrieb identisch zu `Output + Grid`. Im Multi-Instanz-Betrieb ist die Summe nötig: regelt eine zweite Instanz den Netzwert auf ~0, würde `Output + Grid` der eigenen Instanz den Verbrauch unterschätzen und eine auf 2 A gedrosselte Surplus-Instanz käme nie aus Zone 0 heraus. `× Fehler-Anteil` skaliert sowohl den Verbrauchsbezug als auch die PV-Hysterese auf den Lastanteil dieser Instanz (Einzelbetrieb: 1,0) — so bleibt das Totband relativ zur Referenz konstant.

> Solange die Forcierung aktiv ist (Vorhersage ≥ Schwelle **und** PV > Hard Limit Z0 **und** SOC > Zone-3-Schwelle), ist der Austritt komplett gesperrt — SOC- und Verbrauchsterm sind ausgeklammert, damit bei großem PV-Tag früh eingespeist statt abgeregelt wird, ohne auf vollen Akku zu warten. Sobald die PV unter das Hard Limit fällt, die Vorhersage unter die Schwelle sinkt oder der SOC die Zone-3-Schwelle unterschreitet, endet die Forcierung und der normale Austritt greift: bei vollem Akku über den PV-Term (Überschuss weg), bei noch nicht vollem Akku sofort über den SOC-Term. Nachts ist PV = 0 < Hard Limit → Forcierung aus → Austritt, auch bei Tages-/Morgen-Vorhersage. Zone 3 (Safety-Stopp) beendet Surplus zusätzlich jederzeit.

**Austritts-Sperre (optional):** PV-Austritt gesperrt solange Leistungs-Vorhersage ≥ Sperr-Faktor × Hard Limit Z0 UND SOC > Zone-3-Schwelle

> Hält Zone 0 bei kurzen PV-Einbrüchen (Wolken). Liegt die aktuell prognostizierte PV-Leistung deutlich über dem Ausgabelimit (Faktor als Sicherheitsmarge gegen Vorhersagefehler, Standard 1,5), muss ein gemessener Einbruch transient sein — Zone 0 wird gehalten statt auszutreten. Nur der PV-Term ist gesperrt: Der SOC-Austritt bleibt immer aktiv, Zone 3 beendet Surplus jederzeit, und bei nicht verfügbarem Sensor ist die Sperre inaktiv. Der Sensor muss die **aktuelle** prognostizierte PV-Leistung in W liefern (z. B. Solcast `power_now`); k-Einheiten (kW) werden automatisch ×1000 normalisiert.
>
> Hintergrund: Verlässt Zone 0 bei vollem Akku, drosselt der Wechselrichter die PV exakt auf den Eigenbedarf herunter — der Überschuss ist danach nicht mehr messbar, und der Wiedereintritt hängt an zufälligen Verbrauchsschwankungen (minutenlange Verzögerung). Die Sperre vermeidet genau diesen Zustand, indem sie den Austritt bei transienten Einbrüchen gar nicht erst zulässt.
>
> Risiko: Meldet der Sensor dauerhaft einen zu hohen Wert, bleibt Zone 0 entsprechend lange aktiv — bis der SOC-Austritt eingreift.

**Warum die SOC-Schwelle unter dem Vollladepunkt liegen muss:** Der Eintritt prüft `PV > Eigenbedarf + Hysterese`. Das ist nur messbar, solange der Akku noch lädt — dann läuft die PV ungedrosselt und zeigt `Eigenbedarf + Ladeleistung`. Am Vollladepunkt (App-Ladeobergrenze) drosselt der Wechselrichter die PV exakt auf den Eigenbedarf herunter; der Überschuss ist dann unsichtbar und der Eintritt hängt von zufälligen Verbrauchsschwankungen ab — minutenlange Verzögerung möglich. Eine Schwelle ~5 % unter der App-Ladeobergrenze (z. B. 95 % bei Max 100 %) legt den Eintritt sicher in die Ladephase, wo der Überschuss zuverlässig messbar ist. Aus demselben Grund kann der Wiedereintritt nach einer Wolke verzögert sein, wenn der SOC bereits am Maximum gepinnt ist — während der Wolke entlädt sich die Batterie nur über den 2-A-Stabilitätspuffer (siehe oben), das bewegt den SOC praktisch nicht. Dagegen hilft die Austritts-Sperre (siehe oben).

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Aktivieren | Ein/Aus-Schalter | — |
| SOC-Schwelle (%) | Ab diesem SOC wird Überschuss eingespeist | ~5 % unter App-Ladeobergrenze (z. B. 95) |
| SOC-Hysterese (%) | Austritt erst bei SOC < (Schwelle − Hysterese) | 3–5 |
| PV-Hysterese (W) | Mindestüberschuss über Eigenbedarf für Eintritt und Austritt | 30–80 |
| Austritts-Sperre | Ein/Aus — PV-Austritt gesperrt solange Vorhersage ≥ Faktor × Hard Limit Z0 | — |
| Leistungs-Vorhersage-Sensor | 🔌 Sensor wird im **Entitäten**-Tab zugewiesen | — |
| Sperr-Faktor | Sicherheitsmarge der Austritts-Sperre gegen Vorhersagefehler | 1,5 |

---

### ⚡ AC Laden

Optionales Laden bei erkanntem externem Überschuss. Aktiv in Zone 1 und Zone 2. **Startet nicht wenn Überschuss-Einspeisung (Zone 0) oder Tarif-Laden aktiv ist.**

**Eintritts-Bedingung:** SOC < Ladeziel UND kein Überschuss aktiv UND kein AC/Tarif-Laden aktiv UND Modus ≠ `'3'` UND (Grid + ΣOutput_entladend) < −Hysterese

> Der Modus-Guard `≠ '3'` verhindert einen Re-Eintritt wenn AC Laden bereits aktiv ist. `ΣOutput_entladend` ist im Einzelbetrieb der eigene Output, im Multi-Instanz-Betrieb die Summe aller Instanzen im Entlademodus — sonst würde eine Instanz die Entladung einer Schwester-Instanz als externen Netzüberschuss werten und aus dem Netz genau das nachladen, was die Schwester gerade einspeist.

**Abbruch-Bedingung:** Modus = `'3'` UND `ac_charge_active` UND kein Tarif-Laden UND (SOC ≥ Ladeziel ODER (Grid ≥ ac_offset + Hysterese UND |eigener Output| ≤ Toleranz))

> Der `|Output| ≤ Toleranz`-Guard verhindert Fehlauslösung während der PI noch aktiv regelt. `actual_power_sensor` folgt derselben Vorzeichenkonvention wie der Netzsensor (positiv = Bezug, negativ = Einspeisung) — während aktivem AC-Laden ist er durchgehend deutlich negativ (Größenordnung der tatsächlichen Ladeleistung, nicht nur Rauschen nahe 0). Der frühere einseitige `≤ 0`-Vergleich war dadurch praktisch die gesamte Ladedauer erfüllt, unabhängig von der Ladeleistung. Das symmetrische Toleranzband (Einstellung „Selbstjustierung", Standard 2 W, dieselbe wie bei der PI-Konvergenzprüfung) verlangt stattdessen, dass die Ladeleistung tatsächlich auf nahe null heruntergeregelt ist, bevor der Grid-Zweig greift.

Der Lademodus verwendet einen **eigenen invertierten PI-Regler**: `raw_error = (ac_offset − grid) × Fehler-Anteil`. Ein positiver Fehler (Grid zu negativ → zu viel Einspeisung) erhöht die Ladeleistung.

> Der `Fehler-Anteil` hier ist [Pool 2](#multi-instancing) — unabhängig von der Nulleinspeisungs-Verteilung. Laden mehrere Instanzen gleichzeitig, teilen sie sich denselben Netzüberschuss über diesen eigenen Pool, statt sich gegenseitig zu überschätzen.

**Ausgangsbasis für den AC-PI-Stelleingriff:** Wie beim normalen Nulleinspeisungs-PI baut die Korrektur nicht auf dem eigenen zuletzt kommandierten Wert dieser Instanz auf, sondern auf ihrem proportionalen Anteil am Gruppen-Sollwert:
```
ac_power_base_i = (Σ kommandierte Leistung aller gleichzeitig ladenden Instanzen) × Fehler-Anteil_i
neuer_output_i  = ac_power_base_i + PI-Korrektur
```
Einzelbetrieb bzw. nur eine ladende Instanz: identisch zum eigenen kommandierten Wert.

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Aktivieren | Ein/Aus-Schalter | — |
| Ladeziel SOC (%) | Laden stoppt bei diesem SOC | 80–95 |
| Max. Ladeleistung (W) | Obergrenze der AC-Ladeleistung | 400–800 |
| Eintritts-Hysterese (W) | (Grid + ΣOutput_entladend) muss unter −Hysterese liegen | 30–80 |
| Regel-Offset (W) | Zielwert während AC Laden (typisch negativ) | −80 bis −30 |
| AC P-Faktor | Klein halten wegen langer Hardware-Flanke (~25 s) | 0,3–0,5 |
| AC I-Faktor | Ohne Wirkung — die Regelung ist wegen der Hardware-Flanke (~25 s) so träge, dass der I-Anteil bedeutungslos wird | 0,0 |

---

### 💹 Tarif

Optionale Tarif-Arbitrage für dynamische Stromtarife (Tibber, aWATTar …). **Wird blockiert solange Überschuss-Einspeisung (Zone 0) aktiv ist.**

Drei Preisstufen: **Günstig** (Preis < Günstig-Schwelle): Tarif-Laden mit fester Leistung bis SOC-Ziel — wenn das Ladeziel bereits erreicht ist, greift stattdessen der Discharge-Lock. **Mittel** (Günstig ≤ Preis < Teuer): Discharge-Lock — Zone 1 und Zone 2 gesperrt (Output 0 W, Modus Disabled). Der Discharge-Lock gilt für **beide** Stufen (günstig + mittel), also alles unterhalb der Teuer-Schwelle. Wenn der Preis die Teuer-Schwelle überschreitet, wird der Betrieb automatisch wiederhergestellt. **Teuer** (Preis ≥ Teuer-Schwelle): normale SOC-Logik, keine Einschränkung.

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Aktivieren | Ein/Aus-Schalter | — |
| Preis-Sensor | 🔌 Sensor wird im **Entitäten**-Tab zugewiesen | — |
| Günstig-Schwelle (ct/kWh) | Unter diesem Preis → Laden | 5–15 |
| Teuer-Schwelle (ct/kWh) | Über diesem Preis → normale SOC-Logik | 20–35 |
| Ladeziel SOC (%) | Tarif-Laden stoppt bei diesem SOC | 85–95 |
| Ladeleistung (W) | Feste Leistung während Tarif-Laden | 400–800 |

**PV-Vorhersage-Unterdrückung (optional):** Meldet der Vorhersage-Sensor einen Wert ≥ Schwelle, werden Tarif-Laden und Discharge-Lock unterdrückt — automatische Flexibilität an sonnigen Tagen, unabhängig vom aktuellen Preis.

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Aktivieren | Ein/Aus-Schalter | — |
| PV-Vorhersage heute | 🔌 Sensor wird im **Entitäten**-Tab zugewiesen — gemergtes Feld, speist auch die Surplus-Forecast-Erzwingung (siehe Überschuss oben) | — |
| Schwellwert (kWh) | Ab diesem Wert wird Tarif-Laden/Discharge-Lock unterdrückt | 5–15 |

**Dynamische Preisschwellen (optional lokal):** Günstig-Schwelle-Entität und Teuer-Schwelle-Entität, siehe **Entitäten**. Können bei Multi-Instanz zusätzlich global im Verteilungs-Tab hinterlegt werden (meist ein gemeinsamer Hausstrom-Tarif) — jede Instanz überschreibt optional lokal.

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
| Normal | 30 W | 52 W |
| Unruhig | 80 W | 128 W |
| Sehr unruhig | 160 W | 248 W |
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

Gilt für alle Zonen gemeinsam (Zeitfenster-Ebene, nicht pro Zone):

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Trim (Anzahl Werte pro Seite) | Schließt die N höchsten UND N niedrigsten Einzelmesswerte im Stabw.-Fenster vor der Berechnung aus — pro Seite, nicht insgesamt (N=5 → 10 Samples ausgeschlossen). Trennt kurze, seltene Lastspitzen (Kompressor-/Pumpen-Anlaufstrom) von echter Dauerunruhe anhand des betroffenen Fensteranteils, nicht der Ereignisdauer. Wert als Anzahl Samples, nicht Prozent, da die Sample-Zahl im Fenster von der Update-Rate des Netzsensors abhängt. Wirkung live vergleichbar über den ungetrimmten Rohwert (`stddev_raw`). | 0 (Standard, kein Trimmen); vorsichtig erhöhen |

**Mehrere Instanzen am selben Netzsensor:** Der StdDev-Ringpuffer wird nur von einer Instanz (dem Gruppen-Leader, kleinste entry_id unter den aktiv regelnden Instanzen der Netzgruppe) gepflegt — alle anderen übernehmen ihren Wert. Verhindert, dass mehrere unabhängig berechnete, leicht phasenversetzte StdDev-Historien sich gegenseitig hochschaukeln (siehe Troubleshooting). Bei Einzelbetrieb ist die Instanz immer ihr eigener Leader — kein Unterschied zum bisherigen Verhalten.

---

### 🌙 Nacht

Optionale Nachtabschaltung. Deaktiviert **nur Zone 2** wenn PV < PV-Ladereserve (aus den Zonen-Einstellungen — kein separater Parameter). Zone 1 (aggressive Entladung) und AC Laden laufen auch nachts weiter. Zone 2 wird nicht reaktiviert solange ein Tarif-Lock (mittlerer/günstiger Preis) aktiv ist.

---

### 🔧 Debug

Manuelle Eingriffe in den laufenden Regelzustand. Jede Aktion wird im Status-Tab unter **Letzte Aktion** protokolliert.

| Aktion | Wirkung |
|--------|---------|
| Integral zurücksetzen | Setzt den I-Anteil des PI-Reglers auf 0. Sinnvoll nach einem manuellen Eingriff am Wechselrichter. |
| Zone 1 aktivieren | Setzt `cycle_active = true` → aggressiver Entladebetrieb mit vollem Entladestrom. Integral wird zurückgesetzt. |
| Zone 2 aktivieren | Setzt `cycle_active = false` → batterieschonender Betrieb, 0 A Entladestrom, dynamisches Output-Limit. Integral wird zurückgesetzt. |

Der Zonenwechsel ist ein Eingriff in den internen Zustand, kein dauerhafter Modus — der nächste Regelzyklus bewertet die Zonenbedingungen normal weiter und kann ihn sofort wieder überschreiben.

---

## SOC-Zonen und Steuerlogik (Falls)

Die Regellogik arbeitet mit einer geordneten Liste von Falls. Die Reihenfolge ist entscheidend — der erste zutreffende Fall wird ausgeführt.

| Fall | Bedingung | Aktion |
|:-----|:----------|:-------|
| **0A** — Surplus Start | `surplus_enabled` UND `new_surplus = True` UND `surplus_active = False` UND kein AC/Tarif-Laden | `surplus_active → True`, `cycle_active → True` (Zone 0 setzt auf Zone 1 auf). Integral eingefroren. Falls Modus ≠ `'1'`: Timer-Toggle + Modus → `'1'`. (Entladestrom 2 A setzt der zentrale Abgleich, siehe Hinweis 12.) |
| **0B** — Surplus Ende | `surplus_active = True` UND (Überschuss-Option AUS **ODER** Austritts-Bedingung erfüllt) | `surplus_active → False`, `cycle_active → (SOC > Zone-1-Schwelle)` (Zone aus SOC neu abgeleitet). Integral = 0. Output → 0 (analog Fall B/C/F/G/H). Das Ausschalten der Option erzwingt den Austritt, sonst bliebe `surplus_active` hängen und die Batterie auf 2 A gedrosselt. |
| **A** — Zone 1 Start | SOC > Zone-1-Schwelle UND `cycle_active = False` UND kein AC/Tarif-Laden UND (Tarif deaktiviert ODER Preis gültig) UND kein aktiver Tarif-Block (Preis < Teuer) | `cycle_active → True`. Integral = 0. Timer-Toggle. Modus → `'1'`. |
| **B** — Zone 3 Stop | SOC < Zone-3-Schwelle UND `cycle_active = True` UND kein AC/Tarif-Laden | `cycle_active → False`. Integral = 0. Output → 0 W. Timer-Toggle. Modus → `'0'`. |
| **C** — Zone 3 Absicherung | SOC < Zone-3-Schwelle UND `cycle_active = False` UND Modus ≠ `'0'` UND kein AC/Tarif-Laden | Output → 0 W. Timer-Toggle. Modus → `'0'`. Kein Integral-Reset. |
| **D** — Recovery | `(cycle_active = True ODER ac_charge_active = True ODER tariff_charge_active = True)` UND Modus ∉ `{'1','3'}` UND (SOC > Zone-3-Schwelle **ODER** `ac_charge_active`/`tariff_charge_active` aktiv) UND kein aktiver Tarif-Lock (Tarif-Lock greift nicht bei `ac_charge_active`, `tariff_charge_active` oder `surplus_active`) | Timer-Toggle. Modus → `'3'` (wenn `ac_charge_active` oder `tariff_charge_active`) sonst `'1'`. Kein Integral-Reset. |
| **GT** — Tarif-Laden Start | Tarif aktiv UND Preis gültig UND Preis < Günstig-Schwelle UND SOC < Tarif-SOC-Ziel UND kein Tarif-Laden aktiv UND kein Überschuss aktiv UND Modus ≠ `'3'` | `tariff_charge_active → True`. Timer-Toggle. Output → Tarif-Ladeleistung. Modus → `'3'`. |
| **HT** — Tarif-Laden Ende | `tariff_charge_active = True` UND (Preis gültig UND Preis ≥ Günstig-Schwelle ODER SOC ≥ Tarif-SOC-Ziel) | `tariff_charge_active → False`. Integral = 0. Zone 1 → Timer-Toggle + `'1'` / Zone 2 → Timer-Toggle + `'0'` + 0 W. |
| **TM** — Discharge-Lock | Tarif aktiv UND Preis gültig UND Preis < Teuer-Schwelle UND kein AC/Tarif-Laden UND kein Überschuss UND Modus = `'1'` | Integral = 0. Output → 0 W. Timer-Toggle. Modus → `'0'`. Sperrt Zone 1 und Zone 2 (greift für günstig + mittel, d.h. alles unter Teuer-Schwelle). |
| **G** — AC Laden Start | AC aktiv UND kein AC/Tarif-Laden aktiv UND kein Überschuss aktiv UND SOC < Ladeziel UND **Modus ≠ `'3'`** UND (Grid + ΣOutput_entladend) < −Hysterese | `ac_charge_active → True`. Timer-Toggle. Output → 0 W. Modus → `'3'`. |
| **H** — AC Laden Ende | Modus = `'3'` UND `ac_charge_active = True` UND kein Tarif-Laden UND (SOC ≥ Ladeziel ODER (Grid ≥ ac_offset + Hysterese UND \|eigener Output\| ≤ Toleranz)) | `ac_charge_active → False`. Integral = 0. Zone 1 → Timer-Toggle + `'1'` / Zone 2 → Timer-Toggle + `'0'` + 0 W. |
| **I** — Safety | Modus = `'3'` UND kein aktives AC Laden UND kein Tarif-Laden | Integral = 0. Zone 1 → Timer-Toggle + `'1'` / Zone 2 → Timer-Toggle + `'0'` + 0 W. |
| **E** — Zone 2 Start | Zone-3 < SOC ≤ Zone-1 UND `cycle_active = False` UND Modus = `'0'` UND kein AC/Tarif-Laden UND kein Nacht UND kein Tarif-Lock | Integral = 0. Timer-Toggle. Modus → `'1'`. |
| **F** — Nachtabschaltung | Nacht aktiv UND `cycle_active = False` UND Modus ≠ `'0'` UND kein AC/Tarif-Laden | Integral = 0. Output → 0 W. Timer-Toggle. Modus → `'0'`. |

**Reihenfolge-Begründungen:**
- Fall D liegt vor Falls G/H, damit Recovery nur Modus ∉ `{'1','3'}` prüft — der AC-Lade-Modus `'3'` wird durch Recovery nie überschrieben.
- Fall I fängt jeden `'3'`-Zustand ohne legitime Lade-Session auf — egal ob durch externe Modussetzung oder Fehlzustand entstanden.
- Fall D ist gegen Tarif-Lock geblockt (außer bei aktiver AC-/Tarif-Lade-Session oder aktivem Überschuss) — verhindert, dass Recovery den Discharge-Lock durch Modus-Wiederherstellung umgeht; Zone 0 ist ausgenommen, weil Einspeisung bei vollem Speicher unabhängig vom Preis richtig ist (konsistent zu Fall TM).
- Fall D verzichtet auf die Zone-3-Schwelle, wenn eine AC-/Tarif-Lade-Session aktiv ist — Laden muss bei jedem SOC möglich sein, sonst bleibt der Modus bei niedrigem SOC dauerhaft auf `'0'` hängen, obwohl `ac_charge_active`/`tariff_charge_active` noch `True` sind (z. B. nach Deaktivieren/Reaktivieren der Regelung während laufendem Laden).
- Fall E ist gegen Tarif-Lock geblockt — verhindert, dass Zone 2 bei aktivem Lock neu startet.
- Falls GT und G sind gegen aktiven Überschuss geblockt — Zone-0-Einspeisung hat absoluten Vorrang vor Tarif-Laden und AC Laden.
- Fall G verwendet `ΣOutput_entladend` (Summe aller Instanzen im Entlademodus, Einzelbetrieb = eigener Output) statt des Eigenanteils — sonst würde eine Instanz die Entladung einer Schwester-Instanz als externen Netzüberschuss werten und daraufhin genau diese Menge aus dem Netz nachladen (Batterie-zu-Batterie-Umpumpen im Multi-Instanz-Betrieb).

---

## PI-Regler Einstellung

Der Regler wird in drei Schritten eingestellt. Ziel ist ein System, das schnell und präzise auf Änderungen reagiert, aber nicht dauerhaft hin- und herschwingt.

### Schritt 1: Wartezeit finden (P = 1, I = 0)

Die **Wartezeit** deckt Wechselrichter-Reaktion und Messlatenz ab. Sinnvolle Wartezeit: 1–3 s.

### Schritt 2: P-Faktor finden (I = 0)

Bei P = 0,5 beginnen, schrittweise erhöhen bis das System leicht anfängt zu pendeln — dann einen Schritt zurück. Typischer Arbeitsbereich: **0.8–1.5**.

### Schritt 3: I-Faktor hinzufügen

Typischer Arbeitsbereich: **0.03–0.08**. Für AC Laden separat tunen — P besonders klein halten (~0.3–0.5), I-Faktor auf 0 belassen: die Regelung ist wegen der Hardware-Flanke des Solakon ONE (~25 s) so träge, dass der I-Anteil keine Wirkung mehr hat. Tarif-Laden verwendet keinen PI-Regler.

---

## Wichtige Hinweise

1. **Schreibteil erst nach Konfigurationsprüfung aktivieren.** Die Regelung startet mit `Regelung aktiv = Aus`. Nach Einrichtung im Panel den Schreibteil erst dann einschalten wenn alle Parameter geprüft sind.
2. **Zone-1-Schwelle > Zone-3-Schwelle.** Die Integration prüft dies und gibt im Status-Tab einen Fehler aus falls die Limits ungültig sind.
3. **Netzleistungssensor-Polarität.** Positiv = Bezug, negativ = Einspeisung — abweichende Polarität führt zu umgekehrtem Regelverhalten.
4. **AC Laden Eintritts-Guard.** Eintritt in AC Laden ist nur möglich wenn Modus ≠ `'3'`. Das verhindert einen Re-Eintritt wenn AC Laden bereits aktiv ist.
5. **AC Laden P/I-Tuning.** Separates Tuning erforderlich — P klein halten (~0,3–0,5) wegen der langen Hardware-Flanke des Solakon ONE im AC-Lade-Modus (~25 s). I-Faktor bleibt auf 0,0 — bei dieser Trägheit hat der I-Anteil keine Wirkung mehr, reine P-Regelung reicht.
6. **at_max_limit-Guard.** Greift am zonenabhängigen `dynamic_max` (Zone 0: AC-Limit, Zone 1: Hard Limit Z1, Zone 2: `min(Hard-Limit-Z1, PV−Reserve)`). Liegt `current_power` über `dynamic_max` (z.B. weil PV abgefallen ist), läuft der PI trotz positivem Netzfehler und reduziert den Befehl auf die neue Decke — kein Deadlock wenn das dynamic ceiling sinkt.
7. **at_max/at_min-Guards im AC-Lade-Modus.** Beide Guards sind während AC Laden deaktiviert — Fall I übernimmt die Safety-Funktion für unlegitimierte `'3'`-Zustände.
8. **Tarif-Discharge-Lock.** Der Lock gilt für mittlere UND günstige Preiszonen (alles unterhalb der Teuer-Schwelle) und sperrt sowohl Zone 1 als auch Zone 2 (Output 0 W, Modus Disabled). Solange Überschuss-Einspeisung aktiv ist, wird kein Lock ausgelöst. Die Sperre hebt sich automatisch wenn der Preis die Teuer-Schwelle überschreitet — Recovery (Fall D) stellt dann den vorherigen Modus wieder her.
9. **Dynamischer Offset.** Jede Zone wird einzeln aktiviert. Die Netz-Standardabweichung wird intern berechnet — kein externer Statistik-Sensor erforderlich. Nach dem ersten Start einige Minuten warten bis genug Samples gesammelt sind. Bei mehreren Instanzen am selben Netzsensor pflegt nur der Gruppen-Leader den Ringpuffer, alle anderen übernehmen seinen Wert. Optionales **Trimmen** (`stddev_trim_count`, Standard 0): schließt die N höchsten UND die N niedrigsten Einzelmesswerte im Fenster vor der Berechnung aus — pro Seite, nicht insgesamt (N=5 → 10 Samples ausgeschlossen). Trennt kurze, seltene Lastspitzen (z. B. Kompressor-/Pumpen-Anlaufstrom) von echter Dauerunruhe anhand des betroffenen Fensteranteils, nicht der Ereignisdauer — ein Puls, der nur eine Minderheit der Samples füllt, fällt komplett raus, eine Schwankung über den Großteil des Fensters bewegt den Offset weiterhin. Wert wird als Anzahl Samples angegeben, nicht als Prozent, weil die Sample-Zahl im Fenster von der Update-Rate des Netzsensors abhängt. Effekt live vergleichbar über den ungetrimmten Rohwert (Attribut `stddev_raw` am Netz-Stabw.-Sensor, bzw. „StdDev (roh)" im Panel).
10. **Self-Adjusting Wait.** Polls die tatsächliche Ausgangsleistung nach einem Setpoint-Befehl statt einer festen Wartezeit zu schlafen. Die konfigurierte Wartezeit wird zum maximalen Timeout als Sicherheitsnetz.
11. **Export-Limit-Sync.** Ist die optionale Netz-Ausgangsleistungsgrenze-Entität konfiguriert, schreibt jeder Regelzyklus `max(Hard-Limit-Z0, Hard-Limit-Z1)` in diese Entität — sofern er abweicht. Das verhindert, dass externe Eingriffe (App, andere Automation) das Hardware-Limit dauerhaft ändern.
12. **Entladestrom-Abgleich.** Der maximale Entladestrom wird in jedem Zyklus zentral aus dem Regelzustand abgeleitet (Surplus → 2 A, AC-/Tarif-Laden → 0 A, Zone 1 → Max-Entladestrom, sonst 0 A) und mit dem Ist-Wert abgeglichen — vor dem PI-Gate, also auch im Disabled-Leerlauf. Das garantiert, dass ein Klemmwert (insb. die 2 A aus dem Surplus-Trick) nie über einen Zustandswechsel hinaus stehen bleibt und die Batterie drosselt; die einzelnen Falls setzen den Strom nicht mehr selbst.
13. **`Regelung aktiv = Aus`.** Beim Ausschalten erzwingt die Integration Ausgang → 0 W, Entladestrom → Max-Entladestrom und Modus → `'0'` — innerhalb desselben Locks wie der Regelzyklus, damit kein laufender Zyklus den Disabled-Befehl überschreibt. Danach blockt der Guard jeden weiteren Schreibbefehl, auch den Entladestrom-Abgleich aus Punkt 12. Der Sensor „Betriebsmodus“ wird explizit auf „Disabled (Regelung inaktiv)“ gesetzt. Die Flags `cycle_active` und `tariff_charge_active` bleiben bewusst erhalten, damit ein Aus/Ein-Wechsel den Regelkontext nicht verliert. Gilt identisch für Switch-Entität und Panel-Button.

---

## Erzeugte Entitäten

Die Integration erzeugt automatisch folgende Entitäten unter dem Gerät **Solakon ONE**:

| Entität | Typ | Beschreibung |
|---------|-----|-------------|
| `sensor.solakon_one_aktuelle_zone` | Sensor | Aktive Zone (0–3) mit Zusatzattributen |
| `sensor.solakon_one_betriebsmodus` | Sensor | Lesbarer Modustext |
| `sensor.solakon_one_letzte_aktion` | Sensor | Letzter Logeintrag der Steuerlogik |
| `sensor.solakon_one_netz_standardabweichung` | Sensor | Netz-Stabw. in W über das konfigurierte Fenster (getrimmt, falls konfiguriert); Rohwert als Attribut `stddev_raw` |
| `sensor.solakon_one_aktiver_fall` | Sensor | Aktiver Fall (0A, A, B, … TM) mit Klartext-Label |
| `sensor.solakon_one_pi_integral` | Sensor | Aktueller I-Anteil des PI-Reglers |
| `sensor.solakon_one_uberschussleistung` | Sensor | Verwertbarer PV-Überschuss in W — `min(aktuell geltendes Hard-Limit, PV-Leistung) − Ausgangsleistung`, geklemmt auf ≥0. Zeigt die Leistung, die über das aktuelle Hard-Limit oder die verfügbare Sonne hinaus **nicht** mehr sinnvoll ausgegeben werden kann, ohne den Akku zu belasten — z. B. für eine Automation, die bei Überschuss einen Zusatzverbraucher schaltet |
| `switch.solakon_one_regelung_aktiv` | Switch | Hauptschalter — aktiviert/deaktiviert den Schreibteil |
| `binary_sensor.solakon_one_entladezyklus_aktiv` | Binary Sensor | Internes Flag Entladezyklus |
| `binary_sensor.solakon_one_uberschuss_modus` | Binary Sensor | Flag Überschuss-Modus aktiv |
| `binary_sensor.solakon_one_ac_laden_aktiv` | Binary Sensor | Flag AC-Laden aktiv |
| `binary_sensor.solakon_one_tarif_laden_aktiv` | Binary Sensor | Flag Tarif-Laden aktiv |
| `binary_sensor.solakon_one_nachtabschaltung` | Binary Sensor | Flag Nachtabschaltung aktiv |
| `binary_sensor.solakon_one_pv_vorhersage_tarif_gesperrt` | Binary Sensor | PV-Vorhersage sperrt Tarif-Laden |
| `binary_sensor.solakon_one_pv_vorhersage_surplus_erzwungen` | Binary Sensor | PV-Vorhersage erzwingt Surplus-Eintritt |
| `binary_sensor.solakon_one_pv_vorhersage_surplus_austritt_gesperrt` | Binary Sensor | Austritts-Sperre aktiv (Vorhersage ≥ Faktor × Hard Limit Z0) |
| `binary_sensor.solakon_one_pv_vorhersage_zone_1_nacht_forcierung_aktiv` | Binary Sensor | Zone-1-Nacht-Forcierung aktiv |

Die Diagnose-Binärsensoren sind read-only — sie spiegeln interne Coordinator-Zustände wider.

---

## FAQ

**Integration oder Blueprint — was soll ich nehmen?**
Die Integration, wenn du neu anfängst: kein Helfer-Entitäten- und Script-Gerüst, Konfiguration im Panel statt in YAML, Multi-Instanz und dynamischer Offset schon eingebaut. Die Blueprints bleiben gepflegt und sind die bessere Wahl, wenn du eine laufende Installation hast, die du nicht anfassen willst. Parallelbetrieb auf demselben Wechselrichter geht nicht — beide schreiben auf dieselbe Fernsteuerungs-Entität.

**Die Anlage zieht dauerhaft Strom aus dem Netz, obwohl geregelt wird.**
Eine bekannte Ursache ist die Solakon-App: Läuft sie parallel, kann sie ihre eigene Standard-Ausgangsleistung zurückschreiben und den Regler überschreiben. Im Verlauf sieht das nach Sägezahn aus — der Ausgang läuft sauber herunter und springt periodisch wieder hoch. Abhilfe: **Standard-Ausgangsleistung in der App auf 0 W** oder einen 0-W-Zeitplan über 24 h setzen (siehe [Voraussetzungen](#voraussetzungen)).

**Der Akku ist voll, entlädt aber nicht — die PV-Leistung wird nur durchgereicht.**
Dann läuft kein Entladezyklus. Ohne aktiven Zyklus steht der Entladestrom auf 0 A und der Ausgang ist auf den PV-Überschuss gedeckelt (`min(Hard-Limit Z1, max(0, PV − Reserve))`) — die Batterie ist bewusst außen vor. Batteriestrom gibt es nur im Zone-1-Zyklus. Ob er läuft, zeigt `binary_sensor.solakon_one_entladezyklus_aktiv`; startet er nicht, sind Tarif-Lock oder Nachtabschaltung die üblichen Blockierer (siehe [Falls-Tabelle](#soc-zonen-und-steuerlogik-falls)).

**Der SOC ist unter die Zone-1-Schwelle gefallen, der Akku entlädt aber weiter.**
So ist es gedacht. Die SOC-Schwellen sind keine Zustandsgrenzen, sondern Eintritts- bzw. Austrittsbedingungen mit einem breiten Hystereseband dazwischen: Die **Zone-1-Schwelle startet** den Entladezyklus (Fall A), beendet wird er ausschließlich von der **Zone-3-Schwelle** (Fall B). Ohne diesen Abstand würde der Zyklus an der Zone-1-Schwelle dauernd ein- und ausschalten. Zone 2 ist entsprechend kein Zustand, in den man beim Unterschreiten der Zone-1-Schwelle fällt, sondern das Verhalten, solange **kein** Zyklus läuft.

**Der Akku entlädt nachts, obwohl keine Sonne scheint — ist das ein Fehler?**
Nein, gleiche Ursache: Ein einmal gestarteter Zone-1-Zyklus läuft unabhängig von der Tageszeit bis zur Zone-3-Schwelle weiter. Die Nachtabschaltung (**Nacht**-Tab) wirkt ausschließlich auf Zone 2, also auf den zyklusfreien Betrieb.

**Die Batterie entleert sich zu stark.**
Der Hebel ist die **Zone-3-Schwelle** — sie beendet den Zyklus. Die Zone-1-Schwelle anzuheben hilft nicht: sie verzögert nur den Start des nächsten Zyklus und stoppt keinen laufenden.

**Warum fließen in Zone 0 dauerhaft 2 A, auch bei PV > 0?**
Das ist eine Entladefreigabe, kein Sollwert. Bei 0 A schaltet das Gerät ab, weil der Solakon die PV nur regeln kann solange Batteriestrom fließt; 2 A ist die kleinstmögliche Obergrenze, bei der er noch regelt. Wie viel davon tatsächlich fließt, hängt von der PV ab.

**Kann ich bei guter Wettervorhersage bevorzugt einspeisen, statt die Batterie mittags vollzuladen?**
Ja — **Surplus-Forecast-Erzwingung** im **Überschuss**-Tab: Liegt die PV-Vorhersage über der eingestellten Schwelle, wird der Zone-0-Eintritt erzwungen und der Überschuss geht ins Netz statt in die Batterie. Bei schlechter Vorhersage bleibt es beim normalen Laden.

**Wie schalte ich bei Überschuss einen Verbraucher zu?**
Über `sensor.solakon_one_uberschussleistung`. Er zeigt `max(0, min(Hard-Limit, PV) − Ausgangsleistung)`, also den Spielraum zwischen dem, was gerade ausgegeben werden könnte, und dem, was tatsächlich ausgegeben wird — gedacht als Auslöser für eine eigene Automation (Smart Plug, Boiler, Wallbox).

**Ich habe mehrere Smartmeter für getrennte Stromkreise.**
Instanzen werden automatisch nach ihrem Netz-Leistungssensor in [Netzgruppen](#netzgruppen-mehrere-smartmeter) sortiert. Jede Gruppe hat ihre eigene, unabhängige Leistungsverteilung; Instanzen an verschiedenen Zählern beeinflussen sich nicht.

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
Der Reihe nach prüfen: Ist Zone 0 (Überschuss-Einspeisung) aktiv? Die blockiert AC Laden. Ist AC Laden im Tab aktiviert? Liegt `(Grid + ΣOutput_entladend)` unter −Hysterese — im Multi-Instanz-Betrieb zählt die Summe aller entladenden Instanzen, nicht der eigene Output? Ist der SOC unter dem Ladeziel? Das Status-Flag „AC Laden aktiv“ zeigt das Ergebnis.

**AC Laden bricht sofort wieder ab**
Eintritts-Hysterese zu klein — Grid-Wert schwankt bereits über der Abbruch-Schwelle. Hysterese erhöhen oder P/I kleiner setzen.

**Tarif-Laden reagiert nicht auf Preisänderungen**
Preis-Sensor im Tarif-Tab prüfen. Günstig-Schwelle muss über dem aktuellen Preis liegen. Prüfen ob Überschuss-Einspeisung aktiv ist — blockiert Tarif-Laden.

**Discharge-Lock greift nicht**
Preis muss unterhalb der Teuer-Schwelle liegen (gilt für günstig UND mittel). Modus muss `'1'` (Discharge aktiv) sein — bei Modus `'0'` (Disabled) greift TM nicht, weil keine aktive Entladung zu stoppen ist. Überschuss-Einspeisung darf nicht aktiv sein.

**Dynamischer Offset bleibt auf Minimum**
Stabw.-Sensor im Status-Tab prüfen. Nach dem ersten Start einige Minuten warten bis genug Samples gesammelt sind. Volatilitäts-Faktor erhöhen oder Rausch-Schwelle senken.

**Dynamischer Offset kehrt nachts/in Ruhephasen nicht auf das Minimum zurück (Multi-Instanz)**
Volatilitäts-Faktor senken (1.0 statt 1.5) und Rausch-Schwelle deutlich unter den Min. Offset setzen. Der Ringpuffer ist bei mehreren Instanzen am selben Netzsensor gruppengemeinsam, die Historie also bereits abgeglichen.

**Dynamischer Offset kehrt trotz Einzelbetrieb nicht auf das Minimum zurück (periodische Haushaltslast)**
Kühlgeräte oder Pumpen mit wiederkehrendem Anlaufstrom füllen jedes Stabw.-Fenster mit kurzen Ausschlägen — die Netz-Stabw. bleibt strukturell erhöht, obwohl zwischen den Pulsen Ruhe herrscht. Kein Fehlverhalten. Abhilfe: `stddev_trim_count` im Dyn.-Offset-Tab in kleinen Schritten erhöhen und die Wirkung gegen den Rohwert („StdDev (roh)“) vergleichen. Zu hohe Werte filtern auch echte Dauerunruhe weg.

**Recovery (Fall D) greift zu oft**
Der Modus-Reset-Timer läuft ab bevor der Regler ihn zurücksetzen kann. Solakon-Integration auf Polling-Intervall prüfen.

**Integration taucht nach Installation nicht auf**
Home Assistant vollständig neu starten (nicht nur neu laden). HACS-Download-Status überprüfen.

**Eine Instanz zeigt „setup_error" nach HA-Neustart oder Stromausfall (nur bei mehreren Instanzen)**
Seltene Race Condition beim parallelen Setup mehrerer Config-Entries. Die betroffene Instanz friert auf ihrem letzten Wert ein statt sichtbar zu scheitern — sie wirkt gesund, ist aber ungeregelt. Abhilfe: Config-Entry neu laden (Einstellungen → Geräte & Dienste → Instanz → drei Punkte → Neu laden).

**SOC der Instanzen läuft bei mehreren Solakons auseinander**
Bei unterschiedlich großen Batterien muss der Verteilungs-Modus auf **Kapazitätsgewichtet** stehen — „SOC-gewichtet“ rechnet bewusst ohne Kapazität und lässt ungleiche Batterien auseinanderlaufen. Danach die Kapazitätssensoren prüfen: ein **roter Validierungspunkt** heißt, die Entity existiert nicht (meist ein Tippfehler). Ohne gültige Kapazität bei allen Instanzen degradiert der Modus automatisch, mit Meldung im Status-Feld.

**Pool erreicht „Gesamte Max. Ausgangsleistung" nicht, obwohl der Verbrauch das rechtfertigen würde**
Prüfen, ob die Instanzen unterschiedliche Hard-Limits haben (Zonen-Tab) — eine Instanz unter ihrem rechnerischen Anteil wird gekappt, der Rest per Wasserfüllverfahren weitergereicht. Bleibt der Pool trotzdem darunter, reicht die Summe der Hard-Limits selbst nicht aus.

**SOC-Umschaltung rotiert häufiger als die eingestellte Divergenz-Schwelle erwarten lässt**
Normal, wenn eine Instanz zwischendurch in Zone 0 war — die Rotations-Baseline wird beim Verlassen neu verankert. Rotiert es darüber hinaus zu häufig, Divergenz-Schwelle im Verteilungs-Tab erhöhen.

---

## Lizenz

MIT — siehe [LICENSE](LICENSE)

---

## Autor

[@D4nte85](https://github.com/D4nte85)
