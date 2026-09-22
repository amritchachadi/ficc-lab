"""Tests for performance metrics, including degenerate inputs."""

from __future__ import annotations

import pandas as pd

from rates_analytics.metrics.perf import (
    annualized_volatility,
    hit_rate,
    max_drawdown,
    sharpe_ratio,
)


def _series(*values: float) -> pd.Series:
    return pd.Series(values, dtype=float)


def test_sharpe_zero_volatility_returns_zero() -> None:
    assert sharpe_ratio(_series(0.0, 0.0, 0.0)) == 0.0
    assert sharpe_ratio(_series(0.01)) == 0.0  # single observation
    assert sharpe_ratio(pd.Series(dtype=float)) == 0.0


def test_sharpe_positive_for_consistent_gains() -> None:
    rets = _series(0.01, -0.002, 0.012, 0.004, 0.008)
    assert sharpe_ratio(rets) > 0


def test_sharpe_skips_nan_like_pandas_stats_do() -> None:
    rets = _series(float("nan"), 0.01, 0.02)
    assert sharpe_ratio(rets) == sharpe_ratio(rets.dropna())


def test_max_drawdown_known_value() -> None:
    assert max_drawdown(_series(100.0, 120.0, 90.0, 95.0)) == -0.25


def test_max_drawdown_monotonic_equity_is_zero() -> None:
    assert max_drawdown(_series(100.0, 101.0, 102.0)) == 0.0
    assert max_drawdown(pd.Series(dtype=float)) == 0.0


def test_annualized_volatility_sane_range() -> None:
    rets = pd.Series(__import__("numpy").random.default_rng(0).normal(0.001, 0.01, 500))
    vol = annualized_volatility(rets)
    assert 0.05 < vol < 0.5
    assert annualized_volatility(_series(0.01)) == 0.0


def test_hit_rate_fraction_positive() -> None:
    assert hit_rate(_series(0.01, -0.01, 0.02)) == 2 / 3
    assert hit_rate(pd.Series(dtype=float)) == 0.0
