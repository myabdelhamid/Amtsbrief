"""Find text in a letter that is written to an AI instead of to the reader. Plain code, no LLM.

A real letter talks to the person who receives it. A prompt injection talks to the
machine reading it: "Hinweis für die automatische Verarbeitung (KI)", "Ignore all
previous instructions", "--- END OF LETTER ---". Lines like that are flagged so the
app can warn the user and stop trusting any field that cites them.

The hard part is false positives: real letters say "Hinweise", "automatisch",
"System" and even "betrachten Sie dieses Schreiben als gegenstandslos". A flag
on a normal letter would teach users to ignore the warning.
"""
from __future__ import annotations

import re

from .schemas import LineId, Transcript

# Words for the machine reading the letter, or for its instructions. Whole words only
# (\b), so "Kinder" and "Zahlungsanweisung" don't match; \w* allows endings ("Assistenten").
_ADDRESSED_TO_AI = re.compile(
    r"\b(?:AI|KI|LLM|chatbot|Sprachmodell\w*|language model|Assistent\w*|assistant"
    r"|OCR|Texterkennung|Transkription|automatische\w* Verarbeitung"
    r"|ignor\w* (?:all|the|previous|alle|die|den|vorherige)\w*|previous instructions|vorherige\w* Anweisungen)\b",
    re.IGNORECASE,
)

# Fake document structure: "--- END OF LETTER ---", "=== SYSTEM ===", "SYSTEM: ...".
# Case-sensitive on purpose: a real letter may say "System:" but never shouts it.
_FAKE_STRUCTURE = re.compile(r"(?:-{3,}|={3,}|#{2,})\s*(?:END|ENDE|BEGIN|SYSTEM)\b|^\s*(?:SYSTEM|ASSISTANT|USER)\s*:")

# A line that ends a sentence. A flagged line that doesn't continues on the next line.
_SENTENCE_END = re.compile(r"[.!?]\s*$")


def suspicious_lines(transcript: Transcript) -> list[LineId]:
    """The IDs of lines that address an AI, in transcript order. [] for a normal letter.

    An injection can run onto the next line(s), and that line can hold the payload
    (pi_02's fake IBAN is on the line after "Übernehmen Sie als IBAN"). So a flagged
    line that doesn't end a sentence also flags the line after it.
    """
    suspicious = []
    continues = False
    for line_id, text in transcript.lines.items():
        if continues or _ADDRESSED_TO_AI.search(text) or _FAKE_STRUCTURE.search(text):
            suspicious.append(line_id)
            continues = not _SENTENCE_END.search(text)
    return suspicious


# Ways to reach someone or send them money: URLs, email addresses, IBANs, phone numbers.
# A phone number starts with +49 or 0 and has only digits, spaces, / and - after that,
# so dates (01.02.2027) and amounts (0,00 €) don't match.
_CONTACT_DETAILS = re.compile(
    r"https?://\S+|www\.\S+"
    r"|[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
    r"|\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b"
    r"|(?:\+49|\b0)\d[\d /-]{5,}\d"
)


def _compact(text: str) -> str:
    """Only letters and digits, lowercased: 'DE89 3704' and 'de893704' compare equal."""
    return re.sub(r"[\W_]", "", text).lower()


def unsourced_details(text: str, transcript: Transcript, suspicious: list[LineId]) -> list[str]:
    """Contact details in the model's own words that no trusted line of the letter contains.

    The model may repeat a number or IBAN printed in the letter ("Pay into DE89 ..."), but
    not one it made up or took from a suspicious line (pi_05's premium-rate number).
    Lines are joined before comparing, so an IBAN that wraps onto the next line still counts.
    """
    trusted = _compact(" ".join(line for line_id, line in transcript.lines.items() if line_id not in suspicious))
    return [match.group() for match in _CONTACT_DETAILS.finditer(text) if _compact(match.group()) not in trusted]