"""Property-based tests for day count conventions.

The invariants here are the ones that hold for *every* date pair, which is
where hand-picked examples tend not to reach: additivity across a split
point, monotonicity, and the exact-period identity for Act/Act ICMA.
"""

from datetime import date, timedelta

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from rates_analytics.conventions import DayCount, year_fraction

_DATES = st.dates(min_value=date(1990, 1, 1), max_value=date(2070, 12, 31))

# The 30/360 family is deliberately excluded: truncating the 31st means a
# period split on a month end double-counts or drops a day, so these
# conventions are not additive and asserting that they are would be wrong.
_ADDITIVE = [DayCount.ACT_360, DayCount.ACT_365F, DayCount.ACT_ACT_ISDA]

_SIMPLE = [
    DayCount.THIRTY_360_US,
    DayCount.THIRTY_E_360,
    DayCount.THIRTY_E_360_ISDA,
    DayCount.ACT_360,
    DayCount.ACT_365F,
    DayCount.ACT_ACT_ISDA,
]


@given(d=_DATES, convention=st.sampled_from(_SIMPLE))
def test_a_degenerate_period_is_zero(d: date, convention: DayCount) -> None:
    assert year_fraction(d, d, convention) == 0.0


@given(start=_DATES, end=_DATES, convention=st.sampled_from(_SIMPLE))
def test_year_fractions_are_never_negative(
    start: date, end: date, convention: DayCount
) -> None:
    assume(start <= end)
    assert year_fraction(start, end, convention) >= 0.0


@given(start=_DATES, mid=_DATES, end=_DATES, convention=st.sampled_from(_ADDITIVE))
def test_additive_conventions_split_exactly(
    start: date, mid: date, end: date, convention: DayCount
) -> None:
    assume(start <= mid <= end)
    whole = year_fraction(start, end, convention)
    parts = year_fraction(start, mid, convention) + year_fraction(mid, end, convention)
    assert parts == pytest.approx(whole, rel=1e-12, abs=1e-12)


@given(
    start=_DATES,
    end=_DATES,
    extra=st.integers(min_value=1, max_value=400),
    convention=st.sampled_from(_SIMPLE),
)
def test_extending_the_period_never_shortens_it(
    start: date, end: date, extra: int, convention: DayCount
) -> None:
    assume(start <= end)
    later = end + timedelta(days=extra)
    assume(later.year <= 2070)
    assert year_fraction(start, later, convention) >= year_fraction(start, end, convention)


@given(
    ref_start=_DATES,
    length_days=st.integers(min_value=28, max_value=370),
    frequency=st.sampled_from([1, 2, 4, 12]),
)
def test_act_act_icma_on_a_full_period_is_exactly_one_over_frequency(
    ref_start: date, length_days: int, frequency: int
) -> None:
    """The denominator is the reference period, so a full period is frequency-exact.

    This is the property that makes Act/Act ICMA immune to the leap-year
    distortion Act/Act ISDA carries.
    """
    ref_end = ref_start + timedelta(days=length_days)
    assume(ref_end.year <= 2070)
    value = year_fraction(
        ref_start,
        ref_end,
        DayCount.ACT_ACT_ICMA,
        ref_period_start=ref_start,
        ref_period_end=ref_end,
        frequency=frequency,
    )
    assert value == pytest.approx(1.0 / frequency, rel=1e-12)


@given(start=_DATES, end=_DATES)
def test_thirty_e_360_isda_tracks_plain_thirty_e_360_within_two_days(
    start: date, end: date
) -> None:
    """Each end can roll by at most one day under the ISDA month-end rule."""
    assume(start <= end)
    isda = year_fraction(start, end, DayCount.THIRTY_E_360_ISDA) * 360.0
    plain = year_fraction(start, end, DayCount.THIRTY_E_360) * 360.0
    assert abs(isda - plain) <= 2.0 + 1e-9
