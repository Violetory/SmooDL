import asyncio
from pathlib import Path

import httpx
import pytest

from smoodl.config import Settings
from smoodl.container import AppContainer
from smoodl.domain import (
    Artifact,
    Job,
    MediaAsset,
    MediaKind,
    MediaPost,
    MediaVariant,
    Transformation,
    WatermarkState,
)
from smoodl.domain.models import new_id
from smoodl.extractors.base import host_matches
from smoodl.extractors.registry import ExtractorRegistry
from smoodl.main import create_app
from smoodl.storage.local import LocalArtifactStorage


class FakeExtractor:
    name = "fake"
    priority = 1000
    platforms = ("youtube",)
    domains = ("youtube.com",)

    def supports(self, url: str) -> bool:
        return host_matches(url, self.domains)

    async def normalize_url(self, url: str) -> str:
        return url

    async def inspect(self, url: str) -> MediaPost:
        kind = MediaKind.VIDEO if url.rstrip("/").endswith("video") else MediaKind.IMAGE
        return MediaPost(
            platform="youtube",
            title="Fixture post",
            kind=kind,
            assets=[
                MediaAsset(
                    index=1,
                    kind=kind,
                    title="Fixture asset",
                    watermark=WatermarkState.NONE,
                    variants=[
                        MediaVariant(
                            url="https://cdn.example/media.bin",
                            filename_hint="fixture.bin",
                            watermark=WatermarkState.NONE,
                        )
                    ],
                )
            ],
        )


class FakeMaterializer:
    def __init__(self, storage: LocalArtifactStorage, source: Path) -> None:
        self._storage = storage
        self._source = source

    async def materialize(
        self,
        job: Job,
        asset: MediaAsset,
        variant: MediaVariant,
    ) -> Artifact:
        artifact_id = new_id("file")
        stored = await self._storage.put_file(
            job_id=job.id,
            artifact_id=artifact_id,
            source=self._source,
            filename="fixture.bin",
        )
        return Artifact(
            id=artifact_id,
            asset_id=asset.id,
            storage_key=stored.key,
            filename="fixture.bin",
            mime_type="application/octet-stream",
            bytes=stored.bytes,
            sha256=stored.sha256,
            transformation=Transformation.NONE,
        )


@pytest.fixture
def test_container(tmp_path: Path) -> AppContainer:
    settings = Settings(
        data_dir=tmp_path,
        public_base_url="http://test",
        signing_secret="test-secret",
        api_key=None,
        shortcut_api_key=None,
    )
    storage = LocalArtifactStorage(settings.artifact_dir)
    source = tmp_path / "fixture.bin"
    source.write_bytes(b"SmooDL fixture")
    return AppContainer.for_testing(
        settings=settings,
        extractors=ExtractorRegistry([FakeExtractor()]),
        materializer=FakeMaterializer(storage, source),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("primary_key", [None, "primary-test-key"])
async def test_shortcut_key_can_be_revoked_independently(
    test_container: AppContainer, primary_key: str | None
) -> None:
    test_container.settings.api_key = primary_key
    test_container.settings.shortcut_api_key = "shortcut-test-key"
    transport = httpx.ASGITransport(app=create_app(test_container))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path in (
            "/job/create", "/job/get", "/job/materialize", "/job/cancel",
            "/job/subscribe", "/file/authorize", "/platform/list",
        ):
            for authorization in (None, "Bearer wrong-key", "shortcut-test-key"):
                headers = {"Authorization": authorization} if authorization else {}
                denied = await client.post(path, json={}, headers=headers)
                assert denied.status_code == 401
        for key in filter(None, (primary_key, "shortcut-test-key")):
            allowed = await client.post(
                "/platform/list", json={}, headers={"Authorization": f"Bearer {key}"}
            )
            assert allowed.status_code == 200
        assert (await client.get("/system/health")).status_code == 200
        test_container.settings.shortcut_api_key = "replacement-test-key"
        revoked = await client.post(
            "/platform/list", json={}, headers={"Authorization": "Bearer shortcut-test-key"}
        )
        assert revoked.status_code == 401
        if primary_key:
            unchanged = await client.post(
                "/platform/list", json={}, headers={"Authorization": f"Bearer {primary_key}"}
            )
            assert unchanged.status_code == 200


async def wait_for_status(
    client: httpx.AsyncClient,
    job_id: str,
    expected: str,
) -> dict[str, object]:
    for _ in range(100):
        response = await client.post("/job/get", json={"job_id": job_id})
        payload = response.json()
        if payload["status"] == expected:
            return payload
        await asyncio.sleep(0.01)
    raise AssertionError(f"Job did not reach {expected}")


@pytest.mark.asyncio
async def test_image_job_selection_and_download(test_container: AppContainer) -> None:
    app = create_app(test_container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/job/create",
            json={"url": "https://youtube.com/image"},
        )
        assert created.status_code == 202
        job_id = created.json()["id"]
        inspected = await wait_for_status(client, job_id, "awaiting_selection")

        started = await client.post(
            "/job/materialize",
            json={
                "job_id": job_id,
                "asset_ids": [inspected["assets"][0]["id"]],
            },
        )
        assert started.status_code == 202
        completed = await wait_for_status(client, job_id, "completed")
        artifact = completed["artifacts"][0]

        authorized = await client.post(
            "/file/authorize",
            json={"artifact_id": artifact["id"]},
        )
        assert authorized.status_code == 200
        download_url = authorized.json()["download_url"]
        downloaded = await client.get(download_url)
        assert downloaded.status_code == 200
        assert downloaded.content == b"SmooDL fixture"

    await test_container.jobs.shutdown()


@pytest.mark.asyncio
async def test_video_job_materializes_automatically(test_container: AppContainer) -> None:
    app = create_app(test_container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/job/create",
            json={"url": "https://youtube.com/video"},
        )
        completed = await wait_for_status(client, created.json()["id"], "completed")

        assert completed["post"]["media_type"] == "video"
        assert len(completed["artifacts"]) == 1

    await test_container.jobs.shutdown()


@pytest.mark.asyncio
async def test_rpc_paths_do_not_embed_identifiers(test_container: AppContainer) -> None:
    app = create_app(test_container)
    paths = set(app.openapi()["paths"])

    assert "/job/create" in paths
    assert "/job/get" in paths
    assert "/file/authorize" in paths
    assert not any("{" in path for path in paths)
    assert not any(path.startswith("/api") or path.startswith("/v1") for path in paths)


@pytest.mark.asyncio
async def test_optional_api_key_protects_rpc_commands(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        public_base_url="http://test",
        signing_secret="test-secret",
        api_key="shortcut-secret",
    )
    storage = LocalArtifactStorage(settings.artifact_dir)
    source = tmp_path / "fixture.bin"
    source.write_bytes(b"fixture")
    container = AppContainer.for_testing(
        settings=settings,
        extractors=ExtractorRegistry([FakeExtractor()]),
        materializer=FakeMaterializer(storage, source),
    )
    app = create_app(container)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        rejected = await client.post("/platform/list", json={})
        accepted = await client.post(
            "/platform/list",
            json={},
            headers={"Authorization": "Bearer shortcut-secret"},
        )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    await container.jobs.shutdown()
