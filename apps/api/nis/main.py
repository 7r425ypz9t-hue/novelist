"""FastAPI application factory."""

import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import __version__, errors
from .config import get_settings
from .routers import admin, agents, auth, bible, insight, projects, publishing, research

log = logging.getLogger("nis")
STATIC = Path(__file__).resolve().parent / "static"


class RateLimiter:
    """Sliding-window limiter per token/IP. In-process: put a shared limiter (e.g. Redis) in front for
    multi-instance deployments (documented in docs/operations.md)."""

    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window: float = 60.0) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .agents.orchestrator import resume_pending

    try:
        n = resume_pending()
        if n:
            log.info("resumed %s pending agent runs", n)
    except Exception:  # noqa: BLE001 - DB may not be migrated yet on first boot
        log.warning("could not resume pending runs (database not migrated?)")
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Kateb (كاتب) API", version=__version__, lifespan=lifespan,
        description="واجهة برمجية لتطبيق «كاتب» — عربي أولاً، سيادة المؤلف، مقترحات لا تعديلات قسرية.",
        openapi_url="/v1/openapi.json", docs_url="/v1/docs", redoc_url=None,
    )
    errors.install(app)
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "If-Match", "Idempotency-Key"],
        expose_headers=["ETag", "X-Request-ID", "X-Content-SHA256"],
    )
    limiter = RateLimiter()

    @app.middleware("http")
    async def guard(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        path = request.url.path
        if path.startswith("/v1/"):
            auth = request.headers.get("authorization", "")
            key = auth[-24:] if auth else (request.client.host if request.client else "anon")
            is_auth = path.startswith("/v1/auth/login") or path.startswith("/v1/auth/register")
            limit = s.auth_rate_limit_per_minute if is_auth else s.rate_limit_per_minute
            bucket = ("auth:" if is_auth else "api:") + key
            if limit > 0 and not limiter.allow(bucket, limit):
                return JSONResponse({"type": "/problems/rate-limited", "title": "طلبات كثيرة", "status": 429,
                                     "detail": "تجاوزت الحد المسموح؛ أعد المحاولة بعد قليل.", "instance": path},
                                    status_code=429, media_type=errors.PROBLEM_JSON, headers={"Retry-After": "30"})
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if not path.startswith("/v1/docs"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                "font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
            )
        if path.startswith("/v1/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    for r in (auth.router, projects.router, bible.router, research.router, agents.router, publishing.router,
              insight.router, admin.router):
        app.include_router(r)

    @app.get("/v1/health", tags=["system"])
    def health():
        return {"status": "ok", "version": __version__}

    if s.serve_spa and (STATIC / "index.html").exists():
        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            target = (STATIC / path).resolve()
            if path and STATIC in target.parents and target.is_file():
                return FileResponse(target)
            return FileResponse(STATIC / "index.html")

    return app


app = create_app()
