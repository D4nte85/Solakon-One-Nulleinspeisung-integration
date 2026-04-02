# ⚡ Solakon ONE Nulleinspeisung

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue)](https://www.home-assistant.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Vollautomatische **Nulleinspeisung** für den **Solakon ONE** Wechselrichter als native Home Assistant Integration — kein Blueprint, keine Helfer-Entitäten, keine manuelle YAML-Pflege.

Die Integration regelt die Ausgangsleistung des Wechselrichters über einen **PI-Regler** so, dass der Netzbezug möglichst bei 0 W gehalten wird. Alle Parameter werden über ein **Sidebar-Panel** direkt in der HA-Oberfläche konfiguriert und persistent gespeichert.

---

## Funktionsübersicht

### Kernfunktion — Nulleinspeisung mit PI-Regler

Die Netzleistung ist die Regelgröße, die Wechselrichterausgangsleistung die Stellgröße. Der P-Anteil reagiert sofort auf Abweichungen, der I-Anteil gleicht dauerhaften Offset aus. Ein konfigurierbares Totband verhindert unnötige Stelleingriffe bei kleinen Schwankungen. Optional wartet der Regler auf die tatsächliche Leistungsübernahme des Wechselrichters statt auf eine feste Wartezeit (Self-Adjusting Wait).

### SOC-Zonenverwaltung

Das Verhalten wird abhängig vom Batterie-Ladestand in vier Zonen eingeteilt:

| Zone | Bedingung | Verhalten |
|------|-----------|-----------|
| **Zone 0** | SOC ≥ Export-Schwelle (optional) | Überschuss-Einspeisung — Leistung über Eigenbedarf hinaus |
| **Zone 1** | SOC ≥ Zone-1-Schwelle | Aggressive Entladung — erhöhter Entladestrom |
| **Zone 2** | Zone-3-Schwelle < SOC < Zone-1-Schwelle | Normalbetrieb — batterieschonend |
| **Zone 3** | SOC ≤ Zone-3-Schwelle | Sicherheitsstopp — Entladung gesperrt |

### Optionale Module

**☀️ Überschuss-Einspeisung (Zone 0)** — Wenn PV-Erzeugung den Eigenbedarf um mehr als eine konfigurierbare Hysterese übersteigt und der SOC eine Zielschwelle erreicht hat, wird der Wechselrichter über den Nullpunkt hinaus angesteuert. Ein SOC-Hysterese-Band verhindert Flackern beim Ein- und Ausschalten.

**⚡ AC-Laden** — Steuert den Wechselrichter in den Lademodus, wenn der SOC unter ein Ziel fällt und externer Überschuss erkannt wird. Eigener PI-Regler mit separaten P/I-Faktoren, eigenem Offset und konfigurierbarer Leistungsobergrenze.

**💹 Tarif-Arbitrage** — Wertet einen externen Strompreis-Sensor aus und lädt bei günstigem Tarif automatisch auf, sperrt die Entladung bei mittlerem Tarif und gibt sie bei teurem Tarif wieder frei.

**📈 Dynamischer Offset** — Berechnet den Nullpunkt-Offset automatisch aus der Netz-Volatilität (Standardabweichung). Ersetzt den separaten Dynamic-Offset-Blueprint — alle Parameter sind pro Zone (Zone 1, Zone 2, Zone AC) einzeln konfigurierbar, inklusive optionalem negativem Offset.

**🌙 Nachtabschaltung** — Unterdrückt in Zone 2 den Entladebetrieb unterhalb einer konfigurierbaren PV-Erzeugungsschwelle (Nacht/Bewölkung).

### 📊 Interner Stabilitätssensor

Die Integration berechnet intern die **Standardabweichung der Netzleistung** über ein konfigurierbares Zeitfenster (Standard: 60 s). Der Sensor wird ohne externe Helfer direkt aus dem Messwert-Stream erzeugt und gibt eine Aussage über die Netzstabilität — nützlich zur Diagnose und als Grundlage für die integrierte dynamische Offset-Logik.

---

## Voraussetzungen

- Home Assistant 2024.1 oder neuer
- [HACS](https://hacs.xyz) installiert
- Solakon ONE Wechselrichter mit Modbus-Integration in HA
- Sensor für die Netzleistung (z. B. Shelly 3EM, Shelly PM)

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

---

## Konfiguration im Sidebar-Panel

Nach der Einrichtung erscheint in der HA-Seitenleiste der Eintrag **Solakon ONE**. Das Panel ist in acht Tabs gegliedert:

---

### 📊 Status

> Echtzeit-Übersicht aller Regelzustände. Zeigt die aktive Zone, Messwerte, interne Flags und die letzte Regelaktion auf einen Blick.

Zeigt in Echtzeit:
- Aktuell aktive Zone mit farblichem Banner (Zone 0–3)
- Netzleistung, Solarleistung, Ausgangsleistung, SOC
- Netz-Standardabweichung (Stabilitätsindikator)
- PI-Integral-Wert
- Dynamischer Offset Zone 1 / Zone 2 (wenn aktiv)
- Zeitabstand seit letzter Regelaktion
- Letzte Aktion und etwaige Fehlermeldungen
- Status-Flags: Zyklus, Surplus, AC Laden, Tarif-Laden
- Schaltfläche zum manuellen Zurücksetzen des PI-Integrals

---

### 🎛️ PI-Regler

> Kern des Regelkreises. Der PI-Regler passt die AC-Ausgangsleistung des Wechselrichters dynamisch an, um den Netzbezug auf den konfigurierten Zielwert (Offset) zu regeln. Der P-Anteil reagiert sofort auf aktuelle Abweichungen, der I-Anteil summiert Abweichungen über die Zeit auf und eliminiert bleibende Regelabweichungen. Anti-Windup begrenzt das Integral auf ±1000. Bei jedem Zonenwechsel wird das Integral zurückgesetzt. Toleranz-Decay baut das Integral um 5 % pro Zyklus ab, solange der Fehler innerhalb der Toleranz liegt und |Integral| > 10.

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| P-Faktor | Proportionale Verstärkung — sofortige Reaktion auf Abweichung | 0,3–0,8 |
| I-Faktor | Integrale Verstärkung — gleicht dauerhaften Offset aus | 0,05–0,15 |
| Totband (W) | Abweichungen innerhalb dieses Bereichs lösen keinen Stelleingriff aus | 0–30 |
| Wartezeit (s) | Feste Pause zwischen Stelleingriffen (ohne Self-Adjust) oder maximales Timeout als Sicherheitsnetz (mit Self-Adjust) | 10–20 |
| Stabw.-Fenster (s) | Zeitfenster für den internen Standardabweichungs-Sensor | 30–300 |
| Self-Adjusting Wait | Wartet auf die tatsächliche WR-Ausgangsleistung statt fester Wartezeit. Die Wartezeit wird zum Max-Timeout. | Empfohlen |
| Zielwert-Toleranz (W) | Abweichung in Watt, ab der der Zielwert als erreicht gilt (nur bei Self-Adjust) | 2–5 |

**PI-Einstellung von Grund auf:** P-Faktor auf 0,5 und I-Faktor auf 0 setzen. Wartezeit auf 15 s. Beobachten, ob der Regler schwingt oder zu träge ist, dann P schrittweise anpassen. I erst einführen, wenn P-Regelung stabil ist.

---

### 🔋 Zonen

> SOC-Zonenlogik: Steuert das Verhalten des Wechselrichters abhängig vom Batterieladestand. Zone 1 (aggressiv) läuft bis zum Zone-3-Stopp — kein Yo-Yo-Effekt zwischen den Zonen. Zone 2 (batterieschonend) begrenzt die Ausgangsleistung dynamisch auf Max(0, PV − Reserve) und setzt den Entladestrom auf 0 A. Zone 3 (Sicherheitsstopp) setzt Output auf 0 W und Modus auf Disabled.

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Zone 1 SOC-Schwelle (%) | SOC über diesem Wert → Zone 1 (aggressiv) | 40–60 |
| Zone 3 SOC-Schwelle (%) | SOC unter diesem Wert → Zone 3 (Stopp) | 15–25 |
| Max. Entladestrom (A) | Entladestrom in Zone 1 (Zone 2 = 0 A, Surplus = 2 A) | 25–40 |
| Hard Limit (W) | Absolute Obergrenze der Ausgangsleistung in Zone 0 und Zone 1 | 800 |
| Zone 1 Offset (W) | Statischer Zielwert des Reglers in Zone 1. Bei aktivem Dyn. Offset überschrieben | 20–50 |
| Zone 2 Offset (W) | Statischer Zielwert des Reglers in Zone 2 | 10–30 |
| PV-Ladereserve (W) | Watt, die für Batterie-Laden reserviert bleiben (Zone-2-Limit + Nachtschwelle) | 30–100 |

Der **Nullpunkt-Offset** verschiebt den Zielwert des Reglers — ein positiver Wert von z. B. 30 W lässt den Regler auf 30 W Netzbezug regeln (Sicherheitspuffer gegen versehentliche Einspeisung). Ein negativer Wert lässt den Regler gezielt leicht einspeisen.

---

### ☀️ Überschuss

> Optionale Überschuss-Einspeisung (Zone 0). Wenn PV-Erzeugung den Eigenbedarf übersteigt und der Akku ausreichend geladen ist, wird die Leistung über den Nullpunkt hinaus hochgefahren. Ein SOC-Hysterese-Band und eine PV-Hysterese verhindern Flackern bei schwankenden Bedingungen. In Zone 0 wird das PI-Integral eingefroren (kein Decay, kein PI-Aufruf). Der Entladestrom wird auf 2 A (Stabilitätspuffer) gesetzt.

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Aktivieren | Ein/Aus-Schalter für Überschuss-Einspeisung | — |
| SOC-Schwelle (%) | Ab diesem SOC wird Überschuss eingespeist | 90–98 |
| SOC-Hysterese (%) | Austritt erst bei SOC < (Schwelle − Hysterese) | 3–5 |
| PV-Hysterese (W) | Eintritt: PV > Verbrauch + Hysterese; Austritt: PV ≤ Verbrauch − Hysterese | 30–80 |

---

### ⚡ AC Laden

> Optionales AC-Laden bei erkanntem externem Überschuss. Aktiv in Zone 1 und Zone 2. Eintritt: SOC < Ladeziel UND Modus ≠ '3' UND (Grid + Output) < −Hysterese. Der Lademodus verwendet einen eigenen PI-Regler mit separaten P/I-Faktoren und einem eigenen Offset. Wegen der langen Hardware-Flanke des Wechselrichters (~25 s) empfiehlt sich ein kleiner P-Faktor (~0,3–0,5) — der I-Anteil macht die eigentliche Regelarbeit. SOC-Schutz (Zone 3) bleibt vollständig aktiv.

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Aktivieren | Ein/Aus-Schalter für AC Laden | — |
| Ladeziel SOC (%) | Laden stoppt bei diesem SOC. Empfohlen: ≤ Zone-1-Schwelle | 80–95 |
| Max. Ladeleistung (W) | Obergrenze der AC-Ladeleistung | 400–800 |
| Eintritts-Hysterese (W) | (Grid + Output) muss unter −Hysterese liegen | 30–80 |
| Regel-Offset (W) | Zielwert während AC Laden (typisch negativ). Bei Dyn. Offset überschrieben | −80 bis −30 |
| AC P-Faktor | Klein halten wegen langer Hardware-Flanke | 0,3–0,5 |
| AC I-Faktor | Macht bei AC Laden die eigentliche Regelarbeit | 0,05–0,1 |

---

### 💹 Tarif

> Optionale Tarif-Arbitrage. Wertet einen externen Strompreis-Sensor aus (z. B. Tibber, aWATTar) und steuert das Ladeverhalten nach drei Preisstufen: **Günstig** (Preis < Günstig-Schwelle) → AC-Laden mit fester Leistung bis SOC-Ziel. **Mittel** (Günstig-Schwelle ≤ Preis < Teuer-Schwelle) → Discharge-Lock in Zone 2 (Entladung gesperrt, Batterie schonen). **Teuer** (Preis ≥ Teuer-Schwelle) → normale SOC-Logik, Zone 1 läuft weiter.

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Aktivieren | Ein/Aus-Schalter für Tarif-Steuerung | — |
| Preis-Sensor | Sensor-Entität mit aktuellem Strompreis in ct/kWh | — |
| Günstig-Schwelle (ct/kWh) | Unter diesem Preis → Laden | 5–15 |
| Teuer-Schwelle (ct/kWh) | Über diesem Preis → normale SOC-Logik | 20–35 |
| Ladeziel SOC (%) | Tarif-Laden stoppt bei diesem SOC | 85–95 |
| Ladeleistung (W) | Feste Leistung während Tarif-Laden | 400–800 |

---

### 📈 Dyn. Offset

> Optionaler dynamischer Offset. Berechnet den Nullpunkt-Offset automatisch aus der Netz-Volatilität (Standardabweichung der letzten 60 s). Bei ruhigem Netz bleibt der Offset auf dem Minimum, bei unruhigem Netz (z. B. taktende Kompressoren, Waschmaschinen) steigt er automatisch. Ersetzt den separaten Dynamic-Offset-Blueprint und überschreibt die statischen Offsets in den Zonen-Einstellungen. Jede Zone (Zone 1, Zone 2, Zone AC) hat eigene Parameter. Optionaler negativer Offset negiert den berechneten Wert (Regelziel < 0 W).
>
> **Offset-Formel:** `offset = clamp(min + max(0, (StdDev − Rausch) × Faktor), min, max)`

Jede Zone hat einen eigenen Parameterblock mit identischer Struktur:

| Parameter | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| Aktivieren | Ein/Aus-Schalter für Dynamischen Offset | — |
| Min. Offset (W) | Grundpuffer bei ruhigem Netz | 20–40 |
| Max. Offset (W) | Obergrenze bei unruhigem Netz | 150–300 |
| Rausch-Schwelle (W) | StdDev unterhalb dieses Werts = Messrauschen, kein Anstieg | 10–20 |
| Volatilitäts-Faktor | Verstärkung oberhalb der Rausch-Schwelle | 1,0–2,0 |
| Negativer Offset | Offset negieren (Regelziel < 0 W statt > 0 W) | Aus |

---

### 🌙 Nacht

> Optionale Nachtabschaltung. Deaktiviert Zone 2 automatisch wenn die PV-Erzeugung unter die PV-Ladereserve fällt (kein separater Parameter — die PV-Ladereserve aus den Zonen-Einstellungen wird verwendet). Zone 1 (aggressive Entladung) und AC Laden laufen auch nachts weiter.

| Parameter | Beschreibung |
|-----------|-------------|
| Aktivieren | Ein/Aus-Schalter für Nachtabschaltung |

---

Änderungen werden erst nach Klick auf **💾 Speichern** übernommen. Die Speicherleiste erscheint automatisch sobald ein Wert geändert wurde.

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
| `switch.solakon_one_entladezyklus_aktiv` | Switch | Internes Flag Entladezyklus |
| `switch.solakon_one_uberschuss_modus` | Switch | Flag Überschuss-Modus aktiv |
| `switch.solakon_one_ac_laden_aktiv` | Switch | Flag AC-Laden aktiv |
| `switch.solakon_one_tarif_laden_aktiv` | Switch | Flag Tarif-Laden aktiv |

Die Switch-Entitäten sind schreibgeschützt — sie spiegeln interne Zustände wider und können nicht manuell geschaltet werden.

---

## Fehlerbehebung

**Panel öffnet sich, zeigt aber keine Werte an**
Integration neu laden (Einstellungen → Geräte & Dienste → Solakon → drei Punkte → Neu laden). Falls das Problem bleibt, HA-Protokoll auf Fehler der Domain `solakon_nulleinspeisung` prüfen.

**Werte werden nicht gespeichert**
Im Browser-Konsolenfenster (F12) nach WebSocket-Fehlern schauen. Häufige Ursache: Integration wurde noch nicht vollständig geladen.

**Regler schwingt (Leistung pendelt stark)**
P-Faktor reduzieren oder Wartezeit erhöhen. Der Standardabweichungs-Sensor im Status-Tab zeigt, wie instabil das Netz gerade ist — bei hohem Wert (> 50 W) größeres Totband setzen.

**Zone 3 aktiv, obwohl Batterie nicht leer ist**
Zone-3-Schwelle im Zonen-Tab prüfen. Wert muss kleiner als Zone-1-Schwelle sein.

**AC Laden startet nicht trotz Überschuss**
Prüfen ob AC Laden im Tab aktiviert ist und ob die Eintritts-Hysterese erfüllt wird: (Grid + Output) muss unter −Hysterese liegen. Der SOC muss unter dem Ladeziel sein.

**Tarif-Laden reagiert nicht auf Preisänderungen**
Preis-Sensor im Tarif-Tab prüfen — muss eine gültige Sensor-Entität mit numerischem Wert in ct/kWh sein. Günstig-Schwelle muss über dem aktuellen Preis liegen.

**Dynamischer Offset bleibt auf Minimum**
Stabw.-Sensor im Status-Tab prüfen. Nach dem ersten Start braucht der Sensor einige Minuten bis genug Samples gesammelt sind. Volatilitäts-Faktor erhöhen oder Rausch-Schwelle senken falls der Offset zu träge reagiert.

**Integration taucht nach Installation nicht auf**
Home Assistant vollständig neu starten (nicht nur neu laden). HACS-Download-Status überprüfen.

---

## Lizenz

MIT — siehe [LICENSE](LICENSE)

---

## Autor

[@D4nte85](https://github.com/D4nte85)
