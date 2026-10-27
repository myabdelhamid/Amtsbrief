"""Check the LLM's extraction against the transcript. Plain code, no LLM.

STEP 2 EXERCISE: replace each `raise NotImplementedError` with real code
until `uv run pytest backend/tests/test_validate.py -v` is all green.
Work top to bottom. Ask Claude for a hint, not the answer, when stuck.

Nothing the LLM says is shown as fact until code has checked it:
- every cited line ID exists in the transcript,
- every quote really appears in the cited lines (fuzzy, to survive OCR noise),
- the cited value appears inside its quote,
- values parse: German dates and amounts, and the IBAN checksum is valid.
Anything that fails becomes an `Issue`, shown to the user as "Couldn't verify".
"""
from __future__ import annotations

import re
from decimal import Decimal
from difflib import SequenceMatcher

from .deadlines import parse_german_date, resolve
from .schemas import Cited, Extraction, Issue, LineId, Transcript, ValidatedResult

QUOTE_THRESHOLD = 0.9

# Matches German amounts like "35,00", "1.234,56" or "412" anywhere in a string.
# m.group(1) gives you the number as written, e.g. "1.234,56".
_DE_AMOUNT = re.compile(r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)")


def parse_german_amount(text: str) -> Decimal:
    """'1.234,56 €' -> Decimal('1234.56'). Raise ValueError if there is no amount.

    German amounts use '.' between thousands and ',' before the cents.
    Return a Decimal, not a float: floats can't store 0.10 exactly.
    """
    match = _DE_AMOUNT.search(text)
    if match is None:
        raise ValueError(f"no amount in {text!r}")
    # Remove the thousands dots first, then turn the decimal comma into a dot.
    amount = match.group(1).replace(".", "").replace(",", ".")
    return Decimal(amount)


def iban_is_valid(iban: str) -> bool:
    """True if `iban` passes the ISO 13616 mod-97 check. Spaces are allowed.

    The algorithm: remove spaces, move the first 4 characters to the end,
    replace each letter with two digits (A=10, B=11, ... Z=35), read the result
    as one big integer, and check that it leaves remainder 1 when divided by 97.
    Anything that isn't letters and digits after removing spaces is invalid.
    """
    iban = iban.replace(" ", "")
    if not iban.isalnum():
        return False
    rearranged = iban[4:] + iban[:4]
    digits = ""
    for char in rearranged:
        digits += str(int(char, 36))
    return int(digits) % 97 == 1


def quote_matches(quote: str, text: str, threshold: float = QUOTE_THRESHOLD) -> bool:
    """True if `quote` appears in `text`, allowing small differences (OCR noise).

    An exact substring is always a match. Otherwise, compare the quote with every
    piece of `text` that has the same length, and accept if the best similarity
    is at least `threshold`. An empty quote proves nothing, so it never matches.
    """
    if not quote:
        return False
    if quote in text:
        return True
    for start in range(len(text) - len(quote) + 1):
        piece = text[start:start + len(quote)]
        if SequenceMatcher(None, quote, piece).ratio() >= threshold:
            return True
    return False


def missing_lines(lines: list[LineId], transcript: Transcript) -> list[LineId]:
    """The IDs in `lines` that don't exist in the transcript, in the given order."""
    missing = []
    for line_id in lines:
        if line_id not in transcript.lines:
            missing.append(line_id)
    return missing


def check_cited(field: str, cited: Cited, transcript: Transcript) -> list[Issue]:
    """Return the problems with one cited field. An empty list means it checks out.

    Check, in this order, and stop at the first problem:
    1. every cited line exists,
    2. the quote matches the cited lines' text (joined with a space),
    3. the value appears in the quote (exact substring).
    Each problem is one Issue with `field` set to the given field name.
    """
    missing = missing_lines(cited.lines, transcript)
    if missing:
        return [Issue(field=field, problem=f"cites missing lines {missing}")]
    texts = []
    for line_id in cited.lines:
        texts.append(transcript.lines[line_id])
    cited_text = " ".join(texts)
    if not quote_matches(cited.quote, cited_text):
        return [Issue(field=field, problem=f"quote {cited.quote!r} not found in lines {cited.lines}")]
    if cited.value not in cited.quote:
        return [Issue(field=field, problem=f"value {cited.value!r} not found in quote")]
    return []


def validate(extraction: Extraction, transcript: Transcript) -> ValidatedResult:
    """Check every field and resolve the deadlines.

    - sender, letter_date, and amount/reference/iban when present: `check_cited`.
    - letter_date must parse with `parse_german_date`, amount with
      `parse_german_amount`, and iban must pass `iban_is_valid`.
    - every explanation claim must cite existing lines
      (field names "explanation[0]", "explanation[1]", ...).
    - each deadline goes through `deadlines.resolve` with the letter date.
      If that raises ValueError, or the letter date didn't parse, add an Issue
      for "deadlines[i]" and leave that deadline out.
    Fields with problems still stay in `extraction`; the Issues say which ones
    the UI must show as "Couldn't verify".
    """
    issues: list[Issue] = []

    for name in ["sender", "letter_date", "amount", "reference", "iban"]:
        cited = getattr(extraction, name)
        if cited is not None:
            issues += check_cited(name, cited, transcript)

    letter_date = None
    try:
        letter_date = parse_german_date(extraction.letter_date.value)
    except ValueError:
        issues.append(Issue(field="letter_date", problem=f"can't read {extraction.letter_date.value!r} as a date"))

    if extraction.amount is not None:
        try:
            parse_german_amount(extraction.amount.value)
        except ValueError:
            issues.append(Issue(field="amount", problem=f"can't read {extraction.amount.value!r} as an amount"))

    if extraction.iban is not None and not iban_is_valid(extraction.iban.value):
        issues.append(Issue(field="iban", problem="IBAN checksum fails"))

    for i, claim in enumerate(extraction.explanation):
        missing = missing_lines(claim.lines, transcript)
        if missing:
            issues.append(Issue(field=f"explanation[{i}]", problem=f"cites missing lines {missing}"))

    resolved = []
    for i, raw in enumerate(extraction.deadlines):
        if letter_date is None:
            issues.append(Issue(field=f"deadlines[{i}]", problem="letter date unknown, can't compute the deadline"))
            continue
        try:
            resolved.append(resolve(raw, letter_date))
        except ValueError as error:
            issues.append(Issue(field=f"deadlines[{i}]", problem=str(error)))

    return ValidatedResult(extraction=extraction, deadlines=resolved, unsure=issues)
