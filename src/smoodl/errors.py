from dataclasses import dataclass


@dataclass(slots=True)
class SmooDLError(Exception):
    code: str
    message: str
    status_code: int = 400
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


class DependencyMissingError(SmooDLError):
    def __init__(self, dependency: str) -> None:
        super().__init__(
            code="DEPENDENCY_MISSING",
            message=f"Required runtime dependency is not installed: {dependency}",
            status_code=503,
            retryable=False,
        )


class NotFoundError(SmooDLError):
    def __init__(self, resource: str) -> None:
        super().__init__(
            code="NOT_FOUND",
            message=f"{resource} was not found",
            status_code=404,
            retryable=False,
        )


class InvalidStateError(SmooDLError):
    def __init__(self, message: str) -> None:
        super().__init__(
            code="INVALID_JOB_STATE",
            message=message,
            status_code=409,
            retryable=False,
        )
