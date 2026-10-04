"""Dual-curve helpers: forward rates read from a projection curve."""

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
