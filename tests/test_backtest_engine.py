"""Tests for the backtest engine: alignment, costs, and no look-ahead."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from rates_analytics.backtest.engine import run_backtest
from rates_analytics.data.loader import synthetic_prices
from rates_analytics.signals.momentum import momentum_weights


def _panel() -> pd.DataFrame:
    return synthetic_prices(n_assets=4, n_days=300, seed=7)


def _fixed_weights(prices: pd.DataFrame) -> pd.DataFrame:
    """Constant long-short weights, isolating the engine from signal logic."""
    n = prices.shape[1]
    half = n // 2
    row = np.array([1.0 / half] * half + [-1.0 / (n - half)] * (n - half))
    return pd.DataFrame(
        np.tile(row, (len(prices), 1)),
        index=prices.index,
        columns=prices.columns,
    )


def test_engine_rejects_misaligned_weights() -> None:
    prices = _panel()
    weights = _fixed_weights(prices).iloc[:-1]
    with pytest.raises(ValueError, match="align"):
        run_backtest(prices, weights)


def test_equity_starts_at_initial_capital_with_flat_first_day() -> None:
    prices = _panel()
    result = run_backtest(prices, _fixed_weights(prices), initial_capital=250_000.0)
    assert result.equity.iloc[0] == 250_000.0
    # Day-one return is zero by construction: yesterday's close has no
    # preceding weight, and the first weight applies from day 1 to day 2.
    assert result.returns.iloc[0] == 0.0
    assert len(result.equity) == len(prices)


def test_costs_reduce_returns() -> None:
    prices = _panel()
    weights = momentum_weights(prices, lookback=60)  # time-varying: nonzero turnover
    free = run_backtest(prices, weights, cost_bps=0.0).returns
    costly = run_backtest(prices, weights, cost_bps=100.0).returns
    assert (costly <= free + 1e-12).all()
    assert (costly < free).any()


def test_no_lookahead_in_engine() -> None:
    """Perturbing future prices must not change returns before the cut."""
    prices = _panel()
    cut = len(prices) // 2
    perturbed = prices.copy()
    perturbed.iloc[cut:] *= 2.0
    weights = _fixed_weights(prices)
    r1 = run_backtest(prices, weights).returns
    r2 = run_backtest(perturbed, weights).returns
    pd.testing.assert_series_equal(r1.iloc[:cut], r2.iloc[:cut])
    assert not r1.equals(r2)  # the future genuinely changed


def test_summary_contains_metrics_and_metadata() -> None:
    prices = _panel()
    result = run_backtest(prices, _fixed_weights(prices), metadata={"signal": "fixed"})
    summary = result.summary()
    assert summary["signal"] == "fixed"
    assert summary["n_days"] == len(prices)
    assert -1.0 <= float(summary["max_drawdown"]) <= 0.0
