"""Tests for fixed-coupon bond cash flows and pricing."""

from datetime import date

import pytest

from rates_analytics.bonds.fixed import (
    accrued_interest,
    bond_cash_flows,
    clean_price,
    dirty_price,
    price_from_yield,
    yield_to_maturity,
)
from rates_analytics.conventions import DayCount
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


def test_bond_icma_accrued_interest_hand_calculation() -> None:
    """Act/Act ICMA accrued is 2 * 59/181 two months into the period."""
    accrued = accrued_interest(
        face=100,
        coupon_rate=0.04,
        frequency=2,
        last_coupon=date(2026, 1, 15),
        settlement=date(2026, 3, 15),
        next_coupon=date(2026, 7, 15),
        day_count=DayCount.ACT_ACT_ICMA,
    )
    assert accrued == pytest.approx(2 * 59 / 181)


def test_bond_30_360_accrued_interest_hand_calculation() -> None:
    """30/360 US accrued is 4 * 60/360 for the same dates."""
    accrued = accrued_interest(
        face=100,
        coupon_rate=0.04,
        frequency=2,
        last_coupon=date(2026, 1, 15),
        settlement=date(2026, 3, 15),
        next_coupon=date(2026, 7, 15),
        day_count=DayCount.THIRTY_360_US,
    )
    assert accrued == pytest.approx(100 * 0.04 * 60 / 360)


def test_bond_accrued_interest_settlement_on_last_coupon() -> None:
    """Accrued interest is zero if settlement is on the last coupon date."""
    accrued = accrued_interest(
        face=100,
        coupon_rate=0.04,
        frequency=2,
        last_coupon=date(2026, 1, 15),
        settlement=date(2026, 1, 15),
        next_coupon=date(2026, 7, 15),
        day_count=DayCount.ACT_ACT_ICMA,
    )
    assert accrued == pytest.approx(0.0)


def test_bond_accrued_interest_settlement_on_next_coupon() -> None:
    """Settlement on the next coupon date is rejected."""
    with pytest.raises(ValueError, match="before the next"):
        accrued_interest(
            face=100,
            coupon_rate=0.04,
            frequency=2,
            last_coupon=date(2026, 1, 15),
            settlement=date(2026, 7, 15),
            next_coupon=date(2026, 7, 15),
            day_count=DayCount.ACT_ACT_ICMA,
        )


def test_bond_accrued_interest_settlement_before_last_coupon() -> None:
    """Accrued interest raises ValueError if settlement is before the last coupon date."""
    with pytest.raises(ValueError, match="on or after the last coupon"):
        accrued_interest(
            face=100,
            coupon_rate=0.04,
            frequency=2,
            last_coupon=date(2026, 1, 15),
            settlement=date(2026, 1, 14),
            next_coupon=date(2026, 7, 15),
            day_count=DayCount.ACT_ACT_ICMA,
        )


def test_bond_clean_price_calculation() -> None:
    """Clean price is dirty price minus accrued interest."""
    clean = clean_price(dirty=100.25, accrued=0.65)
    assert clean == pytest.approx(99.60)


def test_bond_price_from_yield_par_bond() -> None:
    """A 4% bond priced at a 4% yield is worth par."""
    flows = bond_cash_flows(100, 0.04, 2, 4)
    price = price_from_yield(flows, yield_rate=0.04, frequency=2)
    assert price == pytest.approx(100.0)


def test_bond_price_from_yield_discounted_bond() -> None:
    """Price from yield matches discounted bond price."""
    flows = bond_cash_flows(100, 0.04, 2, 4)
    price = price_from_yield(flows, yield_rate=0.06, frequency=2)
    expected = 2 / 1.03 + 2 / 1.03**2 + 2 / 1.03**3 + 102 / 1.03**4
    assert price == pytest.approx(expected)


def test_compare_price_vs_bond_yield() -> None:
    """Price from 6 percent yield bond is lower than price of 5 percent yield bond."""
    flows = bond_cash_flows(100, 0.04, 2, 4)
    price_5 = price_from_yield(flows, yield_rate=0.05, frequency=2)
    price_6 = price_from_yield(flows, yield_rate=0.06, frequency=2)
    assert price_6 < price_5


def test_bond_empty_cash_flows_price_from_yield() -> None:
    """Price from yield with empty cash flows raises ValueError."""
    with pytest.raises(ValueError, match="Cash flows cannot be empty"):
        price_from_yield([], yield_rate=0.05, frequency=2)


def test_ytm_of_par_price_is_the_coupon_rate() -> None:
    """Yield to maturity of a par bond is the coupon rate."""
    flows = bond_cash_flows(100, 0.04, 2, 4)
    yield_rate = yield_to_maturity(flows, price=100, frequency=2)
    assert yield_rate == pytest.approx(0.04, abs=1e-8)


def test_ytm_recovers_the_yield_used_to_price() -> None:
    """Yield from price and price from yield are consistent."""
    flows = bond_cash_flows(100, 0.04, 2, 4)
    price = price_from_yield(flows, yield_rate=0.05, frequency=2)
    yield_rate = yield_to_maturity(flows, price=price, frequency=2)
    assert yield_rate == pytest.approx(0.05, abs=1e-8)


def test_bond_yields_round_trip() -> None:
    """Yield from price and price from yield are consistent."""
    flows = bond_cash_flows(100, 0.04, 2, 4)
    ytm = yield_to_maturity(flows, price=99.6, frequency=2)
    price = price_from_yield(flows, yield_rate=ytm, frequency=2)
    assert price == pytest.approx(99.6)


def test_bond_yield_out_of_bounds() -> None:
    """A price no yield between the bounds can produce is rejected."""
    flows = bond_cash_flows(100, 0.04, 2, 4)
    with pytest.raises(ValueError, match="Price is outside the range implied by the yield bounds"):
        yield_to_maturity(flows, price=200, frequency=2, lower=0.0, upper=0.1)


def test_bond_yield_price_0() -> None:
    """Yield from price raises ValueError if price is non-positive."""
    flows = bond_cash_flows(100, 0.04, 2, 4)
    with pytest.raises(ValueError, match="Price must be positive"):
        yield_to_maturity(flows, price=0, frequency=2)
