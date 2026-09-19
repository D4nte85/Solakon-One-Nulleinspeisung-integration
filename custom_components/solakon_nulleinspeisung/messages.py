"""Meldungen eines Regelzyklus als Bausteine: weiche Fehler, harter Fehler, Schreibwarnung."""
from __future__ import annotations

from .i18n import Msg


class CycleMessages:
    """Sammelt die Fehlerkette eines Zyklus.

    Ein harter Fehler ersetzt alle übrigen Bausteine. Sonst folgen die weichen
    Fehler in Meldereihenfolge, danach die Warnung aus dem Schreibpfad. Von ihr
    gibt es einen Platz, die letzte Meldung gilt.
    """

    def __init__(self) -> None:
        self._soft: list[Msg] = []
        self._fail: Msg | None = None
        self.hardware_msg: Msg | None = None

    def warn(self, msg: Msg) -> None:
        """Weichen Fehler anhängen."""
        self._soft.append(msg)

    def fail(self, msg: Msg) -> None:
        """Harten Fehler setzen."""
        self._fail = msg

    def hardware(self, msg: Msg) -> None:
        """Warnung aus dem Schreibpfad setzen."""
        self.hardware_msg = msg

    @property
    def msgs(self) -> list[Msg]:
        """Fehlerkette in Anzeigereihenfolge."""
        if self._fail is not None:
            return [self._fail]
        return self._soft + ([self.hardware_msg] if self.hardware_msg else [])
