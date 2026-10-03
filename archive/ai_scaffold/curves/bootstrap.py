"""Curve bootstrapping and interpolation comparison utilities."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from math import exp, log
from statistics import fmean


class InterpolationMethod(StrEnum):
    """Interpolation scheme used between curve pillars."""

    LINEAR_DISCOUNT = "linear_discount"
    LINEAR_ZERO = "linear_zero"
    LOG_DISCOUNT = "log_discount"


@dataclass(frozen=True, slots=True)
class BootstrappingQuote:
    """A single market instrument (deposit or swap) used to calibrate a curve."""

    maturity_years: float
    rate: float
    helper_type: str
    fixed_leg_step: float | None = None

    def __post_init__(self) -> None:
        """Validate that the quote's fields are internally consistent."""
        if self.maturity_years <= 0:
            raise ValueError("maturity_years must be positive")
        if self.helper_type not in {"deposit", "swap"}:
            raise ValueError("helper_type must be 'deposit' or 'swap'")
        if self.helper_type == "swap":
            if self.fixed_leg_step is None or self.fixed_leg_step <= 0:
                raise ValueError("swap helpers need a positive fixed_leg_step")
        elif self.fixed_leg_step is not None:
            raise ValueError("fixed_leg_step is only valid for swap helpers")


@dataclass(frozen=True, slots=True)
class CurveBootstrapResult:
    """The calibrated curve plus each helper's repricing error."""

    curve: PiecewiseCurve
    helper_pv_errors: tuple[float, ...]

    @property
    def max_abs_error(self) -> float:
        """Largest absolute repricing error across all calibration helpers."""
        return max((abs(err) for err in self.helper_pv_errors), default=0.0)

    @property
    def mean_abs_error(self) -> float:
        """Average absolute repricing error across all calibration helpers."""
        return fmean(abs(err) for err in self.helper_pv_errors) if self.helper_pv_errors else 0.0


@dataclass(slots=True)
class PiecewiseCurve:
    """A discount curve defined by pillars, interpolated between them."""

    pillars: list[float]
    discount_factors: list[float]
    interpolation: InterpolationMethod = InterpolationMethod.LINEAR_ZERO

    def __post_init__(self) -> None:
        """Validate that pillars and discount factors are consistent."""
        if len(self.pillars) != len(self.discount_factors):
            raise ValueError("pillars and discount_factors must have the same length")
        if not self.pillars:
            raise ValueError("at least one pillar is required")
        if self.pillars != sorted(self.pillars):
            raise ValueError("pillars must be sorted")
        if any(t <= 0 for t in self.pillars):
            raise ValueError("pillars must be positive")
        if any(df <= 0 or df > 1.0 for df in self.discount_factors):
            raise ValueError("discount factors must lie in (0, 1]")

    def add_pillar(self, maturity: float, discount_factor: float) -> None:
        """Append a new pillar after the curve's current longest maturity."""
        if maturity <= self.pillars[-1]:
            raise ValueError("pillars must be appended in strictly increasing order")
        self.pillars.append(maturity)
        self.discount_factors.append(discount_factor)

    def discount(self, maturity: float) -> float:
        """Return the discount factor at ``maturity``, interpolating between pillars."""
        if maturity <= 0:
            return 1.0
        if maturity <= self.pillars[0]:
            return self._extrapolate_left(maturity)
        for idx, pillar in enumerate(self.pillars):
            if abs(maturity - pillar) < 1e-12:
                return self.discount_factors[idx]
            if maturity < pillar:
                return self._interpolate_between(idx - 1, idx, maturity)
        return self._extrapolate_right(maturity)

    def zero_rate(self, maturity: float) -> float:
        """Return the continuously-compounded zero rate at ``maturity``."""
        if maturity <= 0:
            return 0.0
        return -log(self.discount(maturity)) / maturity

    def forward_rate(self, start: float, end: float) -> float:
        """Return the forward rate implied between ``start`` and ``end``."""
        if end <= start:
            raise ValueError("end must be greater than start")
        return (self.discount(start) / self.discount(end) - 1.0) / (end - start)

    def dense_forward_profile(self, step: float = 1.0 / 12.0) -> list[tuple[float, float]]:
        """Return forward rates on a regular grid, for plotting/inspection."""
        horizon = self.pillars[-1]
        t = step
        grid: list[tuple[float, float]] = []
        while t <= horizon + 1e-12:
            t = round(t, 10)
            grid.append((t, self.forward_rate(max(0.0, t - step), t)))
            t += step
        return grid

    def _interpolate_between(self, left_idx: int, right_idx: int, maturity: float) -> float:
        lt = self.pillars[left_idx]
        rt = self.pillars[right_idx]
        ldf = self.discount_factors[left_idx]
        rdf = self.discount_factors[right_idx]
        w = (maturity - lt) / (rt - lt)
        if self.interpolation == InterpolationMethod.LINEAR_DISCOUNT:
            return ldf + w * (rdf - ldf)
        if self.interpolation == InterpolationMethod.LINEAR_ZERO:
            lz = -log(ldf) / lt
            rz = -log(rdf) / rt
            return exp(-(lz + w * (rz - lz)) * maturity)
        return exp(log(ldf) + w * (log(rdf) - log(ldf)))

    def _extrapolate_left(self, maturity: float) -> float:
        if len(self.pillars) == 1:
            return exp(log(self.discount_factors[0]) * maturity / self.pillars[0])
        return self._interpolate_between(0, 1, maturity)

    def _extrapolate_right(self, maturity: float) -> float:
        if len(self.pillars) == 1:
            return exp(log(self.discount_factors[0]) * maturity / self.pillars[0])
        li = len(self.pillars) - 2
        ri = len(self.pillars) - 1
        lt = self.pillars[li]
        rt = self.pillars[ri]
        ldf = self.discount_factors[li]
        rdf = self.discount_factors[ri]
        w = (maturity - lt) / (rt - lt)
        if self.interpolation == InterpolationMethod.LINEAR_DISCOUNT:
            slope = (rdf - ldf) / (rt - lt)
            return max(1e-12, rdf + slope * (maturity - rt))
        if self.interpolation == InterpolationMethod.LINEAR_ZERO:
            lz = -log(ldf) / lt
            rz = -log(rdf) / rt
            return exp(-(rz + (rz - lz) * w) * maturity)
        rf = -(log(rdf) - log(ldf)) / (rt - lt)
        return rdf * exp(-rf * (maturity - rt))


def forward_rate(curve: PiecewiseCurve, start: float, end: float) -> float:
    """Module-level convenience wrapper around ``PiecewiseCurve.forward_rate``."""
    return curve.forward_rate(start, end)


def par_swap_rate(curve: PiecewiseCurve, maturity: float, fixed_leg_step: float) -> float:
    """Return the par swap rate implied by ``curve`` for a given maturity/step."""
    payment_dates = _payment_schedule(maturity, fixed_leg_step)
    accruals = _accruals(payment_dates)
    discount_sum = sum(
        accrual * curve.discount(payment)
        for accrual, payment in zip(accruals[:-1], payment_dates[:-1], strict=True)
    )
    last_accrual = accruals[-1]
    df_maturity = curve.discount(maturity)
    return (1.0 - df_maturity) / (discount_sum + last_accrual * df_maturity)


def bootstrap_curve(
    helpers: Iterable[BootstrappingQuote],
    interpolation: InterpolationMethod,
) -> CurveBootstrapResult:
    """Bootstrap a discount curve from deposit/swap quotes, solving pillars in maturity order."""
    ordered = sorted(helpers, key=lambda item: item.maturity_years)
    if not ordered:
        raise ValueError("at least one helper is required")

    first = ordered[0]
    curve = PiecewiseCurve(
        pillars=[first.maturity_years],
        discount_factors=[
            _helper_df(PiecewiseCurve([first.maturity_years], [1.0], interpolation), first)
        ],
        interpolation=interpolation,
    )
    errors: list[float] = []
    for helper in ordered:
        df = _helper_df(curve, helper)
        if abs(curve.pillars[-1] - helper.maturity_years) > 1e-12:
            curve.add_pillar(helper.maturity_years, df)
        else:
            curve.discount_factors[-1] = df
        errors.append(_repricing_error(curve, helper))
    return CurveBootstrapResult(curve=curve, helper_pv_errors=tuple(errors))


def demo_curve_quotes() -> tuple[list[BootstrappingQuote], list[BootstrappingQuote]]:
    """Return sample discount and projection curve quotes for demonstration."""
    discount = [
        BootstrappingQuote(1.0 / 12.0, 0.0402, "deposit"),
        BootstrappingQuote(0.25, 0.0415, "deposit"),
        BootstrappingQuote(0.50, 0.0422, "deposit"),
        BootstrappingQuote(1.00, 0.0430, "swap", 0.25),
        BootstrappingQuote(2.00, 0.0415, "swap", 0.25),
        BootstrappingQuote(3.00, 0.0395, "swap", 0.25),
        BootstrappingQuote(5.00, 0.0370, "swap", 0.25),
    ]
    projection = [
        BootstrappingQuote(0.25, 0.0460, "deposit"),
        BootstrappingQuote(0.50, 0.0468, "deposit"),
        BootstrappingQuote(1.00, 0.0474, "swap", 0.25),
        BootstrappingQuote(2.00, 0.0458, "swap", 0.25),
        BootstrappingQuote(3.00, 0.0440, "swap", 0.25),
        BootstrappingQuote(5.00, 0.0415, "swap", 0.25),
    ]
    return discount, projection


def projection_vs_discount_report(
    discount_curve: PiecewiseCurve,
    projection_curve: PiecewiseCurve,
    *,
    notional: float = 100.0,
) -> dict[str, float]:
    """Compare a floating leg's PV under matching vs. mismatched projection/discount curves."""
    float_leg_pv = _floating_leg_pv(
        projection_curve, discount_curve, maturity=5.0, step=0.25, notional=notional
    )
    self_discount_pv = _floating_leg_pv(
        discount_curve, discount_curve, maturity=5.0, step=0.25, notional=notional
    )
    return {
        "float_leg_pv_with_projection": float_leg_pv,
        "float_leg_pv_with_discount_as_projection": self_discount_pv,
        "pv_basis": float_leg_pv - self_discount_pv,
        "discount_5y_zero": discount_curve.zero_rate(5.0),
        "projection_5y_zero": projection_curve.zero_rate(5.0),
    }


def _floating_leg_pv(
    projection_curve: PiecewiseCurve,
    discount_curve: PiecewiseCurve,
    *,
    maturity: float,
    step: float,
    notional: float,
) -> float:
    payments = _payment_schedule(maturity, step)
    accruals = _accruals(payments)
    pv = 0.0
    prev = 0.0
    for accrual, payment in zip(accruals, payments, strict=True):
        pv += (
            notional
            * accrual
            * projection_curve.forward_rate(prev, payment)
            * discount_curve.discount(payment)
        )
        prev = payment
    pv += notional * (1.0 - discount_curve.discount(maturity))
    return pv


def _repricing_error(curve: PiecewiseCurve, helper: BootstrappingQuote) -> float:
    if helper.helper_type == "deposit":
        implied = 1.0 / curve.discount(helper.maturity_years) - 1.0
        return implied / helper.maturity_years - helper.rate
    assert helper.fixed_leg_step is not None
    return par_swap_rate(curve, helper.maturity_years, helper.fixed_leg_step) - helper.rate


def _solve_swap_df(
    curve: PiecewiseCurve, maturity: float, par_rate: float, fixed_leg_step: float
) -> float:
    payment_dates = _payment_schedule(maturity, fixed_leg_step)
    accruals = _accruals(payment_dates)
    known = sum(
        accrual * curve.discount(payment)
        for accrual, payment in zip(accruals[:-1], payment_dates[:-1], strict=True)
    )
    return (1.0 - par_rate * known) / (1.0 + par_rate * accruals[-1])


def _helper_df(curve: PiecewiseCurve, helper: BootstrappingQuote) -> float:
    if helper.helper_type == "deposit":
        return _deposit_df(helper.maturity_years, helper.rate)
    assert helper.fixed_leg_step is not None
    return _solve_swap_df(curve, helper.maturity_years, helper.rate, helper.fixed_leg_step)


def _deposit_df(maturity: float, rate: float) -> float:
    return 1.0 / (1.0 + rate * maturity)


def _payment_schedule(maturity: float, step: float) -> list[float]:
    n_steps = round(maturity / step)
    if abs(n_steps * step - maturity) > 1e-9:
        raise ValueError("maturity must be an integer multiple of step")
    return [round(step * (index + 1), 10) for index in range(n_steps)]


def _accruals(payment_dates: list[float]) -> list[float]:
    prev = 0.0
    out: list[float] = []
    for payment in payment_dates:
        out.append(payment - prev)
        prev = payment
    return out
