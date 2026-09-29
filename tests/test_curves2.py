from datetime import date

import pytest

from rates_analytics.conventions import DayCount
from rates_analytics.curves2.bootstrap import (
    DepositQuote,
    PiecewiseCurve,
    SwapQuote,
    _accruals,
    _payment_schedule,
    _solve_swap_df,
    bootstrap_deposits,
    deposit_to_df,
)


def test_curve_returns_exact_df_at_pillar() -> None:
    """A curve constructed with valid pillars/DFs returns the exact DF at an exact pillar."""
    pillars = [1.0, 2.0, 5.0]
    discount_factors = [0.98, 0.95, 0.88]
    curve = PiecewiseCurve(pillars, discount_factors)
    for pillar, df in zip(pillars, discount_factors, strict=True):
        assert curve.discount(pillar) == pytest.approx(df)


def test_curve_interpolates_between_pillars() -> None:
    """Interpolation at a point between two pillars returns the value you'd expect."""
    pillars = [1.0, 2.0, 5.0]
    discount_factors = [0.98, 0.95, 0.88]
    curve = PiecewiseCurve(pillars, discount_factors)
    # Check interpolation at maturity 3.0
    expected_df = 0.95 + (0.88 - 0.95) * (3.0 - 2.0) / (5.0 - 2.0)
    assert curve.discount(3.0) == pytest.approx(expected_df)


def test_discount_raises_outside_pillar_range() -> None:
    """A maturity outside the pillar range raises ValueError."""
    curve = PiecewiseCurve([1.0, 2.0, 5.0], [0.98, 0.95, 0.88])
    with pytest.raises(ValueError):
        curve.discount(7.0)


def test_construction_with_mismatched_lengths_raises() -> None:
    """Mismatched-length lists should raise ValueError at construction."""
    with pytest.raises(ValueError):
        PiecewiseCurve([1.0, 2.0], [0.98])


def test_deposit_to_df() -> None:
    """Test the deposit_to_df function with a simple case."""
    start = date(2026, 3, 15)
    end = date(2026, 6, 15)
    rate = 0.0402
    day_count = DayCount.ACT_360
    df = deposit_to_df(start, end, rate, day_count)
    expected_t = (end - start).days / 360.0
    expected_df = 1 / (1 + rate * expected_t)

    assert df == pytest.approx(expected_df)


def test_deposit_to_df_higher_rate_gives_lower_df() -> None:
    """A higher deposit rate should yield a lower discount factor."""
    start = date(2026, 3, 15)
    end = date(2026, 6, 15)
    day_count = DayCount.ACT_360
    df_low_rate = deposit_to_df(start, end, 0.03, day_count)
    df_high_rate = deposit_to_df(start, end, 0.06, day_count)

    assert df_high_rate < df_low_rate


def test_bootstrap_deposits_reprices_each_instrument_exactly() -> None:
    """Every deposit used to buiild the curve should reprice exactly to its own maturity."""
    quotes = [
        DepositQuote(date(2026, 1, 1), date(2026, 4, 1), 0.045, DayCount.ACT_360),
        DepositQuote(date(2026, 1, 1), date(2026, 7, 1), 0.048, DayCount.ACT_360),
        DepositQuote(date(2026, 1, 1), date(2027, 1, 1), 0.050, DayCount.ACT_360),
    ]
    curve = bootstrap_deposits(quotes)
    for quote in quotes:
        maturity, expected_df = quote.bootstrap_deposit()
        assert curve.discount(maturity) == pytest.approx(expected_df)


def test_payment_schedule_generates_evenly_spaced_dates() -> None:
    """A 1-year quarterly schedule produces four evenly spaced payment dates."""
    assert _payment_schedule(1.0, 0.25) == [0.25, 0.5, 0.75, 1.0]


def test_payment_schedule_rejects_non_integer_multiple() -> None:
    """A step that doesn't evenly divide maturity should raise ValueError."""
    with pytest.raises(ValueError):
        _payment_schedule(2.0, 0.3)


def test_accruals_matches_gaps_between_payment_dates() -> None:
    """Accruals are the gap between each payment date and the previous one."""
    assert _accruals([0.25, 0.5, 0.75, 1.0]) == pytest.approx([0.25, 0.25, 0.25, 0.25])


def test_solve_swap_df_matches_hand_calculation() -> None:
    """Solved swap DF matches a hand-derived value on clean, exact pillars."""
    curve = PiecewiseCurve(
        pillars=[0.25, 0.5, 0.75, 1.0], discount_factors=[0.99, 0.98, 0.97, 0.96]
    )
    df = _solve_swap_df(curve, maturity=1.0, par_rate=0.045, fixed_leg_step=0.25)
    assert df == pytest.approx(0.956168108776267)


def test_swap_schedule_inputs_divides_evenly() -> None:
    """The swap_schedule_inputs method returns a step size that divides the maturity evenly."""
    for frequency in [1, 2, 4]:
        quote = SwapQuote(date(2026, 1, 1), date(2027, 1, 1), 0.05, DayCount.ACT_360, frequency)
        maturity, step = quote.swap_schedule_inputs()
        n_periods = round(maturity / step)
        assert n_periods * step == pytest.approx(maturity)


def test_swap_quote_rejects_end_before_start() -> None:
    """A SwapQuote with end date before start date should raise ValueError."""
    with pytest.raises(ValueError):
        SwapQuote(date(2026, 1, 1), date(2025, 1, 1), 0.05, DayCount.ACT_360, 4)


def test_swap_quote_rejects_negative_rate() -> None:
    """A SwapQuote with a negative rate should raise ValueError."""
    with pytest.raises(ValueError):
        SwapQuote(date(2026, 1, 1), date(2027, 1, 1), -0.01, DayCount.ACT_360, 4)


def test_swap_quote_rejects_non_positive_frequency() -> None:
    """A SwapQuote with a non-positive frequency should raise ValueError."""
    with pytest.raises(ValueError):
        SwapQuote(date(2026, 1, 1), date(2027, 1, 1), 0.05, DayCount.ACT_360, 0)
