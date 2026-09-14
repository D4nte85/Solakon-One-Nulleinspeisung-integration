# Testumgebung

Home Assistant läuft hier nicht. `harness.py` stellt ein `FakeHass` mit Zustandsspeicher,
virtueller Uhr und Aufrufprotokoll bereit, `ha_stubs.py` die HA-Module, die die Integration
importiert. Drei Schichten nutzen das:

| Schicht | Zweck | Aufruf |
|---|---|---|
| Charakterisierung | Verhalten über Zufallsszenarien festhalten, Referenz in `golden/` | `pytest tests` · neu schreiben nur nach gewollter Änderung: `python tests/regen.py [art]` |
| Invarianten | Verhaltensregeln nach jedem Regellauf aller Charakterisierungsszenarien prüfen | `pytest tests` · Zählung je Regel: `python -m tests.invarianten [regel ...]` |
| Reproduktion | einen Fehlervorgang als benanntes Szenario abspielen | `python tests/repro.py tests/repro/<name>.yaml` |
| Panel | Render-Vergleich von `solakon-panel.js` gegen einen git-Stand | `python tests/panel/vergleich.py [REV]` |

## Einrichtung

```bash
python -m venv ~/.cache/solakon-tests-venv
~/.cache/solakon-tests-venv/bin/pip install -r tests/requirements.txt
~/.cache/solakon-tests-venv/bin/pytest -q -p no:cacheprovider tests
npm install --prefix tests/panel        # nur für den Panel-Vergleich (jsdom)
```

Die Geräteseite der Attrappe folgt der offiziellen Geräte-Integration (Stand 1.7.0).
`geraet.py` hält je genutzter Entity Default-ID (de/en), Einheit, `device_class`,
`min`/`max`/`step` und Select-Optionen mit Beleg; es ist die einzige Quelle dafür und wird
eingecheckt. Die Attribute stehen als Standard an den Zuständen, ein Szenario kann sie
überschreiben. `number.set_value` außerhalb `min`/`max` und unbekannte Select-Optionen
bleiben ohne Wirkung, wie in HA ohne `blocking`. Geschrieben wird `int(value)`, auf `step`
wird nicht gerundet. Den Klon selbst lesen die Tests nicht; er dient beim Nachziehen einer
neuen Version als Referenz:

```bash
git clone https://github.com/solakon-de/solakon-one-homeassistant tests/geraet-integration
git -C tests/geraet-integration pull --tags && git -C tests/geraet-integration describe --tags
```

## Reproduktionsszenarien

Eine Datei je Fehlervorgang unter `tests/repro/`, benannt wie die Bugfix-Seite
(`issue-NN-slug.yaml` bzw. `fix-YYYY-MM-DD-slug.yaml`). Ablauf: Szenario schreiben, am
Stand vor dem Fix rot sehen, Fix, grün — danach bleibt es als Regressionstest in
`pytest tests` (über `test_repro.py`). Ein noch nicht behobener Fehler bekommt
`offen: true` und muss dann rot sein.

```yaml
titel: Kurzbeschreibung
bezug: fix-2026-09-12-sollwert-ueber-entity-max   # Bugfix-Seite
offen: false          # true: Fehler noch nicht behoben, Szenario muss rot sein
sprache: de           # de | en
stunde: 3             # Uhrzeit (UTC) für Nachtlogik
netz: 50              # sensor.grid; Zahl in W oder {wert, einheit, alter}
sensoren:             # gemeinsame Entities mit voller ID
  sensor.preis: {wert: 8.0, einheit: ct/kWh}
verteilung: {}        # optional: Verteilungs-Config der Netzgruppe sensor.grid
instanzen:
  - prefix: a         # erste Instanz immer a; weitere b, c …
    settings: {regulation_enabled: true, tariff_power: 2000}   # über SETTINGS_DEFAULTS
    flags: {cycle_active: false}                              # gespeicherte Zustandsflags
    sensoren: {soc: 40, modus: "1"}   # soc solar ist countdown leistung entladestrom timeout modus export kapazitaet
    integral: 0.0
    folgt_ist: 1      # Ist-Sensor folgt dem Sollwert: 1, -1, 0 (meldet, bleibt stehen), null (gar nicht)
schritte:             # je Schritt: Uhr vor, Sensoren setzen, regeln
  - nach: 0
  - nach: 5
    setzen: {netz: 250, a.soc: 39, sensor.preis: 30.0}
    settings: {tariff_enabled: false}   # optional: über async_update_settings der Instanz a
    wer: a            # a | all
erwartet:
  - schritt: alle     # Nummer ab 1, letzter (Standard) oder alle
    kein_aufruf: {entity: a.leistung, wert_min: 1201}
  - schritt: 1
    instanz: a
    zustand: {tariff_charge_active: true}
  - aufruf: {entity: select.a_mode, wert: "3"}
  - log: Teiltext einer WARNING
```

`zustand` prüft Attribute aus `COORD_ATTRS` in `harness.py` auf Gleichheit, `zustand_nicht` auf Ungleichheit (z. B. `last_error: ""` für „Fehlermeldung gesetzt"). `aufruf`/`kein_aufruf` prüfen
die Schreibbefehle eines Schritts auf eine Entity, optional mit `wert`, `wert_min`,
`wert_max`.

### Aus einem HA-Verlauf

Der CSV-Export des HA-Verlaufs (Spalten `entity_id,state,last_changed`) lässt sich in ein
Szenario-Gerüst übersetzen; Settings, Flags und Erwartungen trägt man danach ein:

```bash
python tests/repro_import.py verlauf.csv --map netz=sensor.shelly_power \
    --map a.soc=sensor.solakon_soc --map a.ist=sensor.solakon_ist \
    --von 2026-09-01T10:00 --bis 2026-09-01T10:30 > tests/repro/issue-NN-slug.yaml
```

Standard ist ein Regelschritt je Änderung des Netzsensors (`--takt netz`), alternativ ein
festes Raster in Sekunden (`--takt 5`). Einheiten, die der Export nicht enthält, gibt
`--einheit netz=kW` an.

## Invarianten

`invarianten.py` hält die Regeln für gewolltes Verhalten als Funktionen `(ctx) -> str | None`,
eine je Regel mit der Nummer aus der Regelbeschreibung (`a1` … `k5`). Jede prüft einen
Regellauf einer Instanz: Eingänge davor, Schreibbefehle, Zustand danach.

- Gezählt werden nur Läufe mit konsistentem Startzustand; Treffer aus widersprüchlichen
  Startflags prüfen das Heilen und laufen getrennt mit.
- Regeln in `VERZOEGERT` gelten nur in Läufen ohne Übergang (kein Fallwechsel, kein
  geschriebener Modus), weil der erste zutreffende Fall gewinnt.
- `test_invarianten.py` prüft jede Regel einzeln. Eine Regel mit offener Bugfix-Seite steht
  in `OFFEN` und muss rot sein; wird sie grün, ist der Eintrag zu entfernen.

## Panel-Vergleich

`tests/panel/render.cjs` lädt `index.html` mit dem echten Panel in jsdom und nimmt über eine
feste Aktionsfolge rund 300 Schnappschüsse des Shadow-DOM auf: 3 Szenarien × 2 Sprachen,
alle Tabs, Eingaben, Speichern, Debug-Schalter, Verteilung, Wettläufe mit Instanzwechsel und
Fehlerpfade. `vergleich.py` rendert einen git-Stand und den Arbeitsstand und zeigt die
Unterschiede; `--ignoriere REGEX` blendet bewusste Änderungen aus.
