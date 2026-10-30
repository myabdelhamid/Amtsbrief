"""The web API, and the built frontend from frontend/dist.

    POST   /api/letters                   upload a file, analyse it, store and return it
    GET    /api/letters                   the user's letters, newest first (summaries)
    GET    /api/letters/{id}              one letter in full
    DELETE /api/letters/{id}              delete it
    GET    /api/letters/{id}/deadlines/{i}.ics   one deadline for the calendar
    GET    /api/calendar                  the user's private feed URL
    GET    /api/calendar/{token}.ics      the feed itself (no sign-in: calendar apps can't)
    GET    /api/config                    the Firebase web config the frontend signs in with

Run locally from the project root:
    AMTSBRIEF_DEV_USER=dev uv run uvicorn app.main:app --app-dir backend --reload
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

from pipeline.analyze import NoTextFound, analyze
from pipeline.preprocess import MAX_BYTES, UnsupportedFile

from . import calendar
from .auth import current_user, dev_user
from .store import FirestoreStore, LetterStore, MemoryStore, StoredLetter

DAILY_LIMIT = int(os.environ.get("AMTSBRIEF_DAILY_LIMIT", "20"))  # letters per user per day: protects the credits
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "dist"

# Never log letter content: only ids, counts and error types.
log = logging.getLogger("amtsbrief")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    if not hasattr(app.state, "client"):
        # 120 s per call; 429s and 5xx are retried twice with backoff (the trial quota is low),
        # so a user sees "busy" only after about 10 s of retrying.
        app.state.client = genai.Client(http_options=types.HttpOptions(
            timeout=120_000, retry_options=types.HttpRetryOptions(attempts=3, initial_delay=2.0, max_delay=10.0)))
    if not hasattr(app.state, "store"):
        app.state.store = make_store()
    yield


def make_store() -> LetterStore:
    if os.environ.get("AMTSBRIEF_STORE", "firestore") == "memory":
        return MemoryStore()
    import firebase_admin
    from firebase_admin import firestore

    if not firebase_admin._apps:
        firebase_admin.initialize_app()  # uses the Cloud Run service account / local gcloud login
    return FirestoreStore(firestore.client())


app = FastAPI(title="Amtsbrief", lifespan=lifespan)


def get_store(request: Request) -> LetterStore:
    return request.app.state.store


def get_client(request: Request) -> genai.Client:
    return request.app.state.client


class LetterSummary(BaseModel):
    """One row in the letter list."""
    id: str
    created_at: datetime
    letter_type: str
    sender: str
    next_deadline: date | None
    unsure: int
    warned: bool


def summary(letter: StoredLetter) -> LetterSummary:
    result = letter.analysis.result
    upcoming = sorted(d.date for d in result.deadlines if d.date >= date.today())
    return LetterSummary(id=letter.id, created_at=letter.created_at,
                         letter_type=result.extraction.letter_type.value, sender=result.extraction.sender.value,
                         next_deadline=upcoming[0] if upcoming else None, unsure=len(result.unsure),
                         warned=bool(result.suspicious))


def own_letter(letter_id: str, uid: str, store: LetterStore) -> StoredLetter:
    letter = store.get(uid, letter_id)
    if letter is None:
        raise HTTPException(404, "Letter not found")
    return letter


# Plain `def`: FastAPI runs it in a thread pool, so a 30 s model call doesn't block other requests.
@app.post("/api/letters")
def upload(file: UploadFile, uid: str = Depends(current_user), store: LetterStore = Depends(get_store),
           client: genai.Client = Depends(get_client)) -> StoredLetter:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    if store.count_since(uid, since) >= DAILY_LIMIT:
        raise HTTPException(429, f"You can analyse {DAILY_LIMIT} letters a day. Try again tomorrow.")
    data = file.file.read(MAX_BYTES + 1)  # read one byte more than allowed, so too-large files are caught
    try:
        analysis = analyze(client, data)
    except UnsupportedFile as error:
        raise HTTPException(415, str(error))
    except NoTextFound:
        raise HTTPException(422, "No text found. Is the whole letter in the photo, and in focus?")
    except (genai_errors.APIError, httpx.TimeoutException) as error:
        log.warning("model call failed: %s %s", type(error).__name__, getattr(error, "code", ""))
        raise HTTPException(503, "The text recognition service is busy. Try again in a minute.")
    letter = store.add(uid, analysis)
    log.info("analysed letter %s: %d pages, %d unsure", letter.id, analysis.pages, len(analysis.result.unsure))
    return letter


@app.get("/api/letters")
def list_letters(uid: str = Depends(current_user), store: LetterStore = Depends(get_store)) -> list[LetterSummary]:
    return [summary(letter) for letter in store.list(uid)]


@app.get("/api/letters/{letter_id}")
def get_letter(letter_id: str, uid: str = Depends(current_user),
               store: LetterStore = Depends(get_store)) -> StoredLetter:
    return own_letter(letter_id, uid, store)


@app.delete("/api/letters/{letter_id}", status_code=204)
def delete_letter(letter_id: str, uid: str = Depends(current_user), store: LetterStore = Depends(get_store)):
    if not store.delete(uid, letter_id):
        raise HTTPException(404, "Letter not found")


ICS = "text/calendar; charset=utf-8"


@app.get("/api/letters/{letter_id}/deadlines/{index}.ics")
def deadline_ics(letter_id: str, index: int, uid: str = Depends(current_user),
                 store: LetterStore = Depends(get_store)) -> Response:
    letter = own_letter(letter_id, uid, store)
    if not 0 <= index < len(letter.analysis.result.deadlines):
        raise HTTPException(404, "Deadline not found")
    return Response(calendar.single_deadline(letter, index), media_type=ICS,
                    headers={"Content-Disposition": "attachment; filename=deadline.ics"})


class Feed(BaseModel):
    url: str


@app.get("/api/calendar")
def feed_url(request: Request, uid: str = Depends(current_user), store: LetterStore = Depends(get_store)) -> Feed:
    return Feed(url=str(request.url_for("feed", token=store.feed_token(uid))))


@app.get("/api/calendar/{token}.ics", name="feed")
def feed(token: str, store: LetterStore = Depends(get_store)) -> Response:
    uid = store.uid_for_feed_token(token)
    if uid is None:
        raise HTTPException(404, "Unknown calendar")
    return Response(calendar.calendar(store.list(uid)), media_type=ICS)


class ClientConfig(BaseModel):
    """Public by design: a Firebase web config identifies the project, it grants nothing."""
    dev: bool
    firebase: dict[str, str]


@app.get("/api/config")
def client_config() -> ClientConfig:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    return ClientConfig(dev=dev_user() is not None, firebase={
        "apiKey": os.environ.get("FIREBASE_API_KEY", ""),
        "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN", f"{project}.firebaseapp.com"),
        "projectId": project,
        "appId": os.environ.get("FIREBASE_APP_ID", ""),
    })


# The built React app. Any path that isn't /api or a file gets index.html,
# so the frontend's own routes (/letters/abc) survive a page reload.
if FRONTEND.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        file = FRONTEND / path
        if path and file.is_file() and FRONTEND in file.resolve().parents:
            return FileResponse(file)
        return FileResponse(FRONTEND / "index.html")
