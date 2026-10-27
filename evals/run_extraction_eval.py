"""Extraction eval: extract + validate each letter, then score the fields against the ground truth.

Needs the transcription cache (run evals/run_transcription_eval.py first).
Results are cached in evals/results/extraction/<stem>.json, so re-runs are free.

Run from the project root:
    uv run python evals/run_extraction_eval.py           # all letters
    uv run python evals/run_extraction_eval.py fi_01     # only the letters you name
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from google import genai

# Running a script puts only its own folder (evals/) on the import path, so add the
# project root (for `evals.`) and backend/ (for `pipeline.`). Paths are relative to the
# project root, which is where this script must be run from anyway.
sys.path[:0] = ["backend", "."]

from pipeline.deadlines import parse_german_date  # noqa: E402
from pipeline.extract import extract_and_validate, to_transcript  # noqa: E402
from pipeline.schemas import Cited, ValidatedResult  # noqa: E402
from pipeline.validate import parse_german_amount  # noqa: E402

from evals.run_transcription_eval import DATA_DIR, RESULTS_DIR, normalize, parse_lines, percent  # noqa: E402

CACHE_DIR = RESULTS_DIR / "extraction"
FIELDS = ["letter_type", "sender", "letter_date", "amount", "reference", "iban", "deadlines"]


# ---------- Comparing one field ----------

def same_text(cited: Cited | None, expected: str | None) -> bool:
    """Equal after collapsing whitespace and treating – and - as the same. Both missing counts as equal."""
    if cited is None or expected is None:
        return cited is None and expected is None
    return normalize(" ".join(cited.value.split())) == normalize(" ".join(expected.split()))


def same_date(cited: Cited, expected: str) -> bool:
    """The cited German date ('02.10.2026') is the expected ISO date ('2026-10-02')."""
    try:
        return parse_german_date(cited.value) == date.fromisoformat(expected)
    except ValueError:
        return False


def same_amount(cited: Cited | None, expected: str | None) -> bool:
    """Same amount of money, however it is written. Both missing counts as equal."""
    if cited is None or expected is None:
        return cited is None and expected is None
    try:
        return parse_german_amount(cited.value) == parse_german_amount(expected)
    except ValueError:
        return False


def same_iban(cited: Cited | None, expected: str | None) -> bool:
    """Same IBAN, ignoring spaces and case. Both missing counts as equal."""
    if cited is None or expected is None:
        return cited is None and expected is None
    return cited.value.replace(" ", "").upper() == expected.replace(" ", "").upper()


def score_fields(result: ValidatedResult, truth: dict) -> dict[str, bool]:
    """For each field in FIELDS: did the extraction get it right?

    deadlines: the set of (is_payment, date) pairs computed by validate(), so a deadline only
               counts if the model read it right AND the code could compute it.
    """
    ex = result.extraction
    deadlines = {(d.is_payment, d.date.isoformat()) for d in result.deadlines}
    return {
        "letter_type": ex.letter_type.value == truth["letter_type"],
        "sender": same_text(ex.sender, truth["sender"]),
        "letter_date": same_date(ex.letter_date, truth["letter_date"]),
        "amount": same_amount(ex.amount, truth["amount"]),
        "reference": same_text(ex.reference, truth["reference"]),
        "iban": same_iban(ex.iban, truth["iban"]),
        "deadlines": deadlines == {(d["is_payment"], d["expected"]) for d in truth["deadlines"]},
    }


# ---------- Running ----------

def load_or_extract(client: genai.Client, stem: str) -> ValidatedResult:
    """The cached result for this letter, or a new extraction (1-2 model calls) that gets cached."""
    cache_path = CACHE_DIR / f"{stem}.json"
    if cache_path.exists():
        return ValidatedResult.model_validate_json(cache_path.read_text())
    transcription_path = RESULTS_DIR / f"{stem}.txt"
    if not transcription_path.exists():
        raise FileNotFoundError(f"No transcription for {stem}. Run evals/run_transcription_eval.py first.")
    print(f"{stem}: calling model...")
    transcript = to_transcript(parse_lines(transcription_path.read_text()))
    result = extract_and_validate(client, transcript)
    cache_path.write_text(result.model_dump_json(indent=2))
    time.sleep(5)
    return result


if __name__ == "__main__":
    stems = sys.argv[1:] or sorted(path.stem for path in DATA_DIR.glob("*.jpg"))
    if not stems:
        raise FileNotFoundError(f"No .jpg files in {DATA_DIR.resolve()}. Run this script from the project root.")
    load_dotenv()
    client = genai.Client()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    correct = {field: 0 for field in FIELDS}
    verified = retried = 0
    for stem in stems:
        result = load_or_extract(client, stem)
        truth = json.loads((DATA_DIR / f"{stem}.json").read_text())
        scores = score_fields(result, truth)
        for field, ok in scores.items():
            correct[field] += ok
        verified += not result.unsure
        retried += result.retried

        wrong = [field for field, ok in scores.items() if not ok]
        line = f"{stem}: {sum(scores.values())}/{len(FIELDS)} fields"
        if wrong:
            line += f", wrong: {', '.join(wrong)}"
        if result.unsure:
            line += f", couldn't verify: {', '.join(issue.field for issue in result.unsure)}"
        if result.retried:
            line += " (retried)"
        print(line)

    n = len(stems)
    print()
    for field in FIELDS:
        print(f"{field:12} {correct[field]}/{n} ({percent(correct[field], n):.1f}%)")
    all_correct = sum(correct.values())
    print(f"{'overall':12} {all_correct}/{n * len(FIELDS)} ({percent(all_correct, n * len(FIELDS)):.1f}%)")
    print(f"fully verified: {verified}/{n}, retried: {retried}/{n}")
