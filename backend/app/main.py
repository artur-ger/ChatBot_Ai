import logging
import time
import uuid
import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.indexing_tasks import router as indexing_tasks_router
from app.api.system import router as system_router
from app.core.config import settings
from app.core.limiter import limiter
from app.db.session import engine
from app.integrations.chroma_store import ChromaVectorStore
from app.observability.logging import configure_logging
from app.observability.metrics import InMemoryMetrics
from app.observability.alerts import send_critical_alert
from app.schemas.chat import ErrorResponse
from app.services.embedding_factory import get_embedding_service
from app.services.llm_client import RuleBasedLlmClient
from app.services.rag_pipeline import RagPipeline
from app.services.retriever import ChromaRetriever
from app.workers import tasks as worker_tasks  # noqa: F401

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    app.state.metrics = InMemoryMetrics()
    embedding_service = get_embedding_service()
    vector_store = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        persist_path=settings.chroma_persist_path,
        collection_name=f"kb_{settings.embedding_model_version}",
    )
    app.state.embedding_service = embedding_service
    app.state.rag_pipeline = RagPipeline(
        retriever=ChromaRetriever(vector_store=vector_store, embedding_service=embedding_service),
        llm_client=RuleBasedLlmClient(),
    )
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    description=(
        "HTTP API for RAG chat and asynchronous document indexing. "
        "All application routes are served under the versioned prefix "
        f"{settings.api_prefix}. Breaking changes will be introduced only "
        "with a new prefix (for example /api/v2) while keeping /api/v1 "
        "stable for integrators."
    ),
)
app.state.limiter = limiter


async def rate_limit_exception_handler(request: Request, exc: Exception) -> Response:
    if isinstance(exc, RateLimitExceeded):
        return _rate_limit_exceeded_handler(request, exc)
    raise exc


app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)
app.add_middleware(SlowAPIMiddleware)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(chat_router, prefix=settings.api_prefix)
app.include_router(documents_router, prefix=settings.api_prefix)
app.include_router(indexing_tasks_router, prefix=settings.api_prefix)
app.include_router(admin_router, prefix=settings.api_prefix)
app.include_router(system_router)

Instrumentator().instrument(app).expose(app, include_in_schema=True)


@app.get("/", include_in_schema=False)
async def frontend_index() -> FileResponse:
    return FileResponse("app/static/index.html")

if settings.otel_exporter_otlp_endpoint:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": settings.app_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


@app.middleware("http")
async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    start = time.perf_counter()
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    logger.info("request_started path=%s method=%s", request.url.path, request.method)
    response = await call_next(request)
    latency_ms = (time.perf_counter() - start) * 1000
    app.state.metrics.observe_ms("request_latency_ms", latency_ms)
    app.state.metrics.inc(f"status_{response.status_code}")
    if response.status_code >= 500:
        app.state.metrics.inc("error_rate")
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_finished path=%s status=%s latency_ms=%.2f",
        request.url.path,
        response.status_code,
        latency_ms,
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s", str(exc))
    asyncio.create_task(
        send_critical_alert(
            title="backend.unhandled_exception",
            details=str(exc),
        )
    )
    err = ErrorResponse(
        error_code="internal_error",
        message="Internal server error",
        retry_allowed=True,
    )
    return JSONResponse(status_code=500, content=err.model_dump())
