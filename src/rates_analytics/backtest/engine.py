"""Vectorized backtesting.

Weights decided at the close of day ``t`` are applied to the return from
``t`` to ``t+1``. That one-line convention is where most backtests leak
information -- the tests pin it explicitly, including a perturbation test
that changes future prices and asserts past positions do not move.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from rates_analytics.metrics.perf import max_drawdown, sharpe_ratio

#: Periods per year for daily data, matching the 252-day convention used
#: throughout the metrics module.
PERIODS_PER_YEAR = 252


@dataclass
class BacktestResult:
    """Backtest outputs.

    Attributes
    ----------
    equity : pd.Series
        Portfolio value over time.
    returns : pd.Series
        Daily portfolio returns, net of costs.
    weights : pd.DataFrame
        Target weights as of each date.
    metadata : dict
        Provenance: config, git SHA, anything needed to reproduce the run.

    """

    equity: pd.Series
    returns: pd.Series
    weights: pd.DataFrame
    metadata: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        """Return headline metrics plus provenance metadata."""
        equity = self.equity
        total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0) if len(equity) > 1 else 0.0
        return {
            "total_return": round(total_return, 6),
            "sharpe": round(sharpe_ratio(self.returns), 4),
            "max_drawdown": round(max_drawdown(self.equity), 4),
            "n_days": len(equity),
            **self.metadata,
        }


def run_backtest(
    prices: pd.DataFrame,
    weights: pd.DataFrame,
    cost_bps: float = 5.0,
    initial_capital: float = 100_000.0,
    metadata: Mapping[str, Any] | None = None,
) -> BacktestResult:
    """Backtest daily-rebalanced weights against a price panel.

    Costs are charged on one-way turnover: a full position flip between
    consecutive days costs ``2 * cost_bps``. Day one applies the previous
    close's weight to nothing, so the first return is zero by construction.

    Parameters
    ----------
    prices : pd.DataFrame
        Close prices, dates by assets.
    weights : pd.DataFrame
        Target weights per date, same shape and index as ``prices``.
    cost_bps : float
        One-way transaction cost in basis points.
    initial_capital : float
        Starting portfolio value.
    metadata : Mapping[str, object] | None
        Provenance recorded in the result.

    Returns
    -------
    BacktestResult
        Equity curve, net returns, weights and metadata.

    Raises
    ------
    ValueError
        If weights and prices are not aligned.

    """
    if prices.shape != weights.shape or not prices.index.equals(weights.index):
        msg = "weights must align with prices (same index and columns)"
        raise ValueError(msg)

    rets = prices.pct_change().fillna(0.0)
    portfolio_ret = (weights.shift(1).fillna(0.0) * rets).sum(axis=1)

    if cost_bps > 0:
        turnover = weights.diff().abs().sum(axis=1).fillna(0.0)
        portfolio_ret = portfolio_ret - turnover * (cost_bps / 10_000.0)

    equity = initial_capital * (1.0 + portfolio_ret).cumprod()
    equity.iloc[0] = initial_capital
    return BacktestResult(
        equity=equity,
        returns=portfolio_ret,
        weights=weights,
        metadata=dict(metadata) if metadata else {},
    )
