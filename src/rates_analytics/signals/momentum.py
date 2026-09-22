"""Signal generation: price panels to target portfolio weights."""

from __future__ import annotations

import numpy as np
import pandas as pd


def momentum_weights(prices: pd.DataFrame, lookback: int = 126) -> pd.DataFrame:
    """Return dollar-neutral cross-sectional momentum weights.

    On each date, assets are ranked by trailing ``lookback``-day return:
    the top half goes long, the bottom half short, equal-sized positions,
    gross exposure 1.0. Weights at date ``t`` use information through ``t``
    only; the backtest engine is responsible for applying them to the
    ``t`` to ``t+1`` return.

    Parameters
    ----------
    prices : pd.DataFrame
        Close prices, dates by assets.
    lookback : int
        Trailing window in business days.

    Returns
    -------
    pd.DataFrame
        Weights aligned to ``prices``.

    Raises
    ------
    ValueError
        If ``lookback`` is not positive or the panel is too short.

    """
    if lookback <= 0:
        msg = f"lookback must be positive, got {lookback}"
        raise ValueError(msg)
    if len(prices) <= lookback:
        msg = f"need more than {lookback} rows, got {len(prices)}"
        raise ValueError(msg)

    trailing_ret = prices.pct_change(periods=lookback)
    weights = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

    for date, row in trailing_ret.dropna().iterrows():
        med = row.median()
        above = row[row > med].index
        below = row[row < med].index
        if len(above):
            weights.loc[date, above] = 1.0 / len(above)
        if len(below):
            weights.loc[date, below] = -1.0 / len(below)
    return weights


def ma_crossover_weights(prices: pd.DataFrame, fast: int = 50, slow: int = 200) -> pd.DataFrame:
    """Return long/flat moving-average crossover weights.

    An asset is held (equal-weight across held assets) while its ``fast``
    -day moving average is above its ``slow``-day average, else it goes to
    cash. A long-biased counterpart to the dollar-neutral momentum signal,
    useful for sanity-checking the engine on both position conventions.

    Raises
    ------
    ValueError
        If ``fast`` is not shorter than ``slow``.

    """
    if fast >= slow:
        msg = f"fast window must be shorter than slow, got {fast} >= {slow}"
        raise ValueError(msg)
    ma_fast = prices.rolling(fast).mean()
    ma_slow = prices.rolling(slow).mean()
    signal = (ma_fast > ma_slow).astype(float)
    held = signal.sum(axis=1)
    held = held.replace(0, np.nan)
    return signal.div(held, axis=0).fillna(0.0)
