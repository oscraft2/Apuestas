import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64u_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode((raw + padding).encode("ascii"))


@dataclass
class AdminSessionPayload:
    sub: str
    iat: int
    exp: int


def create_admin_session(secret: str, max_age_seconds: int, subject: str = "admin") -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + max_age_seconds,
    }
    body = _b64u_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _b64u_encode(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def verify_admin_session(token: str, secret: str, subject: str = "admin") -> AdminSessionPayload | None:
    if not token or "." not in token or not secret:
        return None
    try:
        body, signature = token.split(".", 1)
        expected = _b64u_encode(
            hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_b64u_decode(body).decode("utf-8"))
        now = int(time.time())
        if payload.get("sub") != subject:
            return None
        if int(payload.get("exp", 0)) <= now:
            return None
        return AdminSessionPayload(
            sub=str(payload.get("sub")),
            iat=int(payload.get("iat", now)),
            exp=int(payload.get("exp", now)),
        )
    except Exception:
        return None
