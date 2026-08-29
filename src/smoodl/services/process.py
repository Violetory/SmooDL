import asyncio
import shutil
from dataclasses import dataclass

from smoodl.errors import DependencyMissingError, SmooDLError


@dataclass(frozen=True, slots=True)
class CommandResult:
    stdout: str
    stderr: str


class CommandRunner:
    async def run(
        self,
        executable: str,
        *arguments: str,
        timeout_seconds: int,
    ) -> CommandResult:
        path = shutil.which(executable)
        if path is None:
            raise DependencyMissingError(executable)

        process = await asyncio.create_subprocess_exec(
            path,
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except TimeoutError as error:
            process.kill()
            await process.wait()
            raise SmooDLError(
                code="EXTRACTOR_TIMEOUT",
                message=f"{executable} exceeded the execution timeout",
                status_code=504,
                retryable=True,
            ) from error

        decoded_stdout = stdout.decode(errors="replace")
        decoded_stderr = stderr.decode(errors="replace")
        if process.returncode != 0:
            message = decoded_stderr.strip().splitlines()[-1:] or [f"{executable} failed"]
            raise SmooDLError(
                code="EXTRACTOR_FAILED",
                message=message[0][:500],
                status_code=422,
                retryable=True,
            )
        return CommandResult(stdout=decoded_stdout, stderr=decoded_stderr)
