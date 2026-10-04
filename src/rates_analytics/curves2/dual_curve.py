"""Dual-curve helpers: forward rates and fixed/floating leg present values."""

from itertools import pairwise

from rates_analytics.curves2.bootstrap import PiecewiseCurve


def forward_rate(projection: PiecewiseCurve, t_start: float, t_end: float) -> float:
    """Return the forward rate between two times based on a projection curve.

    Parameters
    ----------
    projection
        The projection curve to use for the forward rate calculation.
    t_start, t_end
        The start and end times (in years) for the forward rate period.

    Returns
    -------
    float
        The forward rate between t_start and t_end.

    Raises
    ------
    ValueError
        If t_end is not strictly after t_start.
    """
    if t_end <= t_start:
        raise ValueError("t_end must be strictly after t_start.")

    df_start = projection.discount(t_start)
    df_end = projection.discount(t_end)

    return (df_start / df_end - 1) / (t_end - t_start)


def _validate_payment_times(payment_times: list[float]) -> None:
    """Raise ValueError unless payment times are non-empty, positive and strictly increasing."""
    if not payment_times:
        raise ValueError("Payment times list cannot be empty.")
    if payment_times[0] <= 0:
        raise ValueError("First payment time must be positive.")
    for t_start, t_end in pairwise(payment_times):
        if t_end <= t_start:
            raise ValueError("Payment times must be strictly increasing.")


def floating_leg_pv(
    discount: PiecewiseCurve, projection: PiecewiseCurve, payment_times: list[float]
) -> float:
    """Calculate the present value of a floating leg given discount and projection curves."""
    _validate_payment_times(payment_times)
    total = 0.0
    t_starts = [0.0, *payment_times[:-1]]
    for t_start, t_end in zip(t_starts, payment_times, strict=True):
        tau = t_end - t_start
        fwd_rate = forward_rate(projection, t_start, t_end)
        total += tau * fwd_rate * discount.discount(t_end)
    return total


def fixed_leg_pv(discount: PiecewiseCurve, payment_times: list[float], rate: float) -> float:
    """Calculate the present value of a fixed leg given a discount curve and fixed rate."""
    _validate_payment_times(payment_times)
    total = 0.0
    t_starts = [0.0, *payment_times[:-1]]
    for t_start, t_end in zip(t_starts, payment_times, strict=True):
        tau = t_end - t_start
        total += rate * tau * discount.discount(t_end)
    return total
