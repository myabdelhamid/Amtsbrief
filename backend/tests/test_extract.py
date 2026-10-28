"""Step 3 exercise: make these pass by filling in pipeline/extract.py. No model calls.

Run:  uv run pytest backend/tests/test_extract.py -v
Tip:  work top to bottom. `extract` itself has no tests here: the eval checks it.
"""
from pipeline import extract
from pipeline.schemas import Cited, Claim, Issue, Transcript

from test_validate import TRANSCRIPT, extraction


# ---------- 1. to_transcript ----------

def test_numbers_lines_from_one_on_page_one():
    assert extract.to_transcript(["Foo", "Bar"]) == Transcript(lines={"P1-L1": "Foo", "P1-L2": "Bar"})


def test_tenth_line_is_l10():
    transcript = extract.to_transcript([f"line {n}" for n in range(1, 11)])
    assert transcript.lines["P1-L10"] == "line 10"


def test_no_lines_gives_empty_transcript():
    assert extract.to_transcript([]) == Transcript(lines={})


def test_page_number_goes_into_the_id():
    assert extract.to_transcript(["Foo"], page=2) == Transcript(lines={"P2-L1": "Foo"})


def test_join_pages_restarts_line_numbers_on_each_page():
    transcript = extract.join_pages([["Foo", "Bar"], ["Baz"]])
    assert transcript == Transcript(lines={"P1-L1": "Foo", "P1-L2": "Bar", "P2-L1": "Baz"})
    assert list(transcript.lines) == ["P1-L1", "P1-L2", "P2-L1"]  # reading order is kept


# ---------- 2. format_transcript and format_feedback ----------

def test_formats_one_id_and_text_per_line():
    transcript = Transcript(lines={"P1-L1": "Foo", "P1-L2": "Bar"})
    assert extract.format_transcript(transcript) == "P1-L1: Foo\nP1-L2: Bar"


def test_formats_one_issue():
    issues = [Issue(field="iban", problem="IBAN checksum fails")]
    assert extract.format_feedback(issues) == "- iban: IBAN checksum fails"


def test_formats_several_issues_one_per_line():
    issues = [Issue(field="iban", problem="IBAN checksum fails"),
              Issue(field="deadlines[0]", problem="relative deadline needs amount, unit and anchor")]
    assert extract.format_feedback(issues) == (
        "- iban: IBAN checksum fails\n"
        "- deadlines[0]: relative deadline needs amount, unit and anchor"
    )


# ---------- 3. build_prompt ----------

def test_prompt_starts_with_instructions_and_contains_transcript():
    prompt = extract.build_prompt(TRANSCRIPT)
    assert prompt.startswith(extract.EXTRACT_PROMPT)
    assert extract.format_transcript(TRANSCRIPT) in prompt


def test_prompt_without_issues_has_no_feedback():
    assert extract.build_prompt(TRANSCRIPT, None) == extract.build_prompt(TRANSCRIPT, [])
    assert "- iban:" not in extract.build_prompt(TRANSCRIPT)


def test_prompt_with_issues_contains_feedback_after_transcript():
    issues = [Issue(field="iban", problem="IBAN checksum fails")]
    prompt = extract.build_prompt(TRANSCRIPT, issues)
    feedback = extract.format_feedback(issues)
    assert feedback in prompt
    assert prompt.index(feedback) > prompt.index(extract.format_transcript(TRANSCRIPT))


# ---------- 4. extract_and_validate (with a fake model) ----------

BAD_IBAN = Cited(value="DE88 3704 0044 0532 0130 00", quote="DE88 3704 0044 0532 0130 00", lines=["P1-L5"])


def fake_model(monkeypatch, answers):
    """Replace `extract` so each call returns the next extraction from `answers`.

    Returns the list of `issues` arguments the fake was called with, one per call.
    """
    calls = []

    def fake_extract(client, transcript, issues=None):
        calls.append(issues)
        return answers[len(calls) - 1]

    monkeypatch.setattr(extract, "extract", fake_extract)
    return calls


def test_correct_first_answer_needs_no_retry(monkeypatch):
    calls = fake_model(monkeypatch, [extraction()])
    result = extract.extract_and_validate(None, TRANSCRIPT)
    assert len(calls) == 1
    assert result.unsure == []
    assert result.retried is False


def test_retry_gets_the_issues_and_can_fix_them(monkeypatch):
    calls = fake_model(monkeypatch, [extraction(iban=BAD_IBAN), extraction()])
    result = extract.extract_and_validate(None, TRANSCRIPT)
    assert len(calls) == 2
    assert calls[0] is None or calls[0] == []
    assert [issue.field for issue in calls[1]] == ["iban"]
    assert result.unsure == []
    assert result.retried is True


def test_retries_only_once(monkeypatch):
    calls = fake_model(monkeypatch, [extraction(iban=BAD_IBAN), extraction(iban=BAD_IBAN)])
    result = extract.extract_and_validate(None, TRANSCRIPT)
    assert len(calls) == 2
    assert [issue.field for issue in result.unsure] == ["iban"]
    assert result.retried is True


# A letter that itself prints an IBAN failing the checksum (like the real ho_04 sample).
PRINTED_BAD = Transcript(lines={**TRANSCRIPT.lines, "P1-L5": "IBAN: DE88 3704 0044 0532 0130 00"})


def test_iban_printed_wrong_in_the_letter_is_not_retried(monkeypatch):
    calls = fake_model(monkeypatch, [extraction(iban=BAD_IBAN)])
    result = extract.extract_and_validate(None, PRINTED_BAD)
    assert len(calls) == 1
    assert [issue.field for issue in result.unsure] == ["iban"]
    assert result.extraction.iban == BAD_IBAN
    assert result.retried is False


def test_feedback_leaves_out_issues_a_retry_cant_fix(monkeypatch):
    bad_claim = [Claim(text="You were fined 35 euros.", lines=["P3-L1"])]
    calls = fake_model(monkeypatch, [extraction(iban=BAD_IBAN, explanation=bad_claim),
                                     extraction(iban=BAD_IBAN)])
    result = extract.extract_and_validate(None, PRINTED_BAD)
    assert [issue.field for issue in calls[1]] == ["explanation[0]"]
    assert [issue.field for issue in result.unsure] == ["iban"]


def test_flagged_field_dropped_by_the_retry_is_kept_as_unverified(monkeypatch):
    calls = fake_model(monkeypatch, [extraction(iban=BAD_IBAN), extraction(iban=None)])
    result = extract.extract_and_validate(None, TRANSCRIPT)
    assert len(calls) == 2
    assert result.extraction.iban == BAD_IBAN
    assert [issue.field for issue in result.unsure] == ["iban"]
