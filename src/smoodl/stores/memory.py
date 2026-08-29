import asyncio

from smoodl.domain import Artifact, Job


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()

    async def put(self, job: Job) -> None:
        async with self._lock:
            self._jobs[job.id] = job.model_copy(deep=True)

    async def get(self, job_id: str) -> Job | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy(deep=True) if job else None

    async def find_artifact(self, artifact_id: str) -> tuple[Job, Artifact] | None:
        async with self._lock:
            for job in self._jobs.values():
                for artifact in job.artifacts:
                    if artifact.id == artifact_id:
                        return job.model_copy(deep=True), artifact.model_copy(deep=True)
        return None
