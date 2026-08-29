from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class JobStatus(StrEnum):
    QUEUED = "queued"
    INSPECTING = "inspecting"
    AWAITING_SELECTION = "awaiting_selection"
    MATERIALIZING = "materializing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

    @property
    def terminal(self) -> bool:
        return self in {
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.EXPIRED,
        }


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    MIXED = "mixed"


class WatermarkState(StrEnum):
    NONE = "none"
    PLATFORM = "platform"
    CREATOR = "creator"
    UNKNOWN = "unknown"


class Transformation(StrEnum):
    NONE = "none"
    REMUX = "remux"
    TRANSCODE = "transcode"


class DownloadStrategy(StrEnum):
    DIRECT = "direct"
    YT_DLP = "yt_dlp"


class QualityPolicy(StrEnum):
    BEST_AVAILABLE = "best_available"
    IOS_COMPATIBLE = "ios_compatible"
    PREFER_MP4 = "prefer_mp4"
    AUDIO_ONLY = "audio_only"
    METADATA_ONLY = "metadata_only"


class WatermarkPolicy(StrEnum):
    PREFER_CLEAN = "prefer_clean"
    REQUIRE_CLEAN = "require_clean"
    ALLOW_ANY = "allow_any"


class JobOptions(BaseModel):
    quality: QualityPolicy = QualityPolicy.BEST_AVAILABLE
    watermark_policy: WatermarkPolicy = WatermarkPolicy.PREFER_CLEAN
    playlist: bool = False


class MediaVariant(BaseModel):
    id: str = Field(default_factory=lambda: new_id("variant"))
    url: str
    mime_type: str | None = None
    container: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    bitrate: int | None = None
    file_size: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    watermark: WatermarkState = WatermarkState.UNKNOWN
    transformation: Transformation = Transformation.NONE
    strategy: DownloadStrategy = DownloadStrategy.DIRECT
    filename_hint: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    tool_metadata: dict[str, Any] = Field(default_factory=dict)


class MediaAsset(BaseModel):
    id: str = Field(default_factory=lambda: new_id("asset"))
    index: int
    kind: MediaKind
    title: str | None = None
    thumbnail_url: str | None = None
    thumbnail_headers: dict[str, str] = Field(default_factory=dict)
    width: int | None = None
    height: int | None = None
    watermark: WatermarkState = WatermarkState.UNKNOWN
    variants: list[MediaVariant] = Field(default_factory=list)


class MediaPost(BaseModel):
    id: str = Field(default_factory=lambda: new_id("post"))
    platform: str
    source_id: str | None = None
    title: str | None = None
    author: str | None = None
    kind: MediaKind
    assets: list[MediaAsset] = Field(default_factory=list)


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: new_id("file"))
    asset_id: str
    storage_key: str
    filename: str
    mime_type: str
    bytes: int
    sha256: str
    width: int | None = None
    height: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    transformation: Transformation = Transformation.NONE
    save_target: str = "files"
    created_at: datetime = Field(default_factory=utc_now)


class JobError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class Job(BaseModel):
    id: str = Field(default_factory=lambda: new_id("job"))
    source_url: str
    options: JobOptions = Field(default_factory=JobOptions)
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0
    post: MediaPost | None = None
    artifacts: list[Artifact] = Field(default_factory=list)
    error: JobError | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()
