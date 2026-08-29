from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from smoodl.domain import (
    JobOptions,
    JobStatus,
    MediaKind,
    QualityPolicy,
    Transformation,
    WatermarkPolicy,
    WatermarkState,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JobCreateRequest(StrictModel):
    url: HttpUrl
    quality: QualityPolicy = QualityPolicy.BEST_AVAILABLE
    watermark_policy: WatermarkPolicy = WatermarkPolicy.PREFER_CLEAN
    playlist: bool = False

    def options(self) -> JobOptions:
        return JobOptions(
            quality=self.quality,
            watermark_policy=self.watermark_policy,
            playlist=self.playlist,
        )


class JobGetRequest(StrictModel):
    job_id: str


class JobMaterializeRequest(StrictModel):
    job_id: str
    asset_ids: list[str] = Field(min_length=1)
    archive: str = "auto"


class JobCancelRequest(StrictModel):
    job_id: str


class JobSubscribeRequest(StrictModel):
    job_id: str


class FileAuthorizeRequest(StrictModel):
    artifact_id: str


class AssetView(BaseModel):
    id: str
    index: int
    type: MediaKind
    title: str | None
    thumbnail_url: str | None
    width: int | None
    height: int | None
    watermark: WatermarkState


class PostView(BaseModel):
    id: str
    platform: str
    source_id: str | None
    title: str | None
    author: str | None
    media_type: MediaKind


class ArtifactView(BaseModel):
    id: str
    asset_id: str
    filename: str
    mime_type: str
    bytes: int
    sha256: str
    width: int | None
    height: int | None
    video_codec: str | None
    audio_codec: str | None
    transformation: Transformation
    is_reencoded: bool
    save_target: str
    download_url: str
    expires_at: datetime


class ErrorView(BaseModel):
    code: str
    message: str
    retryable: bool


class JobView(BaseModel):
    id: str
    status: JobStatus
    progress: float
    created_at: datetime
    updated_at: datetime
    post: PostView | None
    assets: list[AssetView]
    artifacts: list[ArtifactView]
    error: ErrorView | None


class SubscriptionResponse(BaseModel):
    events_url: str
    expires_at: datetime


class FileAuthorizeResponse(BaseModel):
    download_url: str
    expires_at: datetime


class PlatformListResponse(BaseModel):
    platforms: list[dict[str, object]]


class HealthResponse(BaseModel):
    status: str
    version: str
    dependencies: dict[str, bool]


class VersionResponse(BaseModel):
    name: str
    version: str


class ApiErrorEnvelope(BaseModel):
    error: ErrorView
