from datetime import UTC, datetime, timedelta

from smoodl.api.schemas import ArtifactView, AssetView, ErrorView, JobView, PostView
from smoodl.config import Settings
from smoodl.domain import Job, Transformation
from smoodl.services.tokens import TokenService


class JobPresenter:
    def __init__(self, settings: Settings, tokens: TokenService) -> None:
        self._settings = settings
        self._tokens = tokens

    def present(self, job: Job) -> JobView:
        base = self._settings.public_base_url.rstrip("/")
        assets: list[AssetView] = []
        if job.post:
            for asset in job.post.assets:
                thumbnail_url = None
                if asset.thumbnail_url:
                    token = self._tokens.issue(
                        scope="preview",
                        subject=f"{job.id}:{asset.id}",
                        ttl_seconds=self._settings.preview_token_ttl_seconds,
                    )
                    thumbnail_url = f"{base}/preview/download?token={token}"
                assets.append(
                    AssetView(
                        id=asset.id,
                        index=asset.index,
                        type=asset.kind,
                        title=asset.title,
                        thumbnail_url=thumbnail_url,
                        width=asset.width,
                        height=asset.height,
                        watermark=asset.watermark,
                    )
                )

        expires_at = datetime.now(UTC) + timedelta(
            seconds=self._settings.download_token_ttl_seconds
        )
        artifacts = []
        for artifact in job.artifacts:
            token = self._tokens.issue(
                scope="download",
                subject=artifact.id,
                ttl_seconds=self._settings.download_token_ttl_seconds,
            )
            artifacts.append(
                ArtifactView(
                    id=artifact.id,
                    asset_id=artifact.asset_id,
                    filename=artifact.filename,
                    mime_type=artifact.mime_type,
                    bytes=artifact.bytes,
                    sha256=artifact.sha256,
                    width=artifact.width,
                    height=artifact.height,
                    video_codec=artifact.video_codec,
                    audio_codec=artifact.audio_codec,
                    transformation=artifact.transformation,
                    is_reencoded=artifact.transformation == Transformation.TRANSCODE,
                    save_target=artifact.save_target,
                    download_url=f"{base}/file/download?token={token}",
                    expires_at=expires_at,
                )
            )

        return JobView(
            id=job.id,
            status=job.status,
            progress=job.progress,
            created_at=job.created_at,
            updated_at=job.updated_at,
            post=(
                PostView(
                    id=job.post.id,
                    platform=job.post.platform,
                    source_id=job.post.source_id,
                    title=job.post.title,
                    author=job.post.author,
                    media_type=job.post.kind,
                )
                if job.post
                else None
            ),
            assets=assets,
            artifacts=artifacts,
            error=(
                ErrorView(
                    code=job.error.code,
                    message=job.error.message,
                    retryable=job.error.retryable,
                )
                if job.error
                else None
            ),
        )
