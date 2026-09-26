"""Rückgekoppelter Streckensimulator für das AC-Laden.

Gerätemodell nach der Messung vom 2026-09-26 (Wiki: 2026-09-26-ac-geraeteverhalten-messung):
Totzeit bis zur Übernahme eines Sollwerts, Rampe 34 W/s beim Erhöhen, schneller Anlauf aus 0
mit 75 W/s bis höchstens 160 W, Senken als Sprung mit Unterschwingen, Totzone ±10 W mit
bleibender Abweichung, Mindestladeleistung. Netz = Hauslast + Ladeleistung; Netz- und
Ist-Sensor melden in eigenem Takt. Ein Regelzyklus läuft bei jeder Netzmeldung, sofern der
vorige mit seiner Wartezeit fertig ist, und liest dabei Netz, Ist-Leistung und Sollwert.

Alle Leistungen positiv als Ladeleistung, das Netz positiv als Bezug.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable

DT = 0.1


@dataclass
class Geraet:
    """Ladeleistung des Geräts, das einem übernommenen Sollwert folgt."""

    totzeit: float = 2.0
    rampe: float = 34.0
    anlauf: float = 75.0
    anlauf_bis: float = 160.0
    totzone: float = 10.0
    unterschwingen: float = 15.0
    aus_unter: float = 15.0
    stabil_ab: float = 45.0
    seed: int = 1
    leistung: float = 0.0
    _ziel: float = 0.0
    _anlauf_aktiv: bool = False
    _befehle: list = field(default_factory=list)
    _rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def schreiben(self, t: float, wert: float) -> None:
        """Sollwert, den das Gerät nach der Totzeit übernimmt."""
        self._befehle.append((t + self.totzeit, wert))

    def _uebernehmen(self, wert: float) -> None:
        if abs(wert - self._ziel) <= self.totzone and self._ziel > 0:
            return
        abweichung = self._rng.uniform(-self.totzone, self.totzone)
        self._ziel = 0.0 if wert < self.aus_unter else max(0.0, wert + abweichung)
        if self._ziel < self.leistung - self.totzone:
            self.leistung = max(0.0, self._ziel - self.unterschwingen) if self._ziel > 0 else 0.0
        elif self.leistung == 0 and self._ziel > 0:
            self._anlauf_aktiv = True

    def schritt(self, t: float) -> None:
        """Einen Zeitschritt DT weiterrechnen."""
        while self._befehle and self._befehle[0][0] <= t:
            self._uebernehmen(self._befehle.pop(0)[1])
        if 0 < self._ziel < self.stabil_ab:
            self.leistung = self._ziel + (20.0 if int(t) % 2 else -20.0)
            return
        if self.leistung < self._ziel:
            schnell = self._anlauf_aktiv and self.leistung < self.anlauf_bis
            rate = self.anlauf if schnell else self.rampe
            self.leistung = min(self._ziel, self.leistung + rate * DT)
            if self.leistung >= self.anlauf_bis:
                self._anlauf_aktiv = False
        elif self.leistung > self._ziel:
            self.leistung = self._ziel
        if self.leistung >= self._ziel:
            self._anlauf_aktiv = False


@dataclass
class Messpunkt:
    """Zustand zu einem Zeitpunkt der Simulation."""

    t: float
    netz: float
    ladeleistung: float
    sollwert: float


# regler(netz, ist_ladeleistung, sollwert) -> neuer Sollwert oder None (nichts schreiben)
Regler = Callable[[float, float, float], "float | None"]


def simulieren(
    regler: Regler,
    hauslast: Callable[[float], float],
    dauer: float,
    geraet: Geraet | None = None,
    netz_takt: float = 2.0,
    ist_takt: float = 1.0,
    wartezeit: float = 3.0,
) -> list[Messpunkt]:
    """Geschlossener Regelkreis über `dauer` Sekunden; liefert den Verlauf in DT-Schritten."""
    g = geraet or Geraet()
    netz_meldung = hauslast(0.0)
    ist_meldung = 0.0
    sollwert = 0.0
    frei_ab = 0.0
    verlauf: list[Messpunkt] = []
    for n in range(int(dauer / DT)):
        t = round(n * DT, 3)
        g.schritt(t)
        netz = hauslast(t) + g.leistung
        if abs(t / ist_takt - round(t / ist_takt)) < 1e-6:
            ist_meldung = g.leistung
        if abs(t / netz_takt - round(t / netz_takt)) < 1e-6:
            netz_meldung = netz
            if t >= frei_ab:
                neu = regler(netz_meldung, ist_meldung, sollwert)
                if neu is not None:
                    sollwert = neu
                    g.schreiben(t, neu)
                    frei_ab = t + wartezeit
        verlauf.append(Messpunkt(t, netz, g.leistung, sollwert))
    return verlauf


def stufen(*punkte: tuple[float, float]) -> Callable[[float], float]:
    """Hauslast als Treppe: (ab Sekunde, Wert), aufsteigend."""
    def last(t: float) -> float:
        wert = punkte[0][1]
        for ab, w in punkte:
            if t >= ab:
                wert = w
        return wert
    return last


def bewertung(verlauf: list[Messpunkt], ziel: float, von: float, bis: float, band: float = 25.0) -> dict:
    """Kennzahlen im Fenster [von, bis) gegen die nötige Ladeleistung `ziel`.

    Überschwingen: höchste Ladeleistung über dem Ziel (Netzbezug über den Offset hinaus),
    gezählt ab dem ersten Eintritt ins Band; die Störung selbst zählt nicht.
    Einschwingzeit: letzter Zeitpunkt außerhalb des Bands, ab Fensterbeginn.
    """
    fenster = [p for p in verlauf if von <= p.t < bis]
    ausserhalb = [p.t for p in fenster if abs(p.ladeleistung - ziel) > band]
    erst = next((i for i, p in enumerate(fenster) if abs(p.ladeleistung - ziel) <= band), len(fenster))
    danach = [p.ladeleistung - ziel for p in fenster[erst:]]
    return {
        "ueberschwingen": round(max([0.0, *danach]), 1),
        "einschwingzeit": round((ausserhalb[-1] + DT - von) if ausserhalb else 0.0, 1),
        "schreibvorgaenge": sum(1 for a, b in zip(verlauf, verlauf[1:])
                                if von <= b.t < bis and a.sollwert != b.sollwert),
    }
