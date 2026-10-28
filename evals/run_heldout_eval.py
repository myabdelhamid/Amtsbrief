"""Held-out eval: the letters in evals/private/ that the field definitions were NOT tuned on.

Each PDF is rendered page by page, each page is transcribed by its own model call,
the pages are joined into one transcript (P1-L1 ... P2-L1 ...), then extracted and
scored with the same fields as run_extraction_eval.py. Ground truth has no `lines`,
so only extraction is scored.

Everything is cached in evals/results/private/ (gitignored, like the letters):
<stem>_p<n>.txt per page, extraction/<stem>.json per letter.

Run from the project root:
    uv run python evals/run_heldout_eval.py            # all held-out letters
    uv run python evals/run_heldout_eval.py ho_04      # only the letters you name
"""
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

sys.path[:0] = ["backend", "."]

from pipeline.extract import join_pages  # noqa: E402
from pipeline.preprocess import load_pages  # noqa: E402
from pipeline.transcribe import parse_lines, transcribe  # noqa: E402

from evals.run_extraction_eval import extract_cached, report  # noqa: E402
from evals.run_transcription_eval import RESULTS_DIR  # noqa: E402

PRIVATE_DIR = Path("evals/private")
CACHE_DIR = RESULTS_DIR / "private"


def transcribe_pages(client: genai.Client, stem: str) -> list[list[str]]:
    """The parsed lines of each page of evals/private/<stem>.pdf, transcribing uncached pages."""
    pages = []
    for n, image in enumerate(load_pages((PRIVATE_DIR / f"{stem}.pdf").read_bytes()), start=1):
        cache_path = CACHE_DIR / f"{stem}_p{n}.txt"
        if cache_path.exists():
            raw_text = cache_path.read_text()
        else:
            print(f"{stem} page {n}: calling model...")
            raw_text = transcribe(client, image)
            cache_path.write_text(raw_text)
            time.sleep(5)
        pages.append(parse_lines(raw_text))
    return pages


if __name__ == "__main__":
    stems = sys.argv[1:] or sorted(path.stem for path in PRIVATE_DIR.glob("ho_*.json"))
    if not stems:
        raise FileNotFoundError(f"No ground truth in {PRIVATE_DIR.resolve()}. Run this script from the project root.")
    load_dotenv()
    client = genai.Client(http_options=types.HttpOptions(timeout=120_000))  # ms; a hung call fails instead of waiting forever
    (CACHE_DIR / "extraction").mkdir(parents=True, exist_ok=True)

    rows = []
    for stem in stems:
        transcript = join_pages(transcribe_pages(client, stem))
        result = extract_cached(client, transcript, CACHE_DIR / "extraction" / f"{stem}.json")
        truth = json.loads((PRIVATE_DIR / f"{stem}.json").read_text())
        rows.append((stem, result, truth))
    report(rows)
