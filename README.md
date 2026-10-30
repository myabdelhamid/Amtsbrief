# Amtsbrief

Amtsbrief explains German official letters (Finanzamt, Bürgeramt, Krankenkasse, landlord, fines)
in plain English. You upload a photo or PDF, and it finds the amounts and deadlines, shows the
line in the letter that each claim comes from, and puts the deadlines in your calendar.

It's built around one rule: **the model's output is never shown as fact until code has checked it
against the letter.**

## How it works

```
upload ─▶ preprocess ─▶ transcribe ─▶ extract ─▶ validate ─▶ store + calendar
          (pages)       (vision LLM,   (LLM fills   (plain code)
                         numbered       a schema,
                         lines)         cites lines)
```

1. **Preprocess** (`backend/pipeline/preprocess.py`): PDFs (digital or scanned), JPEG, PNG,
   WebP and HEIC become one JPEG per page. EXIF is removed, so GPS data never leaves the server.
   PDFs are rendered as images and their text layer is ignored, so it can't differ from what a
   person sees.
2. **Transcribe** (`transcribe.py`): Gemini copies each page line by line as `L1: …`. Pages are
   joined as `P1-L1`, `P2-L1`, …
3. **Extract** (`extract.py`): a second call fills a Pydantic schema. Every field carries a
   verbatim quote and the line IDs it came from.
4. **Validate** (`validate.py`, plain code):
   - cited lines exist
   - quotes match the lines (fuzzy, ≥ 0.9)
   - dates and amounts parse
   - IBAN checksums pass

   A failed check gets one retry with specific feedback. Anything still failing goes to
   **"Couldn't verify"** instead of being shown.
5. **Deadlines** (`deadlines.py`): the model only extracts the wording ("innerhalb eines Monats
   nach Bekanntgabe"). Code computes the date, showing each step:
   - the 4-day receipt rule
   - month-end clamping
   - start or end of a calendar period
   - the weekend shift

   Wording the code can't compute is never guessed.

### Design decisions

- **Transcription and extraction are separate calls.** This lets every claim cite transcript
  lines, and lets code verify those citations.
- **The LLM never does date math.** Legal deadlines have rules, and code applies them the same
  way every time.
- **No tools, no actions.** The app informs and reminds; what to do about a letter is the
  user's decision. The model can only fill a schema.

## Prompt-injection defenses

A letter is untrusted input: anyone can print "ignore your instructions" on one. Six attack
letters, based on published attacks (indirect injection, hidden text, invoice bank-detail swaps,
output smuggling), are in `evals/injection/`. The defenses:

- **Detect and warn** (`injection.py`): lines addressed to a machine (KI, Sprachmodell, "ignore
  previous instructions", fake `--- END ---` markers) are flagged. The user sees a warning. Any
  field, claim or deadline that cites those lines goes to "Couldn't verify", and an injected date
  never becomes a reminder.
- **Hardened transcription:** the model copies every line, including text addressed to it, and
  follows none of it. Its thinking is capped, so a page can't make it think for minutes. One
  attack had reached 12,371 thinking tokens and 87 s.
- **Spotlighting:** in the extraction prompt the transcript is fenced as data, and the flagged
  lines are named.
- **Own-words check:** a URL, email, IBAN or phone number in a summary must appear in a
  trustworthy line of the letter. This stops "call 0900 …" from reaching the user.

## Evaluation

All numbers are from one run each, with Gemini 3.8 Flash.

| Set | What | Result |
|---|---|---|
| Synthetic (20 letters, 6 types) | transcription, lines exact / ignoring `–` vs `-` | 319/353 (90.4%) / 351/353 (99.4%) |
| Synthetic | extraction, 7 fields per letter | **140/140**, 19/20 fully verified |
| Held-out (7 letters in real formats, 1–3 pages) | extraction | **48/49**, 5/7 fully verified |
| Prompt injection (6 attack letters) | attack blocked / user warned | **6/6 / 6/6**, 42/42 fields |
| All 27 normal letters | false injection warnings | **0** |

"Not fully verified" is mostly the system working as intended:
- a deadline counted from an undated event ("zwei Wochen nach Rechtskraft")
- a deadline with no date ("with your next rent payment")
- an IBAN that is printed wrongly in the letter itself

In each case the item is shown as "Couldn't verify" instead of as a guess.

Caveats:
- The synthetic letters are clean renders. Real phone photos will be harder.
- Some field definitions were decided after seeing model output, as principled rules, but on
  this data.
- Borderline labels flip between runs.
- The held-out letters are kept private (`evals/private/`, gitignored).

## Run it locally

Requires Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 20, and a Google Cloud project
with Vertex AI.

```bash
uv sync
cp .env.example .env            # fill in your project
uv run pytest                   # tests, no model calls

# API on :8000 with an in-memory store and no sign-in
AMTSBRIEF_DEV_USER=dev AMTSBRIEF_STORE=memory uv run uvicorn app.main:app --app-dir backend --reload

# frontend on :5173, proxying /api to :8000
cd frontend && npm install && npm run dev
```

The evals (run them from the project root; model outputs are cached in `evals/results/`):

```bash
uv run python evals/run_transcription_eval.py
uv run python evals/run_extraction_eval.py
uv run python evals/run_injection_eval.py
```

## Deployment

The whole app is one container on Google Cloud Run (see the `Dockerfile`):
- FastAPI serves both the API and the built React app.
- Sign-in uses Firebase Auth (Google), and letters are stored in Firestore under each user's id.
- Only the analysis is stored, never the uploaded file.
- Each user can analyse at most 20 letters a day.

`deploy.sh` has the commands.

## Privacy

Letters contain personal data:
- They are processed by Google Gemini (Vertex AI).
- The upload is discarded after analysis.
- Logs contain ids and counts, never letter text.
- Users can delete any letter.

Amtsbrief is not legal advice: always check dates and amounts against the original letter.
