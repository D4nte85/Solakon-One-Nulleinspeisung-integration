# Testumgebung

Home Assistant läuft hier nicht. `harness.py` stellt ein `FakeHass` mit Zustandsspeicher,
virtueller Uhr und Aufrufprotokoll bereit, `ha_stubs.py` die HA-Module, die die Integration
importiert. Vier Schichten nutzen das:

| Schicht | Zweck | Aufruf |
|---|---|---|
| Charakterisierung | Verhalten über Zufallsszenarien festhalten, Referenz in `golden/` | `pytest tests` · neu schreiben nur nach gewollter Änderung: `python tests/regen.py [art]` |
| Invarianten | Verhaltensregeln nach jedem Regellauf aller Charakterisierungsszenarien prüfen | `pytest tests` · Zählung je Regel: `python -m tests.invarianten [regel ...]` |
| Reproduktion | einen Fehlervorgang als benanntes Szenario abspielen | `python tests/repro.py tests/repro/<name>.yaml` |
| Panel | Render-Vergleich von `solakon-panel.js` gegen einen git-Stand | `python tests/panel/vergleich.py [REV]` |

Zustände folgen Home Assistant: Setzen mit gleichem Zustand und gleichen Attributen rückt nur
`last_reported` vor, `last_updated` bleibt stehen. Das gilt auch für Szenario-Zustände und
Repro-`setzen`; nur ein ausdrückliches `age` (`alter`) setzt `last_updated`. Ein Ist-Sensor mit
`folgt_ist: 0` meldet also neu, gilt für die Stillstandserkennung aber als unverändert.
`last_reported` ist der Zeitpunkt des Setzens. Jede Lesung der Uhr (`time.time()`) rückt sie um
eine Mikrosekunde vor, so liegt eine Meldung vor einem Schreibbefehl echt davor. Folger-Sensoren
melden nach dem Service-Call wie ein Poll: bei der nächsten Lesung, dem nächsten Setzen oder zu
Beginn des nächsten Wartens.

Entitäten folgen Home Assistant im Lebenszyklus (`test_lebenszyklus.py`): Die Hinzufüge-Funktion
`hass.config_entries.adder(entry_id)` führt die Entitäten je Eintrag, weist eine zweite lebende
Entität mit gleicher `unique_id` ab und führt `async_added_to_hass` aus. `Entity.async_remove`
führt `async_will_remove_from_hass` aus, `async_unload_platforms` entfernt so die Entitäten des
Eintrags, bevor `async_unload_entry` die Instanz abräumt.

`Store` und Tasks folgen Home Assistant (`helpers/storage.py`). `hass.storage[key]` hält den
Umschlag wie die Datei in `.storage` (`version`, `minor_version`, `data`): Tests legen Stände
über `h.put_store` ab und lesen sie über `h.stored`. Laden migriert ältere Versionen über
`_async_migrate_func` und speichert das Ergebnis. `async_delay_save` schreibt erst nach Ablauf
der Frist, und zwar den Stand zum Schreibzeitpunkt. `async_remove` verwirft nur den
Schreibauftrag der eigenen Instanz. `async_create_task` plant die Koroutine ein, statt sie im
Aufrufer auszuführen. `await hass.async_block_till_done()` arbeitet die eingeplanten Tasks ab
und danach die fälligen Schreibaufträge. Den Inhalt protokolliert die Attrappe erst beim
Schreiben (`store_write`). Szenarioläufe rufen `_async_regulate` je Schritt selbst auf, schreiben
zu Beginn jedes Schritts die fälligen Aufträge, am Ende des Laufs alle übrigen, und schließen
angestoßene Zyklen am Ende ungelaufen (`h.run`, `conftest.py`).

Der Szenariogenerator (`scenarios.py`) zieht aus einem Zufallsstrom je Szenarioart. Neue
Settings kommen über `gen_settings_ext` aus einem zweiten Strom (`solakon-<art>-ext`) dazu; so
bleibt die Hauptfolge stabil und ein neues Golden zeigt nur die Wirkung der neuen Felder.

## Einrichtung

Die Tests laufen im System-Python (`/usr/bin/python3`) — kein venv, keine pyenv-Version.
Die Pakete aus `tests/requirements.txt` kommen aus der Paketverwaltung:

```bash
sudo pacman -S --needed python-pytest python-voluptuous python-yaml
python3 -m pytest -q -p no:cacheprovider tests
npm install --prefix tests/panel        # nur für den Panel-Vergleich (jsdom)
```

Die Geräteseite der Attrappe folgt der offiziellen Geräte-Integration (Stand 1.7.0).
`geraet.py` hält je genutzter Entity Default-ID (de/en), Einheit, `device_class`,
`min`/`max`/`step` und Select-Optionen mit Beleg; es ist die einzige Quelle dafür und wird
eingecheckt. Die Attribute stehen als Standard an den Zuständen, ein Szenario kann sie
überschreiben. `number.set_value` außerhalb `min`/`max` und unbekannte Select-Optionen
bleiben ohne Wirkung, wie in HA ohne `blocking`. Geschrieben wird `int(value)`, auf `step`
wird nicht gerundet. Den Klon selbst lesen die Tests nicht (`conftest.py` schließt ihn von
`pytest tests` aus); er dient beim Nachziehen einer
neuen Version als Referenz:

```bash
git clone https://github.com/solakon-de/solakon-one-homeassistant tests/geraet-integration
git -C tests/geraet-integration pull --tags && git -C tests/geraet-integration describe --tags
```

Der Config-Flow hat eigene Tests in `test_config_flow.py`. Geräte- und Entitätsregistrierung
aus `ha_stubs.py` bilden dort Solakon-Geräte nach (`DeviceEntry`, `RegistryEntry` mit
`unique_id`, Gerät und `disabled_by`); Schlüssel und Domain je Feld kommen aus
`geraet.ENTITIES`.

## CI

Bei Push und Pull Request laufen `tests.yml` (`ruff check --select F` und `pytest` unter
Python 3.12 und 3.14) und `validate.yml` (HACS ohne Brands, `hassfest`). `ruff` prüft nur die
pyflakes-Regeln: undefinierte Namen, unbenutzte Importe und Variablen, auch in Zweigen, die
die Tests selten erreichen. `hassfest` prüft `manifest.json` und das Schema der
Übersetzungsdateien, die `pytest` über die HA-Stubs nicht sieht. Gleiche Schlüssel in `de`
und `en` prüft `test_translations.py`.

## Reproduktionsszenarien

Eine Datei je Fehlervorgang unter `tests/repro/`, benannt wie die Bugfix-Seite
(`issue-NN-slug.yaml`, `fix-YYYY-MM-DD-slug.yaml`, für neue Funktionen `feat-…`, aus Reviews
`review-…`). Ablauf: Szenario schreiben, am
Stand vor dem Fix rot sehen, Fix, grün — danach bleibt es als Regressionstest in
`pytest tests` (über `test_repro.py`). Ein noch nicht behobener Fehler bekommt
`offen: true` und muss dann rot sein. Unbekannte Felder in Szenario, Instanz, Schritt, Erwartung
und Bedingung sowie eine unbekannte `instanz` sind ein Szenariofehler.

```yaml
titel: Kurzbeschreibung
bezug: fix-2026-09-12-sollwert-ueber-entity-max   # Bugfix-Seite
offen: true           # optional: Fehler noch nicht behoben, Szenario muss rot sein
sprache: de           # de | en
stunde: 3             # Uhrzeit (UTC) für Nachtlogik
netz: 50              # sensor.grid; Zahl in W oder {wert, einheit, alter}
sensoren:             # gemeinsame Entities mit voller ID
  sensor.preis: {wert: 8.0, einheit: ct/kWh}
verteilung: {}        # optional: Verteilungs-Config der Netzgruppe sensor.grid
verteilung_netz: {}   # optional: Configs weiterer Netzgruppen, {sensor.grid_other: {...}}
instanzen:
  - prefix: a         # erste Instanz immer a; weitere b, c …
    netzsensor: sensor.grid   # optional; sensor.grid_other bildet eine zweite Netzgruppe (Wert wie netz)
    settings: {regulation_enabled: true, tariff_power: 1000}   # über SETTINGS_DEFAULTS
    flags: {cycle_active: false, charge_session: tariff_charge}   # gespeicherte Zustandsflags; charge_session none|ac_charge|tariff_charge|grid_charge; unbekannte Flags sind ein Szenariofehler
    gespeichert: false   # optional: Settings am Laden vorbei, ohne Rücksetzen auf den Standard; ohne flags
    sensoren: {soc: 40, modus: "1"}   # soc solar ist countdown leistung entladestrom timeout modus export kapazitaet
    integral: 0.0
    vorheriger_ist: 0.0   # Ist-Leistung des vorigen Regelzyklus (`surplus.prev_actual`)
    export_limit: true    # false: Instanz ohne Export-Limit-Entität
    folgt_ist: 1      # Ist-Sensor folgt dem Sollwert: 1, -1, 0 (meldet, bleibt stehen), null (gar nicht)
schritte:             # je Schritt: Uhr vor, Sensoren setzen, regeln
  - nach: 0
  - nach: 5
    setzen: {netz: 250, a.soc: 39, sensor.preis: 30.0}
    settings: {tariff_enabled: false}   # optional: über async_update_settings der Instanz a
    wer: a            # a | all
    nach_aufruf: {entity: a.export, setzen: {a.solar: unavailable}}   # optional: einmalig nach dem ersten Schreibbefehl auf entity, auch wenn HA ihn abweist
erwartet:
  - schritt: alle     # Nummer ab 1, letzter (Standard) oder alle
    kein_aufruf: {entity: a.leistung, wert_min: 1201}
  - schritt: 1
    instanz: a
    zustand: {charge_session: tariff_charge}
  - aufruf: {entity: select.a_mode, wert: "3"}
  - log: Teiltext einer WARNING
```

`nach_aufruf` setzt Sensoren mitten im Regelzyklus, sobald die Integration zum ersten Mal auf `entity` schreibt, auch wenn HA den Wert abweist. So lässt sich ein Ausfall zwischen zwei Lesungen desselben Regelzyklus nachstellen. Der Eintrag gilt nur für seinen Schritt.

`zustand` prüft Attribute aus `COORD_ATTRS` in `harness.py` auf Gleichheit; der Schlüssel ist der Pfad am Coordinator (`display.operating_state`, `surplus.prev_actual`, `dyn.offsets.z1_night`). `zustand_nicht` auf Ungleichheit (z. B. `last_error: ""` für „Fehlermeldung gesetzt"). `aufruf`/`kein_aufruf` prüfen
die Schreibbefehle eines Schritts auf eine Entity, optional mit `wert`, `wert_min`,
`wert_max`. Trägt eine Erwartung mehrere Prüfarten, ist sie nur erfüllt, wenn jede erfüllt ist.

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
eine je Regel mit der Nummer aus der Regelbeschreibung (`a1` … `k9`; `d2` ist entfallen). Jede prüft einen
Regellauf einer Instanz: Eingänge davor, Schreibbefehle, Zustand danach.

- Gezählt werden nur Läufe mit konsistentem Startzustand; Treffer aus widersprüchlichen
  Startflags prüfen das Heilen und laufen getrennt mit.
- Der Szenariogenerator schreibt die Art der Lade-Session direkt als `charge_session` in den
  Speicherstand; die Regeln lesen sie über `invarianten._art` und `invarianten._session`.
- Regeln in `VERZOEGERT` gelten nur in Läufen ohne Übergang (kein Fallwechsel, kein
  geschriebener Modus), weil der erste zutreffende Fall gewinnt.
- `test_invarianten.py` prüft jede Regel einzeln. Eine Regel mit offener Bugfix-Seite steht
  in `OFFEN` und muss rot sein; wird sie grün, ist der Eintrag zu entfernen.

## Panel-Vergleich

`tests/panel/render.cjs` lädt `index.html` mit dem echten Panel in jsdom und nimmt über eine
feste Aktionsfolge rund 300 Schnappschüsse des Shadow-DOM auf: 4 Szenarien × 2 Sprachen,
alle Tabs, Eingaben, Validierungspunkt (Zahl, Text, fehlende Entity), Speichern, Debug-Schalter,
Verteilung, Wettläufe mit Instanzwechsel und Fehlerpfade. `vergleich.py` rendert einen git-Stand
und den Arbeitsstand, jeweils mit den Panel- und Entity-Texten dieses Stands, und zeigt die
Unterschiede; `--ignoriere REGEX` blendet bewusste Änderungen aus.
