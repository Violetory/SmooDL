from urllib.parse import urlparse

from smoodl.domain import MediaPost
from smoodl.errors import SmooDLError
from smoodl.extractors.base import Extractor, ExtractorRejectedError


class ExtractorRegistry:
    def __init__(self, extractors: list[Extractor] | None = None) -> None:
        self._extractors = sorted(
            extractors or [],
            key=lambda extractor: extractor.priority,
            reverse=True,
        )

    def register(self, extractor: Extractor) -> None:
        self._extractors.append(extractor)
        self._extractors.sort(key=lambda item: item.priority, reverse=True)

    def supports(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and any(
            extractor.supports(url) for extractor in self._extractors
        )

    async def inspect(self, url: str) -> MediaPost:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise SmooDLError("UNSUPPORTED_URL", "A valid HTTP(S) URL is required", 422)

        candidates = [extractor for extractor in self._extractors if extractor.supports(url)]
        if not candidates:
            raise SmooDLError(
                "UNSUPPORTED_PLATFORM",
                "No extractor is registered for this URL",
                422,
            )

        last_error: Exception | None = None
        for extractor in candidates:
            try:
                normalized = await extractor.normalize_url(url)
                return await extractor.inspect(normalized)
            except ExtractorRejectedError as error:
                last_error = error
            except SmooDLError as error:
                last_error = error

        if isinstance(last_error, SmooDLError):
            raise last_error
        raise SmooDLError(
            "EXTRACTOR_FAILED",
            str(last_error or "No extractor produced media"),
            422,
            True,
        )

    def platform_descriptions(self) -> list[dict[str, object]]:
        grouped: dict[str, dict[str, object]] = {}
        for extractor in self._extractors:
            for platform in extractor.platforms:
                availability = getattr(extractor, "is_available_for", lambda _platform: True)
                item = grouped.setdefault(
                    platform,
                    {"name": platform, "extractors": [], "available": False},
                )
                extractors = item["extractors"]
                if isinstance(extractors, list) and extractor.name not in extractors:
                    extractors.append(extractor.name)
                item["available"] = bool(item["available"]) or bool(availability(platform))
        return sorted(grouped.values(), key=lambda item: str(item["name"]))
