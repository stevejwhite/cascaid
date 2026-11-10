import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from psychiatry_api.access import AccessBoundary, AccessVerifier
from psychiatry_api.authoring.routes import authoring_router
from psychiatry_api.blueprint_catalogue import BlueprintMatrix, matrix
from psychiatry_api.cases import CaseSummary, load_cases
from psychiatry_api.config import Settings
from psychiatry_api.health import readiness
from psychiatry_api.recordings import recording_router
from psychiatry_api.roleplay.routes import session_router
from psychiatry_api.schemas import ErrorResponse, Health, Readiness, SourceCatalogue, SourceSummary
from psychiatry_api.sources import SourceStatus, load_registry


def create_app(
    settings: Settings | None = None, access_verifier: AccessVerifier | None = None
) -> FastAPI:
    settings = settings or Settings()
    # Production publishes no interactive API documentation; contracts are generated offline.
    hidden = {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(
        title="PsychiatryEduAI CASC", version="0.2.0", **(hidden if settings.production else {})
    )
    # The local runtime serves one request at a time; queue turns rather than overlap them.
    app.include_router(session_router(settings, asyncio.Lock()))
    if not settings.online:
        app.include_router(recording_router(settings))
    # The case editor returns full cases: never mounted in a production profile.
    if settings.authoring_enabled and not settings.production:
        app.include_router(authoring_router(settings))
    if settings.online:
        app.add_middleware(AccessBoundary, settings=settings, verifier=access_verifier)

    @app.get("/health", response_model=Health)
    def health() -> Health:
        return Health()

    @app.get("/api/status", response_model=Readiness)
    async def status() -> Readiness:
        return await readiness(settings)

    @app.get("/ready", response_model=Readiness, responses={503: {"model": Readiness}})
    async def ready() -> JSONResponse:
        result = await readiness(settings)
        return JSONResponse(
            result.model_dump(mode="json"), status_code=200 if result.status == "ready" else 503
        )

    @app.get(
        "/api/cases",
        response_model=tuple[CaseSummary, ...],
        responses={503: {"model": ErrorResponse}},
    )
    def cases() -> tuple[CaseSummary, ...]:
        try:
            return tuple(CaseSummary.of(case) for case in load_cases(settings.cases_path))
        except Exception as error:
            raise HTTPException(503, f"Station cases are invalid: {error}") from error

    @app.get(
        "/api/blueprint", response_model=BlueprintMatrix, responses={503: {"model": ErrorResponse}}
    )
    def blueprint() -> BlueprintMatrix:
        try:
            return matrix(settings.cases_path)
        except Exception as error:
            raise HTTPException(503, "Blueprint catalogue is invalid or unavailable") from error

    @app.get(
        "/api/sources", response_model=SourceCatalogue, responses={503: {"model": ErrorResponse}}
    )
    def sources() -> SourceCatalogue:
        try:
            registry = load_registry(settings.source_registry_path)
        except Exception as error:
            raise HTTPException(503, "Source registry is invalid or unavailable") from error
        summaries = []
        for source in registry.sources:
            if source.status == SourceStatus.BLOCKED:
                state, detail = "blocked", "A licence for the intended use is required."
            elif source.status in {SourceStatus.PENDING_PERMISSION, SourceStatus.PENDING_REUSE}:
                state, detail = "awaiting_permission", "Reuse review or permission is outstanding."
            elif source.ingestion_enabled:
                state, detail = (
                    ("in_use", "Original fictional cases.")
                    if source.category == "fixture"
                    else ("in_use", "Station structure only; no full text is indexed.")
                )
            else:
                state, detail = "not_used", "Not used by the CASC proof of concept."
            summaries.append(SourceSummary(source=source, access_state=state, detail=detail))
        return SourceCatalogue(sources=tuple(summaries))

    return app


app = create_app()
