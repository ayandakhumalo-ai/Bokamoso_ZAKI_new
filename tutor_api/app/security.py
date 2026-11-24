"""Password hashing, JWT tokens, and the 'who is calling?' dependency."""
import time
from collections import defaultdict, deque

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db
from .config import settings

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())


def verify_password(password: str, hashed: bytes) -> bool:
    return bcrypt.checkpw(password.encode(), hashed)


def create_token(user_id: int) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "iat": now, "exp": now + settings.token_minutes * 60}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    try:
        payload = jwt.decode(creds.credentials, settings.secret_key, algorithms=["HS256"])
        user = db.get_user_by_id(int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


def require_role(role: str):
    """Dependency factory: only logged-in users with this role get through."""
    def checker(user=Depends(current_user)):
        if user["role"] != role:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"This endpoint is for {role} accounts")
        return user
    return checker


def require_admin(x_admin_key: str | None = Header(default=None)):
    if x_admin_key != settings.admin_key:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin key required")


# --- very small in-memory rate limiter (per user, sliding 60s window) ---
_hits: dict[int, deque] = defaultdict(deque)


def check_rate_limit(user_id: int) -> None:
    now = time.monotonic()
    q = _hits[user_id]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= settings.rate_limit_per_min:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Slow down, try again shortly")
    q.append(now)


def reset_rate_limits() -> None:
    _hits.clear()
