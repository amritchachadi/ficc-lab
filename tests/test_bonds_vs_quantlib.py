"""Cross-check of the bond functions against QuantLib."""

from datetime import date
from typing import Any

import pytest

from rates_analytics.bonds.fixed import (
    accrued_interest,
    bond_cash_flows,
    price_from_yield,
    yield_to_maturity,
)

ql: Any = pytest.importorskip("QuantLib", reason="QuantLib is an optional cross-check")


def _ql_bond() -> Any:
    """Return QuantLib's version of the 2-year 4% semiannual bond, valued on 15 Jan 2026."""
    today = ql.Date(15, 1, 2026)
    ql.Settings.instance().evaluationDate = today
    schedule = ql.Schedule(
        today,
        ql.Date(15, 1, 2028),
        ql.Period(ql.Semiannual),
        ql.NullCalendar(),
        ql.Unadjusted,
        ql.Unadjusted,
        ql.DateGeneration.Backward,
        False,
    )
    return ql.FixedRateBond(0, 100.0, schedule, [0.04], ql.ActualActual(ql.ActualActual.ISMA))


def test_accrued_interest_matches_quantlib() -> None:
    """Act/Act ICMA accrued on 15 Mar 2026 agrees with QuantLib."""
    expected = _ql_bond().accruedAmount(ql.Date(15, 3, 2026))
    actual = accrued_interest(100, 0.04, 2, date(2026, 1, 15), date(2026, 3, 15), date(2026, 7, 15))
    assert actual == pytest.approx(expected, abs=1e-12)


def test_price_from_yield_matches_quantlib() -> None:
    """Price from yield at 5% agrees with QuantLib."""
    dc = ql.ActualActual(ql.ActualActual.ISMA)
    today = ql.Date(15, 1, 2026)
    expected = ql.BondFunctions.cleanPrice(
        _ql_bond(), 0.05, dc, ql.Compounded, ql.Semiannual, today
    )
    flows = bond_cash_flows(100, 0.04, 2, 4)
    actual = price_from_yield(flows, yield_rate=0.05, frequency=2)
    assert actual == pytest.approx(expected, abs=1e-10)


def test_yield_from_price_matches_quantlib() -> None:
    """Yield to maturity at price 99.6 agrees with QuantLib."""
    dc = ql.ActualActual(ql.ActualActual.ISMA)
    today = ql.Date(15, 1, 2026)
    price = 99.6
    ql_price = ql.BondPrice(price, ql.BondPrice.Clean)
    expected = ql.BondFunctions.bondYield(
        _ql_bond(), ql_price, dc, ql.Compounded, ql.Semiannual, today
    )
    flows = bond_cash_flows(100, 0.04, 2, 4)
    actual = yield_to_maturity(flows, price=price, frequency=2)
    assert actual == pytest.approx(expected, abs=1e-8)
