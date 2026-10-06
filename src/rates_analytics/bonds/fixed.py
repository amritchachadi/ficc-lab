"""Bond cash flows and pricing."""


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
