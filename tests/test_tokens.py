import time

import pytest

from smoodl.services.tokens import InvalidTokenError, TokenService


def test_token_round_trip() -> None:
    tokens = TokenService("secret")
    token = tokens.issue(scope="download", subject="file_123", ttl_seconds=60)

    payload = tokens.verify(token, scope="download")

    assert payload.subject == "file_123"
    assert payload.expires_at > int(time.time())


def test_token_rejects_wrong_scope() -> None:
    tokens = TokenService("secret")
    token = tokens.issue(scope="download", subject="file_123", ttl_seconds=60)

    with pytest.raises(InvalidTokenError):
        tokens.verify(token, scope="events")
