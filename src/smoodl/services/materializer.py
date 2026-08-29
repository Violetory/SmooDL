import json
import mimetypes
import shutil
import tempfile
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin

import httpx

from smoodl.config import Settings
from smoodl.domain import (
    Artifact,
    DownloadStrategy,
    Job,
    MediaAsset,
    MediaVariant,
    QualityPolicy,
    Transformation,
)
from smoodl.domain.models import new_id
from smoodl.errors import DependencyMissingError, SmooDLError
from smoodl.services.network import validate_public_url
from smoodl.services.process import CommandRunner
from smoodl.storage.base import ArtifactStorage
from smoodl.storage.local import safe_filename


class Materializer(Protocol):
    async def materialize(
        self,
        job: Job,
        asset: MediaAsset,
        variant: MediaVariant,
    ) -> Artifact: ...


class DefaultMaterializer:
    def __init__(
        self,
        settings: Settings,
        runner: CommandRunner,
        storage: ArtifactStorage,
    ) -> None:
        self._settings = settings
        self._runner = runner
        self._storage = storage
        self._settings.work_dir.mkdir(parents=True, exist_ok=True)

    async def materialize(
        self,
        job: Job,
        asset: MediaAsset,
        variant: MediaVariant,
    ) -> Artifact:
        if variant.strategy == DownloadStrategy.YT_DLP:
            return await self._materialize_with_yt_dlp(job, asset, variant)
        return await self._materialize_direct(job, asset, variant)

    async def _materialize_with_yt_dlp(
        self,
        job: Job,
        asset: MediaAsset,
        variant: MediaVariant,
    ) -> Artifact:
        if shutil.which("yt-dlp") is None:
            raise DependencyMissingError("yt-dlp")
        if job.post and job.post.platform == "youtube" and shutil.which("deno") is None:
            raise DependencyMissingError("deno")

        with tempfile.TemporaryDirectory(dir=self._settings.work_dir) as temporary:
            directory = Path(temporary)
            output = directory / "%(title).180B [%(id)s].%(ext)s"
            arguments = [
                "--no-playlist",
                "--no-progress",
                "--no-warnings",
                "--merge-output-format",
                "mkv",
                "--output",
                str(output),
            ]
            if shutil.which("deno") is not None:
                arguments.extend(("--js-runtimes", "deno"))
            if job.options.quality == QualityPolicy.IOS_COMPATIBLE:
                arguments.extend(
                    (
                        "--format",
                        "bv*[ext=mp4][vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4]",
                        "--merge-output-format",
                        "mp4",
                    )
                )
            if self._settings.yt_dlp_cookies_file:
                arguments.extend(("--cookies", str(self._settings.yt_dlp_cookies_file)))
            arguments.append(job.source_url)
            await self._runner.run(
                "yt-dlp",
                *arguments,
                timeout_seconds=self._settings.job_timeout_seconds,
            )
            media_files = [
                path
                for path in directory.iterdir()
                if path.is_file() and path.suffix not in {".part", ".ytdl", ".json"}
            ]
            if not media_files:
                raise SmooDLError("DOWNLOAD_FAILED", "yt-dlp produced no media file", 502, True)
            source = max(media_files, key=lambda path: path.stat().st_size)
            if source.stat().st_size > self._settings.max_download_bytes:
                raise SmooDLError("FILE_TOO_LARGE", "The downloaded file exceeds the limit", 413)
            return await self._store_artifact(
                job=job,
                asset=asset,
                source=source,
                filename=source.name,
                mime_type=mimetypes.guess_type(source.name)[0] or "application/octet-stream",
                transformation=(
                    Transformation.REMUX
                    if bool(variant.tool_metadata.get("requires_merge"))
                    else Transformation.NONE
                ),
            )

    async def _materialize_direct(
        self,
        job: Job,
        asset: MediaAsset,
        variant: MediaVariant,
    ) -> Artifact:
        with tempfile.TemporaryDirectory(dir=self._settings.work_dir) as temporary:
            directory = Path(temporary)
            filename = safe_filename(variant.filename_hint or f"media-{asset.index}")
            source = directory / filename
            mime_type = await self._download_direct(variant, source)
            return await self._store_artifact(
                job=job,
                asset=asset,
                source=source,
                filename=filename,
                mime_type=mime_type,
                transformation=Transformation.NONE,
            )

    async def _download_direct(self, variant: MediaVariant, destination: Path) -> str:
        current_url = variant.url
        headers = variant.headers
        async with httpx.AsyncClient(timeout=self._settings.http_timeout_seconds) as client:
            for _ in range(6):
                await validate_public_url(current_url)
                async with client.stream(
                    "GET",
                    current_url,
                    headers=headers,
                    follow_redirects=False,
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise SmooDLError(
                                "DOWNLOAD_FAILED",
                                "Media redirect has no location",
                                502,
                            )
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    expected = int(response.headers.get("content-length", "0") or 0)
                    if expected > self._settings.max_download_bytes:
                        raise SmooDLError("FILE_TOO_LARGE", "The media file exceeds the limit", 413)
                    size = 0
                    with destination.open("wb") as handle:
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > self._settings.max_download_bytes:
                                raise SmooDLError(
                                    "FILE_TOO_LARGE",
                                    "The media file exceeds the limit",
                                    413,
                                )
                            handle.write(chunk)
                    return str(
                        response.headers.get(
                            "content-type",
                            "application/octet-stream",
                        ).split(";", 1)[0]
                    )
        raise SmooDLError("DOWNLOAD_FAILED", "Too many media redirects", 502, True)

    async def _store_artifact(
        self,
        *,
        job: Job,
        asset: MediaAsset,
        source: Path,
        filename: str,
        mime_type: str,
        transformation: Transformation,
    ) -> Artifact:
        artifact_id = new_id("file")
        stored = await self._storage.put_file(
            job_id=job.id,
            artifact_id=artifact_id,
            source=source,
            filename=filename,
        )
        metadata = await self._probe(source)
        return Artifact(
            id=artifact_id,
            asset_id=asset.id,
            storage_key=stored.key,
            filename=filename,
            mime_type=mime_type,
            bytes=stored.bytes,
            sha256=stored.sha256,
            width=metadata.get("width"),
            height=metadata.get("height"),
            video_codec=metadata.get("video_codec"),
            audio_codec=metadata.get("audio_codec"),
            transformation=transformation,
            save_target=_save_target(mime_type, metadata),
        )

    async def _probe(self, source: Path) -> dict[str, Any]:
        if shutil.which("ffprobe") is None:
            return {}
        try:
            result = await self._runner.run(
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-of",
                "json",
                str(source),
                timeout_seconds=30,
            )
            data = json.loads(result.stdout)
        except (SmooDLError, json.JSONDecodeError):
            return {}
        metadata: dict[str, Any] = {}
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                metadata["width"] = stream.get("width")
                metadata["height"] = stream.get("height")
                metadata["video_codec"] = stream.get("codec_name")
            elif stream.get("codec_type") == "audio":
                metadata["audio_codec"] = stream.get("codec_name")
        return metadata


def _save_target(mime_type: str, metadata: dict[str, Any]) -> str:
    if mime_type.startswith("image/"):
        return "photos"
    if mime_type in {"video/mp4", "video/quicktime"} and metadata.get("video_codec") in {
        None,
        "h264",
        "hevc",
    }:
        return "photos"
    return "files"
