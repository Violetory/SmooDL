from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredFile:
    key: str
    path: Path
    bytes: int
    sha256: str


class ArtifactStorage(Protocol):
    async def put_file(
        self,
        *,
        job_id: str,
        artifact_id: str,
        source: Path,
        filename: str,
    ) -> StoredFile: ...

    def resolve(self, key: str) -> Path: ...
