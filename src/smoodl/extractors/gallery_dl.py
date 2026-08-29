import mimetypes
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

from smoodl.config import Settings
from smoodl.domain import (
    DownloadStrategy,
    MediaAsset,
    MediaKind,
    MediaPost,
    MediaVariant,
    WatermarkState,
)
from smoodl.errors import DependencyMissingError
from smoodl.extractors.base import ExtractorRejectedError, host_matches
from smoodl.services.process import CommandRunner

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".m3u8"}


class GalleryDlExtractor:
    name = "gallery-dl"
    priority = 100
    platforms: tuple[str, ...] = ("tiktok", "instagram", "x", "pinterest")
    domains: tuple[str, ...] = (
        "tiktok.com",
        "instagram.com",
        "x.com",
        "twitter.com",
        "pinterest.com",
        "pin.it",
    )

    def __init__(self, settings: Settings, runner: CommandRunner) -> None:
        self._settings = settings
        self._runner = runner

    def supports(self, url: str) -> bool:
        return host_matches(url, self.domains)

    def is_available_for(self, _platform: str) -> bool:
        return shutil.which("gallery-dl") is not None

    async def normalize_url(self, url: str) -> str:
        return url.strip()

    async def inspect(self, url: str) -> MediaPost:
        if shutil.which("gallery-dl") is None:
            raise DependencyMissingError("gallery-dl")
        arguments = ["--quiet", "--get-urls"]
        if self._settings.gallery_dl_cookies_file:
            arguments.extend(("--cookies", str(self._settings.gallery_dl_cookies_file)))
        arguments.append(url)
        result = await self._runner.run(
            "gallery-dl",
            *arguments,
            timeout_seconds=self._settings.job_timeout_seconds,
        )
        urls = [line.strip() for line in result.stdout.splitlines() if line.startswith("http")]
        if not urls:
            raise ExtractorRejectedError("gallery-dl did not find downloadable media")

        assets: list[MediaAsset] = []
        kinds: set[MediaKind] = set()
        for index, media_url in enumerate(urls, start=1):
            path = Path(unquote(urlparse(media_url).path))
            kind = MediaKind.VIDEO if path.suffix.lower() in _VIDEO_EXTENSIONS else MediaKind.IMAGE
            kinds.add(kind)
            filename = path.name or f"media-{index}"
            mime_type = mimetypes.guess_type(filename)[0]
            variant = MediaVariant(
                url=media_url,
                mime_type=mime_type,
                container=path.suffix.lstrip(".") or None,
                watermark=WatermarkState.UNKNOWN,
                strategy=DownloadStrategy.DIRECT,
                filename_hint=filename,
            )
            assets.append(
                MediaAsset(
                    index=index,
                    kind=kind,
                    title=f"Media {index}",
                    thumbnail_url=media_url if kind == MediaKind.IMAGE else None,
                    variants=[variant],
                )
            )

        post_kind = next(iter(kinds)) if len(kinds) == 1 else MediaKind.MIXED
        return MediaPost(
            platform=_platform_from_url(url),
            kind=post_kind,
            assets=assets,
        )


def _platform_from_url(url: str) -> str:
    if host_matches(url, ("pinterest.com", "pin.it")):
        return "pinterest"
    if host_matches(url, ("instagram.com",)):
        return "instagram"
    if host_matches(url, ("tiktok.com",)):
        return "tiktok"
    return "x"
