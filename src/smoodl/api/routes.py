import asyncio
import shutil
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import cast

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from smoodl.api.schemas import (
    FileAuthorizeRequest,
    FileAuthorizeResponse,
    HealthResponse,
    JobCancelRequest,
    JobCreateRequest,
    JobGetRequest,
    JobMaterializeRequest,
    JobSubscribeRequest,
    JobView,
    PlatformListResponse,
    SubscriptionResponse,
    VersionResponse,
)
from smoodl.container import AppContainer
from smoodl.errors import NotFoundError, SmooDLError
from smoodl.services.network import open_public_stream
from smoodl.services.tokens import InvalidTokenError

router = APIRouter()


def _container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.container)


@router.post("/job/create", response_model=JobView, status_code=202)
async def create_job(payload: JobCreateRequest, request: Request) -> JobView:
    container = _container(request)
    job = await container.jobs.create(str(payload.url), payload.options())
    return container.presenter.present(job)


@router.post("/job/get", response_model=JobView)
async def get_job(payload: JobGetRequest, request: Request) -> JobView:
    container = _container(request)
    return container.presenter.present(await container.jobs.get(payload.job_id))


@router.post("/job/materialize", response_model=JobView, status_code=202)
async def materialize_job(payload: JobMaterializeRequest, request: Request) -> JobView:
    container = _container(request)
    job = await container.jobs.materialize(payload.job_id, payload.asset_ids)
    return container.presenter.present(job)


@router.post("/job/cancel", response_model=JobView)
async def cancel_job(payload: JobCancelRequest, request: Request) -> JobView:
    container = _container(request)
    return container.presenter.present(await container.jobs.cancel(payload.job_id))


@router.post("/job/subscribe", response_model=SubscriptionResponse)
async def subscribe_job(payload: JobSubscribeRequest, request: Request) -> SubscriptionResponse:
    container = _container(request)
    await container.jobs.get(payload.job_id)
    ttl = container.settings.event_token_ttl_seconds
    token = container.tokens.issue(scope="events", subject=payload.job_id, ttl_seconds=ttl)
    base = container.settings.public_base_url.rstrip("/")
    return SubscriptionResponse(
        events_url=f"{base}/job/events?token={token}",
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
    )


@router.get("/job/events")
async def job_events(request: Request, token: str = Query(min_length=1)) -> StreamingResponse:
    container = _container(request)
    try:
        payload = container.tokens.verify(token, scope="events")
    except InvalidTokenError as error:
        raise SmooDLError("INVALID_TOKEN", str(error), 401) from error
    await container.jobs.get(payload.subject)

    async def events() -> AsyncIterator[str]:
        last_update = None
        heartbeat = 0
        while not await request.is_disconnected():
            job = await container.jobs.get(payload.subject)
            marker = job.updated_at.isoformat()
            if marker != last_update:
                data = container.presenter.present(job).model_dump_json()
                yield f"event: job\ndata: {data}\n\n"
                last_update = marker
                heartbeat = 0
            else:
                heartbeat += 1
                if heartbeat >= 30:
                    yield ": heartbeat\n\n"
                    heartbeat = 0
            if job.status.terminal:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/file/authorize", response_model=FileAuthorizeResponse)
async def authorize_file(
    payload: FileAuthorizeRequest,
    request: Request,
) -> FileAuthorizeResponse:
    container = _container(request)
    if await container.store.find_artifact(payload.artifact_id) is None:
        raise NotFoundError("Artifact")
    ttl = container.settings.download_token_ttl_seconds
    token = container.tokens.issue(
        scope="download",
        subject=payload.artifact_id,
        ttl_seconds=ttl,
    )
    base = container.settings.public_base_url.rstrip("/")
    return FileAuthorizeResponse(
        download_url=f"{base}/file/download?token={token}",
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
    )


@router.get("/file/download")
async def download_file(request: Request, token: str = Query(min_length=1)) -> FileResponse:
    container = _container(request)
    try:
        payload = container.tokens.verify(token, scope="download")
    except InvalidTokenError as error:
        raise SmooDLError("INVALID_TOKEN", str(error), 401) from error
    found = await container.store.find_artifact(payload.subject)
    if found is None:
        raise NotFoundError("Artifact")
    _, artifact = found
    path = container.storage.resolve(artifact.storage_key)
    if not path.is_file():
        raise NotFoundError("Artifact file")
    return FileResponse(
        path,
        media_type=artifact.mime_type,
        filename=artifact.filename,
    )


@router.get("/preview/download")
async def download_preview(request: Request, token: str = Query(min_length=1)) -> StreamingResponse:
    container = _container(request)
    try:
        payload = container.tokens.verify(token, scope="preview")
        job_id, asset_id = payload.subject.split(":", 1)
    except (InvalidTokenError, ValueError) as error:
        raise SmooDLError("INVALID_TOKEN", str(error), 401) from error
    job = await container.jobs.get(job_id)
    asset = next(
        (item for item in (job.post.assets if job.post else []) if item.id == asset_id),
        None,
    )
    if asset is None or not asset.thumbnail_url:
        raise NotFoundError("Preview")
    stream = await open_public_stream(
        asset.thumbnail_url,
        headers=asset.thumbnail_headers,
        timeout_seconds=container.settings.http_timeout_seconds,
    )
    media_type = stream.response.headers.get("content-type", "application/octet-stream").split(
        ";", 1
    )[0]
    headers = {}
    if length := stream.response.headers.get("content-length"):
        headers["Content-Length"] = length
    return StreamingResponse(stream.chunks(), media_type=media_type, headers=headers)


@router.post("/platform/list", response_model=PlatformListResponse)
async def list_platforms(request: Request) -> PlatformListResponse:
    return PlatformListResponse(platforms=_container(request).extractors.platform_descriptions())


@router.get("/system/health", response_model=HealthResponse)
async def system_health(request: Request) -> HealthResponse:
    settings = _container(request).settings
    return HealthResponse(
        status="ok",
        version=settings.version,
        dependencies={
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "ffprobe": shutil.which("ffprobe") is not None,
            "yt-dlp": shutil.which("yt-dlp") is not None,
            "gallery-dl": shutil.which("gallery-dl") is not None,
            "deno": shutil.which("deno") is not None,
        },
    )


@router.get("/system/version", response_model=VersionResponse)
async def system_version(request: Request) -> VersionResponse:
    settings = _container(request).settings
    return VersionResponse(name=settings.app_name, version=settings.version)
