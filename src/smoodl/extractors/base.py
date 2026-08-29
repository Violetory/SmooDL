from typing import Protocol
from urllib.parse import urlparse

from smoodl.domain import MediaPost


class ExtractorRejectedError(Exception):
    """Raised when an extractor cannot produce media for a supported URL."""


class Extractor(Protocol):
    name: str
    priority: int
    platforms: tuple[str, ...]
    domains: tuple[str, ...]

    def supports(self, url: str) -> bool: ...

    async def normalize_url(self, url: str) -> str: ...

    async def inspect(self, url: str) -> MediaPost: ...


def host_matches(url: str, domains: tuple[str, ...]) -> bool:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)
