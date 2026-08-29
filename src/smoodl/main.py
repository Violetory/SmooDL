import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from smoodl.api.routes import router
from smoodl.api.schemas import ApiErrorEnvelope, ErrorView
from smoodl.container import AppContainer
from smoodl.errors import SmooDLError


def create_app(container: AppContainer | None = None) -> FastAPI:
    resolved = container or AppContainer.build()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await resolved.jobs.shutdown()

    app = FastAPI(
        title="SmooDL",
        version=resolved.settings.version,
        description="Action-oriented media inspection and download service.",
        lifespan=lifespan,
    )
    app.state.container = resolved
    app.include_router(router)

    @app.middleware("http")
    async def authenticate(request: Request, call_next):  # type: ignore[no-untyped-def]
        api_key = resolved.settings.api_key
        protected = request.method == "POST" and request.url.path in {
            "/job/create",
            "/job/get",
            "/job/materialize",
            "/job/cancel",
            "/job/subscribe",
            "/file/authorize",
            "/platform/list",
        }
        if api_key and protected:
            authorization = request.headers.get("authorization", "")
            expected = f"Bearer {api_key}"
            if not hmac.compare_digest(authorization, expected):
                body = ApiErrorEnvelope(
                    error=ErrorView(
                        code="UNAUTHORIZED",
                        message="A valid bearer token is required",
                        retryable=False,
                    )
                )
                return JSONResponse(status_code=401, content=body.model_dump(mode="json"))
        return await call_next(request)

    @app.exception_handler(SmooDLError)
    async def handle_smoodl_error(_request: Request, error: SmooDLError) -> JSONResponse:
        body = ApiErrorEnvelope(
            error=ErrorView(
                code=error.code,
                message=error.message,
                retryable=error.retryable,
            )
        )
        return JSONResponse(status_code=error.status_code, content=body.model_dump(mode="json"))

    return app


app = create_app()
