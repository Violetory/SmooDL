import json
import mimetypes
import shutil
from typing import Any

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


class YtDlpExtractor:
    name = "yt-dlp"
    priority = 200
    platforms: tuple[str, ...] = (
        "youtube",
        "tiktok",
        "instagram",
        "x",
        "xiaohongshu",
    )
    domains: tuple[str, ...] = (
        "youtube.com",
        "youtu.be",
        "tiktok.com",
        "instagram.com",
        "x.com",
        "twitter.com",
        "xiaohongshu.com",
        "xhslink.cn",
    )

    def __init__(self, settings: Settings, runner: CommandRunner) -> None:
        self._settings = settings
        self._runner = runner

    def supports(self, url: str) -> bool:
        return host_matches(url, self.domains)

    def is_available_for(self, platform: str) -> bool:
        return shutil.which("yt-dlp") is not None and (
            platform != "youtube" or shutil.which("deno") is not None
        )

    async def normalize_url(self, url: str) -> str:
        return url.strip()

    async def inspect(self, url: str) -> MediaPost:
        if shutil.which("yt-dlp") is None:
            raise DependencyMissingError("yt-dlp")
        platform_hint = _platform_from_url(url)
        if platform_hint == "youtube" and shutil.which("deno") is None:
            raise DependencyMissingError("deno")

        arguments = [
            "--dump-single-json",
            "--skip-download",
            "--no-warnings",
            "--no-playlist",
        ]
        if shutil.which("deno") is not None:
            arguments.extend(("--js-runtimes", "deno"))
        if self._settings.yt_dlp_cookies_file:
            arguments.extend(("--cookies", str(self._settings.yt_dlp_cookies_file)))
        arguments.append(url)

        result = await self._runner.run(
            "yt-dlp",
            *arguments,
            timeout_seconds=self._settings.job_timeout_seconds,
        )
        try:
            info: dict[str, Any] = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise ExtractorRejectedError("yt-dlp returned invalid metadata") from error

        entries = info.get("entries")
        items = [entry for entry in entries if entry] if isinstance(entries, list) else [info]
        assets: list[MediaAsset] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            media_url = str(item.get("webpage_url") or url)
            title = _optional_string(item.get("title"))
            extension = _optional_string(item.get("ext")) or "mkv"
            mime_type = mimetypes.guess_type(f"file.{extension}")[0] or "video/*"
            variant = MediaVariant(
                url=media_url,
                mime_type=mime_type,
                container=extension,
                width=_optional_int(item.get("width")),
                height=_optional_int(item.get("height")),
                fps=_optional_float(item.get("fps")),
                bitrate=_optional_int(item.get("tbr")),
                file_size=_optional_int(item.get("filesize") or item.get("filesize_approx")),
                video_codec=_optional_string(item.get("vcodec")),
                audio_codec=_optional_string(item.get("acodec")),
                watermark=WatermarkState.UNKNOWN,
                strategy=DownloadStrategy.YT_DLP,
                filename_hint=f"{title or item.get('id') or 'video'}.{extension}",
                tool_metadata={
                    "source_id": item.get("id"),
                    "requires_merge": bool(item.get("requested_formats")),
                },
            )
            assets.append(
                MediaAsset(
                    index=index,
                    kind=MediaKind.VIDEO,
                    title=title,
                    thumbnail_url=_optional_string(item.get("thumbnail")),
                    width=variant.width,
                    height=variant.height,
                    variants=[variant],
                )
            )

        if not assets:
            raise ExtractorRejectedError("yt-dlp did not find downloadable video media")

        platform = _optional_string(info.get("extractor_key"))
        return MediaPost(
            platform=(platform or platform_hint).lower(),
            source_id=_optional_string(info.get("id")),
            title=_optional_string(info.get("title")),
            author=_optional_string(info.get("uploader") or info.get("channel")),
            kind=MediaKind.VIDEO,
            assets=assets,
        )


def _platform_from_url(url: str) -> str:
    if host_matches(url, ("youtube.com", "youtu.be")):
        return "youtube"
    if host_matches(url, ("tiktok.com",)):
        return "tiktok"
    if host_matches(url, ("instagram.com",)):
        return "instagram"
    if host_matches(url, ("xiaohongshu.com", "xhslink.cn")):
        return "xiaohongshu"
    return "x"


def _optional_string(value: object) -> str | None:
    return str(value) if value not in (None, "") else None


def _optional_int(value: object) -> int | None:
    try:
        return int(float(str(value))) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    try:
        return float(str(value)) if value is not None else None
    except (TypeError, ValueError):
        return None
