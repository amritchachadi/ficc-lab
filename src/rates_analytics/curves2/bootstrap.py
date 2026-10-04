"""A piecewise-constant discount curve, defined by pillar maturities and discount factors."""

import math
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from rates_analytics.conventions import DayCount, year_fraction


class InterpolationMethod(StrEnum):
    """Interpolation scheme used between curve pillars."""

    LINEAR_DISCOUNT = "linear_discount"
    LINEAR_ZERO = "linear_zero"
    LOG_DISCOUNT = "log_discount"


class PiecewiseCurve:
    """A piecewise-constant discount curve, defined by pillar maturities and discount factors.

    Discount factors are currently required to lie in [0, 1], which means
    this curve does not yet support the negative-rate regime (observed
    historically in EUR and JPY markets). Revisiting this is a known,
    deliberate scope limit, not an oversight.
    """

    pillars: list[float]
    discount_factors: list[float]

    def __init__(
        self,
        pillars: list[float],
        discount_factors: list[float],
        interpolation: InterpolationMethod = InterpolationMethod.LINEAR_DISCOUNT,
    ) -> None:
        """Initialize the piecewise curve with pillars and discount factors."""
        self.pillars = pillars
        self.discount_factors = discount_factors
        self.interpolation = interpolation
        if len(self.pillars) != len(self.discount_factors):
            raise ValueError("Pillars and discount factors must have the same length.")
        if not self.pillars:
            raise ValueError("Pillars cannot be empty.")
        if not self.discount_factors:
            raise ValueError("Discount factors cannot be empty.")
        if sorted(self.pillars) != self.pillars:
            raise ValueError("Pillars must be sorted in ascending order.")
        if not all(0 <= df <= 1 for df in self.discount_factors):
            raise ValueError("Discount factors must be in the range [0, 1].")
        if self.interpolation == InterpolationMethod.LINEAR_ZERO and self.pillars[0] <= 0:
            raise ValueError(
                "LINEAR_ZERO interpolation is undefined when the first pillar is at t=0."
            )

    def discount(self, maturity: float) -> float:
        """Return the discount factor for a given maturity."""
        if maturity in self.pillars:
            index = self.pillars.index(maturity)
            return self.discount_factors[index]
        else:
            for i in range(len(self.pillars) - 1):
                if self.pillars[i] <= maturity <= self.pillars[i + 1]:
                    t0, t1 = self.pillars[i], self.pillars[i + 1]
                    df0, df1 = self.discount_factors[i], self.discount_factors[i + 1]
                    w = (maturity - t0) / (t1 - t0)
                    if self.interpolation == InterpolationMethod.LINEAR_DISCOUNT:
                        return df0 + w * (df1 - df0)
                    elif self.interpolation == InterpolationMethod.LINEAR_ZERO:
                        z1 = -math.log(df1) / t1
                        z0 = -math.log(df0) / t0
                        z = z0 + w * (z1 - z0)
                        return math.exp(-z * maturity)
                    else:  # LOG_DISCOUNT
                        return math.exp(math.log(df0) + w * (math.log(df1) - math.log(df0)))
            raise ValueError("Maturity does not fall within any defined pillar intervals.")


def deposit_to_df(start: date, end: date, rate: float, day_count: DayCount) -> float:
    """Convert a deposit rate to a discount factor."""
    t = year_fraction(start, end, day_count)
    return 1 / (1 + rate * t)


@dataclass
class DepositQuote:
    """A deposit quote with start and end dates, rate, and day count convention."""

    start: date
    end: date
    rate: float
    day_count: DayCount

    def to_discount_factor(self) -> float:
        """Convert the deposit quote to a discount factor."""
        return deposit_to_df(self.start, self.end, self.rate, self.day_count)

    def bootstrap_deposit(self) -> tuple[float, float]:
        """Return the maturity and discount factor for bootstrapping."""
        maturity = year_fraction(self.start, self.end, self.day_count)
        df = self.to_discount_factor()
        return maturity, df

    def __post_init__(self) -> None:
        """Validate the deposit quote after initialization."""
        if self.end <= self.start:
            raise ValueError("End date must be strictly after start date.")
        if self.rate < 0:
            raise ValueError(
                "Negative rates are not yet supported: PiecewiseCurve currently "
                "requires discount factors in [0, 1], which excludes the "
                "negative-rate regime (e.g. EUR/JPY historically)."
            )


@dataclass
class SwapQuote:
    """A swap quote with start/end dates, par rate, day count , and fixed leg payment step."""

    start: date
    end: date
    rate: float
    day_count: DayCount
    frequency: int

    def __post_init__(self) -> None:
        """Validate the swap quote after initialization."""
        if self.end <= self.start:
            raise ValueError("End date must be strictly after start date.")
        if self.rate < 0:
            raise ValueError(
                "Negative rates are not yet supported: PiecewiseCurve currently "
                "requires discount factors in [0, 1], which excludes the "
                "negative-rate regime (e.g. EUR/JPY historically)."
            )
        if self.frequency <= 0:
            raise ValueError("Frequency must be positive.")

    def swap_schedule_inputs(self) -> tuple[float, float]:
        """Return the maturity and step size for the swap's fixed leg payment schedule."""
        maturity = year_fraction(self.start, self.end, self.day_count)
        n_periods = round(maturity * self.frequency)
        step = maturity / n_periods
        return maturity, step


def bootstrap_deposits(quotes: list[DepositQuote]) -> PiecewiseCurve:
    """Bootstrap a piecewise curve from a list of deposit quotes."""
    pairs = [quote.bootstrap_deposit() for quote in quotes]
    sorted_pairs = sorted(pairs, key=lambda pair: pair[0])
    pillars = [pair[0] for pair in sorted_pairs]
    discount_factors = [pair[1] for pair in sorted_pairs]
    return PiecewiseCurve(pillars, discount_factors)


def _payment_schedule(maturity: float, step: float) -> list[float]:
    """Generate a payment schedule for a given maturity and step size."""
    n_steps = round(maturity / step)
    if abs(n_steps * step - maturity) > 1e-9:
        raise ValueError("Maturity must be an integer multiple of step.")
    else:
        schedule = []
        current_time = 0.0
        while current_time < maturity:
            current_time += step
            schedule.append(current_time)
        return schedule


def _accruals(payment_dates: list[float]) -> list[float]:
    """Generate accrual periods from a list of payment dates."""
    accruals = []
    previous_date = 0.0
    for payment_date in payment_dates:
        accruals.append(payment_date - previous_date)
        previous_date = payment_date
    return accruals


def _solve_swap_df(
    curve: PiecewiseCurve, maturity: float, par_rate: float, fixed_leg_step: float
) -> float:
    """Solve for the discount factor at a given maturity for a par swap.

    Assumes every payment date before ``maturity`` already falls within
    the curve's existing pillar range (either as an exact pillar or
    interpolatable between two pillars) -- if not, this raises via
    PiecewiseCurve.discount's own out-of-range check.

    Confirmed limitation (not just theoretical): payment dates are
    plain float years, and each instrument's schedule is generated
    independently from its own year_fraction-derived maturity and its
    own derived step. Even two swaps a single quarter apart in tenor
    produce slightly different step sizes (e.g. 0.253472 vs 0.253704
    for two Act/360 swaps three months apart), so their payment grids
    never actually coincide. This means a bootstrap_curve built purely
    from independently-generated float schedules cannot, in general,
    be made gap-free no matter how densely instruments are added --
    confirmed by direct testing, not just reasoned about. A real fix
    needs all instruments to share one common anchor date and a
    consistent, date-based schedule generation, not independent
    float-based schedules per instrument.
    """
    payment_schedule = _payment_schedule(maturity, fixed_leg_step)
    accruals = _accruals(payment_schedule)
    known_sum = sum(
        accrual * curve.discount(payment_date)
        for accrual, payment_date in zip(accruals[:-1], payment_schedule[:-1], strict=True)
    )
    return (1 - par_rate * known_sum) / (1 + par_rate * accruals[-1])


def _quote_maturity(quote: DepositQuote | SwapQuote) -> float:
    if isinstance(quote, DepositQuote):
        maturity, _ = quote.bootstrap_deposit()
    else:
        maturity, _ = quote.swap_schedule_inputs()
    return maturity


def bootstrap_curve(quotes: list[DepositQuote | SwapQuote]) -> PiecewiseCurve:
    """Bootstrap a piecewise curve from a list of deposit and swap quotes."""
    pillars: list[float] = []
    discount_factors: list[float] = []
    sorted_quotes = sorted(quotes, key=_quote_maturity)
    for quote in sorted_quotes:
        if isinstance(quote, DepositQuote):
            maturity, df = quote.bootstrap_deposit()
        else:
            maturity, step = quote.swap_schedule_inputs()
            curve_so_far = PiecewiseCurve(pillars, discount_factors)
            df = _solve_swap_df(curve_so_far, maturity, quote.rate, step)

        if pillars and abs(pillars[-1] - maturity) < 1e-9:
            raise ValueError(
                f"Two instruments produced maturities within tolerance of each other "
                f"({pillars[-1]} and {maturity}); caller must resolve which one to use."
            )

        pillars.append(maturity)
        discount_factors.append(df)
    return PiecewiseCurve(pillars, discount_factors)
