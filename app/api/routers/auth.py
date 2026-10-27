import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.rate_limit import (
    LOGIN_IDENTIFIER,
    LOGIN_IP,
    OAUTH_CALLBACK,
    OAUTH_EXCHANGE,
    OAUTH_START,
    PASSWORD,
    REFRESH,
    REGISTER,
    enforce,
)
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    OAuthAccountRead,
    OAuthAccountsRead,
    OAuthExchangeRequest,
    OAuthLinkStartResponse,
    PasswordChangeRequest,
    TokenResponse,
)
from app.schemas.user import UserRead, UserRegister
from app.services import auth_service, oauth_service
from app.services.errors import BadRequestError, UnauthorizedError
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


def _redirect_frontend(path: str, params: dict[str, str]) -> RedirectResponse:
    url = f"{settings.frontend_base_url}{path}?{urlencode(params)}"
    response = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    response.delete_cookie(settings.OAUTH_STATE_COOKIE_NAME, path=OAUTH_COOKIE_PATH)
    return response


def _set_oauth_state_cookie(response: Response, value: str) -> None:
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
def github_start(request: Request) -> RedirectResponse:
    enforce(request, "oauth-start", OAUTH_START)
    try:
        authorize_url, state_cookie = oauth_service.build_authorization()
    except OAuthFlowError as exc:
        return _redirect_frontend("/oauth/callback", {"error": exc.code})

    response = RedirectResponse(authorize_url, status_code=status.HTTP_302_FOUND)
    _set_oauth_state_cookie(response, state_cookie)
    return response


@router.get("/oauth/github/link/start", response_model=OAuthLinkStartResponse)
def github_link_start(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
) -> OAuthLinkStartResponse:
    enforce(request, "oauth-link-start", OAUTH_START, subject=str(current_user.id))
    try:
        authorize_url, state_cookie = oauth_service.build_authorization(
            mode="link", user_id=current_user.id
        )
    except OAuthFlowError as exc:
        raise BadRequestError(
            "El acceso con GitHub no esta configurado en este entorno"
        ) from exc

    _set_oauth_state_cookie(response, state_cookie)
    return OAuthLinkStartResponse(authorize_url=authorize_url)


@router.get("/oauth/github/callback")
def github_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    state_cookie: str | None = Cookie(
        default=None, alias=settings.OAUTH_STATE_COOKIE_NAME
    ),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    enforce(request, "oauth-callback", OAUTH_CALLBACK)
    if error:
        code_name = "access_denied" if error == "access_denied" else "oauth_unavailable"
        if _is_link_state(state, state_cookie):
            return _redirect_frontend("/perfil", {"oauth_error": code_name})
        return _redirect_frontend("/oauth/callback", {"error": code_name})
    if not code or not state:
        return _redirect_frontend("/oauth/callback", {"error": "invalid_request"})

    try:
        oauth_state = oauth_service.validate_state(state, state_cookie)
    except OAuthFlowError as exc:
        return _redirect_frontend("/oauth/callback", {"error": exc.code})

    if oauth_state.mode == "link":
        try:
            user = db.get(User, oauth_state.user_id)
            if user is None or not user.is_active:
                raise OAuthFlowError("account_disabled")
            oauth_service.link_github(db, user, code, oauth_state.verifier)
        except OAuthFlowError as exc:
            return _redirect_frontend("/perfil", {"oauth_error": exc.code})
        except Exception:
            logger.exception("Fallo inesperado al vincular GitHub")
            return _redirect_frontend("/perfil", {"oauth_error": "oauth_unavailable"})
        return _redirect_frontend("/perfil", {"oauth": "linked"})

    try:
        user = oauth_service.authenticate_github(db, code, oauth_state.verifier)
        exchange_code = oauth_service.issue_exchange_code(db, user)
    except OAuthFlowError as exc:
        return _redirect_frontend("/oauth/callback", {"error": exc.code})
    except Exception:
        logger.exception("Fallo inesperado en el callback de GitHub")
        return _redirect_frontend("/oauth/callback", {"error": "oauth_unavailable"})

    return _redirect_frontend("/oauth/callback", {"code": exchange_code})


def _is_link_state(state: str | None, state_cookie: str | None) -> bool:
    if not state or not state_cookie:
        return False
    try:
        return oauth_service.validate_state(state, state_cookie).mode == "link"
    except OAuthFlowError:
        return False


@router.get("/oauth/accounts", response_model=OAuthAccountsRead)
def oauth_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OAuthAccountsRead:
    account = oauth_service.get_linked_account(db, current_user.id)
    return OAuthAccountsRead(
        github=OAuthAccountRead.model_validate(account) if account else None
    )


@router.delete("/oauth/github", status_code=status.HTTP_204_NO_CONTENT)
def unlink_github(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    oauth_service.unlink_github(db, current_user)


@router.post("/oauth/exchange", response_model=TokenResponse)
def exchange_oauth(
    payload: OAuthExchangeRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    enforce(request, "oauth-exchange", OAUTH_EXCHANGE)
    user = oauth_service.consume_exchange_code(db, payload.code)
    _set_refresh_cookie(response, issue_refresh_token(db, user))
    return _token_response(user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    refresh_token: str | None = Cookie(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    enforce(request, "password", PASSWORD, subject=str(current_user.id))
    auth_service.change_password(
        db,
        current_user,
        payload.current_password,
        payload.new_password,
        keep_refresh_token=refresh_token,
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserRegister,
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    enforce(request, "register", REGISTER)
    return auth_service.register_user(db, payload)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    enforce(request, "login-ip", LOGIN_IP)
    enforce(request, "login-user", LOGIN_IDENTIFIER, subject=payload.username)
    user, refresh_raw = auth_service.login_user(db, payload.username, payload.password)
    _set_refresh_cookie(response, refresh_raw)
    return _token_response(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> TokenResponse:
    enforce(request, "refresh", REFRESH)
    if not refresh_token:
        raise UnauthorizedError("Sin refresh token")

    try:
        user, new_raw = rotate_refresh_token(db, refresh_token)
    except UnauthorizedError:
        response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/")
        raise

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
