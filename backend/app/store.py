"""Where analysed letters are kept. One interface, two implementations:

- MemoryStore: a dict, for tests and local development. Gone when the server stops.
- FirestoreStore: production. Every letter lives under users/{uid}/letters/{id}, so a
  query can only ever reach the signed-in user's own letters.

Only the analysis is stored (transcript, extracted fields, issues), never the uploaded
photo or PDF. The calendar feed needs a secret per user, because calendar apps can't
send a sign-in token: feed_tokens/{token} maps it back to the user.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel

from pipeline.schemas import Analysis


class StoredLetter(BaseModel):
    id: str
    created_at: datetime
    analysis: Analysis


class LetterStore(Protocol):
    def add(self, uid: str, analysis: Analysis) -> StoredLetter: ...
    def list(self, uid: str) -> list[StoredLetter]: ...  # newest first
    def get(self, uid: str, letter_id: str) -> StoredLetter | None: ...
    def delete(self, uid: str, letter_id: str) -> bool: ...  # False if there was nothing to delete
    def count_since(self, uid: str, since: datetime) -> int: ...
    def feed_token(self, uid: str) -> str: ...  # created on first use
    def uid_for_feed_token(self, token: str) -> str | None: ...


def new_letter(analysis: Analysis) -> StoredLetter:
    return StoredLetter(id=uuid.uuid4().hex, created_at=datetime.now(timezone.utc), analysis=analysis)


class MemoryStore:
    def __init__(self) -> None:
        self.letters: dict[str, dict[str, StoredLetter]] = {}
        self.tokens: dict[str, str] = {}  # token -> uid

    def add(self, uid: str, analysis: Analysis) -> StoredLetter:
        letter = new_letter(analysis)
        self.letters.setdefault(uid, {})[letter.id] = letter
        return letter

    def list(self, uid: str) -> list[StoredLetter]:
        return sorted(self.letters.get(uid, {}).values(), key=lambda letter: letter.created_at, reverse=True)

    def get(self, uid: str, letter_id: str) -> StoredLetter | None:
        return self.letters.get(uid, {}).get(letter_id)

    def delete(self, uid: str, letter_id: str) -> bool:
        return self.letters.get(uid, {}).pop(letter_id, None) is not None

    def count_since(self, uid: str, since: datetime) -> int:
        return sum(letter.created_at >= since for letter in self.letters.get(uid, {}).values())

    def feed_token(self, uid: str) -> str:
        for token, owner in self.tokens.items():
            if owner == uid:
                return token
        token = secrets.token_urlsafe(32)
        self.tokens[token] = uid
        return token

    def uid_for_feed_token(self, token: str) -> str | None:
        return self.tokens.get(token)


class FirestoreStore:
    def __init__(self, client) -> None:  # a google.cloud.firestore.Client
        self.db = client

    def _letters(self, uid: str):
        return self.db.collection("users").document(uid).collection("letters")

    @staticmethod
    def _from_doc(doc) -> StoredLetter:
        data = doc.to_dict()
        # The analysis is stored as one JSON string: it round-trips exactly through
        # Pydantic, and Firestore's rules for map keys never get in the way.
        return StoredLetter(id=doc.id, created_at=data["created_at"],
                            analysis=Analysis.model_validate_json(data["analysis_json"]))

    def add(self, uid: str, analysis: Analysis) -> StoredLetter:
        letter = new_letter(analysis)
        self._letters(uid).document(letter.id).set(
            {"created_at": letter.created_at, "analysis_json": analysis.model_dump_json()})
        return letter

    def list(self, uid: str) -> list[StoredLetter]:
        docs = self._letters(uid).order_by("created_at", direction="DESCENDING").stream()
        return [self._from_doc(doc) for doc in docs]

    def get(self, uid: str, letter_id: str) -> StoredLetter | None:
        doc = self._letters(uid).document(letter_id).get()
        return self._from_doc(doc) if doc.exists else None

    def delete(self, uid: str, letter_id: str) -> bool:
        ref = self._letters(uid).document(letter_id)
        if not ref.get().exists:
            return False
        ref.delete()
        return True

    def count_since(self, uid: str, since: datetime) -> int:
        query = self._letters(uid).where("created_at", ">=", since)
        return query.count().get()[0][0].value

    def feed_token(self, uid: str) -> str:
        user = self.db.collection("users").document(uid)
        doc = user.get()
        if doc.exists and doc.to_dict().get("feed_token"):
            return doc.to_dict()["feed_token"]
        token = secrets.token_urlsafe(32)
        self.db.collection("feed_tokens").document(token).set({"uid": uid})
        user.set({"feed_token": token}, merge=True)
        return token

    def uid_for_feed_token(self, token: str) -> str | None:
        doc = self.db.collection("feed_tokens").document(token).get()
        return doc.to_dict()["uid"] if doc.exists else None
