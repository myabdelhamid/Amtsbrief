"""Step 1 exercise: make these pass by filling in pipeline/deadlines.py.

Run:  uv run pytest backend/tests/test_deadlines.py -v
Tip:  work top to bottom. Each section only needs the functions above it.
"""
from datetime import date

import pytest

from pipeline import deadlines
from pipeline.schemas import RawDeadline


# ---------- 1. parse_german_date ----------

def test_parses_date_inside_a_sentence():
    assert deadlines.parse_german_date("Datum: 02.10.2026") == date(2026, 10, 2)
    assert deadlines.parse_german_date("bis zum 6.11.2026 zahlen") == date(2026, 11, 6)


def test_rejects_text_without_a_date():
    with pytest.raises(ValueError):
        deadlines.parse_german_date("Keine Frist angegeben")


def test_rejects_impossible_dates():
    with pytest.raises(ValueError):
        deadlines.parse_german_date("31.02.2026")


# ---------- 2. add_months ----------

def test_adds_one_month():
    assert deadlines.add_months(date(2026, 10, 6), 1) == date(2026, 11, 6)


def test_rolls_over_into_next_year():
    assert deadlines.add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_clamps_to_month_end():
    assert deadlines.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert deadlines.add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)  # leap year


# ---------- 3. next_working_day ----------

def test_weekday_stays_the_same():
    assert deadlines.next_working_day(date(2026, 11, 6)) == date(2026, 11, 6)  # Friday


def test_weekend_moves_to_monday():
    assert deadlines.next_working_day(date(2026, 11, 7)) == date(2026, 11, 9)  # Saturday
    assert deadlines.next_working_day(date(2026, 11, 8)) == date(2026, 11, 9)  # Sunday


# ---------- 4. resolve ----------

def raw(**kw) -> RawDeadline:
    return RawDeadline(phrase="x", applies_to="reply", lines=["P1-L1"], **kw)


def test_relative_deadline_counts_from_deemed_receipt():
    d = deadlines.resolve(raw(kind="relative", amount=1, unit="months", anchor="receipt"), date(2026, 10, 2))
    assert d.date == date(2026, 11, 6)
    assert d.steps == ["Dated 2 Oct", "Deemed received 6 Oct (+4 days)", "+1 month = 6 Nov"]


def test_relative_weeks_from_letter_date():
    d = deadlines.resolve(raw(kind="relative", amount=2, unit="weeks", anchor="letter_date"), date(2026, 10, 2))
    assert d.date == date(2026, 10, 16)
    assert d.steps == ["Dated 2 Oct", "+2 weeks = 16 Oct"]


def test_absolute_deadline_on_weekend_is_shifted():
    d = deadlines.resolve(raw(kind="absolute", date_text="07.11.2026"), date(2026, 10, 1))
    assert d.date == date(2026, 11, 9)
    assert d.steps == ["Stated in letter: 7 Nov", "Falls on a weekend, moves to 9 Nov"]


def test_relative_deadline_missing_fields_is_rejected():
    with pytest.raises(ValueError):
        deadlines.resolve(raw(kind="relative", amount=1), date(2026, 10, 2))
