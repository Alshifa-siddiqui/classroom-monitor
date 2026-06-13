import hmac
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, Optional

from fastapi import Depends, Header, HTTPException, Request, WebSocket, status

from .auth import role_satisfies, verify_token
from .config import settings

log = logging.getLogger(__name__)


@dataclass
class AuthContext:
    username: str
    role: str
    student_id: Optional[int] = None  # set for accounts linked to a student


def _from_bearer(authorization: str) -> Optional[AuthContext]:
    if not authorization.startswith("Bearer "):
        return None
    payload = verify_token(authorization[7:], settings.JWT_SECRET)
    if payload is None:
        return None
    return AuthContext(username=payload.get("sub", "?"),
                       role=payload.get("role", "viewer"),
                       student_id=payload.get("student_id"))


def _from_api_key(key: str) -> Optional[AuthContext]:
    if key and hmac.compare_digest(key, settings.API_KEY):
        # legacy shared key keeps old clients working; treated as admin
        return AuthContext(username="api-key", role="admin")
    return None


def get_current_user(authorization: str = Header(default=""),
                     x_api_key: str = Header(default="")) -> AuthContext:
    ctx = _from_bearer(authorization) or _from_api_key(x_api_key)
    if ctx is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Not authenticated")
    return ctx


def require_role(min_role: str):
    def checker(user: AuthContext = Depends(get_current_user)) -> AuthContext:
        if not role_satisfies(user.role, min_role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Requires {min_role} role")
        return user
    return checker


# Kept for any code still importing the old dependency name
def require_api_key(x_api_key: str = Header(default="")) -> None:
    if _from_api_key(x_api_key) is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid API key")


class SlidingWindowLimiter:
    """Per-key sliding-window rate limiter (in-memory, single process)."""

    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self._hits: Dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.time()
        window = self._hits[key]
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= self.max_per_minute:
            return False
        window.append(now)
        return True


rest_limiter = SlidingWindowLimiter(settings.RATE_LIMIT_PER_MINUTE)
login_limiter = SlidingWindowLimiter(settings.LOGIN_RATE_LIMIT_PER_MINUTE)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class WebSocketLimiter:
    """Per-IP and global connection limits for the /live WebSocket."""

    def __init__(self, max_total: int, max_per_ip: int):
        self.max_total = max_total
        self.max_per_ip = max_per_ip
        self._per_ip: Dict[str, int] = defaultdict(int)
        self._total = 0

    def try_acquire(self, ip: str) -> bool:
        if self._total >= self.max_total or self._per_ip[ip] >= self.max_per_ip:
            return False
        self._per_ip[ip] += 1
        self._total += 1
        return True

    def release(self, ip: str) -> None:
        if self._per_ip[ip] > 0:
            self._per_ip[ip] -= 1
            self._total -= 1


ws_limiter = WebSocketLimiter(settings.WS_MAX_CONNECTIONS, settings.WS_MAX_PER_IP)


def ws_authenticate(websocket: WebSocket) -> Optional[AuthContext]:
    """WS auth: JWT via ?token=, or the legacy ?api_key=. Viewer role suffices."""
    token = websocket.query_params.get("token", "")
    if token:
        payload = verify_token(token, settings.JWT_SECRET)
        if payload is not None:
            return AuthContext(username=payload.get("sub", "?"),
                               role=payload.get("role", "viewer"))
    return _from_api_key(websocket.query_params.get("api_key", ""))


def audit(db, username: str, action: str, detail: str = "") -> None:
    """Best-effort audit trail; never lets a logging failure break the request."""
    from .models import AuditLog
    try:
        db.add(AuditLog(username=username, action=action, detail=detail[:300]))
        db.commit()
    except Exception:
        log.exception("audit write failed")
        db.rollback()
