"""Coupon schedule generation, business day adjustment and month arithmetic.

Schedules are built by rolling *from the anchor* rather than by repeatedly
stepping a cursor, so a February or month-end roll early in the schedule
cannot drift the dates that follow it.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from datetime import date, timedelta
from enum import Enum, StrEnum

_SATURDAY = 5


class BusinessDayConvention(StrEnum):
    """How to move a date that falls on a non-business day."""

    UNADJUSTED = "Unadjusted"
    FOLLOWING = "Following"
    MODIFIED_FOLLOWING = "Modified Following"
    PRECEDING = "Preceding"
    MODIFIED_PRECEDING = "Modified Preceding"


class Frequency(int, Enum):
    """Coupon frequency in payments per year."""

    ANNUAL = 1
    SEMIANNUAL = 2
    QUARTERLY = 4
    MONTHLY = 12


class Generation(StrEnum):
    """Which end of the schedule the regular periods are measured from.

    ``BACKWARD`` rolls from maturity, leaving any stub at the front, which
    is the usual market convention for bonds.
    """

    BACKWARD = "Backward"
    FORWARD = "Forward"


class Calendar:
    """A business day calendar: weekends plus an explicit holiday set."""

    def __init__(self, holidays: Iterable[date] = ()) -> None:
        self._holidays = frozenset(holidays)

    @property
    def holidays(self) -> frozenset[date]:
        """Return the holiday set."""
        return self._holidays

    def is_business_day(self, d: date) -> bool:
        """Return whether ``d`` is a weekday and not a holiday."""
        return d.weekday() < _SATURDAY and d not in self._holidays

    def _roll(self, d: date, step: int) -> date:
        while not self.is_business_day(d):
            d += timedelta(days=step)
        return d

    def adjust(self, d: date, convention: BusinessDayConvention) -> date:
        """Return ``d`` moved to a business day under ``convention``.

        The modified variants fall back to rolling the other way when the
        straightforward roll would cross a month boundary.
        """
        if convention is BusinessDayConvention.UNADJUSTED or self.is_business_day(d):
            return d

        match convention:
            case BusinessDayConvention.FOLLOWING:
                return self._roll(d, 1)
            case BusinessDayConvention.PRECEDING:
                return self._roll(d, -1)
            case BusinessDayConvention.MODIFIED_FOLLOWING:
                rolled = self._roll(d, 1)
                return self._roll(d, -1) if rolled.month != d.month else rolled
            case BusinessDayConvention.MODIFIED_PRECEDING:
                rolled = self._roll(d, -1)
                return self._roll(d, 1) if rolled.month != d.month else rolled
            case _:  # pragma: no cover - exhaustive over the enum
                msg = f"unhandled convention {convention}"
                raise ValueError(msg)


def add_months(anchor: date, months: int, *, eom: bool = False) -> date:
    """Return ``anchor`` shifted by ``months`` calendar months.

    The day of month is clamped to the length of the target month, so
    31 January plus one month is 28 or 29 February. When ``eom`` is set and
    ``anchor`` is the last day of its month, the result is pinned to the
    last day of the target month instead of merely clamped.
    """
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    last = calendar.monthrange(year, month)[1]

    if eom and anchor.day == calendar.monthrange(anchor.year, anchor.month)[1]:
        return date(year, month, last)
    return date(year, month, min(anchor.day, last))


def generate_schedule(
    start: date,
    end: date,
    frequency: Frequency,
    *,
    calendar_: Calendar | None = None,
    convention: BusinessDayConvention = BusinessDayConvention.UNADJUSTED,
    eom: bool = False,
    generation: Generation = Generation.BACKWARD,
    adjust_terminal: bool = True,
) -> list[date]:
    """Return the adjusted period boundary dates from ``start`` to ``end``.

    The returned list always begins at ``start`` and ends at ``end`` (each
    possibly adjusted), so a schedule of *n* coupon periods has *n + 1*
    entries. Any irregular period lands at the front under
    :attr:`Generation.BACKWARD` and at the back under
    :attr:`Generation.FORWARD`.

    Parameters
    ----------
    start, end
        Effective and maturity dates. ``end`` must be strictly after
        ``start``.
    frequency
        Coupon frequency in payments per year.
    calendar_
        Business day calendar. Defaults to weekends only.
    convention
        Business day convention applied to every boundary.
    eom
        Apply the end-of-month rule when rolling.
    generation
        Which end to measure the regular periods from.
    adjust_terminal
        Whether to adjust the maturity date. Many bonds pay on an
        unadjusted maturity even when intermediate coupons are adjusted, so
        this is separable.

    Returns
    -------
    list of date
        Strictly increasing boundary dates.

    Raises
    ------
    ValueError
        If ``end`` is not strictly after ``start``.
    """
    if end <= start:
        msg = f"end ({end}) must be strictly after start ({start})"
        raise ValueError(msg)

    cal = calendar_ if calendar_ is not None else Calendar()
    months = 12 // int(frequency)
    unadjusted = _unadjusted_dates(start, end, months, eom=eom, generation=generation)

    adjusted = [cal.adjust(d, convention) for d in unadjusted[:-1]]
    terminal = cal.adjust(end, convention) if adjust_terminal else end
    adjusted.append(terminal)

    return _dedupe_increasing(adjusted)


def _unadjusted_dates(
    start: date,
    end: date,
    months: int,
    *,
    eom: bool,
    generation: Generation,
) -> list[date]:
    dates: list[date] = []

    if generation is Generation.BACKWARD:
        k = 0
        cursor = end
        while cursor > start:
            dates.append(cursor)
            k += 1
            cursor = add_months(end, -months * k, eom=eom)
        dates.append(start)
        dates.reverse()
    else:
        k = 0
        cursor = start
        while cursor < end:
            dates.append(cursor)
            k += 1
            cursor = add_months(start, months * k, eom=eom)
        dates.append(end)

    return dates


def _dedupe_increasing(dates: list[date]) -> list[date]:
    """Collapse duplicates that adjustment can create around a short stub."""
    out: list[date] = []
    for d in dates:
        if not out or d > out[-1]:
            out.append(d)
    return out
