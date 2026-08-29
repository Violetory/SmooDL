import asyncio
import ipaddress
import socket
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from smoodl.errors import SmooDLError


async def validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SmooDLError("UNSUPPORTED_URL", "A valid HTTP(S) media URL is required", 422)
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as error:
        raise SmooDLError(
            "DOWNLOAD_FAILED",
            "The media host could not be resolved",
            502,
            True,
        ) from error

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise SmooDLError(
                "UNSAFE_MEDIA_URL",
                "The media URL resolves to a non-public address",
                422,
            )


@dataclass(slots=True)
class PublicStream:
    client: httpx.AsyncClient
    response: httpx.Response

    async def chunks(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self.response.aiter_bytes():
                yield chunk
        finally:
            await self.response.aclose()
            await self.client.aclose()


async def open_public_stream(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 60,
) -> PublicStream:
    client = httpx.AsyncClient(timeout=timeout_seconds)
    current_url = url
    try:
        for _ in range(6):
            await validate_public_url(current_url)
            request = client.build_request("GET", current_url, headers=headers)
            response = await client.send(request, stream=True)
            if response.is_redirect:
                location = response.headers.get("location")
                await response.aclose()
                if not location:
                    raise SmooDLError("DOWNLOAD_FAILED", "Media redirect has no location", 502)
                from urllib.parse import urljoin

                current_url = urljoin(current_url, location)
                continue
            response.raise_for_status()
            return PublicStream(client=client, response=response)
        raise SmooDLError("DOWNLOAD_FAILED", "Too many media redirects", 502, True)
    except Exception:
        await client.aclose()
        raise
