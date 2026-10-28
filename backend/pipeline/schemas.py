"""Data shapes shared by the extract and validate steps.

The LLM fills `Extraction`. Every factual field carries the line IDs it came
from and a verbatim quote, so the validator can check it against the
transcript instead of trusting it.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

LineId = str  # "P1-L9" = page 1, line 9


class Transcript(BaseModel):
    """Output of the transcribe step: numbered lines, in reading order."""
    lines: dict[LineId, str]


# ---------- What the LLM returns ----------

class Cited(BaseModel):
    value: str = Field(description="The value as written in the letter, e.g. '412,00 €' or '02.10.2026'")
    quote: str = Field(description="Verbatim text from the cited line(s) containing the value")
    lines: list[LineId] = Field(min_length=1)


class LetterType(str, Enum):
    tax = "tax"
    registration = "registration"
    health_insurance = "health_insurance"
    landlord = "landlord"
    fine = "fine"
    other = "other"


class RawDeadline(BaseModel):
    """The deadline exactly as the letter phrases it. The LLM does NO date math."""
    phrase: str = Field(description="Verbatim wording, e.g. 'innerhalb eines Monats nach Bekanntgabe'")
    kind: Literal["absolute", "relative"]
    date_text: str | None = Field(None, description="For absolute deadlines: the date as written, e.g. '06.11.2026'")
    amount: int | None = Field(None, description="For relative deadlines: e.g. 1")
    unit: Literal["days", "weeks", "months"] | None = None
    anchor: Literal["letter_date", "receipt", "other"] | None = Field(None, description=(
        "For relative deadlines, what the period counts from: 'receipt' for nach Bekanntgabe / "
        "Zugang / Zustellung / Erhalt; 'letter_date' for nach dem Datum dieses Schreibens; "
        "'other' for an event the letter doesn't date, e.g. nach Rechtskraft or nach "
        "Zahlungseingang. Never pick 'receipt' or 'letter_date' when the letter counts from "
        "something else."))
    summary: str = Field(description=(
        "One plain-English sentence saying what is due by this deadline, for a reminder, "
        "e.g. 'Pay the 317,40 € payment reminder.' or 'The period to object ends.'"))
    purpose: Literal["payment", "objection", "appointment", "other"] = Field(description=(
        "'payment' if money must be paid by this date; 'objection' if it ends the period to "
        "object (Einspruch / Widerspruch); 'appointment' for a date the user must be present "
        "or available (a Termin, a visit); 'other' for everything else."))
    lines: list[LineId] = Field(min_length=1)


class Claim(BaseModel):
    text: str = Field(description="One plain-English sentence for the user")
    lines: list[LineId] = Field(min_length=1)


class Extraction(BaseModel):
    letter_type: LetterType = Field(description=(
        "What the letter is, not who sent it: a Verwarnungsgeld or Bußgeld is 'fine' even "
        "when the Bürgeramt or Bezirksamt sends it."))
    sender: Cited
    letter_date: Cited
    amount: Cited | None = Field(None, description=(
        "Money that changes hands because of this letter: what you must pay, or what you "
        "will receive (a refund, a credit). Empty for amounts that are only mentioned, "
        "such as a future rent you are asked to agree to."))
    reference: Cited | None = None
    iban: Cited | None = Field(None, description=(
        "The account the user must pay into. Empty when the letter asks for no payment, "
        "e.g. the user's own account for a refund or the sender's account in the footer."))
    deadlines: list[RawDeadline]
    explanation: list[Claim]


# ---------- What the validator returns ----------

class ResolvedDeadline(BaseModel):
    date: date
    summary: str
    purpose: Literal["payment", "objection", "appointment", "other"]
    steps: list[str] = Field(description="Human-readable calculation, shown in the UI")
    lines: list[LineId]


class Issue(BaseModel):
    field: str
    problem: str


class ValidatedResult(BaseModel):
    extraction: Extraction
    deadlines: list[ResolvedDeadline]
    unsure: list[Issue] = Field(description="Shown to the user as 'Couldn't verify'")
    retried: bool = False
