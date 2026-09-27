"""A piecewise-constant discount curve, defined by pillar maturities and discount factors."""

from datetime import date

from rates_analytics.conventions import DayCount, year_fraction


class PiecewiseCurve:
    """A piecewise-constant discount curve, defined by pillar maturities and discount factors."""

    pillars: list[float]
    discount_factors: list[float]

    def __init__(self, pillars: list[float], discount_factors: list[float]) -> None:
        """Initialize the piecewise curve with pillars and discount factors."""
        self.pillars = pillars
        self.discount_factors = discount_factors
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
                    return df0 + (df1 - df0) * (maturity - t0) / (t1 - t0)
            raise ValueError("Maturity does not fall within any defined pillar intervals.")


def deposit_to_df(start: date, end: date, rate: float, day_count: DayCount) -> float:
    """Convert a deposit rate to a discount factor."""
    t = year_fraction(start, end, day_count)
    return 1 / (1 + rate * t)
