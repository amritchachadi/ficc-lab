"""Synthetic daily price panels and an optional real-data loader."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def synthetic_prices(
    n_assets: int = 3,
    n_days: int = 756,
    start: str = "2022-01-03",
    seed: int = 42,
    annual_drift: float = 0.05,
    annual_vol: float = 0.20,
    drift_spread: float = 0.0,
) -> pd.DataFrame:
    """Return a dates-by-assets DataFrame of synthetic close prices.

    Draws are geometric Brownian motion, deterministic given ``seed``. With
    ``drift_spread`` = 0 the panel is pure noise: no signal can have positive
    expected return against it, which makes it the null case for strategy
    testing. With ``drift_spread`` > 0, asset ``i`` receives an annual drift
    of ``annual_drift + spread * (2*i/(n-1) - 1)`` -- a persistent winner and
    loser ordering that cross-sectional signals can detect.

    Parameters
    ----------
    n_assets : int
        Number of columns in the panel.
    n_days : int
        Number of business days.
    start : str
        First calendar date of the index.
    seed : int
        Generator seed; identical seeds give identical panels.
    annual_drift : float
        Mean annual log-drift shared by all assets.
    annual_vol : float
        Annual return volatility, identical across assets.
    drift_spread : float
        Annual drift dispersion across assets; 0.0 for a noise panel.

    Returns
    -------
    pd.DataFrame
        Prices starting near 100, business-day index, ``ASSET{i}`` columns.

    Raises
    ------
    ValueError
        If dimensions are non-positive.

    """
    if n_assets < 1 or n_days < 1:
        msg = f"need n_assets >= 1 and n_days >= 1, got {n_assets}, {n_days}"
        raise ValueError(msg)

    rng = np.random.default_rng(seed)
    dt = 1.0 / 252.0
    dates = pd.bdate_range(start=start, periods=n_days)
    if drift_spread and n_assets > 1:
        drifts = annual_drift + drift_spread * np.linspace(-1.0, 1.0, n_assets)
    else:
        drifts = np.full(n_assets, annual_drift)
    rets = rng.normal(
        loc=np.asarray(drifts) * dt,
        scale=annual_vol * np.sqrt(dt),
        size=(n_days, n_assets),
    )
    prices = 100.0 * np.cumprod(1.0 + rets, axis=0)
    return pd.DataFrame(
        prices,
        index=dates,
        columns=[f"ASSET{i + 1}" for i in range(n_assets)],
    )


def load_yfinance(tickers: Sequence[str], start: str, end: str | None = None) -> pd.DataFrame:
    """Return adjusted closes from Yahoo Finance.

    An optional convenience, deliberately outside the tested core: real data
    arrives dirty, and the loaders for it belong with the caching layer once
    the conventions work is further along.

    Raises
    ------
    ImportError
        When the ``yfinance`` extra is not installed.
    ValueError
        When the request returns no data.

    """
    try:
        import yfinance as yf
    except ImportError as exc:
        msg = "yfinance is not installed; this loader is optional by design"
        raise ImportError(msg) from exc

    data = yf.download(list(tickers), start=start, end=end, auto_adjust=True, progress=False)
    if data.empty:
        msg = f"no data returned for {tickers}"
        raise ValueError(msg)
    close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]]
    return pd.DataFrame(close.dropna(how="all"))
