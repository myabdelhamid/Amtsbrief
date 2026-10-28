import json
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(http_options=types.HttpOptions(timeout=120_000))  # ms; a hung call fails instead of waiting forever

MODEL = "gemini-3.8-flash"
DATA_DIR = Path("evals/data") 
RESULTS_DIR = Path("evals/results")
LINE_PREFIX = re.compile(r"^L\d+:\s*")

TRANSCRIBE_PROMPT = """
You're given a photo of a German letter. Follow these rules exactly:
1. Transcribe the letter exactly as written, in German, with no translation
2. Give one output line per line of text in the letter
3. Each output line must start with L1:, L2: and so on
4. No corrections, no summaries, no extra text before or after
5. If a line is empty, don't output it

Here is an example of how your output should look, between triple backticks:

```
Example 1:
Input:
Berlin, den 17. Oktober 2026

Lieber Thomas,

wie geht es dir? mir geht es sehr gut.
Ich schreibe dir, weil ich bald Geburtstag habe. Ich möchte meinen
Geburtstg am nächsten samstag mit ein paar Freunden feiern. Die Party
findet bei mir zu Hause statt und beginnt um 19:00 Uhr.
Hast du Zeit und Lust zu kommen? Sag mir bitte Bescheid, ob du da sein
kannst. Wenn du magst, kannst du auch einen Sala oder etwas zum
Knabbern mitbringen.

Ich würde mich sehr freuen dich bald wiederzusehen!

Viele Grüße
Dein Marwan Abdelhamid

//////////////////////////////////////////////////

Output:
L1: Berlin, den 17. Oktober 2026
L2: Lieber Thomas,
L3: wie geht es dir? mir geht es sehr gut.
L4: Ich schreibe dir, weil ich bald Geburtstag habe. Ich möchte meinen
L5: Geburtstg am nächsten samstag mit ein paar Freunden feiern. Die Party
L6: findet bei mir zu Hause statt und beginnt um 19:00 Uhr.
L7: Hast du Zeit und Lust zu kommen? Sag mir bitte Bescheid, ob du da sein
L8: kannst. Wenn du magst, kannst du auch einen Sala oder etwas zum
L9: Knabbern mitbringen.
L10: Ich würde mich sehr freuen dich bald wiederzusehen!
L11: Viele Grüße
L12: Dein Marwan Abdelhamid
```
"""


def transcribe(image_bytes: bytes) -> str:
    """Send one image to the model and return its raw text answer."""
    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
    response = client.models.generate_content(
        model=MODEL,
        contents=[TRANSCRIBE_PROMPT, image_part],
    )
    return response.text


def parse_lines(text: str) -> list[str]:
    """'L1: Foo\\nL2: Bar' -> ['Foo', 'Bar']. Lines that are empty after the prefix are dropped."""
    lines = []
    for raw in text.splitlines():
        line = LINE_PREFIX.sub("", raw.strip())
        if line:
            lines.append(line)
    return lines


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
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    total_exact = total_normalized = total_total = 0
    for path in images:
        cache_path = RESULTS_DIR / f"{path.stem}.txt"
        if cache_path.exists():
            raw_text = cache_path.read_text()
        else:
            print(f"{path.stem}: calling model...")
            raw_text = transcribe(path.read_bytes())
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
        total_total += total
    print(
        f"overall: exact {total_exact}/{total_total} ({percent(total_exact, total_total):.1f}%), "
        f"normalized {total_normalized}/{total_total} ({percent(total_normalized, total_total):.1f}%)"
    )
