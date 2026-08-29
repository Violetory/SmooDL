import asyncio
import hashlib
import re
import shutil
from pathlib import Path

from smoodl.storage.base import StoredFile

_UNSAFE_FILENAME = re.compile(r"[^\w.()\[\] -]+", re.UNICODE)


def safe_filename(value: str, fallback: str = "download") -> str:
    value = value.replace("/", "_").replace("\\", "_").strip()
    value = _UNSAFE_FILENAME.sub("_", value).strip(" .")
    return value[:180] or fallback


class LocalArtifactStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    async def put_file(
        self,
        *,
        job_id: str,
        artifact_id: str,
        source: Path,
        filename: str,
    ) -> StoredFile:
        clean_name = safe_filename(filename)
        relative = Path(job_id) / artifact_id / clean_name
        destination = (self.root / relative).resolve()
        if not destination.is_relative_to(self.root):
            raise ValueError("Artifact path escaped storage root")
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source, destination)
        size, digest = await asyncio.to_thread(_digest_file, destination)
        return StoredFile(
            key=relative.as_posix(),
            path=destination,
            bytes=size,
            sha256=digest,
        )

    def resolve(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Artifact path escaped storage root")
        return path


def _digest_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()
