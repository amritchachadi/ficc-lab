"""Bond cash flows and pricing."""

from datetime import date

from rates_analytics.conventions import DayCount, year_fraction
from rates_analytics.curves2.bootstrap import PiecewiseCurve


def bond_cash_flows(
    face: float, coupon_rate: float, frequency: int, n_periods: int
) -> list[tuple[float, float]]:
    """Return the (time, amount) cash flows of a fixed-coupon bullet bond."""
    if face <= 0:
        raise ValueError("Face value must be positive.")
    if coupon_rate < 0:
        raise ValueError("Coupon rate cannot be negative.")
    if frequency <= 0:
        raise ValueError("Frequency must be positive.")
    if n_periods < 1:
        raise ValueError("Number of periods must be at least 1.")
    coupon_payment = face * coupon_rate / frequency
    cash_flows = []
    for period in range(1, n_periods + 1):
        amount = coupon_payment
        if period == n_periods:
            amount += face
        cash_flows.append((period / frequency, amount))
    return cash_flows


def dirty_price(curve: PiecewiseCurve, cash_flows: list[tuple[float, float]]) -> float:
    """Calculate the dirty price of a bond given a discount curve and cash flows."""
    if not cash_flows:
        raise ValueError("Cash flows cannot be empty.")
    return sum(amount * curve.discount(time) for time, amount in cash_flows)


def accrued_interest(
    face: float,
    coupon_rate: float,
    frequency: int,
    last_coupon: date,
    settlement: date,
    next_coupon: date,
    day_count: DayCount = DayCount.ACT_ACT_ICMA,
) -> float:
    """Calculate the accrued interest of a bond given last coupon and settlement dates."""
    if not last_coupon <= settlement < next_coupon:
        raise ValueError("Settlement must be on or after the last coupon and before the next.")
    tau = year_fraction(
        last_coupon,
        settlement,
        day_count,
        ref_period_start=last_coupon,
        ref_period_end=next_coupon,
        frequency=frequency,
    )
    return face * coupon_rate * tau


def clean_price(dirty: float, accrued: float) -> float:
    """Calculate the clean price of a bond given dirty price and accrued interest."""
    return dirty - accrued
