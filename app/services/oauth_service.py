import base64
import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import RoleName
from app.models.oauth import OAuthAccount, OAuthExchangeCode
from app.models.role import Role
from app.models.user import User
from app.services.errors import InternalError, UnauthorizedError

logger = logging.getLogger(__name__)

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
GITHUB_API_VERSION = "2022-11-28"


class OAuthFlowError(Exception):
    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail or code
        super().__init__(self.detail)


@dataclass(frozen=True)
class GitHubIdentity:
    account_id: str
    login: str
    email: str


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _hash_code(raw_code: str) -> str:
    return hashlib.sha256(raw_code.encode("utf-8")).hexdigest()


def build_authorization() -> tuple[str, str]:
    if not settings.github_oauth_configured:
        raise OAuthFlowError("not_configured")

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    now = datetime.now(UTC)
    state_cookie = jwt.encode(
        {
            "type": "oauth_state",
            "nonce": state,
            "verifier": verifier,
            "mode": "login",
            "iat": now,
            "exp": now + timedelta(seconds=settings.OAUTH_STATE_TTL_SECONDS),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_REDIRECT_URI,
        "scope": settings.GITHUB_OAUTH_SCOPES,
        "state": state,
        "code_challenge": _code_challenge(verifier),
        "code_challenge_method": "S256",
        "allow_signup": "true",
    }
    return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}", state_cookie


def validate_state(state: str | None, state_cookie: str | None) -> str:
    if not state or not state_cookie:
        raise OAuthFlowError("invalid_state")

    try:
        payload = jwt.decode(
            state_cookie,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except jwt.PyJWTError as exc:
        raise OAuthFlowError("invalid_state") from exc

    nonce = payload.get("nonce")
    verifier = payload.get("verifier")
    if (
        payload.get("type") != "oauth_state"
        or payload.get("mode") != "login"
        or not isinstance(nonce, str)
        or not isinstance(verifier, str)
        or not secrets.compare_digest(nonce, state)
    ):
        raise OAuthFlowError("invalid_state")
    return verifier


def authenticate_github(db: Session, code: str, verifier: str) -> User:
    access_token = _exchange_github_code(code, verifier)
    identity = _fetch_github_identity(access_token)

    account = db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == "github",
            OAuthAccount.provider_account_id == identity.account_id,
        )
    )
    if account is not None:
        return _login_account(db, account, identity)

    existing = db.scalar(
        select(User).where(func.lower(User.email) == identity.email.lower())
    )
    if existing is not None:
        raise OAuthFlowError("email_in_use")

    return _create_user(db, identity)


def issue_exchange_code(db: Session, user: User) -> str:
    now = datetime.now(UTC)
    db.execute(delete(OAuthExchangeCode).where(OAuthExchangeCode.expires_at < now))

    raw_code = secrets.token_urlsafe(32)
    db.add(
        OAuthExchangeCode(
            user_id=user.id,
            code_hash=_hash_code(raw_code),
            expires_at=now + timedelta(seconds=settings.OAUTH_EXCHANGE_TTL_SECONDS),
        )
    )
    db.commit()
    return raw_code


def consume_exchange_code(db: Session, raw_code: str) -> User:
    now = datetime.now(UTC)
    stored = db.scalar(
        select(OAuthExchangeCode)
        .where(OAuthExchangeCode.code_hash == _hash_code(raw_code))
        .with_for_update()
    )
    if stored is None or stored.used_at is not None or stored.expires_at < now:
        db.rollback()
        raise UnauthorizedError("Codigo de autorizacion invalido o expirado")

    user = db.get(User, stored.user_id)
    if user is None or not user.is_active:
        db.rollback()
        raise UnauthorizedError("Usuario no valido")

    stored.used_at = now
    db.commit()
    db.refresh(user)
    return user


def _exchange_github_code(code: str, verifier: str) -> str:
    if not settings.github_oauth_configured:
        raise OAuthFlowError("not_configured")

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": settings.GITHUB_REDIRECT_URI,
                    "code_verifier": verifier,
                },
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        logger.warning("No se pudo contactar con GitHub: %s", exc.__class__.__name__)
        raise OAuthFlowError("oauth_unavailable") from exc

    if response.status_code != 200:
        logger.warning("GitHub rechazo el canje del codigo: %s", response.status_code)
        raise OAuthFlowError("oauth_unavailable")

    try:
        payload = response.json()
    except ValueError as exc:
        raise OAuthFlowError("oauth_unavailable") from exc

    if not isinstance(payload, dict):
        raise OAuthFlowError("oauth_unavailable")
    if payload.get("error"):
        logger.warning("GitHub devolvio un error al canjear el codigo")
        raise OAuthFlowError("oauth_unavailable")

    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise OAuthFlowError("oauth_unavailable")
    return access_token


def _github_get(url: str, access_token: str) -> object:
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": GITHUB_API_VERSION,
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("No se pudo consultar GitHub: %s", exc.__class__.__name__)
        raise OAuthFlowError("oauth_unavailable") from exc

    if response.status_code != 200:
        logger.warning("GitHub rechazo la consulta: %s", response.status_code)
        raise OAuthFlowError("oauth_unavailable")

    try:
        return response.json()
    except ValueError as exc:
        raise OAuthFlowError("oauth_unavailable") from exc


def _fetch_github_identity(access_token: str) -> GitHubIdentity:
    user_data = _github_get(GITHUB_USER_URL, access_token)
    if not isinstance(user_data, dict):
        raise OAuthFlowError("oauth_unavailable")

    account_id = user_data.get("id")
    login = user_data.get("login")
    if account_id is None or not isinstance(login, str) or not login:
        raise OAuthFlowError("oauth_unavailable")

    emails = _github_get(GITHUB_EMAILS_URL, access_token)
    if not isinstance(emails, list):
        raise OAuthFlowError("oauth_unavailable")

    verified = [
        item
        for item in emails
        if isinstance(item, dict)
        and item.get("verified") is True
        and isinstance(item.get("email"), str)
        and "@" in item["email"]
    ]
    chosen = next((item for item in verified if item.get("primary") is True), None)
    if chosen is None and verified:
        chosen = verified[0]
    if chosen is None:
        raise OAuthFlowError("email_unverified")

    return GitHubIdentity(
        account_id=str(account_id),
        login=login,
        email=chosen["email"].lower(),
    )


def _login_account(db: Session, account: OAuthAccount, identity: GitHubIdentity) -> User:
    user = db.get(User, account.user_id)
    if user is None:
        raise OAuthFlowError("oauth_unavailable")
    if not user.is_active:
        raise OAuthFlowError("account_disabled")

    account.username = identity.login
    account.email = identity.email
    account.last_login_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def _username_base(identity: GitHubIdentity) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]", "", identity.login)[:40]
    if len(base) < 3:
        base = f"github-{identity.account_id}"[:40]
    return base


def _unique_username(db: Session, identity: GitHubIdentity) -> str:
    base = _username_base(identity)
    candidate = base
    counter = 1
    while db.scalar(
        select(User.id).where(func.lower(User.username) == candidate.lower())
    ) is not None:
        counter += 1
        suffix = f"-{counter}"
        candidate = f"{base[: 50 - len(suffix)]}{suffix}"
    return candidate


def _create_user(db: Session, identity: GitHubIdentity) -> User:
    cliente_role = db.scalar(select(Role).where(Role.name == RoleName.CLIENTE))
    if cliente_role is None:
        raise InternalError("Rol CLIENTE no inicializado")

    last_error: IntegrityError | None = None
    for _ in range(3):
        user = User(
            username=_unique_username(db, identity),
            email=identity.email,
            password_hash=None,
            role_id=cliente_role.id,
        )
        db.add(user)
        try:
            db.flush()
            db.add(
                OAuthAccount(
                    user_id=user.id,
                    provider="github",
                    provider_account_id=identity.account_id,
                    username=identity.login,
                    email=identity.email,
                )
            )
            db.commit()
            db.refresh(user)
            return user
        except IntegrityError as exc:
            db.rollback()
            last_error = exc
            account = db.scalar(
                select(OAuthAccount).where(
                    OAuthAccount.provider == "github",
                    OAuthAccount.provider_account_id == identity.account_id,
                )
            )
            if account is not None:
                return _login_account(db, account, identity)
            if db.scalar(
                select(User.id).where(func.lower(User.email) == identity.email.lower())
            ) is not None:
                raise OAuthFlowError("email_in_use") from exc
            if cliente_role is None:
                cliente_role = db.scalar(
                    select(Role).where(Role.name == RoleName.CLIENTE)
                )

    raise OAuthFlowError("oauth_unavailable") from last_error
