"""JWT (HS256) and password hashing built on the standard library only."""
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

PBKDF2_ITERATIONS = 200_000

# "student" sits below "viewer": students see only their own portal,
# not the live classroom dashboard
ROLE_LEVELS = {"student": 0, "viewer": 1, "teacher": 2, "admin": 3}


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(payload: dict, secret: str, expires_minutes: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    body = dict(payload)
    body["iat"] = int(time.time())
    body["exp"] = int(time.time()) + expires_minutes * 60
    signing_input = (_b64url_encode(json.dumps(header, separators=(",", ":")).encode())
                     + "." +
                     _b64url_encode(json.dumps(body, separators=(",", ":")).encode()))
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + _b64url_encode(sig)


def verify_token(token: str, secret: str) -> Optional[dict]:
    try:
        signing_input, _, sig_part = token.rpartition(".")
        if not signing_input:
            return None
        expected = hmac.new(secret.encode(), signing_input.encode(),
                            hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig_part)):
            return None
        header = json.loads(_b64url_decode(signing_input.split(".")[0]))
        if header.get("alg") != "HS256":
            return None
        payload = json.loads(_b64url_decode(signing_input.split(".")[1]))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt,
                                 PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                     bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


def role_satisfies(user_role: str, required_role: str) -> bool:
    return ROLE_LEVELS.get(user_role, 0) >= ROLE_LEVELS.get(required_role, 99)
