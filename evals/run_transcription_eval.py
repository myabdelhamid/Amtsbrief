import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Running a script puts only its own folder (evals/) on the import path, so add backend/.
sys.path.insert(0, "backend")

from pipeline.transcribe import parse_lines, transcribe  # noqa: E402

DATA_DIR = Path("evals/data")
RESULTS_DIR = Path("evals/results")


def load_ground_truth(stem: str) -> list[str]:
    """Return the non-empty reference lines from evals/data/<stem>.json."""
    path = DATA_DIR / f"{stem}.json"
    data = json.loads(path.read_text())
    return [line for line in data["lines"] if line != ""]


def normalize(line: str) -> str:
    """Make formatting-only differences equal: en dash becomes hyphen."""
    return line.replace("–", "-")


def score_letter(predicted: list[str], expected: list[str]) -> tuple[int, int, int]:
    """Return (exact matches, normalized matches, total), where total is the longer list's length."""
    exact = 0
    normalized = 0
    for got, want in zip(predicted, expected):
        if got == want:
            exact += 1
        if normalize(got) == normalize(want):
            normalized += 1
    total = max(len(predicted), len(expected))
    return exact, normalized, total


def percent(part: int, whole: int) -> float:
    """part / whole as a percentage, 0.0 when whole is 0."""
    if whole == 0:
        return 0.0
    return part / whole * 100


if __name__ == "__main__":
    images = sorted(DATA_DIR.glob("*.jpg"))
    if not images:
        raise FileNotFoundError(
            f"No .jpg files in {DATA_DIR.resolve()}. Run this script from the project root."
        )
    load_dotenv()
    client = genai.Client(http_options=types.HttpOptions(timeout=120_000))  # ms; a hung call fails instead of waiting forever
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    total_exact = total_normalized = total_lines = 0
    for path in images:
        cache_path = RESULTS_DIR / f"{path.stem}.txt"
        if cache_path.exists():
            raw_text = cache_path.read_text()
        else:
            print(f"{path.stem}: calling model...")
            raw_text = transcribe(client, path.read_bytes())
            cache_path.write_text(raw_text)
            time.sleep(5)
        results[path.stem] = parse_lines(raw_text)
        exact, normalized, total = score_letter(results[path.stem], load_ground_truth(path.stem))
        print(
            f"{path.stem}: exact {exact}/{total} ({percent(exact, total):.1f}%), "
            f"normalized {normalized}/{total} ({percent(normalized, total):.1f}%)"
        )
        total_exact += exact
        total_normalized += normalized
        total_lines += total
    print(
        f"overall: exact {total_exact}/{total_lines} ({percent(total_exact, total_lines):.1f}%), "
        f"normalized {total_normalized}/{total_lines} ({percent(total_normalized, total_lines):.1f}%)"
    )
