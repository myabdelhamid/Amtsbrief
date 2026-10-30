"""Who is calling: the Firebase ID token in `Authorization: Bearer <token>`.

The frontend signs the user in with Google through Firebase and sends the ID token with
every request. firebase_admin checks its signature, expiry and audience (our project).
For local development, AMTSBRIEF_DEV_USER skips sign-in, but never on Cloud Run
(K_SERVICE is set there), so a forgotten variable can't open production.
"""
from __future__ import annotations

import os

from fastapi import Header, HTTPException


def dev_user() -> str | None:
    if os.environ.get("K_SERVICE"):
        return None
    return os.environ.get("AMTSBRIEF_DEV_USER")


def current_user(authorization: str | None = Header(None)) -> str:
    """The signed-in user's Firebase uid, or 401."""
    if (user := dev_user()) is not None:
        return user
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in first")
    import firebase_admin  # imported here so tests and dev mode don't need credentials
    from firebase_admin import auth

    if not firebase_admin._apps:
        firebase_admin.initialize_app()  # the project comes from GOOGLE_CLOUD_PROJECT
    try:
        return auth.verify_id_token(authorization.removeprefix("Bearer "))["uid"]
    except (auth.InvalidIdTokenError, auth.ExpiredIdTokenError, auth.RevokedIdTokenError, ValueError):
        raise HTTPException(401, "Your sign-in expired, sign in again")
