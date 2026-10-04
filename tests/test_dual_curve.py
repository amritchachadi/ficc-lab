"""Tests for dual-curve helpers."""

import pytest

from rates_analytics.curves2.bootstrap import PiecewiseCurve
from rates_analytics.curves2.dual_curve import fixed_leg_pv, floating_leg_pv, forward_rate


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


def _curves() -> tuple[PiecewiseCurve, PiecewiseCurve]:
    """Return (discount, projection) curves used by the leg tests."""
    discount = PiecewiseCurve([0.0, 0.5, 1.0], [1.0, 0.99, 0.975])
    projection = PiecewiseCurve([0.0, 0.5, 1.0], [1.0, 0.98, 0.96])
    return discount, projection


def test_floating_leg_pv_matches_hand_calculation() -> None:
    """Floating leg PV matches the hand value 0.0405165816."""
    discount, projection = _curves()
    assert floating_leg_pv(discount, projection, [0.5, 1.0]) == pytest.approx(0.0405165816)


def test_fixed_leg_pv_matches_hand_calculation() -> None:
    """Fixed leg PV matches the hand value 0.0393."""
    discount, _ = _curves()
    assert fixed_leg_pv(discount, [0.5, 1.0], rate=0.04) == pytest.approx(0.0393)


def test_fixed_leg_pv_rejects_empty_payment_times() -> None:
    """Fixed leg PV raises ValueError for empty payment times."""
    discount, _ = _curves()
    with pytest.raises(ValueError, match="cannot be empty"):
        fixed_leg_pv(discount, [], rate=0.04)


def test_first_payment_time_must_be_positive() -> None:
    """Fixed leg PV raises ValueError if the first payment time is not positive."""
    discount, _ = _curves()
    with pytest.raises(ValueError, match="must be positive"):
        fixed_leg_pv(discount, [0.0, 0.5], rate=0.04)


def test_payment_times_must_be_strictly_increasing() -> None:
    """A descending schedule is rejected."""
    discount, _ = _curves()
    with pytest.raises(ValueError, match="strictly increasing"):
        fixed_leg_pv(discount, [1.0, 0.5], rate=0.04)


def test_payment_times_must_be_increasing_throughout() -> None:
    """A schedule that rises then falls is rejected, not just first-vs-last."""
    discount, _ = _curves()
    with pytest.raises(ValueError, match="strictly increasing"):
        fixed_leg_pv(discount, [0.5, 2.0, 1.0], rate=0.04)


def test_floating_leg_pv_rejects_empty_payment_times() -> None:
    """Floating leg PV raises ValueError for empty payment times."""
    discount, projection = _curves()
    with pytest.raises(ValueError, match="cannot be empty"):
        floating_leg_pv(discount, projection, [])


def test_fixed_leg_pv_accepts_single_payment() -> None:
    """A one-period leg is valid: PV is rate * tau * DF with tau = 1.0."""
    discount, _ = _curves()
    assert fixed_leg_pv(discount, [1.0], rate=0.04) == pytest.approx(0.04 * 1.0 * 0.975)
