"""Tests for momentum signals and the synthetic data generator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from rates_analytics.data.loader import synthetic_prices
from rates_analytics.signals.momentum import ma_crossover_weights, momentum_weights


def test_synthetic_panel_is_deterministic() -> None:
    pd.testing.assert_frame_equal(
        synthetic_prices(seed=123, n_assets=3, n_days=100),
        synthetic_prices(seed=123, n_assets=3, n_days=100),
    )


def test_synthetic_panel_shape_and_positivity() -> None:
    panel = synthetic_prices(n_assets=5, n_days=252, seed=1)
    assert panel.shape == (252, 5)
    assert (panel > 0).all().all()
    with pytest.raises(ValueError):
        synthetic_prices(n_assets=0)


def test_drift_spread_orders_realized_returns() -> None:
    """With dispersion, the top-drift asset should outperform the bottom one."""
    panel = synthetic_prices(n_assets=4, n_days=5000, seed=9, drift_spread=0.50)
    growth = panel.iloc[-1] / panel.iloc[0]
    assert growth.iloc[-1] > growth.iloc[0]


def test_momentum_weights_shape_and_neutrality() -> None:
    prices = synthetic_prices(n_assets=4, n_days=300, seed=7)
    weights = momentum_weights(prices, lookback=60)
    assert weights.shape == prices.shape
    assert weights.index.equals(prices.index)
    active = weights[weights.abs().sum(axis=1) > 0]
    assert np.allclose(active.sum(axis=1), 0.0, atol=1e-9)


def test_momentum_no_lookahead() -> None:
    """Changing future prices must not move earlier weights."""
    base = synthetic_prices(n_assets=4, n_days=300, seed=7)
    perturbed = base.copy()
    perturbed.iloc[-10:] *= 2.0
    w1 = momentum_weights(base, lookback=60)
    w2 = momentum_weights(perturbed, lookback=60)
    pd.testing.assert_frame_equal(w1.iloc[:-10], w2.iloc[:-10])


def test_momentum_requires_enough_history() -> None:
    prices = synthetic_prices(n_assets=2, n_days=50, seed=1)
    with pytest.raises(ValueError, match="need more than"):
        momentum_weights(prices, lookback=100)
    with pytest.raises(ValueError, match="positive"):
        momentum_weights(prices, lookback=0)


def test_ma_crossover_bounds_and_validation() -> None:
    prices = synthetic_prices(n_assets=3, n_days=300, seed=5)
    weights = ma_crossover_weights(prices, fast=10, slow=30)
    assert weights.shape == prices.shape
    assert (weights >= 0).all().all()
    assert (weights.sum(axis=1) <= 1.0 + 1e-9).all()
    with pytest.raises(ValueError, match="shorter"):
        ma_crossover_weights(prices, fast=30, slow=10)
