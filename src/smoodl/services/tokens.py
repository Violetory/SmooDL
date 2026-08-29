import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any


class InvalidTokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TokenPayload:
    scope: str
    subject: str
    expires_at: int


class TokenService:
    def __init__(self, secret: str) -> None:
        self._secret = secret.encode()

    def issue(self, *, scope: str, subject: str, ttl_seconds: int) -> str:
        payload = {
            "scope": scope,
            "subject": subject,
            "exp": int(time.time()) + ttl_seconds,
        }
        encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        signature = _encode(hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest())
        return f"{encoded}.{signature}"

    def verify(self, token: str, *, scope: str) -> TokenPayload:
        try:
            encoded, signature = token.split(".", 1)
            expected = _encode(hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(signature, expected):
                raise InvalidTokenError("Invalid token signature")
            data: dict[str, Any] = json.loads(_decode(encoded))
            if data.get("scope") != scope:
                raise InvalidTokenError("Invalid token scope")
            expires_at = int(data["exp"])
            if expires_at < int(time.time()):
                raise InvalidTokenError("Token has expired")
            return TokenPayload(
                scope=str(data["scope"]),
                subject=str(data["subject"]),
                expires_at=expires_at,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            if isinstance(error, InvalidTokenError):
                raise
            raise InvalidTokenError("Malformed token") from error


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
