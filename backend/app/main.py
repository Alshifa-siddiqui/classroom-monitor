import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.auth_routes import router as auth_router, seed_admin
from .api.routes import router
from .api.websocket import live_endpoint, manager
from .config import settings, validate_settings
from .database import init_db
from .security import client_ip, rest_limiter

log = logging.getLogger("app")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    if settings.LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    for warning in validate_settings(settings):
        log.warning("CONFIG: %s", warning)
    init_db()
    seed_admin()
    app.state.pipeline = None
    log.info("startup complete (production=%s)", settings.PRODUCTION)
    yield
    pipeline = getattr(app.state, "pipeline", None)
    if pipeline is not None and pipeline.running:
        log.info("shutdown: stopping pipeline")
        await pipeline.stop()
    await manager.shutdown()
    log.info("shutdown complete")


app = FastAPI(title="Classroom Monitor", version="2.0.0", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["X-API-Key", "Content-Type", "Authorization"],
)


@app.middleware("http")
async def request_guard(request: Request, call_next):
    """Per-IP rate limiting + request logging."""
    if request.url.path != "/health":
        if not rest_limiter.allow(client_ip(request)):
            return JSONResponse(status_code=429,
                                content={"detail": "Rate limit exceeded"})
    start = time.time()
    response = await call_next(request)
    if request.url.path != "/health":
        log.info("%s %s -> %d (%.0fms)", request.method, request.url.path,
                 response.status_code, (time.time() - start) * 1000)
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500,
                        content={"detail": "Internal server error"})


app.include_router(auth_router)
app.include_router(router)


@app.websocket("/live")
async def live(websocket: WebSocket):
    await live_endpoint(websocket)


@app.get("/health")
def health():
    """Liveness: the process is up and serving."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness: database reachable and CV models present."""
    from sqlalchemy import text

    from .config import MODELS_DIR
    from .database import engine

    checks = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
    checks["face_detector"] = ("ok" if (MODELS_DIR / "face_detection_yunet_2023mar.onnx").exists()
                               or (MODELS_DIR / "deploy.prototxt").exists() else "fallback")
    checks["face_recognition"] = ("ok" if (MODELS_DIR / "face_recognition_sface_2021dec.onnx").exists()
                                  else "fallback")
    checks["emotion_model"] = ("ok" if (MODELS_DIR / "emotion-ferplus-8.onnx").exists()
                               else "fallback")
    status_code = 200 if checks["database"] == "ok" else 503
    return JSONResponse(status_code=status_code,
                        content={"status": "ready" if status_code == 200 else "degraded",
                                 "checks": checks})


# Serve the built React app from the backend itself (single-process deploy).
# Mounted LAST so every API route and the WebSocket are matched first; the
# SPA is served for the root path. Only active once `npm run build` has run.
from pathlib import Path  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if (_DIST / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="spa")
    log.info("Serving frontend from %s", _DIST)
else:
    log.warning("frontend/dist not found — run 'npm run build' to serve the UI "
                "from the backend (API still works on this port)")
