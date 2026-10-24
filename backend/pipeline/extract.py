"""Turn a transcript into an `Extraction` with one Gemini call, then check it in code.

STEP 3 EXERCISE: replace each `raise NotImplementedError` with real code
until `uv run pytest backend/tests/test_extract.py -v` is all green.
Work top to bottom. Ask Claude for a hint, not the answer, when stuck.

The flow:  lines -> Transcript -> prompt -> Gemini (JSON shaped like Extraction)
           -> validate() -> if anything failed, ONE retry with the problems as
           feedback -> validate() again -> ValidatedResult.
`extract` is the only function that calls the model. Everything else is plain
code, so the tests run without API calls.
"""
from __future__ import annotations

from google import genai
from google.genai import types

from .schemas import Extraction, Issue, Transcript, ValidatedResult
from .validate import validate

MODEL = "gemini-3.8-flash"

# TODO (yours to write): the instructions for the model. The transcript and any
# feedback are added after this text by `build_prompt`, so don't include them here.
# Things the model must be told, at least:
# - it gets a German letter as numbered lines ("P1-L4: ...") and must fill the JSON schema
# - every `value` is copied exactly as written in the letter, never reformatted
#   (dates stay "02.10.2026", amounts stay "35,00 €")
# - every `quote` is copied verbatim from the cited lines, and every `lines` list
#   uses the IDs exactly as given ("P1-L4"), never invented ones
# - it must NOT compute deadline dates: fill RawDeadline from the wording only
#   (absolute: date_text; relative: amount, unit, anchor)
# - "nach Bekanntgabe / Zugang / Zustellung" means anchor = "receipt"
# - an appointment date (Termin) is not a deadline
# - leave amount, reference and iban empty when the letter doesn't contain them
# - summaries and explanation claims are short, plain English, for a non-German speaker
EXTRACT_PROMPT = """
    You'll get a German letter as numbered lines ("P1-L4: ..."), you must fill the JSON schema.
    Every `value` is copied exactly as written in the letter, never reform them (dates stay "02.10.2026", amounts stay "35,00 €")
    Every `quote` is copied verbatim from the cited lines, and every `lines` list uses the IDs exactly as given ("P1-L4"), never invent them.
    You must NOT compute deadline dates: fill RawDeadline from the wording only (absolute: date_text; relative: amount, unit, anchor)
    "nach Bekanntgabe / Zugang / Zustellung" means anchor = "receipt"
    An appointment date (Termin) is not a deadline
    Leave amount, reference and iban empty when the letter doesn't contain them
    Summaries and explanation claims are short, for a non-German speaker use plain English
"""


def to_transcript(lines: list[str]) -> Transcript:
    """['Foo', 'Bar'] -> Transcript(lines={'P1-L1': 'Foo', 'P1-L2': 'Bar'}).

    Every letter is one page for now, so the page is always P1.
    Line numbers start at 1, like the L1:, L2: prefixes the transcription uses.
    """
    numbered = {}
    for n, text in enumerate(lines, start=1):
        numbered[f"P1-L{n}"] = text
    return Transcript(lines=numbered)


def format_transcript(transcript: Transcript) -> str:
    """The transcript as the model will see it: one 'ID: text' per line.

    Transcript(lines={'P1-L1': 'Foo', 'P1-L2': 'Bar'}) -> 'P1-L1: Foo\\nP1-L2: Bar'
    """
    return "\n".join(f"{line_id}: {text}" for line_id, text in transcript.lines.items())


def format_feedback(issues: list[Issue]) -> str:
    """The problems from validate(), as a bulleted list for the retry prompt.

    [Issue(field='iban', problem='IBAN checksum fails')] -> '- iban: IBAN checksum fails'
    One line per issue, joined with '\\n'.
    """
    return "\n".join(f"- {issue.field}: {issue.problem}" for issue in issues)


def build_prompt(transcript: Transcript, issues: list[Issue] | None = None) -> str:
    """EXTRACT_PROMPT, then the formatted transcript, then the feedback if there is any.

    Without issues (None or an empty list) the prompt has no feedback part at all.
    With issues, add a short sentence telling the model its previous answer had these
    problems and to fix them, followed by `format_feedback(issues)`.
    """
    issues_text = ""
    if issues:
        issues_text = f"\n\nYour previous answer had these problems. Fix them:\n{format_feedback(issues)}"
    return f"{EXTRACT_PROMPT}\n\n Transcript: {format_transcript(transcript)}{issues_text}"


def extract(client: genai.Client, transcript: Transcript, issues: list[Issue] | None = None) -> Extraction:
    """Ask Gemini to fill `Extraction` for this transcript. The only function here that costs money.

    Pass a config to `client.models.generate_content` that asks for JSON shaped like
    `Extraction`: types.GenerateContentConfig(response_mime_type=..., response_schema=...).
    Then turn `response.text` into an Extraction with `Extraction.model_validate_json`,
    which also checks the shape and raises if the model returned something else.
    Not unit-tested: check it with the eval on one letter.
    """
    prompt_string = build_prompt(transcript, issues)
    response = client.models.generate_content(
        model = MODEL,
        contents = prompt_string,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Extraction
        )
    )
    return Extraction.model_validate_json(response.text)


def extract_and_validate(client: genai.Client, transcript: Transcript) -> ValidatedResult:
    """Extract, validate, and retry ONCE if validate() found problems.

    1. extract, then validate.
    2. If the result has no issues, return it.
    3. Otherwise extract again with those issues as feedback, validate the new
       extraction, and return that result with `retried` set to True.
    Never more than two model calls per letter.
    """
    extraction = extract(client, transcript)
    validation_result = validate(extraction, transcript)
    if validation_result.unsure:
        extraction = extract(client, transcript, validation_result.unsure)
        validation_result = validate(extraction, transcript)
        validation_result.retried = True
    return validation_result
