"""Authentication service: verifies credentials and manages session tokens."""

from __future__ import annotations

import time

from shopapi.core.config import Settings, get_settings
from shopapi.core.errors import AuthenticationError
from shopapi.core.security import hash_password, new_session_token, verify_password
from shopapi.db.database import Database
from shopapi.db.repositories import SessionRepository, UserRepository


class AuthService:
    def __init__(self, db: Database, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.users = UserRepository(db)
        self.sessions = SessionRepository(db)

    def register(self, username: str, password: str, full_name: str = "") -> dict:
        return self.users.add(username, hash_password(password), full_name)

    def authenticate(self, username: str, password: str) -> dict:
        user = self.users.get(username)
        if user is None or not verify_password(password, user["password_hash"]):
            raise AuthenticationError("invalid username or password")
        return user

    def issue_token(self, username: str) -> tuple[str, int]:
        """Create an opaque session token. Returns (token, ttl_seconds)."""
        ttl = self.settings.access_token_ttl_minutes * 60
        token = new_session_token()
        self.sessions.save(token, username, time.time() + ttl)
        return token, ttl

    def resolve_token(self, token: str) -> dict:
        session = self.sessions.get(token)
        if session is None or session["expires_at"] < time.time():
            raise AuthenticationError("invalid or expired token")
        user = self.users.get(session["username"])
        if user is None:
            raise AuthenticationError("user no longer exists")
        return user

    def logout(self, token: str) -> None:
        self.sessions.delete(token)
