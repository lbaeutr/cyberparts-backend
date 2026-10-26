import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, OAuthExchangeRequest, TokenResponse
from app.schemas.user import UserRead, UserRegister
from app.services import auth_service, oauth_service
from app.services.errors import UnauthorizedError
from app.services.oauth_service import OAuthFlowError
from app.services.token_service import (
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Autenticacion"])

OAUTH_COOKIE_PATH = f"{settings.API_PREFIX}/auth/oauth"


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/",
    )


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user.id), user.role_name),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserRead.model_validate(user),
    )


def _redirect_frontend(params: dict[str, str]) -> RedirectResponse:
    url = f"{settings.frontend_base_url}/oauth/callback?{urlencode(params)}"
    response = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    response.delete_cookie(settings.OAUTH_STATE_COOKIE_NAME, path=OAUTH_COOKIE_PATH)
    return response


def _set_oauth_state_cookie(response: RedirectResponse, value: str) -> None:
    response.set_cookie(
        key=settings.OAUTH_STATE_COOKIE_NAME,
        value=value,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.OAUTH_STATE_TTL_SECONDS,
        path=OAUTH_COOKIE_PATH,
    )


@router.get("/oauth/github/start")
def github_start() -> RedirectResponse:
    try:
        authorize_url, state_cookie = oauth_service.build_authorization()
    except OAuthFlowError as exc:
        return _redirect_frontend({"error": exc.code})

    response = RedirectResponse(authorize_url, status_code=status.HTTP_302_FOUND)
    _set_oauth_state_cookie(response, state_cookie)
    return response


@router.get("/oauth/github/callback")
def github_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    state_cookie: str | None = Cookie(
        default=None, alias=settings.OAUTH_STATE_COOKIE_NAME
    ),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if error:
        code_name = "access_denied" if error == "access_denied" else "oauth_unavailable"
        return _redirect_frontend({"error": code_name})
    if not code or not state:
        return _redirect_frontend({"error": "invalid_request"})

    try:
        verifier = oauth_service.validate_state(state, state_cookie)
        user = oauth_service.authenticate_github(db, code, verifier)
        exchange_code = oauth_service.issue_exchange_code(db, user)
    except OAuthFlowError as exc:
        return _redirect_frontend({"error": exc.code})
    except Exception:
        logger.exception("Fallo inesperado en el callback de GitHub")
        return _redirect_frontend({"error": "oauth_unavailable"})

    return _redirect_frontend({"code": exchange_code})


@router.post("/oauth/exchange", response_model=TokenResponse)
def exchange_oauth(
    payload: OAuthExchangeRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = oauth_service.consume_exchange_code(db, payload.code)
    _set_refresh_cookie(response, issue_refresh_token(db, user))
    return _token_response(user)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)) -> User:
    return auth_service.register_user(db, payload)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    user, refresh_raw = auth_service.login_user(db, payload.username, payload.password)
    _set_refresh_cookie(response, refresh_raw)
    return _token_response(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> TokenResponse:
    if not refresh_token:
        raise UnauthorizedError("Sin refresh token")

    user, new_raw = rotate_refresh_token(db, refresh_token)
    _set_refresh_cookie(response, new_raw)
    return _token_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> None:
    if refresh_token:
        revoke_refresh_token(db, refresh_token)
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/")


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
