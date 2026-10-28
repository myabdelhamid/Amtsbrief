"""Step 2 exercise: make these pass by filling in pipeline/validate.py.

Run:  uv run pytest backend/tests/test_validate.py -v
Tip:  work top to bottom. Each section only needs the functions above it.
"""
from datetime import date
from decimal import Decimal

import pytest

from pipeline import validate
from pipeline.schemas import Cited, Claim, Extraction, RawDeadline, Transcript


# ---------- 1. parse_german_amount ----------

def test_parses_amount_with_cents():
    assert validate.parse_german_amount("35,00 €") == Decimal("35.00")


def test_parses_amount_with_thousands_separator():
    assert validate.parse_german_amount("Betrag: 1.234,56 €") == Decimal("1234.56")


def test_parses_amount_without_cents():
    assert validate.parse_german_amount("412 €") == Decimal("412")


def test_rejects_text_without_an_amount():
    with pytest.raises(ValueError):
        validate.parse_german_amount("Kein Betrag")


# ---------- 2. iban_is_valid ----------

def test_accepts_valid_iban_with_spaces():
    assert validate.iban_is_valid("DE89 3704 0044 0532 0130 00")


def test_accepts_valid_iban_without_spaces():
    assert validate.iban_is_valid("DE89370400440532013000")


def test_rejects_iban_with_one_wrong_digit():
    assert not validate.iban_is_valid("DE88 3704 0044 0532 0130 00")


def test_rejects_text_that_is_not_an_iban():
    assert not validate.iban_is_valid("keine IBAN")
    assert not validate.iban_is_valid("")


# ---------- 3. quote_matches ----------

LINE = "Bitte zahlen Sie 35,00 € innerhalb einer Woche."


def test_exact_substring_matches():
    assert validate.quote_matches("35,00 €", LINE)


def test_one_ocr_typo_in_a_long_quote_matches():
    assert validate.quote_matches("innerhalb einer Woche", LINE.replace("einer", "elner"))


def test_dash_difference_matches():
    assert validate.quote_matches("Musterstadt - Bürgeramt", "Bezirksamt Musterstadt – Bürgeramt")


def test_one_wrong_digit_in_an_amount_does_not_match():
    assert not validate.quote_matches("36,00 €", LINE)


def test_unrelated_quote_does_not_match():
    assert not validate.quote_matches("Mahnung", LINE)


# ---------- 4. missing_lines and check_cited ----------

TRANSCRIPT = Transcript(lines={
    "P1-L1": "Ordnungsamt Musterstadt",
    "P1-L2": "Musterstadt, den 02.10.2026",
    "P1-L3": "Aktenzeichen: 5512 0099 1234",
    "P1-L4": "Bitte zahlen Sie 35,00 € innerhalb einer Woche.",
    "P1-L5": "IBAN: DE89 3704 0044 0532 0130 00",
})


def test_no_missing_lines():
    assert validate.missing_lines(["P1-L1", "P1-L4"], TRANSCRIPT) == []


def test_reports_missing_lines_in_order():
    assert validate.missing_lines(["P1-L9", "P1-L1", "P2-L1"], TRANSCRIPT) == ["P1-L9", "P2-L1"]


def test_correct_citation_has_no_issues():
    cited = Cited(value="35,00 €", quote="zahlen Sie 35,00 €", lines=["P1-L4"])
    assert validate.check_cited("amount", cited, TRANSCRIPT) == []


def test_citation_of_missing_line_is_an_issue():
    cited = Cited(value="35,00 €", quote="zahlen Sie 35,00 €", lines=["P1-L9"])
    issues = validate.check_cited("amount", cited, TRANSCRIPT)
    assert len(issues) == 1
    assert issues[0].field == "amount"


def test_quote_not_in_cited_line_is_an_issue():
    cited = Cited(value="35,00 €", quote="zahlen Sie 35,00 €", lines=["P1-L1"])
    issues = validate.check_cited("amount", cited, TRANSCRIPT)
    assert len(issues) == 1
    assert issues[0].field == "amount"


def test_value_not_in_quote_is_an_issue():
    cited = Cited(value="45,00 €", quote="zahlen Sie 35,00 €", lines=["P1-L4"])
    issues = validate.check_cited("amount", cited, TRANSCRIPT)
    assert len(issues) == 1
    assert issues[0].field == "amount"


def test_quote_can_span_two_cited_lines():
    cited = Cited(value="Musterstadt", quote="Ordnungsamt Musterstadt Musterstadt, den", lines=["P1-L1", "P1-L2"])
    assert validate.check_cited("sender", cited, TRANSCRIPT) == []


# ---------- 5. validate ----------

def extraction(**overrides) -> Extraction:
    """A correct extraction of TRANSCRIPT. Pass keyword arguments to break one field."""
    fields = dict(
        letter_type="fine",
        sender=Cited(value="Ordnungsamt Musterstadt", quote="Ordnungsamt Musterstadt", lines=["P1-L1"]),
        letter_date=Cited(value="02.10.2026", quote="den 02.10.2026", lines=["P1-L2"]),
        amount=Cited(value="35,00 €", quote="zahlen Sie 35,00 €", lines=["P1-L4"]),
        reference=Cited(value="5512 0099 1234", quote="Aktenzeichen: 5512 0099 1234", lines=["P1-L3"]),
        iban=Cited(value="DE89 3704 0044 0532 0130 00", quote="IBAN: DE89 3704 0044 0532 0130 00", lines=["P1-L5"]),
        deadlines=[RawDeadline(phrase="innerhalb einer Woche", kind="relative", amount=1, unit="weeks",
                               anchor="letter_date", summary="Pay the 35,00 € fine.", purpose="payment",
                               lines=["P1-L4"])],
        explanation=[Claim(text="You were fined 35 euros.", lines=["P1-L4"])],
    )
    fields.update(overrides)
    return Extraction(**fields)


def fields_with_issues(result) -> list[str]:
    return sorted(issue.field for issue in result.unsure)


def test_correct_extraction_has_no_issues_and_resolves_the_deadline():
    result = validate.validate(extraction(), TRANSCRIPT)
    assert result.unsure == []
    assert [d.date for d in result.deadlines] == [date(2026, 10, 9)]


def test_invalid_iban_is_an_issue():
    bad = Cited(value="DE88 3704 0044 0532 0130 00", quote="DE88 3704 0044 0532 0130 00", lines=["P1-L5"])
    result = validate.validate(extraction(iban=bad), TRANSCRIPT)
    assert "iban" in fields_with_issues(result)


def test_letter_without_iban_is_fine():
    result = validate.validate(extraction(iban=None), TRANSCRIPT)
    assert result.unsure == []


def test_explanation_citing_missing_line_is_an_issue():
    claim = Claim(text="You were fined 35 euros.", lines=["P3-L1"])
    result = validate.validate(extraction(explanation=[claim]), TRANSCRIPT)
    assert fields_with_issues(result) == ["explanation[0]"]


def test_deadline_that_cannot_be_resolved_is_left_out():
    broken = RawDeadline(phrase="innerhalb einer Woche", kind="relative", amount=1,
                         summary="Pay the fine.", purpose="payment", lines=["P1-L4"])
    result = validate.validate(extraction(deadlines=[broken]), TRANSCRIPT)
    assert fields_with_issues(result) == ["deadlines[0]"]
    assert result.deadlines == []


def test_unparseable_letter_date_blocks_deadlines():
    transcript = Transcript(lines={**TRANSCRIPT.lines, "P1-L2": "Musterstadt, den zweiten Oktober"})
    letter_date = Cited(value="zweiten Oktober", quote="den zweiten Oktober", lines=["P1-L2"])
    result = validate.validate(extraction(letter_date=letter_date), transcript)
    assert fields_with_issues(result) == ["deadlines[0]", "letter_date"]
    assert result.deadlines == []


def test_resolved_deadline_keeps_summary_and_purpose():
    [deadline] = validate.validate(extraction(), TRANSCRIPT).deadlines
    assert deadline.summary == "Pay the 35,00 € fine."
    assert deadline.purpose == "payment"


def test_deadline_counted_from_an_undated_event_is_an_issue():
    after_final = RawDeadline(phrase="zwei Wochen nach Rechtskraft", kind="relative", amount=2, unit="weeks",
                              anchor="other", summary="Pay the fine.", purpose="payment", lines=["P1-L4"])
    result = validate.validate(extraction(deadlines=[after_final]), TRANSCRIPT)
    assert fields_with_issues(result) == ["deadlines[0]"]
    assert result.deadlines == []

def test_invalid_iban_printed_in_the_letter_is_not_retried():
    transcript = Transcript(lines={**TRANSCRIPT.lines, "P1-L5": "IBAN: DE88 3704 0044 0532 0130 00"})
    printed = Cited(value="DE88 3704 0044 0532 0130 00", quote="IBAN: DE88 3704 0044 0532 0130 00", lines=["P1-L5"])
    [issue] = validate.validate(extraction(iban=printed), transcript).unsure
    assert issue.field == "iban"
    assert issue.retry is False


def test_invalid_iban_the_model_mistyped_is_retried():
    mistyped = Cited(value="DE88 3704 0044 0532 0130 00", quote="DE88 3704 0044 0532 0130 00", lines=["P1-L5"])
    [issue] = validate.validate(extraction(iban=mistyped), TRANSCRIPT).unsure
    assert issue.retry is True


def test_undated_event_is_not_retried_but_missing_fields_are():
    after_final = RawDeadline(phrase="zwei Wochen nach Rechtskraft", kind="relative", amount=2, unit="weeks",
                              anchor="other", summary="Pay the fine.", purpose="payment", lines=["P1-L4"])
    incomplete = RawDeadline(phrase="innerhalb einer Woche", kind="relative", amount=1,
                             summary="Pay the fine.", purpose="payment", lines=["P1-L4"])
    result = validate.validate(extraction(deadlines=[after_final, incomplete]), TRANSCRIPT)
    assert [(issue.field, issue.retry) for issue in result.unsure] == [("deadlines[0]", False), ("deadlines[1]", True)]
