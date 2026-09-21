"""Known-value tests for day count conventions.

Cases are taken from the ISDA 2006 Definitions and SIFMA worked examples,
plus pairs chosen specifically to separate conventions that agree on
ordinary dates and diverge only at month ends.
"""

from datetime import date

import pytest

from rates_analytics.conventions import DayCount, year_fraction

_D = date


@pytest.mark.parametrize(
    ("start", "end", "expected_days"),
    [
        (_D(2007, 1, 15), _D(2007, 1, 30), 15),
        (_D(2007, 1, 15), _D(2007, 2, 15), 30),
        (_D(2007, 1, 15), _D(2007, 7, 15), 180),
        (_D(2007, 9, 30), _D(2008, 3, 31), 180),
        (_D(2007, 9, 30), _D(2007, 10, 31), 30),
        (_D(2007, 8, 31), _D(2008, 2, 29), 179),
        # D2 is the 31st but D1 is before the 30th, so D2 is *not* truncated.
        (_D(2007, 1, 15), _D(2007, 1, 31), 16),
    ],
)
def test_thirty_360_us_known_values(start: date, end: date, expected_days: int) -> None:
    assert year_fraction(start, end, DayCount.THIRTY_360_US) == pytest.approx(expected_days / 360.0)


@pytest.mark.parametrize(
    ("start", "end", "expected_days"),
    [
        (_D(2007, 1, 15), _D(2007, 1, 30), 15),
        (_D(2007, 9, 30), _D(2008, 3, 31), 180),
        (_D(2007, 8, 31), _D(2008, 2, 29), 179),
        # The discriminating case against 30/360 US: 30E/360 always
        # truncates the 31st, regardless of the start day.
        (_D(2007, 1, 15), _D(2007, 1, 31), 15),
    ],
)
def test_thirty_e_360_known_values(start: date, end: date, expected_days: int) -> None:
    assert year_fraction(start, end, DayCount.THIRTY_E_360) == pytest.approx(expected_days / 360.0)


def test_thirty_e_360_isda_rolls_a_short_february_to_thirty() -> None:
    """29 February is a month end, so ISDA rolls it to 30 and plain 30E/360 does not.

    This one pair separates the two conventions that are most often
    conflated in instrument static data.
    """
    start, end = _D(2007, 8, 31), _D(2008, 2, 29)
    assert year_fraction(start, end, DayCount.THIRTY_E_360_ISDA) == pytest.approx(180 / 360.0)
    assert year_fraction(start, end, DayCount.THIRTY_E_360) == pytest.approx(179 / 360.0)


def test_thirty_e_360_isda_exempts_a_february_termination_date() -> None:
    start, end = _D(2007, 8, 31), _D(2008, 2, 29)
    assert year_fraction(
        start, end, DayCount.THIRTY_E_360_ISDA, is_termination=True
    ) == pytest.approx(179 / 360.0)


def test_thirty_360_us_february_rule_is_gated_on_the_eom_flag() -> None:
    """Two consecutive February month ends are a full year only under the EOM rule."""
    start, end = _D(2008, 2, 29), _D(2009, 2, 28)
    assert year_fraction(start, end, DayCount.THIRTY_360_US, eom=True) == pytest.approx(1.0)
    assert year_fraction(start, end, DayCount.THIRTY_360_US, eom=False) == pytest.approx(
        359 / 360.0
    )


def test_actual_conventions() -> None:
    start, end = _D(2007, 1, 15), _D(2007, 2, 15)
    assert year_fraction(start, end, DayCount.ACT_360) == pytest.approx(31 / 360.0)
    assert year_fraction(start, end, DayCount.ACT_365F) == pytest.approx(31 / 365.0)


def test_act_act_isda_splits_at_the_year_boundary() -> None:
    """ISDA worked example: 61 days in 2003 over 365, 121 days in 2004 over 366."""
    value = year_fraction(_D(2003, 11, 1), _D(2004, 5, 1), DayCount.ACT_ACT_ISDA)
    assert value == pytest.approx(61 / 365.0 + 121 / 366.0)
    assert value == pytest.approx(0.497724380, abs=1e-9)


def test_act_act_icma_returns_exactly_one_period() -> None:
    """A full semiannual coupon period is 0.5 regardless of its actual length."""
    start, end = _D(2003, 11, 1), _D(2004, 5, 1)
    assert year_fraction(
        start,
        end,
        DayCount.ACT_ACT_ICMA,
        ref_period_start=start,
        ref_period_end=end,
        frequency=2,
    ) == pytest.approx(0.5)


def test_act_act_icma_requires_its_reference_period() -> None:
    with pytest.raises(ValueError, match="requires ref_period_start"):
        year_fraction(_D(2003, 11, 1), _D(2004, 5, 1), DayCount.ACT_ACT_ICMA)


def test_reversed_dates_raise_rather_than_returning_a_negative_fraction() -> None:
    with pytest.raises(ValueError, match="precedes"):
        year_fraction(_D(2008, 1, 1), _D(2007, 1, 1), DayCount.ACT_360)
