import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock

from fastapi import HTTPException, Request, status

from app.core.config import settings

CLEANUP_INTERVAL_SECONDS = 60
STALE_AFTER_SECONDS = 3600


@dataclass(frozen=True)
class Limit:
    attempts: int
    window_seconds: int


class SlidingWindowLimiter:
    """Limite por ventana deslizante en memoria (un contador por proceso)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._last_cleanup = clock()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._last_cleanup = self._clock()

    def check(self, key: str, limit: Limit) -> int | None:
        """Registra un intento. Devuelve los segundos de espera si se supera."""
        now = self._clock()
        with self._lock:
            self._cleanup(now)
            hits = self._hits[key]
            horizon = now - limit.window_seconds
            while hits and hits[0] <= horizon:
                hits.popleft()
            if len(hits) >= limit.attempts:
                return max(1, int(hits[0] + limit.window_seconds - now) + 1)
            hits.append(now)
            return None

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < CLEANUP_INTERVAL_SECONDS:
            return
        self._last_cleanup = now
        stale = [
            key
            for key, hits in self._hits.items()
            if not hits or hits[-1] <= now - STALE_AFTER_SECONDS
        ]
        for key in stale:
            del self._hits[key]


LIMITER = SlidingWindowLimiter()

LOGIN_IP = Limit(attempts=5, window_seconds=60)
LOGIN_IDENTIFIER = Limit(attempts=5, window_seconds=300)
REGISTER = Limit(attempts=3, window_seconds=3600)
REFRESH = Limit(attempts=30, window_seconds=60)
OAUTH_START = Limit(attempts=10, window_seconds=60)
OAUTH_CALLBACK = Limit(attempts=10, window_seconds=60)
OAUTH_EXCHANGE = Limit(attempts=20, window_seconds=60)
PASSWORD = Limit(attempts=5, window_seconds=60)


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


def enforce(
    request: Request,
    name: str,
    limit: Limit,
    subject: str | None = None,
) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return

    key = f"{name}:{_client_ip(request)}"
    if subject:
        key = f"{key}:{subject.strip().lower()}"

    retry_after = LIMITER.check(key, limit)
    if retry_after is None:
        return

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Demasiados intentos. Prueba de nuevo en {retry_after} s.",
        headers={"Retry-After": str(retry_after)},
    )
