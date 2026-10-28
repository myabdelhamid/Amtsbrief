"""Page image -> numbered lines, with one vision-model call per page.

The model is asked to prefix every line with L1:, L2: ..., and `parse_lines`
strips those prefixes again. Pages are numbered later, by `extract.join_pages`.
"""
from __future__ import annotations

import re

from google import genai
from google.genai import types

from .extract import MODEL

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


def transcribe(client: genai.Client, image_bytes: bytes) -> str:
    """Send one JPEG page to the model and return its raw text answer (L1: ... lines)."""
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
