# rates-analytics

[![ci](https://github.com/amritchachadi/ficc-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/amritchachadi/ficc-lab/actions/workflows/ci.yml)

Fixed-income analytics with explicit, tested convention handling: day counts and
schedule generation, a curve-construction layer (deposit and swap bootstrapping
with selectable interpolation, plus dual-curve swap pricing), and fixed-coupon
bond pricing cross-checked against QuantLib. Rate risk comes next.

The premise is that most fixed-income pricing errors are not model errors. They
are convention errors, and the same handful recur throughout the literature and
vendor documentation: the wrong day count on the floating leg of a fixed-to-float
bond, a month-end roll that drifts, a floating-rate note whose duration is
computed as though its coupon were fixed. This library treats those known
pitfalls as the primary subject rather than as edge cases bolted on after a happy
path works.

## Status

Early and actively developed. The conventions layer is implemented and tested.
A single-curve bootstrapper and dual-curve swap pricing (`curves2`) are
implemented with documented limits, as are fixed-coupon bullet bonds (`bonds`).
Dual-curve bootstrapping from market quotes, FRNs and callables, risk and
inflation are not written yet.
See [Limitations](#limitations) and [How this was built](#how-this-was-built).

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

## Curves

`rates_analytics.curves2` builds a discount curve from market quotes:

- **Deposits** convert directly to a discount factor, `DF = 1 / (1 + r·t)`, with
  `t` from the quote's day count.
- **Par swaps** are solved in closed form for the discount factor at the swap's
  maturity, given the discount factors already bootstrapped for earlier
  payment dates.
- **Bootstrapping** proceeds in maturity order, so every instrument reprices
  exactly at its own pillar. Two instruments producing the same maturity raise
  rather than silently overwriting each other.
- **Interpolation** is selectable per curve: linear on discount factors (the
  default), linear on zero rates, or log-linear on discount factors. They agree
  at the pillars and differ between them, which is what drives differences in
  implied forward rates (slope discontinuities at pillars are the usual "kink").
- **Dual-curve pricing** (`curves2.dual_curve`): forward rates are read from a
  projection curve and cash flows are discounted on a separate curve. Fixed and
  floating leg PVs, swap PV and the par swap rate are provided; single-curve
  pricing is the special case where both curves are the same.

```python
from datetime import date

from rates_analytics.conventions import DayCount
from rates_analytics.curves2.bootstrap import (
    DepositQuote,
    InterpolationMethod,
    PiecewiseCurve,
    bootstrap_deposits,
)

# Deposits only: every quote reprices exactly at its own maturity.
curve = bootstrap_deposits(
    [
        DepositQuote(date(2026, 1, 1), date(2026, 4, 1), 0.045, DayCount.ACT_360),
        DepositQuote(date(2026, 1, 1), date(2026, 7, 1), 0.048, DayCount.ACT_360),
        DepositQuote(date(2026, 1, 1), date(2027, 1, 1), 0.050, DayCount.ACT_360),
    ]
)

# The same pillars, interpolated three ways, give three different values
# between pillars and identical values at them.
pillars, dfs = [1.0, 2.0, 5.0], [0.95, 0.90, 0.75]
for method in InterpolationMethod:
    PiecewiseCurve(pillars, dfs, method).discount(3.0)
```

## Bonds

`rates_analytics.bonds` prices fixed-coupon bullet bonds two ways, off a curve
and off a single yield, and separates the price a buyer pays from the price
that is quoted:

- **Cash flows** are `(time, amount)` pairs: a coupon of
  `face · coupon / frequency` each period, with the face added to the last one.
- **Dirty price** discounts each cash flow on a curve, `Σ CF · DF(t)`. This is
  what changes hands at settlement.
- **Accrued interest** is `face · coupon · τ`, where `τ` is the year fraction
  from the last coupon to settlement in the bond's own day count (Act/Act ICMA
  by default, with the coupon period as its reference). **Clean price** is dirty
  minus accrued, which is why the quoted price does not jump on coupon dates.
- **Price from yield** discounts every cash flow at one rate, compounded at the
  coupon frequency: `Σ CF / (1 + y/f)^(f·t)`.
- **Yield to maturity** inverts that by bisection. Price is monotone in yield,
  so bisection is guaranteed to converge once the bracket contains the answer:
  the bracket is checked up front, and the loop stops on interval width rather
  than on a price residual. Newton is faster but can overshoot on long or
  deep-discount bonds; for a pricing library, a guaranteed answer was the
  better trade.

```python
from datetime import date

from rates_analytics.bonds.fixed import (
    accrued_interest,
    bond_cash_flows,
    dirty_price,
    price_from_yield,
    yield_to_maturity,
)
from rates_analytics.conventions import DayCount
from rates_analytics.curves2.bootstrap import PiecewiseCurve

# 2-year, 4% semiannual bond: [(0.5, 2), (1.0, 2), (1.5, 2), (2.0, 102)]
flows = bond_cash_flows(100, 0.04, 2, 4)

curve = PiecewiseCurve([0.5, 1.0, 1.5, 2.0], [0.98, 0.96, 0.94, 0.92])
dirty_price(curve, flows)  # 99.6

price_from_yield(flows, 0.05, 2)  # 98.119013
yield_to_maturity(flows, 99.6, 2)  # 0.0421064

# Settlement 59 days into a 181-day coupon period.
args = (100, 0.04, 2, date(2026, 1, 15), date(2026, 3, 15), date(2026, 7, 15))
accrued_interest(*args)  # 0.651934  (Act/Act ICMA: 2 * 59/181)
accrued_interest(*args, day_count=DayCount.THIRTY_360_US)  # 0.666667  (60/360)
```

## Validation

There is no authoritative free dataset of bond analytics to regress against, so
correctness here rests on three independent legs:

1. **Known values.** Worked examples from the ISDA 2006 Definitions and SIFMA,
   plus date pairs chosen specifically to separate conventions that agree on
   ordinary dates and diverge only at month ends. Curve code is checked against
   hand-derived discount factors.
2. **Properties.** Invariants asserted over generated dates with `hypothesis`:
   additivity across a split point for the conventions that are genuinely
   additive (and *not* for the 30/360 family, which is not), monotonicity in the
   end date, and the exact `1/frequency` identity for a full Act/Act ICMA period.
3. **An independent implementation.** The conventions layer is written from the
   published specifications and imports nothing. QuantLib is a separate
   implementation of the same specifications, and
   `tests/test_daycount_vs_quantlib.py` asserts the two agree over generated
   dates. Where they disagree for a documented reason, the reason is recorded in
   the test. `tests/test_bonds_vs_quantlib.py` does the same for bonds against a
   QuantLib `FixedRateBond`: accrued interest agrees to 1e-12, price from yield
   to 1e-10, and yield to maturity to 1e-8.

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

CI runs exactly that on 3.11 and 3.12. `main` is protected: changes land through
pull requests, and the `check` and `backtest` jobs must pass before merge.

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
  transaction costs. Its findings are advisory: each one is checked against the
  code before anything changes, and some are wrong.

The backtest stack behind those scripts lives in `src/rates_analytics/`
(`data`, `signals`, `backtest`, `metrics`): vectorized engine, dollar-neutral
cross-sectional momentum, Sharpe/drawdown/vol metrics, and a synthetic panel
generator that can embed real drift structure or produce pure noise — the
null case every signal should be measured against.

CI wires this into three workflows: `ci` (lint, types, tests), `backtest`
(a PR gate that runs the config and checks guard rails, uploading the report
as an artifact), and `llm-review` (the PR reviewer above, non-blocking). Set
`OPENROUTER_API_KEY` as a repository secret for the LLM workflows; the rest
never need a key. Keep real keys in `.env`, which is git-ignored.

## How this was built

This is a learning project, developed with AI assistance, and the repo says so
openly.

- The **conventions layer, schedules, and the research/backtest tooling** were
  scaffolded with AI assistance and then reviewed, tested and extended by hand.
- The **`curves2` package and its tests** were written by hand as a learning
  exercise: design, validation rules, and the interpolation schemes.
- The **`bonds` package and its tests**, including the QuantLib cross-check,
  were written by hand the same way.
- An earlier AI-generated curve bootstrapper is kept for reference under
  [`archive/`](archive/README.md). It is excluded from lint, type checks and CI,
  and nothing in `src/` imports it.

Commit history is left as it happened.

## Limitations

- **Scope.** Conventions, schedules, a single-curve deposit/swap bootstrapper,
  dual-curve swap pricing on given curves, and fixed-coupon bullet bonds. No
  dual-curve bootstrapping from market quotes, no FRNs or callables, no risk
  yet.
- **Bond cash flows** are on a regular year-fraction grid: no stub periods, no
  business-day adjustment and no ex-coupon period. Curve and yield pricing
  therefore assume valuation on a coupon date; accrued interest is computed
  separately from actual dates.
- **Yield to maturity** searches 0% to 100% by default. A negative yield needs
  an explicit lower bound.

- **Schedule alignment in `curves2`.** Each instrument's payment schedule is
  generated independently as float year fractions, so grids from different
  instruments do not coincide. A swap's earlier payment dates can fall outside
  the pillars bootstrapped so far, and the bootstrap then raises ("does not fall
  within any defined pillar intervals"). This is documented in code and pinned
  by a test. The fix is a shared, date-based schedule grid and is planned.
- **No extrapolation.** Querying a maturity outside the pillar range raises.
- **No negative rates.** Discount factors must lie in [0, 1].
- **Calendars** are weekend-plus-explicit-holidays. There are no built-in
  currency or exchange calendars; supply your own holiday set.
- **Stubs** are implicit in the generation direction. Explicit long stubs and
  user-specified first/last regular dates are not supported.
- **Act/Act ICMA** takes the reference period as an argument rather than
  deriving it from a schedule.
- Not performance-tuned, and not intended for production use.

## Roadmap

1. Curve construction — a shared date grid to remove the alignment limit, then
   dual-curve SOFR bootstrapping (OIS discounting plus projection), with a
   comparison of interpolation schemes and their effect on forward rates rather
   than just on zeros. Single-curve bootstrapping and the three interpolation
   schemes are done.
2. Rate risk (next) — duration and convexity, DV01, key-rate durations by
   helper perturbation, bucketed DV01, and curve-reshaping scenarios.
3. Bond analytics — FRN (discount margin, and duration measured to the next
   reset rather than to maturity), fixed-to-float with per-step conventions, and
   callable with OAS against a calibrated short-rate model. Fixed bullets are
   done.
4. Inflation — TIPS with correct Ref-CPI lag and intra-month interpolation, and a
   real curve bootstrapped from zero-coupon inflation swaps.

## License

MIT. See `LICENSE`.
