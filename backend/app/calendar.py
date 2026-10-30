"""Deadlines as iCalendar (.ics), so the user's own calendar does the reminding.

Each resolved deadline becomes an all-day event with an alarm REMIND_BEFORE it. The
letters give dates, not times, so no time is guessed. Only resolved deadlines are
included: one under "Couldn't verify" never becomes a reminder.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from icalendar import Alarm, Calendar, Event

from .store import StoredLetter

REMIND_BEFORE = timedelta(days=3)
PURPOSE_LABEL = {"payment": "Payment due", "objection": "Objection deadline",
                 "appointment": "Appointment", "other": "Deadline"}


def _event(letter: StoredLetter, index: int) -> Event:
    deadline = letter.analysis.result.deadlines[index]
    sender = letter.analysis.result.extraction.sender.value
    event = Event()
    # A stable UID: re-importing the same deadline updates the event instead of copying it.
    event.add("uid", f"{letter.id}-{index}@amtsbrief")
    event.add("dtstamp", datetime.now(timezone.utc))
    event.add("dtstart", deadline.date)
    event.add("dtend", deadline.date + timedelta(days=1))  # all-day events end the next day
    event.add("summary", f"{PURPOSE_LABEL[deadline.purpose]}: {deadline.summary}")
    event.add("description", f"From your letter from {sender}.\n" + "\n".join(deadline.steps)
              + "\nCheck the date against the original letter. This is not legal advice.")
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", deadline.summary)
    alarm.add("trigger", -REMIND_BEFORE)
    event.add_component(alarm)
    return event


def calendar(letters: list[StoredLetter]) -> bytes:
    """One calendar with every resolved deadline of the given letters."""
    cal = Calendar()
    cal.add("prodid", "-//Amtsbrief//Deadlines//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "Amtsbrief deadlines")
    for letter in letters:
        for index in range(len(letter.analysis.result.deadlines)):
            cal.add_component(_event(letter, index))
    return cal.to_ical()


def single_deadline(letter: StoredLetter, index: int) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//Amtsbrief//Deadlines//EN")
    cal.add("version", "2.0")
    cal.add_component(_event(letter, index))
    return cal.to_ical()
