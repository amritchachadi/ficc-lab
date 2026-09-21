"""Tests for schedule generation, month arithmetic and business day adjustment."""

from datetime import date, timedelta

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from rates_analytics.conventions import (
    BusinessDayConvention,
    Calendar,
    DayCount,
    Frequency,
    Generation,
    add_months,
    generate_schedule,
    year_fraction,
)

_D = date
_DATES = st.dates(min_value=date(1995, 1, 1), max_value=date(2060, 12, 31))
_ADJUSTING = [
    BusinessDayConvention.FOLLOWING,
    BusinessDayConvention.MODIFIED_FOLLOWING,
    BusinessDayConvention.PRECEDING,
    BusinessDayConvention.MODIFIED_PRECEDING,
]


def test_add_months_clamps_into_a_short_month() -> None:
    assert add_months(_D(2007, 1, 31), 1) == _D(2007, 2, 28)
    assert add_months(_D(2008, 1, 31), 1) == _D(2008, 2, 29)


def test_add_months_with_eom_pins_to_the_month_end() -> None:
    """Clamping and the EOM rule diverge on the way out of February.

    Without the rule, 29 February is carried forward as a day number; with
    it, the date tracks the month end instead.
    """
    assert add_months(_D(2008, 2, 29), 2) == _D(2008, 4, 29)
    assert add_months(_D(2008, 2, 29), 2, eom=True) == _D(2008, 4, 30)


def test_add_months_is_anchored_not_iterative() -> None:
    """Rolling out and back from the anchor is lossless for mid-month days."""
    anchor = _D(2007, 1, 15)
    assert add_months(add_months(anchor, 7), -7) == anchor


def test_semiannual_schedule_boundaries() -> None:
    dates = generate_schedule(_D(2020, 3, 15), _D(2023, 3, 15), Frequency.SEMIANNUAL)
    assert dates[0] == _D(2020, 3, 15)
    assert dates[-1] == _D(2023, 3, 15)
    assert len(dates) == 7


def test_backward_generation_puts_the_stub_at_the_front() -> None:
    dates = generate_schedule(_D(2020, 1, 20), _D(2023, 3, 15), Frequency.SEMIANNUAL)
    assert dates[0] == _D(2020, 1, 20)
    assert dates[1] == _D(2020, 3, 15)
    assert dates[-1] == _D(2023, 3, 15)


def test_forward_generation_puts_the_stub_at_the_back() -> None:
    dates = generate_schedule(
        _D(2020, 3, 15),
        _D(2023, 5, 1),
        Frequency.SEMIANNUAL,
        generation=Generation.FORWARD,
    )
    assert dates[-2] == _D(2023, 3, 15)
    assert dates[-1] == _D(2023, 5, 1)


def test_modified_following_does_not_cross_into_the_next_month() -> None:
    """31 May 2020 is a Sunday: Following rolls into June, Modified must not."""
    cal = Calendar()
    assert cal.adjust(_D(2020, 5, 31), BusinessDayConvention.FOLLOWING) == _D(2020, 6, 1)
    assert cal.adjust(_D(2020, 5, 31), BusinessDayConvention.MODIFIED_FOLLOWING) == _D(
        2020, 5, 29
    )


def test_holidays_are_respected() -> None:
    cal = Calendar(holidays=[_D(2021, 7, 5)])
    assert not cal.is_business_day(_D(2021, 7, 5))
    assert cal.adjust(_D(2021, 7, 5), BusinessDayConvention.FOLLOWING) == _D(2021, 7, 6)


def test_terminal_date_can_be_left_unadjusted() -> None:
    """Many bonds pay on an unadjusted maturity even with adjusted coupons."""
    saturday = _D(2021, 5, 15)
    assert saturday.weekday() == 5
    dates = generate_schedule(
        _D(2019, 5, 15),
        saturday,
        Frequency.SEMIANNUAL,
        convention=BusinessDayConvention.FOLLOWING,
        adjust_terminal=False,
    )
    assert dates[-1] == saturday


def test_end_before_start_raises() -> None:
    with pytest.raises(ValueError, match="strictly after"):
        generate_schedule(_D(2021, 1, 1), _D(2020, 1, 1), Frequency.ANNUAL)


@given(
    start=_DATES,
    tenor_days=st.integers(min_value=40, max_value=365 * 30),
    frequency=st.sampled_from(list(Frequency)),
    convention=st.sampled_from([*_ADJUSTING, BusinessDayConvention.UNADJUSTED]),
    eom=st.booleans(),
    generation=st.sampled_from(list(Generation)),
)
def test_schedules_are_strictly_increasing(
    start: date,
    tenor_days: int,
    frequency: Frequency,
    convention: BusinessDayConvention,
    eom: bool,
    generation: Generation,
) -> None:
    end = start + timedelta(days=tenor_days)
    assume(end.year <= 2070)
    dates = generate_schedule(
        start,
        end,
        frequency,
        convention=convention,
        eom=eom,
        generation=generation,
    )
    assert len(dates) >= 2
    assert all(b > a for a, b in zip(dates, dates[1:], strict=True))


@given(
    start=_DATES,
    tenor_days=st.integers(min_value=40, max_value=365 * 20),
    frequency=st.sampled_from(list(Frequency)),
    convention=st.sampled_from(_ADJUSTING),
)
def test_every_adjusted_date_is_a_business_day(
    start: date, tenor_days: int, frequency: Frequency, convention: BusinessDayConvention
) -> None:
    end = start + timedelta(days=tenor_days)
    assume(end.year <= 2070)
    cal = Calendar()
    dates = generate_schedule(start, end, frequency, convention=convention)
    assert all(cal.is_business_day(d) for d in dates)


@given(d=_DATES)
def test_modified_conventions_stay_within_the_month(d: date) -> None:
    cal = Calendar()
    for convention in (
        BusinessDayConvention.MODIFIED_FOLLOWING,
        BusinessDayConvention.MODIFIED_PRECEDING,
    ):
        assert cal.adjust(d, convention).month == d.month


@given(
    start=_DATES,
    tenor_days=st.integers(min_value=40, max_value=365 * 20),
    frequency=st.sampled_from(list(Frequency)),
)
def test_accruals_over_a_schedule_tile_the_whole_life(
    start: date, tenor_days: int, frequency: Frequency
) -> None:
    """Act/360 is additive, so the coupon periods must tile the bond life exactly."""
    end = start + timedelta(days=tenor_days)
    assume(end.year <= 2070)
    dates = generate_schedule(start, end, frequency)
    total = sum(
        year_fraction(a, b, DayCount.ACT_360)
        for a, b in zip(dates, dates[1:], strict=True)
    )
    assert total == pytest.approx(year_fraction(dates[0], dates[-1], DayCount.ACT_360))
