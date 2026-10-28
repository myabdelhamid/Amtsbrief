"""Deterministic deadline arithmetic. Pure functions, no LLM, fully unit-testable.

STEP 1 EXERCISE: replace each `raise NotImplementedError` with real code
until `uv run pytest backend/tests/test_deadlines.py -v` is all green.
Work top to bottom. Ask Claude for a hint, not the answer, when stuck.

Rules encoded here (German administrative and tax letters):
- Letters sent by post count as received ("bekannt gegeben") on the 4th day
  after posting. We use the letter date as the posting date.
- A deadline that ends on a Saturday or Sunday moves to the next working day.
  Appointments don't move: they happen on the stated day.
  Public holidays are not handled yet.
- A period counted from an event the letter doesn't date (anchor "other", e.g.
  "nach Rechtskraft") can't be computed, so resolve() raises ValueError.
- A snap moves the counted date to the start or end of its calendar week
  (Monday to Sunday), month, quarter or year: "Ablauf des zweiten Monats nach
  Zugang" is +2 months, then the end of that month. The weekend shift comes
  after the snap, because the snapped day is the real last day.
- Wording that fits no shape (kind "unsupported") is never guessed: ValueError.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from .schemas import RawDeadline, ResolvedDeadline

RECEIPT_DAYS = 4

# Matches German dates like "02.10.2026" or "6.11.2026" anywhere in a string.
# m.groups() gives you ("02", "10", "2026") as strings.
_DE_DATE = re.compile(r"(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})")


def parse_german_date(text: str) -> date:
    x = _DE_DATE.search(text)
    if x is None:
        raise ValueError
    date_tuple = x.groups()
    y = int(date_tuple[0])
    m = int(date_tuple[1])
    d = int(date_tuple[2])
    return(date(d,m,y))


def add_months(d: date, n: int) -> date:
    y = d.year
    m = d.month
    dd = d.day
    y += n//12
    if m + n%12 <= 12:
        m += n%12
    else:
        m += (n%12-12)
        y += 1
    dd = min(calendar.monthrange(y, m)[1], dd)
    return date(y, m, dd)


def next_working_day(d: date) -> date:
    if d.weekday() <= 4:
        return d
    else:
        return d + timedelta(days=7-d.weekday())
    

def _fmt(d: date) -> str:
    """date(2026, 10, 6) -> '6 Oct'. Given to you, it's only formatting."""
    return f"{d.day} {d.strftime('%b')}"


def add_period(d: date, amount: int, unit: str) -> date:
    """Add `amount` days, weeks, months or years to `d`."""
    if unit == "days":
        return d + timedelta(days=amount)
    elif unit == "weeks":
        return d + timedelta(weeks=amount)
    elif unit == "months":
        return add_months(d, amount)
    elif unit == "years":
        return add_months(d, 12 * amount)
    raise ValueError(f"unknown unit {unit!r}")


def snap(d: date, to: str, unit: str) -> date:
    """The first ('start') or last ('end') day of the week, month, quarter or year that contains d."""
    if unit == "week":
        monday = d - timedelta(days=d.weekday())
        return monday if to == "start" else monday + timedelta(days=6)
    if unit == "month":
        first_month = last_month = d.month
    elif unit == "quarter":
        first_month = 3 * ((d.month - 1) // 3) + 1  # 1, 4, 7 or 10
        last_month = first_month + 2
    elif unit == "year":
        first_month, last_month = 1, 12
    else:
        raise ValueError(f"unknown snap unit {unit!r}")
    if to == "start":
        return date(d.year, first_month, 1)
    return date(d.year, last_month, calendar.monthrange(d.year, last_month)[1])


def resolve(raw: RawDeadline, letter_date: date) -> ResolvedDeadline:
    steps: list[str] = []

    if raw.kind == "unsupported":
        raise ValueError(f"wording the code can't compute: {raw.phrase!r}")
    if (raw.snap_to is None) != (raw.snap_unit is None):
        raise ValueError("snap_to and snap_unit must be set together")

    if raw.kind == "absolute":
        if not raw.date_text:
            raise ValueError("absolute deadline without date_text")
        due = parse_german_date(raw.date_text)
        steps.append(f"Stated in letter: {_fmt(due)}")
    else:
        if raw.amount is None or raw.unit is None or raw.anchor is None:
            raise ValueError("relative deadline needs amount, unit and anchor")
        if raw.anchor == "other":
            raise ValueError(f"counted from an event the letter doesn't date: {raw.phrase!r}")
        start = letter_date
        steps.append(f"Dated {_fmt(letter_date)}")
        if raw.anchor == "receipt":
            start = letter_date + timedelta(days=RECEIPT_DAYS)
            steps.append(f"Deemed received {_fmt(start)} (+{RECEIPT_DAYS} days)")
        due = add_period(start, raw.amount, raw.unit)
        label = raw.unit[:-1] if raw.amount == 1 else raw.unit
        if raw.amount:
            steps.append(f"+{raw.amount} {label} = {_fmt(due)}")
        if raw.snap_to is not None:
            due = snap(due, raw.snap_to, raw.snap_unit)
            steps.append(f"{raw.snap_to.capitalize()} of that {raw.snap_unit} = {_fmt(due)}")

    shifted = due
    if raw.purpose != "appointment":
        shifted = next_working_day(due)
        if shifted != due:
            steps.append(f"Falls on a weekend, moves to {_fmt(shifted)}")

    return ResolvedDeadline(date=shifted, summary=raw.summary, purpose=raw.purpose,
                            steps=steps, lines=raw.lines)
