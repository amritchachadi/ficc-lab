"""Day count conventions.

Implemented directly from published specifications and deliberately free of
third-party dependencies. These are cross-checked against QuantLib in
``tests/test_daycount_vs_quantlib.py`` rather than delegating to it: two
independent implementations agreeing is the validation story for this repo.

References
----------
ISDA 2006 Definitions, Section 4.16 ("Day Count Fraction").
SIFMA, *Standard Securities Calculation Methods*, vol. 1 (30/360 US).
ICMA Rule 251 (Actual/Actual ICMA).
"""

from __future__ import annotations

import calendar
from datetime import date
from enum import StrEnum


class DayCount(StrEnum):
    """Supported day count conventions."""

    THIRTY_360_US = "30/360 US"
    THIRTY_E_360 = "30E/360"
    THIRTY_E_360_ISDA = "30E/360 ISDA"
    ACT_360 = "Act/360"
    ACT_365F = "Act/365F"
    ACT_ACT_ISDA = "Act/Act ISDA"
    ACT_ACT_ICMA = "Act/Act ICMA"


def _days_in_month(d: date) -> int:
    return calendar.monthrange(d.year, d.month)[1]


def _is_last_day_of_month(d: date) -> bool:
    return d.day == _days_in_month(d)


def _is_last_day_of_february(d: date) -> bool:
    return d.month == 2 and _is_last_day_of_month(d)


def _is_leap(year: int) -> bool:
    return calendar.isleap(year)


def _thirty_360_us(start: date, end: date, *, eom: bool) -> int:
    """Return accrual days under 30/360 US (bond basis), per SIFMA.

    The February rules apply only when the security follows the
    end-of-month rule, which is why ``eom`` is an explicit input rather
    than something inferred from the dates.
    """
    d1, d2 = start.day, end.day

    if eom and _is_last_day_of_february(start) and _is_last_day_of_february(end):
        d2 = 30
    if eom and _is_last_day_of_february(start):
        d1 = 30
    if d2 == 31 and d1 in (30, 31):
        d2 = 30
    if d1 == 31:
        d1 = 30

    return 360 * (end.year - start.year) + 30 * (end.month - start.month) + (d2 - d1)


def _thirty_e_360(start: date, end: date) -> int:
    """Return accrual days under 30E/360 (Eurobond basis).

    No February special case: the 31st is simply truncated to the 30th at
    both ends. This is the convention most commonly mislabelled "30/360".
    """
    d1 = 30 if start.day == 31 else start.day
    d2 = 30 if end.day == 31 else end.day
    return 360 * (end.year - start.year) + 30 * (end.month - start.month) + (d2 - d1)


def _thirty_e_360_isda(start: date, end: date, *, is_termination: bool) -> int:
    """Return accrual days under 30E/360 ISDA.

    Differs from plain 30E/360 in that *any* month-end rolls to 30, not just
    the 31st -- so a 28/29 February start or end is affected. The end date is
    exempt when it is the termination date falling in February.
    """
    d1 = 30 if _is_last_day_of_month(start) else start.day
    exempt = end.month == 2 and is_termination
    d2 = 30 if _is_last_day_of_month(end) and not exempt else end.day
    return 360 * (end.year - start.year) + 30 * (end.month - start.month) + (d2 - d1)


def _act_act_isda(start: date, end: date) -> float:
    """Return the year fraction under Actual/Actual ISDA.

    Days are apportioned to the calendar year they fall in and divided by
    that year's own length, so a period spanning a leap year boundary uses
    both 365 and 366 as denominators.
    """
    if start.year == end.year:
        return (end - start).days / (366.0 if _is_leap(start.year) else 365.0)

    head = (date(start.year + 1, 1, 1) - start).days / (366.0 if _is_leap(start.year) else 365.0)
    tail = (end - date(end.year, 1, 1)).days / (366.0 if _is_leap(end.year) else 365.0)
    whole_years = end.year - start.year - 1
    return head + whole_years + tail


def year_fraction(
    start: date,
    end: date,
    convention: DayCount,
    *,
    eom: bool = False,
    is_termination: bool = False,
    ref_period_start: date | None = None,
    ref_period_end: date | None = None,
    frequency: int | None = None,
) -> float:
    """Return the accrual year fraction between two dates.

    Parameters
    ----------
    start, end
        Accrual period boundaries. ``end`` must not precede ``start``.
    convention
        The day count convention to apply.
    eom
        Whether the security follows the end-of-month rule. Only consulted
        by :attr:`DayCount.THIRTY_360_US`.
    is_termination
        Whether ``end`` is the final termination date. Only consulted by
        :attr:`DayCount.THIRTY_E_360_ISDA`.
    ref_period_start, ref_period_end, frequency
        The enclosing coupon period and coupon frequency in payments per
        year. Required by :attr:`DayCount.ACT_ACT_ICMA` and ignored
        otherwise.

    Returns
    -------
    float
        The year fraction, non-negative.

    Raises
    ------
    ValueError
        If ``end`` precedes ``start``, or if an Act/Act ICMA reference
        period is incomplete.
    """
    if end < start:
        msg = f"end ({end}) precedes start ({start})"
        raise ValueError(msg)

    match convention:
        case DayCount.THIRTY_360_US:
            return _thirty_360_us(start, end, eom=eom) / 360.0
        case DayCount.THIRTY_E_360:
            return _thirty_e_360(start, end) / 360.0
        case DayCount.THIRTY_E_360_ISDA:
            return _thirty_e_360_isda(start, end, is_termination=is_termination) / 360.0
        case DayCount.ACT_360:
            return (end - start).days / 360.0
        case DayCount.ACT_365F:
            return (end - start).days / 365.0
        case DayCount.ACT_ACT_ISDA:
            return _act_act_isda(start, end)
        case DayCount.ACT_ACT_ICMA:
            if ref_period_start is None or ref_period_end is None or frequency is None:
                msg = (
                    "Act/Act ICMA requires ref_period_start, ref_period_end and "
                    "frequency: the denominator is the length of the enclosing "
                    "coupon period, not of the accrual period"
                )
                raise ValueError(msg)
            if ref_period_end <= ref_period_start:
                msg = "reference period must be non-empty and increasing"
                raise ValueError(msg)
            period_days = (ref_period_end - ref_period_start).days
            return (end - start).days / (frequency * period_days)
