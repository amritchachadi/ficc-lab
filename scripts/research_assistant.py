"""LLM research assistant: strategy brief to draft strategy note.

Takes a one-line idea, routes it through the research model for a
structured note (hypothesis, data requirements, risks, backtest plan),
and optionally has the code model sketch an implementation scaffold
shaped like this repo. Research output is a starting point for human
work, not a substitute for it.

Usage::

    export OPENROUTER_API_KEY=...  # or keep it in .env
    uv run python scripts/research_assistant.py \
        --idea "momentum in G10 FX with vol targeting" \
        --with-code --out docs/strategy_notes/fx_momentum.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from rates_analytics.config import Settings  # noqa: E402
from rates_analytics.llm.router import OpenRouterClient  # noqa: E402

SYSTEM_RESEARCH = (
    "You are a senior quantitative researcher at a systematic FICC desk. "
    "Given a strategy idea, produce a rigorous but concise strategy note with "
    "sections: Hypothesis (economic rationale), Data Requirements, Feature "
    "Ideas, Risks and Failure Modes, Backtest Plan (naming pitfalls: look-ahead "
    "bias, survivorship, convention errors), and Evaluation Metrics. Be "
    "specific and skeptical."
)

SYSTEM_CODE = (
    "You are a quantitative developer. Given a strategy note, sketch a "
    "Python implementation scaffold (signal function signature, config "
    "schema, test cases) consistent with the ficc-lab repo layout "
    "(src/rates_analytics/signals, src/rates_analytics/backtest, tests/). "
    "Return one python code block only."
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="LLM research assistant")
    parser.add_argument("--idea", required=True, help="One-line strategy idea")
    parser.add_argument("--out", default=None, help="Write markdown note to this path")
    parser.add_argument("--with-code", action="store_true", help="Also sketch a code scaffold")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns a process exit code."""
    args = parse_args(argv)
    client = OpenRouterClient(Settings.from_env())

    note = f"# Strategy Note: {args.idea}\n\n## Research Synthesis\n\n"
    note += client.chat(
        [
            {"role": "system", "content": SYSTEM_RESEARCH},
            {"role": "user", "content": f"Strategy idea: {args.idea}"},
        ],
        task="research",
    ).content

    if args.with_code:
        note += "\n\n## Code Scaffold (draft)\n\n"
        note += client.chat(
            [
                {"role": "system", "content": SYSTEM_CODE},
                {"role": "user", "content": note},
            ],
            task="code",
        ).content

    print(note)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(note, encoding="utf-8")
        print(f"\nSaved to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
