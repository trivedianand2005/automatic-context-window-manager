"""Account endpoints (email/password + GitHub) and per-user saved packages."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.api.deps import client_ip, get_accounts, require_user
from app.api.schemas import (
    AuthProviders,
    AuthResponse,
    ErrorResponse,
    LoginRequest,
    SavedPackageOut,
    SavedPackageSummary,
    SavePackageRequest,
    SignupRequest,
    UserOut,
)
from app.core.exceptions import ACWMError
from app.services.accounts import AccountService, PublicUser
from app.storage.database import as_utc

router = APIRouter()
STATE_COOKIE = "acwm_gh_state"
ERRORS = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
}


def _auth_response(accounts: AccountService, token: str, user: PublicUser) -> AuthResponse:
    return AuthResponse(
        token=token,
        expires_in_minutes=accounts.settings.jwt_ttl_minutes,
        user=UserOut(**user.__dict__),
    )


@router.get("/auth/providers", response_model=AuthProviders, tags=["auth"])
def providers(accounts: AccountService = Depends(get_accounts)) -> AuthProviders:
    s = accounts.settings
    return AuthProviders(
        github=s.github_enabled, require_auth=s.require_auth, database=accounts.db.description
    )


@router.post(
    "/auth/signup", response_model=AuthResponse, status_code=201, responses=ERRORS, tags=["auth"]
)
def signup(
    body: SignupRequest, request: Request, accounts: AccountService = Depends(get_accounts)
) -> AuthResponse:
    token, user = accounts.signup(body.email, body.password, body.display_name, client_ip(request))
    return _auth_response(accounts, token, user)


@router.post("/auth/login", response_model=AuthResponse, responses=ERRORS, tags=["auth"])
def login(
    body: LoginRequest, request: Request, accounts: AccountService = Depends(get_accounts)
) -> AuthResponse:
    token, user = accounts.login(body.email, body.password, client_ip(request))
    return _auth_response(accounts, token, user)


@router.get("/auth/me", response_model=UserOut, responses=ERRORS, tags=["auth"])
def me(user: PublicUser = Depends(require_user)) -> UserOut:
    return UserOut(**user.__dict__)


@router.get(
    "/auth/github/login",
    tags=["auth"],
    response_class=RedirectResponse,
    responses={302: {"description": "Redirect to GitHub"}, 501: {"model": ErrorResponse}},
)
def github_login(accounts: AccountService = Depends(get_accounts)) -> RedirectResponse:
    url, cookie = accounts.github_start()
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(
        STATE_COOKIE,
        cookie,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=accounts.settings.public_api_url.startswith("https://"),
        path="/auth/github",
    )
    return resp


@router.get(
    "/auth/github/callback",
    tags=["auth"],
    response_class=RedirectResponse,
    responses={302: {"description": "Redirect back to the web app"}},
)
def github_callback(
    request: Request,
    code: str | None = Query(None, max_length=200),
    state: str | None = Query(None, max_length=200),
    error: str | None = Query(None, max_length=200),
    accounts: AccountService = Depends(get_accounts),
) -> RedirectResponse:
    """Finish GitHub login and send the browser back to the web app.

    The token travels in the URL *fragment* (#...), which browsers never send to servers,
    so it does not appear in server or proxy logs. The redirect target is fixed by
    configuration (ACWM_FRONTEND_URL), so this cannot be used as an open redirect.
    """
    base = accounts.settings.frontend_url.rstrip("/") + "/"
    try:
        if error:
            raise ACWMError("GitHub login was cancelled.")
        if not code:
            raise ACWMError("GitHub did not return a login code.")
        token, _ = accounts.github_finish(code, state or "", request.cookies.get(STATE_COOKIE))
        target = f"{base}#auth_token={quote(token)}"
    except ACWMError as exc:
        target = f"{base}#auth_error={quote(exc.message)}"
    resp = RedirectResponse(target, status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/auth/github")
    return resp


# ------------------------------------------------------------ saved packages
def _summary(row) -> SavedPackageSummary:
    return SavedPackageSummary(
        id=row.id,
        title=row.title,
        task=row.task,
        repository_name=row.repository_name,
        item_count=row.item_count,
        rendered_tokens=row.rendered_tokens,
        created_at=as_utc(row.created_at),
    )


@router.get(
    "/packages", response_model=list[SavedPackageSummary], responses=ERRORS, tags=["packages"]
)
def list_packages(
    user: PublicUser = Depends(require_user), accounts: AccountService = Depends(get_accounts)
) -> list[SavedPackageSummary]:
    return [_summary(r) for r in accounts.list_packages(user.id)]


@router.post(
    "/packages",
    response_model=SavedPackageSummary,
    status_code=201,
    responses=ERRORS,
    tags=["packages"],
)
def save_package(
    body: SavePackageRequest,
    user: PublicUser = Depends(require_user),
    accounts: AccountService = Depends(get_accounts),
) -> SavedPackageSummary:
    row = accounts.save_package(user.id, body.package.model_dump(mode="json"), body.title)
    return _summary(row)


@router.get(
    "/packages/{package_id}", response_model=SavedPackageOut, responses=ERRORS, tags=["packages"]
)
def get_package(
    package_id: int,
    user: PublicUser = Depends(require_user),
    accounts: AccountService = Depends(get_accounts),
) -> SavedPackageOut:
    row = accounts.get_package(user.id, package_id)
    return SavedPackageOut(**_summary(row).model_dump(), package=row.package)


@router.delete("/packages/{package_id}", status_code=204, responses=ERRORS, tags=["packages"])
def delete_package(
    package_id: int,
    user: PublicUser = Depends(require_user),
    accounts: AccountService = Depends(get_accounts),
) -> Response:
    accounts.delete_package(user.id, package_id)
    return Response(status_code=204)
