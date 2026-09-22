"""Performance and risk metrics.

Daily-data conventions throughout: 252 periods per year, sample standard
deviation (``ddof=1``). Degenerate inputs return 0.0 rather than ``nan``
because a metric that propagates ``nan`` through a report is worse than one
that quietly flags an empty sample with zero.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def sharpe_ratio(returns: pd.Series, periods_per_year: int = 252, rf: float = 0.0) -> float:
    """Return the annualized Sharpe ratio of a return series."""
    if len(returns) < 2:
        return 0.0
    std = returns.std(ddof=1)
    if std == 0 or math.isnan(std):
        return 0.0
    excess = returns - rf / periods_per_year
    return float(np.sqrt(periods_per_year) * excess.mean() / excess.std(ddof=1))


def max_drawdown(equity: pd.Series) -> float:
    """Return the worst peak-to-trough drawdown, as a negative fraction."""
    if len(equity) == 0:
        return 0.0
    running_max = equity.cummax()
    return float((equity / running_max - 1.0).min())


def annualized_volatility(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Return annualized return volatility."""
    if len(returns) < 2:
        return 0.0
    return float(returns.std(ddof=1) * np.sqrt(periods_per_year))


def hit_rate(returns: pd.Series) -> float:
    """Return the fraction of periods with a positive return."""
    if len(returns) == 0:
        return 0.0
    return float((returns > 0).mean())
