"""Tariflage: wirksame Schwellen, Preisvergleiche, Prognose-Unterdrückung, Tarifsperre, Meldungen."""
from __future__ import annotations

from dataclasses import dataclass

from .const import (
    TARIFF_UNIT_SUSPECT_PRICE, TARIFF_UNIT_SUSPECT_SECONDS, TARIFF_UNIT_SUSPECT_THRESHOLD,
)
from .i18n import Msg
from .schema import CycleSettings

# Einheiten-Teilstrings eines Preises in ct/kWh bzw. €/kWh.
CENT_UNITS = ("ct", "cent", "öre", "ore")
EURO_UNITS = ("€", "eur")


@dataclass(frozen=True)
class TariffState:
    """Tariflage eines Zyklus: Preis, wirksame Schwellen, Vergleiche, Prognose-Unterdrückung, Meldungen.

    `price` ist 0.0 ohne gültigen Preis. `below_exp` und `below_cheap` gelten nur bei
    wirksamem Tarif mit gültigem Preis; ohne sie beendet HT ein laufendes Tarif-Laden.
    `suppressed`: Die PV-Prognose erreicht ihre Schwelle und setzt Tarif-Laden und
    Tarifsperre aus. `price_warning` meldet den Preissensor ohne Zahl, `unit_warning`
    den Verdacht auf €/kWh.
    """

    price: float
    cheap: float
    exp: float
    below_exp: bool
    below_cheap: bool
    suppressed: bool = False
    price_warning: Msg | None = None
    unit_warning: Msg | None = None

    @property
    def warnings(self) -> tuple[Msg, ...]:
        """Meldungen der Tariflage in Ausgabereihenfolge: Preissensor, dann Einheit."""
        return tuple(w for w in (self.price_warning, self.unit_warning) if w)

    @property
    def allows_discharge(self) -> bool:
        """Start von Zone 1/2 (A, E) erlaubt: Preis nicht unter der Teuer-Schwelle."""
        return not self.below_exp

    def discharge_locked(self, charging: bool, surplus: bool) -> bool:
        """Tarifsperre für D, TM, die Rückkehr in Modus 1 und die Anzeige: Preis unter der Teuer-Schwelle, keine Lade-Session, kein Überschuss."""
        return self.below_exp and not charging and not surplus


class Tariff:
    """Tariflage je Zyklus; hält die Prognose-Unterdrückung und den Verdacht auf einen €/kWh-Preis über Zyklen.

    `suppressed` gilt ab `forecast`; bei ausgeschalteter Regelung und nach einem Kernsensor ohne Zahl
    leert ihn der Coordinator mit der Prognoselage.
    """

    def __init__(self) -> None:
        self.unit_suspect_since: float = 0.0
        self.suppressed: bool = False

    def forecast(self, pv_forecast: float | None, cs: CycleSettings) -> None:
        """Prognose-Unterdrückung des Zyklus: PV-Prognose vorhanden und mindestens ihre Schwelle."""
        self.suppressed = pv_forecast is not None and pv_forecast >= cs.pv_forecast_threshold

    def assess(
        self, cs: CycleSettings, *, price: float | None, unit: str, price_warning: Msg | None,
        cheap_entity: float | None, exp_entity: float | None, now: float,
    ) -> TariffState:
        """Tariflage aus Preis, Schwellen und der Prognose-Unterdrückung aus `forecast` desselben Zyklus.

        `price` ist None ohne Preissensor, ohne Zahl oder bei ausgeschaltetem Tarif.
        Eine Schwellen-Entität ohne Zahl (`None`) fällt auf den Settings-Wert zurück.
        """
        suppressed = self.suppressed
        cheap = cheap_entity if cheap_entity is not None else cs.tariff_cheap
        exp = exp_entity if exp_entity is not None else cs.tariff_exp
        valid = price is not None
        value = price if price is not None else 0.0
        usable = cs.tariff_enabled and not suppressed and valid
        if not valid:
            self._clear_suspect()
        return TariffState(
            price=value, cheap=cheap, exp=exp,
            below_exp=usable and value < exp,
            below_cheap=usable and value < cheap,
            suppressed=suppressed,
            price_warning=price_warning,
            unit_warning=self._unit_warning(unit, value, cheap, now) if valid else None,
        )

    def _clear_suspect(self) -> None:
        """Verdacht auf €-Einheit beenden."""
        self.unit_suspect_since = 0.0

    def _unit_warning(self, unit: str, price: float, cheap: float, now: float) -> Msg | None:
        """Meldung, wenn der Preis-Sensor vermutlich €/kWh statt ct/kWh liefert, sonst None.

        Kriterium ist der Wert: ein Preis unter TARIFF_UNIT_SUSPECT_PRICE bei einer
        Günstig-Schwelle ab TARIFF_UNIT_SUSPECT_THRESHOLD ist in ct/kWh kaum erreichbar.
        Gemeldet wird erst nach TARIFF_UNIT_SUSPECT_SECONDS ununterbrochenem Verdacht und
        nur bei price >= 0. Eine ct-Einheit unterdrückt die Meldung, eine €-Einheit macht
        sie sofort. Umgerechnet wird nichts.
        """
        if any(token in unit for token in CENT_UNITS):
            self.unit_suspect_since = 0.0
            return None

        if not (cheap >= TARIFF_UNIT_SUSPECT_THRESHOLD and 0.0 <= price < TARIFF_UNIT_SUSPECT_PRICE):
            self.unit_suspect_since = 0.0
            return None

        if not self.unit_suspect_since:
            self.unit_suspect_since = now

        euro_unit = any(token in unit for token in EURO_UNITS)
        if not euro_unit and now - self.unit_suspect_since < TARIFF_UNIT_SUSPECT_SECONDS:
            return None

        return ("warn_tariff_unit", {"price": price, "cheap": cheap})
