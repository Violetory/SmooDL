from typing import Protocol

from smoodl.domain import Artifact, Job


class JobStore(Protocol):
    async def put(self, job: Job) -> None: ...

    async def get(self, job_id: str) -> Job | None: ...

    async def find_artifact(self, artifact_id: str) -> tuple[Job, Artifact] | None: ...
