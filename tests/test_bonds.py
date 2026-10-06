"""Tests for fixed-coupon bond cash flows and pricing."""

import pytest

from rates_analytics.bonds.fixed import bond_cash_flows, dirty_price
from rates_analytics.curves2.bootstrap import PiecewiseCurve


def test_bond_cash_flows_match_hand_schedule() -> None:
    """A 2-year 4% semiannual bond pays 2, 2, 2 and 102."""
    flows = bond_cash_flows(100, 0.04, 2, 4)
    assert [t for t, _ in flows] == pytest.approx([0.5, 1.0, 1.5, 2.0])
    assert [a for _, a in flows] == pytest.approx([2.0, 2.0, 2.0, 102.0])


def test_bond_single_period() -> None:
    """A single-period semiannual bond makes one payment of 102 at 0.5 years."""
    flows = bond_cash_flows(100, 0.04, 2, 1)
    assert [t for t, _ in flows] == pytest.approx([0.5])
    assert [a for _, a in flows] == pytest.approx([102.0])


def test_bond_invalid_face() -> None:
    """A bond with non-positive face value raises ValueError."""
    with pytest.raises(ValueError, match="Face value must be positive"):
        bond_cash_flows(0, 0.04, 2, 4)


def test_bond_invalid_coupon_rate() -> None:
    """A bond with negative coupon rate raises ValueError."""
    with pytest.raises(ValueError, match="Coupon rate cannot be negative"):
        bond_cash_flows(100, -0.04, 2, 4)


def test_bond_invalid_frequency() -> None:
    """A bond with non-positive frequency raises ValueError."""
    with pytest.raises(ValueError, match="Frequency must be positive"):
        bond_cash_flows(100, 0.04, 0, 4)


def test_bond_invalid_n_periods() -> None:
    """A bond with less than 1 period raises ValueError."""
    with pytest.raises(ValueError, match="Number of periods must be at least 1"):
        bond_cash_flows(100, 0.04, 2, 0)


def _curve() -> PiecewiseCurve:
    """Return the curve used by the pricing tests."""
    return PiecewiseCurve([0.5, 1.0, 1.5, 2.0], [0.98, 0.96, 0.94, 0.92])


def test_dirty_price_match_hand_value() -> None:
    """A 2-year 4% semiannual bond has a dirty price of 99.6."""
    curve = _curve()
    flows = bond_cash_flows(100, 0.04, 2, 4)
    price = dirty_price(curve, flows)
    assert price == pytest.approx(99.6)


def test_par_bond_price() -> None:
    """A par bond has a dirty price of 100."""
    curve = _curve()
    par_rate = (1 - 0.92) / 1.9
    flows = bond_cash_flows(100, par_rate, 2, 4)
    price = dirty_price(curve, flows)
    assert price == pytest.approx(100.0)


def test_empty_cash_flows() -> None:
    """Dirty price with empty cash flows raises ValueError."""
    curve = _curve()
    with pytest.raises(ValueError, match="Cash flows cannot be empty"):
        dirty_price(curve, [])


def test_bond_maturing_past_last_pillar() -> None:
    """A bond maturing after the last pillar raises ValueError."""
    curve = _curve()
    flows = bond_cash_flows(100, 0.04, 2, 10)
    with pytest.raises(ValueError, match="does not fall within any defined pillar interval"):
        dirty_price(curve, flows)
