"""Tests for the transcription eval helpers. No model calls.

Run:  uv run pytest backend/tests/test_eval_helpers.py -v
"""
from pipeline.transcribe import parse_lines

from evals.run_transcription_eval import normalize, percent, score_letter


# ---------- 1. percent ----------

def test_percent_of_part_and_whole():
    assert percent(9, 12) == 75.0


def test_percent_of_zero_lines_is_zero():
    assert percent(0, 0) == 0.0


# ---------- 2. normalize ----------

def test_en_dash_becomes_hyphen():
    assert normalize("a – b") == "a - b"


def test_hyphen_stays_hyphen():
    assert normalize("E-Mail") == "E-Mail"


def test_text_without_dash_is_unchanged():
    assert normalize("Ordnungsamt Musterstadt") == "Ordnungsamt Musterstadt"


# ---------- 3. score_letter: returns (exact, normalized, total) ----------

def test_dash_difference_counts_only_when_normalized():
    assert score_letter(["a - b"], ["a – b"]) == (0, 1, 1)


def test_correct_hyphen_stays_correct():
    assert score_letter(["E-Mail"], ["E-Mail"]) == (1, 1, 1)


def test_correct_en_dash_stays_correct():
    assert score_letter(["a – b"], ["a – b"]) == (1, 1, 1)


def test_missing_line_counts_in_total():
    assert score_letter(["a", "b"], ["a", "b", "c"]) == (2, 2, 3)


def test_extra_line_counts_in_total():
    assert score_letter(["a", "b", "c", "d"], ["a", "b", "c"]) == (3, 3, 4)


def test_empty_letter_scores_zero_of_zero():
    assert score_letter([], []) == (0, 0, 0)


# ---------- 4. parse_lines ----------

def test_strips_line_prefixes():
    assert parse_lines("L1: Foo\nL2: Bar") == ["Foo", "Bar"]


def test_keeps_colon_inside_the_text():
    assert parse_lines("L7: Betreff: Mahnung") == ["Betreff: Mahnung"]


def test_keeps_line_without_prefix_whole():
    assert parse_lines("Betreff: Mahnung") == ["Betreff: Mahnung"]


def test_strips_prefix_without_space():
    assert parse_lines("L5:Foo") == ["Foo"]


def test_ignores_prefix_in_the_middle_of_a_line():
    assert parse_lines("Text with L5: inside") == ["Text with L5: inside"]


def test_drops_empty_lines():
    assert parse_lines("L1: Foo\n\n   \nL5:\nL6: Bar") == ["Foo", "Bar"]
