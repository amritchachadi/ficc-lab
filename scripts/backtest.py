"""Run a backtest from a YAML config and print a JSON summary.

Usage::

    uv run python scripts/backtest.py --config configs/momentum.yaml \
        [--out reports/backtest.json]

Runs identically locally and in CI: the default data source is the
deterministic synthetic panel, so no network or data subscription is
needed for a meaningful run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from rates_analytics.backtest.engine import run_backtest  # noqa: E402
from rates_analytics.data.loader import synthetic_prices  # noqa: E402
from rates_analytics.metrics.perf import annualized_volatility, hit_rate  # noqa: E402
from rates_analytics.signals.momentum import (  # noqa: E402
    ma_crossover_weights,
    momentum_weights,
)

SIGNALS = {
    "momentum": momentum_weights,
    "ma_crossover": ma_crossover_weights,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Run a ficc-lab backtest")
    parser.add_argument("--config", required=True, help="Path to strategy YAML")
    parser.add_argument("--out", default=None, help="Write JSON report to this path")
    return parser.parse_args(argv)


def load_prices(data_cfg: dict[str, Any]) -> pd.DataFrame:
    """Build the price panel described by the data config section."""
    return synthetic_prices(
        n_assets=int(data_cfg.get("n_assets", 3)),
        n_days=int(data_cfg.get("n_days", 756)),
        seed=int(data_cfg.get("seed", 42)),
        annual_drift=float(data_cfg.get("annual_drift", 0.05)),
        annual_vol=float(data_cfg.get("annual_vol", 0.20)),
        drift_spread=float(data_cfg.get("drift_spread", 0.0)),
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns a process exit code."""
    args = parse_args(argv)
    config: dict[str, Any] = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))

    signal_name = str(config["signal"]["name"])
    if signal_name not in SIGNALS:
        print(f"Unknown signal '{signal_name}'. Available: {sorted(SIGNALS)}", file=sys.stderr)
        return 2
    signal_params = {k: v for k, v in config["signal"].items() if k != "name"}

    prices = load_prices(config["data"])
    weights = SIGNALS[signal_name](prices, **signal_params)

    result = run_backtest(
        prices,
        weights,
        cost_bps=float(config.get("backtest", {}).get("cost_bps", 5.0)),
        metadata={
            "git_sha": os.environ.get("GITHUB_SHA", "local"),
            "signal": signal_name,
            "config": config,
        },
    )

    summary = result.summary()
    summary["annualized_vol"] = round(annualized_volatility(result.returns), 4)
    summary["hit_rate"] = round(hit_rate(result.returns), 4)

    print(json.dumps(summary, indent=2, default=str))
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"Report written to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
