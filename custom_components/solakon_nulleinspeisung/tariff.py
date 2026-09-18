"""Tariflage: wirksame Schwellen, Preisvergleiche, Prognosesperre, Entladesperre, Einheitenwarnung."""
from __future__ import annotations

from dataclasses import dataclass

from .const import (
    TARIFF_UNIT_SUSPECT_PRICE, TARIFF_UNIT_SUSPECT_SECONDS, TARIFF_UNIT_SUSPECT_THRESHOLD,
)
from .i18n import Msg


def forecast_suppressed(pv_forecast: float | None, threshold: float) -> bool:
    """True, wenn die PV-Prognose den Tarif abschaltet: Wert vorhanden und mindestens `threshold`."""
    return pv_forecast is not None and pv_forecast >= threshold


@dataclass(frozen=True)
class TariffState:
    """Preislage eines Zyklus: Preis, wirksame Schwellen und Vergleiche.

    `price` ist 0.0 ohne gültigen Preis. `below_exp` und `below_cheap` gelten nur bei
    wirksamem Tarif, `at_least_cheap` bei jedem gültigen Preis — HT beendet das
    Tarif-Laden auch bei abgeschaltetem Tarif.
    """

    price: float
    cheap: float
    exp: float
    below_exp: bool
    below_cheap: bool
    at_least_cheap: bool
    unit_warning: Msg | None = None

    @property
    def allows_discharge(self) -> bool:
        """Start von Zone 1/2 (A, E) erlaubt: Preis nicht unter der Teuer-Schwelle."""
        return not self.below_exp

    def discharge_locked(self, charging: bool, surplus: bool) -> bool:
        """Entladesperre für D, TM und die Anzeige: Preis unter der Teuer-Schwelle, keine Lade-Session, kein Überschuss."""
        return self.below_exp and not charging and not surplus


class Tariff:
    """Tariflage je Zyklus; hält den Verdacht auf einen €/kWh-Preis über Zyklen."""

    def __init__(self) -> None:
        self.unit_suspect_since: float = 0.0

    def assess(
        self, *, enabled: bool, suppressed: bool, price: float | None,
        cheap_entity: float | None, cheap_setting: float,
        exp_entity: float | None, exp_setting: float, unit: str, now: float,
    ) -> TariffState:
        """Tariflage aus Preis, Schwellen und Prognosesperre.

        `enabled`: Tarif eingeschaltet und Preissensor gesetzt. Eine Schwellen-Entität
        ohne Zahl (`None`) fällt auf den Settings-Wert zurück.
        """
        cheap = cheap_entity if cheap_entity is not None else cheap_setting
        exp = exp_entity if exp_entity is not None else exp_setting
        valid = price is not None
        value = price if price is not None else 0.0
        usable = enabled and not suppressed and valid
        return TariffState(
            price=value, cheap=cheap, exp=exp,
            below_exp=usable and value < exp,
            below_cheap=usable and value < cheap,
            at_least_cheap=valid and value >= cheap,
            unit_warning=self._unit_warning(unit, value, cheap, now) if valid else None,
        )

    def _unit_warning(self, unit: str, price: float, cheap: float, now: float) -> Msg | None:
        """Meldung, wenn der Preis-Sensor vermutlich €/kWh statt ct/kWh liefert, sonst None.

        Kriterium ist der Wert: ein Preis unter TARIFF_UNIT_SUSPECT_PRICE bei einer
        Günstig-Schwelle ab TARIFF_UNIT_SUSPECT_THRESHOLD ist in ct/kWh kaum erreichbar.
        Gemeldet wird erst nach TARIFF_UNIT_SUSPECT_SECONDS ununterbrochenem Verdacht und
        nur bei price >= 0. Eine ct-Einheit unterdrückt die Meldung, eine €-Einheit macht
        sie sofort. Umgerechnet wird nichts.
        """
        if any(token in unit for token in ("ct", "cent", "öre", "ore")):
            self.unit_suspect_since = 0.0
            return None

        if not (cheap >= TARIFF_UNIT_SUSPECT_THRESHOLD and 0.0 <= price < TARIFF_UNIT_SUSPECT_PRICE):
            self.unit_suspect_since = 0.0
            return None

        if not self.unit_suspect_since:
            self.unit_suspect_since = now

        euro_unit = any(token in unit for token in ("€", "eur"))
        if not euro_unit and now - self.unit_suspect_since < TARIFF_UNIT_SUSPECT_SECONDS:
            return None

        return ("warn_tariff_unit", {"price": price, "cheap": cheap})
