"""User accounts (email/password and GitHub) and per-user saved context packages.

Security notes:
* Passwords are hashed with scrypt (standard library) and a random salt; plaintext is never
  stored or logged.
* Login returns a signed JWT (HS256, ``ACWM_JWT_SECRET``) that the browser sends as a
  Bearer token. Tokens expire (default 7 days); there is no server-side revocation list.
* GitHub accounts are linked only by GitHub's numeric user id, never by matching emails,
  so a GitHub account can never take over an email/password account.
* The GitHub flow uses ``state`` (CSRF protection) and PKCE (S256); both are bound to the
  browser with a short-lived, signed, HttpOnly cookie.
* Failed logins and signups are rate-limited in memory (per process).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt
from pydantic import ValidationError
from sqlalchemy import func, select

from app.context.package_models import ContextPackage
from app.core.config import Settings
from app.core.exceptions import (
    AccountExistsError,
    ACWMError,
    AuthenticationError,
    NotConfiguredError,
    NotFoundError,
    ProviderError,
    QuotaExceededError,
    RateLimitedError,
)
from app.core.logging_config import get_logger
from app.storage.database import Database, SavedPackage, User, as_utc

log = get_logger("accounts")

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$")
MIN_PASSWORD, MAX_PASSWORD = 8, 128
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
JWT_ALG, JWT_ISSUER = "HS256", "acwm"
GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_USER = "https://api.github.com/user"
OAUTH_STATE_TTL = timedelta(minutes=10)


class InvalidInputError(ACWMError):
    code = "invalid_input"
    http_status = 422


# ------------------------------------------------------------------ passwords
def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(),
            salt=_unb64(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(_unb64(expected)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, _unb64(expected))


# Hash of a random password, used to keep failed logins for unknown emails as slow as
# failed logins for known ones (avoids revealing which emails exist via timing).
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


# ---------------------------------------------------------------- rate limits
class RateLimiter:
    """Sliding-window counter per key, in memory (per server process)."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit, self.window = limit, window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                raise RateLimitedError(
                    "Too many attempts. Please wait a few minutes and try again."
                )

    def hit(self, key: str) -> None:
        with self._lock:
            self._hits.setdefault(key, deque()).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


@dataclass
class PublicUser:
    id: int
    display_name: str
    email: str | None
    github_login: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, u: User) -> PublicUser:
        return cls(u.id, u.display_name, u.email, u.github_login, as_utc(u.created_at))


class AccountService:
    def __init__(
        self, settings: Settings, db: Database, github_transport: httpx.BaseTransport | None = None
    ) -> None:
        self.settings = settings
        self.db = db
        self._github_transport = github_transport
        self.login_limiter = RateLimiter(limit=10, window_seconds=300)
        self.signup_limiter = RateLimiter(limit=10, window_seconds=3600)

    # ------------------------------------------------------------- tokens
    def create_token(self, user_id: int) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "iss": JWT_ISSUER,
            "typ": "access",
            "iat": now,
            "exp": now + timedelta(minutes=self.settings.jwt_ttl_minutes),
        }
        return jwt.encode(payload, self.settings.jwt_secret, algorithm=JWT_ALG)

    def user_from_token(self, token: str) -> PublicUser:
        try:
            claims = jwt.decode(
                token,
                self.settings.jwt_secret,
                algorithms=[JWT_ALG],
                issuer=JWT_ISSUER,
                options={"require": ["exp", "sub", "iss"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("Your session has expired. Please log in again.") from exc
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid login token. Please log in again.") from exc
        if claims.get("typ") != "access":
            raise AuthenticationError("Invalid login token. Please log in again.")
        with self.db.session() as s:
            user = s.get(User, int(claims["sub"]))
            if user is None:
                raise AuthenticationError("This account no longer exists.")
            return PublicUser.from_model(user)

    # ------------------------------------------------------ email/password
    @staticmethod
    def _clean_email(email: str) -> str:
        email = (email or "").strip().lower()
        if len(email) > 320 or not EMAIL_RE.match(email):
            raise InvalidInputError("Please enter a valid email address.")
        return email

    def signup(
        self, email: str, password: str, display_name: str | None, client_ip: str
    ) -> tuple[str, PublicUser]:
        self.signup_limiter.check(f"ip:{client_ip}")
        email = self._clean_email(email)
        if not (MIN_PASSWORD <= len(password or "") <= MAX_PASSWORD):
            raise InvalidInputError(
                f"Password must be {MIN_PASSWORD}-{MAX_PASSWORD} characters long."
            )
        name = (display_name or "").strip()[:100] or email.split("@")[0]
        self.signup_limiter.hit(f"ip:{client_ip}")
        with self.db.session() as s, s.begin():
            if s.scalar(select(User).where(User.email == email)) is not None:
                raise AccountExistsError(
                    "An account with this email already exists. Please log in."
                )
            user = User(email=email, password_hash=hash_password(password), display_name=name)
            s.add(user)
            s.flush()
            public = PublicUser.from_model(user)
        log.info("New email account created (user id %s)", public.id)
        return self.create_token(public.id), public

    def login(self, email: str, password: str, client_ip: str) -> tuple[str, PublicUser]:
        email = (email or "").strip().lower()
        keys = (f"ip:{client_ip}", f"email:{email}")
        for k in keys:
            self.login_limiter.check(k)
        with self.db.session() as s:
            user = s.scalar(select(User).where(User.email == email))
            ok = verify_password(password or "", user.password_hash if user else _DUMMY_HASH)
            if not (user and ok):
                for k in keys:
                    self.login_limiter.hit(k)
                raise AuthenticationError("Incorrect email or password.")
            public = PublicUser.from_model(user)
        self.login_limiter.reset(f"email:{email}")
        return self.create_token(public.id), public

    # --------------------------------------------------------------- GitHub
    def _github_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=15,
            transport=self._github_transport,
            headers={"Accept": "application/json", "User-Agent": "acwm"},
        )

    @property
    def github_callback_url(self) -> str:
        return f"{self.settings.public_api_url}/auth/github/callback"

    def github_start(self) -> tuple[str, str]:
        """Return (authorize URL, signed state cookie value)."""
        if not self.settings.github_enabled:
            raise NotConfiguredError("GitHub login is not configured on this server.")
        nonce = secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(48)
        challenge = _b64(hashlib.sha256(verifier.encode()).digest())
        cookie = jwt.encode(
            {
                "typ": "gh_state",
                "nonce": nonce,
                "verifier": verifier,
                "iss": JWT_ISSUER,
                "exp": datetime.now(UTC) + OAUTH_STATE_TTL,
            },
            self.settings.jwt_secret,
            algorithm=JWT_ALG,
        )
        query = urlencode(
            {
                "client_id": self.settings.github_client_id,
                "redirect_uri": self.github_callback_url,
                "scope": "read:user",
                "state": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "allow_signup": "true",
            }
        )
        return f"{GITHUB_AUTHORIZE}?{query}", cookie

    def github_finish(self, code: str, state: str, cookie: str | None) -> tuple[str, PublicUser]:
        if not self.settings.github_enabled:
            raise NotConfiguredError("GitHub login is not configured on this server.")
        try:
            data = jwt.decode(
                cookie or "", self.settings.jwt_secret, algorithms=[JWT_ALG], issuer=JWT_ISSUER
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError(
                "GitHub login expired or was started in another browser. Please try again."
            ) from exc
        if (
            data.get("typ") != "gh_state"
            or not state
            or not hmac.compare_digest(str(data.get("nonce")), state)
        ):
            raise AuthenticationError("GitHub login could not be verified (state mismatch).")
        with self._github_client() as client:
            try:
                tok = client.post(
                    GITHUB_TOKEN,
                    data={
                        "client_id": self.settings.github_client_id,
                        "client_secret": self.settings.github_client_secret,
                        "code": code,
                        "redirect_uri": self.github_callback_url,
                        "code_verifier": data["verifier"],
                    },
                )
                access = tok.json().get("access_token") if tok.status_code == 200 else None
                if not access:
                    raise AuthenticationError("GitHub did not accept the login. Please try again.")
                me = client.get(GITHUB_USER, headers={"Authorization": f"Bearer {access}"})
            except httpx.HTTPError as exc:
                raise ProviderError("Could not reach GitHub. Please try again.") from exc
            except ValueError as exc:
                raise ProviderError("GitHub returned an unexpected response.") from exc
        if me.status_code != 200:
            raise ProviderError("Could not read your GitHub profile.")
        profile = me.json()
        gh_id = str(profile.get("id") or "")
        login = str(profile.get("login") or "")[:100]
        if not gh_id or not login:
            raise ProviderError("GitHub returned an incomplete profile.")
        name = (profile.get("name") or login)[:100]
        with self.db.session() as s, s.begin():
            user = s.scalar(select(User).where(User.github_id == gh_id))
            if user is None:
                user = User(github_id=gh_id, github_login=login, display_name=name)
                s.add(user)
                log.info("New GitHub account linked")
            else:
                user.github_login = login
            s.flush()
            public = PublicUser.from_model(user)
        return self.create_token(public.id), public

    # ------------------------------------------------------- saved packages
    def save_package(self, user_id: int, package: dict, title: str | None) -> SavedPackage:
        try:
            pkg = ContextPackage.model_validate(package)
        except ValidationError as exc:
            raise InvalidInputError("This is not a valid context package.") from exc
        with self.db.session() as s, s.begin():
            count = s.scalar(
                select(func.count())
                .select_from(SavedPackage)
                .where(SavedPackage.user_id == user_id)
            )
            if count >= self.settings.max_saved_packages:
                raise QuotaExceededError(
                    f"You can keep up to {self.settings.max_saved_packages} saved packages. "
                    "Delete some to save new ones."
                )
            row = SavedPackage(
                user_id=user_id,
                title=((title or "").strip() or pkg.task)[:200],
                task=pkg.task,
                repository_name=pkg.repository.root_name[:200],
                item_count=len(pkg.items),
                rendered_tokens=pkg.token_stats.rendered_context_tokens,
                package=pkg.model_dump(mode="json"),
            )
            s.add(row)
            s.flush()
            return row

    def list_packages(self, user_id: int) -> list[SavedPackage]:
        with self.db.session() as s:
            return list(
                s.scalars(
                    select(SavedPackage)
                    .where(SavedPackage.user_id == user_id)
                    .order_by(SavedPackage.created_at.desc(), SavedPackage.id.desc())
                )
            )

    def get_package(self, user_id: int, package_id: int) -> SavedPackage:
        with self.db.session() as s:
            row = s.get(SavedPackage, package_id)
            # Same error whether it does not exist or belongs to someone else.
            if row is None or row.user_id != user_id:
                raise NotFoundError("Saved package not found.")
            return row

    def delete_package(self, user_id: int, package_id: int) -> None:
        with self.db.session() as s, s.begin():
            row = s.get(SavedPackage, package_id)
            if row is None or row.user_id != user_id:
                raise NotFoundError("Saved package not found.")
            s.delete(row)
