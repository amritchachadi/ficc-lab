"""Tests for dual-curve helpers."""

import pytest

from rates_analytics.curves2.bootstrap import PiecewiseCurve
from rates_analytics.curves2.dual_curve import forward_rate


def test_forward_rate_matches_hand_calculation() -> None:
    """Forward rate over [0.5, 1.0] matches a hand-derived value."""
    proj = PiecewiseCurve([0.0, 0.5, 1.0], [1.0, 0.98, 0.96])
    assert forward_rate(proj, 0.5, 1.0) == pytest.approx(0.0416666666)


def test_forward_rate_raises_for_bad_ordering() -> None:
    """Forward rate raises ValueError if t_end = t_start."""
    proj = PiecewiseCurve([0.0, 0.5, 1.0], [1.0, 0.98, 0.96])
    with pytest.raises(ValueError, match="strictly after"):
        forward_rate(proj, 1.0, 1.0)


def test_forward_rate_raises_for_zero_or_negative_interval() -> None:
    """Forward rate raises ValueError for 0 or negative intervals."""
    proj = PiecewiseCurve([0.0, 0.5, 1.0], [1.0, 0.98, 0.96])
    with pytest.raises(ValueError, match="strictly after"):
        forward_rate(proj, 1.0, 0.5)


def test_forward_rate_first_period_starts_from_unit_discount_factor() -> None:
    """Forward rate over [0.0, 0.5] matches a hand-derived value."""
    proj = PiecewiseCurve([0.0, 0.5, 1.0], [1.0, 0.98, 0.96])
    assert forward_rate(proj, 0.0, 0.5) == pytest.approx((1.0 / 0.98 - 1) / 0.5)


def test_floating_leg_telescopes_when_curves_match() -> None:
    """With identical curves, sum(tau * F * DF) equals 1 - DF(T)."""
    curve = PiecewiseCurve([0.0, 0.5, 1.0], [1.0, 0.98, 0.96])
    periods = [(0.0, 0.5), (0.5, 1.0)]
    total = 0.0
    for t_start, t_end in periods:
        tau = t_end - t_start
        total += tau * forward_rate(curve, t_start, t_end) * curve.discount(t_end)
    assert total == pytest.approx(1 - curve.discount(1.0))
