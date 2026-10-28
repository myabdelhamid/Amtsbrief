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
    kw.setdefault("purpose", "other")
    return RawDeadline(phrase="x", summary="x", lines=["P1-L1"], **kw)


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


def test_relative_deadline_from_undated_event_is_rejected():
    with pytest.raises(ValueError):
        deadlines.resolve(raw(kind="relative", amount=2, unit="weeks", anchor="other"), date(2026, 10, 2))


def test_appointment_on_weekend_is_not_shifted():
    d = deadlines.resolve(raw(kind="absolute", date_text="07.11.2026", purpose="appointment"), date(2026, 10, 1))
    assert d.date == date(2026, 11, 7)
    assert d.steps == ["Stated in letter: 7 Nov"]


# ---------- 5. snap: start or end of a calendar period ----------

def test_snap_week_runs_monday_to_sunday():
    wednesday = date(2026, 11, 25)
    assert deadlines.snap(wednesday, "start", "week") == date(2026, 11, 23)
    assert deadlines.snap(wednesday, "end", "week") == date(2026, 11, 29)


def test_snap_month_end_knows_february():
    assert deadlines.snap(date(2028, 2, 10), "end", "month") == date(2028, 2, 29)  # leap year
    assert deadlines.snap(date(2027, 2, 10), "start", "month") == date(2027, 2, 1)


def test_snap_quarter_and_year():
    assert deadlines.snap(date(2026, 11, 5), "end", "quarter") == date(2026, 12, 31)
    assert deadlines.snap(date(2027, 2, 10), "start", "quarter") == date(2027, 1, 1)
    assert deadlines.snap(date(2027, 5, 10), "end", "quarter") == date(2027, 6, 30)
    assert deadlines.snap(date(2027, 5, 10), "start", "year") == date(2027, 1, 1)


# The ho_02 letter is dated 05.11.2026, so it counts as received on Mon 09.11.

def test_end_of_the_second_month_after_receipt():
    # "bis zum Ablauf des zweiten Monats nach Zugang": +2 months = 9 Jan, end = Sun 31 Jan
    d = deadlines.resolve(raw(kind="relative", amount=2, unit="months", anchor="receipt",
                              snap_to="end", snap_unit="month"), date(2026, 11, 5))
    assert d.date == date(2027, 2, 1)
    assert d.steps == ["Dated 5 Nov", "Deemed received 9 Nov (+4 days)", "+2 months = 9 Jan",
                       "End of that month = 31 Jan", "Falls on a weekend, moves to 1 Feb"]


def test_start_of_the_third_calendar_month_after_receipt():
    # "ab Beginn des dritten Kalendermonats nach Erhalt": +3 months = 9 Feb, start = 1 Feb
    d = deadlines.resolve(raw(kind="relative", amount=3, unit="months", anchor="receipt",
                              snap_to="start", snap_unit="month"), date(2026, 11, 5))
    assert d.date == date(2027, 2, 1)


def test_start_of_the_third_week_after_receipt():
    # Dated Tue 03.11, received Sat 07.11, +3 weeks = Sat 28.11, start of that week = Mon 23.11
    d = deadlines.resolve(raw(kind="relative", amount=3, unit="weeks", anchor="receipt",
                              snap_to="start", snap_unit="week"), date(2026, 11, 3))
    assert d.date == date(2026, 11, 23)


def test_end_of_the_second_calendar_week_moves_off_sunday():
    # Received Sat 07.11, +2 weeks = Sat 21.11, end of that week = Sun 22.11, moves to Mon 23.11
    d = deadlines.resolve(raw(kind="relative", amount=2, unit="weeks", anchor="receipt",
                              snap_to="end", snap_unit="week"), date(2026, 11, 3))
    assert d.date == date(2026, 11, 23)
    assert d.steps[-2:] == ["End of that week = 22 Nov", "Falls on a weekend, moves to 23 Nov"]


def test_end_of_the_current_quarter():
    # "zum Quartalsende": no period (amount 0), just the end of the letter date's quarter
    d = deadlines.resolve(raw(kind="relative", amount=0, unit="months", anchor="letter_date",
                              snap_to="end", snap_unit="quarter"), date(2026, 11, 5))
    assert d.date == date(2026, 12, 31)
    assert d.steps == ["Dated 5 Nov", "End of that quarter = 31 Dec"]


def test_plain_counted_weeks_are_not_snapped():
    # "innerhalb von zwei Wochen nach Zugang" stays receipt + 14 days: Sat 21.11 -> Mon 23.11
    d = deadlines.resolve(raw(kind="relative", amount=2, unit="weeks", anchor="receipt"), date(2026, 11, 3))
    assert d.date == date(2026, 11, 23)
    assert not any("of that" in step for step in d.steps)


def test_unsupported_wording_is_rejected():
    with pytest.raises(ValueError):
        deadlines.resolve(raw(kind="unsupported"), date(2026, 11, 5))


def test_snap_needs_both_fields():
    with pytest.raises(ValueError):
        deadlines.resolve(raw(kind="relative", amount=2, unit="months", anchor="receipt", snap_to="end"),
                          date(2026, 11, 5))
