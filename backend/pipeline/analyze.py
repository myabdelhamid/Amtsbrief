"""One uploaded file -> everything the results page shows. Chains the pipeline steps.

    bytes -> preprocess.load_pages -> transcribe (one call per page, in parallel)
          -> parse_lines -> extract.join_pages -> extract_and_validate (1-2 calls)

At most MAX_PAGES + 2 model calls per letter. Raises preprocess.UnsupportedFile for
files it can't read and NoTextFound when the pages have no text (a photo of a cat).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from google import genai

from .extract import extract_and_validate, join_pages
from .preprocess import load_pages
from .schemas import Analysis
from .transcribe import parse_lines, transcribe

PARALLEL_PAGES = 3  # more would hit the trial quota's 429s on long letters


class NoTextFound(ValueError):
    """The file opened fine, but the model found no text on any page."""


def analyze(client: genai.Client, data: bytes) -> Analysis:
    """Transcribe, extract and validate one letter (a PDF or a photo)."""
    pages = load_pages(data)
    with ThreadPoolExecutor(max_workers=PARALLEL_PAGES) as pool:
        # map keeps the input order, so page 2 stays page 2 even if it finishes first
        raw_pages = list(pool.map(lambda image: transcribe(client, image), pages))
    transcript = join_pages([parse_lines(raw) for raw in raw_pages])
    if not transcript.lines:
        raise NoTextFound("no text found on the page(s)")
    return Analysis(transcript=transcript, result=extract_and_validate(client, transcript), pages=len(pages))
