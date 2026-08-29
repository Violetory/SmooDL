import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from smoodl.domain import Job, JobError, JobOptions, JobStatus, MediaKind
from smoodl.errors import InvalidStateError, NotFoundError, SmooDLError
from smoodl.extractors.registry import ExtractorRegistry
from smoodl.services.materializer import Materializer
from smoodl.services.selector import VariantSelector
from smoodl.stores.base import JobStore

logger = logging.getLogger(__name__)


class JobService:
    def __init__(
        self,
        store: JobStore,
        extractors: ExtractorRegistry,
        selector: VariantSelector,
        materializer: Materializer,
    ) -> None:
        self._store = store
        self._extractors = extractors
        self._selector = selector
        self._materializer = materializer
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def create(self, source_url: str, options: JobOptions) -> Job:
        if not self._extractors.supports(source_url):
            raise SmooDLError(
                "UNSUPPORTED_PLATFORM",
                "No extractor is registered for this URL",
                422,
            )
        job = Job(source_url=source_url, options=options)
        await self._store.put(job)
        self._schedule(job.id, self._inspect(job.id))
        return job

    async def get(self, job_id: str) -> Job:
        job = await self._store.get(job_id)
        if job is None:
            raise NotFoundError("Job")
        return job

    async def materialize(self, job_id: str, asset_ids: list[str]) -> Job:
        job = await self.get(job_id)
        if job.status != JobStatus.AWAITING_SELECTION or job.post is None:
            raise InvalidStateError("The job is not waiting for media selection")
        known_ids = {asset.id for asset in job.post.assets}
        selected = list(dict.fromkeys(asset_ids))
        if not selected or not set(selected).issubset(known_ids):
            raise SmooDLError("INVALID_ASSET_SELECTION", "One or more asset IDs are invalid", 422)
        job.status = JobStatus.MATERIALIZING
        job.progress = 0.5
        job.touch()
        await self._store.put(job)
        self._schedule(job.id, self._materialize(job.id, selected))
        return job

    async def cancel(self, job_id: str) -> Job:
        job = await self.get(job_id)
        if job.status.terminal:
            raise InvalidStateError("A terminal job cannot be cancelled")
        task = self._tasks.get(job_id)
        if task:
            task.cancel()
        job.status = JobStatus.CANCELLED
        job.touch()
        await self._store.put(job)
        return job

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _inspect(self, job_id: str) -> None:
        try:
            job = await self.get(job_id)
            job.status = JobStatus.INSPECTING
            job.progress = 0.1
            job.touch()
            await self._store.put(job)

            post = await self._extractors.inspect(job.source_url)
            if not post.assets:
                raise SmooDLError(
                    "EXTRACTOR_FAILED",
                    "The post contains no downloadable media",
                    422,
                )
            job = await self.get(job_id)
            if job.status == JobStatus.CANCELLED:
                return
            job.post = post
            job.progress = 0.4
            if all(asset.kind == MediaKind.VIDEO for asset in post.assets):
                job.status = JobStatus.MATERIALIZING
                await self._store.put(job)
                await self._materialize(job.id, [asset.id for asset in post.assets])
            else:
                job.status = JobStatus.AWAITING_SELECTION
                job.touch()
                await self._store.put(job)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self._fail(job_id, error)

    async def _materialize(self, job_id: str, asset_ids: list[str]) -> None:
        try:
            job = await self.get(job_id)
            if job.post is None:
                raise InvalidStateError("The job has no inspected post")
            assets = [asset for asset in job.post.assets if asset.id in set(asset_ids)]
            artifacts = []
            for index, asset in enumerate(assets, start=1):
                latest = await self.get(job_id)
                if latest.status == JobStatus.CANCELLED:
                    return
                variant = self._selector.select(asset.variants, job.options)
                artifacts.append(await self._materializer.materialize(job, asset, variant))
                job.progress = 0.5 + (index / len(assets)) * 0.5
                job.touch()
                await self._store.put(job)
            job.artifacts.extend(artifacts)
            job.status = JobStatus.COMPLETED
            job.progress = 1
            job.touch()
            await self._store.put(job)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self._fail(job_id, error)

    async def _fail(self, job_id: str, error: Exception) -> None:
        logger.exception("Job %s failed", job_id, exc_info=error)
        job = await self._store.get(job_id)
        if job is None or job.status == JobStatus.CANCELLED:
            return
        if isinstance(error, SmooDLError):
            job.error = JobError(
                code=error.code,
                message=error.message,
                retryable=error.retryable,
            )
        else:
            job.error = JobError(
                code="INTERNAL_ERROR",
                message="The job failed unexpectedly",
                retryable=True,
            )
        job.status = JobStatus.FAILED
        job.touch()
        await self._store.put(job)

    def _schedule(self, job_id: str, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coroutine, name=f"smoodl-{job_id}")
        self._tasks[job_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(job_id, None))
