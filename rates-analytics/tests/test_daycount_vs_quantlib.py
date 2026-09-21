"""Cross-validation of the day count layer against QuantLib.

This is the repo's core validation idea: the conventions module is written
from the published specifications and depends on nothing, and QuantLib is
an independent implementation of the same specifications. Where the two
agree over randomly generated dates, both are probably right. Where they
disagree, the disagreement is itself the interesting result and belongs in
the README rather than being papered over.

Skips cleanly when QuantLib is not installed, so the pure-Python layer
stays testable on its own.
"""

from datetime import date, timedelta
from typing import Any

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from rates_analytics.conventions import DayCount, year_fraction

ql: Any = pytest.importorskip("QuantLib", reason="QuantLib is an optional cross-check")

_DATES = st.dates(min_value=date(1995, 1, 1), max_value=date(2060, 12, 31))
_TOL = 1e-12


def _to_ql(d: date) -> Any:
    return ql.Date(d.day, d.month, d.year)


@given(start=_DATES, end=_DATES)
def test_act_360_matches_quantlib(start: date, end: date) -> None:
    assume(start <= end)
    expected = ql.Actual360().yearFraction(_to_ql(start), _to_ql(end))
    assert year_fraction(start, end, DayCount.ACT_360) == pytest.approx(expected, abs=_TOL)


@given(start=_DATES, end=_DATES)
def test_act_365_fixed_matches_quantlib(start: date, end: date) -> None:
    assume(start <= end)
    expected = ql.Actual365Fixed().yearFraction(_to_ql(start), _to_ql(end))
    assert year_fraction(start, end, DayCount.ACT_365F) == pytest.approx(expected, abs=_TOL)


@given(start=_DATES, end=_DATES)
def test_act_act_isda_matches_quantlib(start: date, end: date) -> None:
    assume(start <= end)
    expected = ql.ActualActual(ql.ActualActual.ISDA).yearFraction(_to_ql(start), _to_ql(end))
    assert year_fraction(start, end, DayCount.ACT_ACT_ISDA) == pytest.approx(expected, abs=_TOL)


@given(start=_DATES, end=_DATES)
def test_thirty_e_360_matches_quantlib_eurobond_basis(start: date, end: date) -> None:
    assume(start <= end)
    counter = ql.Thirty360(ql.Thirty360.EurobondBasis)
    expected = counter.yearFraction(_to_ql(start), _to_ql(end))
    assert year_fraction(start, end, DayCount.THIRTY_E_360) == pytest.approx(expected, abs=_TOL)


@given(start=_DATES, end=_DATES)
def test_thirty_360_us_matches_quantlib_under_the_eom_rule(start: date, end: date) -> None:
    """QuantLib's USA variant applies the February rules unconditionally.

    Our implementation gates them on an explicit ``eom`` flag, because
    whether a security follows the end-of-month rule is instrument static
    data and not inferable from a date pair. Passing ``eom=True`` is
    therefore the correct comparison; ``eom=False`` has no QuantLib
    counterpart by design.
    """
    assume(start <= end)
    expected = ql.Thirty360(ql.Thirty360.USA).yearFraction(_to_ql(start), _to_ql(end))
    assert year_fraction(start, end, DayCount.THIRTY_360_US, eom=True) == pytest.approx(
        expected, abs=_TOL
    )


@given(
    ref_start=_DATES,
    # QuantLib infers the coupon frequency from the reference period length
    # as round(12 * days / 365), so only periods that round to six months
    # are a like-for-like comparison against an explicit frequency of 2.
    length_days=st.integers(min_value=170, max_value=195),
    offset_days=st.integers(min_value=0, max_value=195),
)
def test_act_act_icma_matches_quantlib_isma(
    ref_start: date, length_days: int, offset_days: int
) -> None:
    """Compare a partial accrual inside a semiannual reference period."""
    ref_end = ref_start + timedelta(days=length_days)
    accrual_end = min(ref_start + timedelta(days=offset_days), ref_end)
    assume(ref_end.year <= 2060)

    expected = ql.ActualActual(ql.ActualActual.ISMA).yearFraction(
        _to_ql(ref_start), _to_ql(accrual_end), _to_ql(ref_start), _to_ql(ref_end)
    )
    actual = year_fraction(
        ref_start,
        accrual_end,
        DayCount.ACT_ACT_ICMA,
        ref_period_start=ref_start,
        ref_period_end=ref_end,
        frequency=2,
    )
    assert actual == pytest.approx(expected, abs=1e-10)
