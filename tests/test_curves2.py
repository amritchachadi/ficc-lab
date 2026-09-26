import pytest

from rates_analytics.curves2.bootstrap import PiecewiseCurve


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
