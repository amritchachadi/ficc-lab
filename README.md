# rates-analytics

[![ci](https://github.com/amritchachadi/ficc-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/amritchachadi/ficc-lab/actions/workflows/ci.yml)

Fixed-income analytics with explicit, tested convention handling: day counts and
schedule generation today, curve construction and bond pricing next.

The premise is that most fixed-income pricing errors are not model errors. They
are convention errors, and the same handful recur throughout the literature and
vendor documentation: the wrong day count on the floating leg of a fixed-to-float
bond, a month-end roll that drifts, a floating-rate note whose duration is
computed as though its coupon were fixed. This library treats those known
pitfalls as the primary subject rather than as edge cases bolted on after a happy
path works.

## Status

Early. The conventions layer is implemented and tested; everything below it in
the roadmap is not written yet. See [Limitations](#limitations).

## What is implemented

**Day counts** — `30/360 US` (SIFMA), `30E/360`, `30E/360 ISDA`, `Act/360`,
`Act/365F`, `Act/Act ISDA`, `Act/Act ICMA`.

Conventions that are commonly conflated are kept genuinely distinct, and the
distinctions are pinned by tests:

- `30E/360` truncates only the 31st; `30E/360 ISDA` rolls *any* month end to the
  30th, so a 29 February boundary differs between them by a day.
- The `30/360 US` February rules are gated on an explicit `eom` flag, because
  whether a security follows the end-of-month rule is instrument static data and
  is not inferable from a date pair.
- `Act/Act ICMA` requires its enclosing reference period. It will raise rather
  than silently fall back to the accrual period as a denominator.

**Schedules** — business day conventions (following, modified following,
preceding, modified preceding), weekend-plus-holiday calendars, the end-of-month
rule, and backward or forward period generation with a stub at the
corresponding end.

Dates are rolled *from the anchor* (`anchor + k months`) rather than by stepping
a cursor forward repeatedly, so a February or month-end clamp early in a
schedule cannot drift every date after it.

## Validation

There is no authoritative free dataset of bond analytics to regress against, so
correctness here rests on three independent legs:

1. **Known values.** Worked examples from the ISDA 2006 Definitions and SIFMA,
   plus date pairs chosen specifically to separate conventions that agree on
   ordinary dates and diverge only at month ends.
2. **Properties.** Invariants asserted over generated dates with `hypothesis`:
   additivity across a split point for the conventions that are genuinely
   additive (and *not* for the 30/360 family, which is not), monotonicity in the
   end date, and the exact `1/frequency` identity for a full Act/Act ICMA period.
3. **An independent implementation.** The conventions layer is written from the
   published specifications and imports nothing. QuantLib is a separate
   implementation of the same specifications, and
   `tests/test_daycount_vs_quantlib.py` asserts the two agree over generated
   dates. Where they disagree for a documented reason, the reason is recorded in
   the test.

Tests are offline and deterministic. No test reaches the network.

## Usage

```python
from datetime import date

from rates_analytics.conventions import (
    BusinessDayConvention,
    Calendar,
    DayCount,
    Frequency,
    generate_schedule,
    year_fraction,
)

# A 29 February boundary: 30E/360 and 30E/360 ISDA differ by one day.
year_fraction(date(2007, 8, 31), date(2008, 2, 29), DayCount.THIRTY_E_360)  # 179/360
year_fraction(date(2007, 8, 31), date(2008, 2, 29), DayCount.THIRTY_E_360_ISDA)  # 180/360

# A semiannual schedule with a short front stub, adjusted for weekends.
generate_schedule(
    date(2020, 1, 20),
    date(2023, 3, 15),
    Frequency.SEMIANNUAL,
    calendar_=Calendar(holidays=[date(2021, 7, 5)]),
    convention=BusinessDayConvention.MODIFIED_FOLLOWING,
)
```

## Development

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras --dev
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

CI runs exactly that on 3.11 and 3.12.

## Research tooling (OpenRouter)

The repo carries a thin LLM layer routed through
[OpenRouter](https://openrouter.ai): one API key, three model slots
(`research`, `code`, `fast`) assigned via environment variables, so models
can be swapped without touching call sites. The slots back three tools:

- **`scripts/research_assistant.py`** — turns a one-line strategy idea into a
  structured strategy note (hypothesis, data needs, risks, backtest plan,
  metrics) and optionally sketches a code scaffold shaped like this repo:

  ```bash
  cp .env.example .env  # add your key from https://openrouter.ai/keys
  uv run python scripts/research_assistant.py \
      --idea "momentum in G10 FX with vol targeting" \
      --with-code --out docs/strategy_notes/fx_momentum.md
  ```

- **`scripts/backtest.py`** — runs a YAML-configured backtest
  (`configs/momentum.yaml`) against the deterministic synthetic panel, so
  CI can gate strategies with no network or data subscription:

  ```bash
  uv run python scripts/backtest.py --config configs/momentum.yaml \
      --out reports/backtest.json
  ```

- **`scripts/llm_pr_review.py`** — the code model reviews every PR diff and
  posts its findings as a PR comment. The prompt encodes this repo's own
  failure modes: convention errors, look-ahead bias in backtests, ignored
  transaction costs.

The backtest stack behind those scripts lives in `src/rates_analytics/`
(`data`, `signals`, `backtest`, `metrics`): vectorized engine, dollar-neutral
cross-sectional momentum, Sharpe/drawdown/vol metrics, and a synthetic panel
generator that can embed real drift structure or produce pure noise — the
null case every signal should be measured against.

CI wires this into three workflows: `ci` (lint, types, tests), `backtest`
(a PR gate that runs the config and checks guard rails, uploading the report
as an artifact), and `llm-review` (the PR reviewer above). Set
`OPENROUTER_API_KEY` as a repository secret for the LLM workflows; the rest
never need a key.

## Limitations

- **Scope.** Conventions only so far. No curves, no pricing, no risk yet.
- **Calendars** are weekend-plus-explicit-holidays. There are no built-in
  currency or exchange calendars; supply your own holiday set.
- **Stubs** are implicit in the generation direction. Explicit long stubs and
  user-specified first/last regular dates are not supported.
- **Act/Act ICMA** takes the reference period as an argument rather than
  deriving it from a schedule.
- Not performance-tuned, and not intended for production use.

## Roadmap

1. Curve construction — dual-curve SOFR bootstrapping (OIS discounting plus
   projection), with a comparison of interpolation schemes and their effect on
   forward rates rather than just on zeros.
2. Bond analytics — fixed bullet, FRN (discount margin, and duration measured to
   the next reset rather than to maturity), fixed-to-float with per-step
   conventions, and callable with OAS against a calibrated short-rate model.
3. Rate risk — key-rate durations by helper perturbation, bucketed DV01, and
   curve-reshaping scenarios.
4. Inflation — TIPS with correct Ref-CPI lag and intra-month interpolation, and a
   real curve bootstrapped from zero-coupon inflation swaps.

## License

MIT. See `LICENSE`.
