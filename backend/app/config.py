import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader; real environment variables take precedence."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


class Settings:
    API_KEY: str = _env("API_KEY", "change-me-dev-key")
    DATABASE_URL: str = _env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'classroom.db'}")
    # Comma-separated CORS allowlist
    FRONTEND_ORIGIN: str = _env("FRONTEND_ORIGIN",
                                "http://localhost:5173,http://127.0.0.1:5173")

    @property
    def cors_origins(self) -> list:
        return [o.strip() for o in self.FRONTEND_ORIGIN.split(",") if o.strip()]

    # Camera: integer index ("0") or a video file / RTSP URL
    CAMERA_SOURCE: str = _env("CAMERA_SOURCE", "0")

    TARGET_FPS: int = int(_env("TARGET_FPS", "10"))
    FRAME_BROADCAST_FPS: int = int(_env("FRAME_BROADCAST_FPS", "5"))
    ANALYTICS_BROADCAST_INTERVAL: float = float(_env("ANALYTICS_BROADCAST_INTERVAL", "0.5"))
    SUMMARY_FLUSH_INTERVAL: float = float(_env("SUMMARY_FLUSH_INTERVAL", "10"))
    JPEG_QUALITY: int = int(_env("JPEG_QUALITY", "70"))
    FRAME_WIDTH: int = int(_env("FRAME_WIDTH", "640"))

    # Alert thresholds (spec)
    ABSENCE_ALERT_SECONDS: float = float(_env("ABSENCE_ALERT_SECONDS", "120"))
    LOW_ATTENTION_THRESHOLD: float = float(_env("LOW_ATTENTION_THRESHOLD", "0.3"))
    LOW_ATTENTION_SECONDS: float = float(_env("LOW_ATTENTION_SECONDS", "60"))
    NEGATIVE_EMOTION_CONSECUTIVE: int = int(_env("NEGATIVE_EMOTION_CONSECUTIVE", "3"))
    ALERT_COOLDOWN_SECONDS: float = float(_env("ALERT_COOLDOWN_SECONDS", "120"))

    # WebSocket rate limiting
    WS_MAX_CONNECTIONS: int = int(_env("WS_MAX_CONNECTIONS", "20"))
    WS_MAX_PER_IP: int = int(_env("WS_MAX_PER_IP", "3"))

    # Tracking
    TRACK_LOST_FRAMES: int = int(_env("TRACK_LOST_FRAMES", "30"))
    REID_SIMILARITY: float = float(_env("REID_SIMILARITY", "0.75"))

    # Auth
    JWT_SECRET: str = _env("JWT_SECRET", "change-me-jwt-secret")
    JWT_EXPIRES_MINUTES: int = int(_env("JWT_EXPIRES_MINUTES", "480"))
    ADMIN_USERNAME: str = _env("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = _env("ADMIN_PASSWORD", "admin123")
    # if set, anyone who supplies this code at signup is created as admin
    ADMIN_SIGNUP_CODE: str = _env("ADMIN_SIGNUP_CODE", "")

    # REST rate limiting (per client IP)
    RATE_LIMIT_PER_MINUTE: int = int(_env("RATE_LIMIT_PER_MINUTE", "240"))
    LOGIN_RATE_LIMIT_PER_MINUTE: int = int(_env("LOGIN_RATE_LIMIT_PER_MINUTE", "10"))

    # Hardening
    PRODUCTION: bool = _env("PRODUCTION", "false").lower() in ("1", "true", "yes")
    LOG_FORMAT: str = _env("LOG_FORMAT", "text")  # text | json
    ANALYTICS_CACHE_SECONDS: float = float(_env("ANALYTICS_CACHE_SECONDS", "5"))
    # detection slows to every Nth frame after the scene has been empty a while
    IDLE_DETECT_EVERY: int = int(_env("IDLE_DETECT_EVERY", "3"))
    IDLE_AFTER_FRAMES: int = int(_env("IDLE_AFTER_FRAMES", "50"))


_DEFAULT_SECRETS = {
    "API_KEY": "change-me-dev-key",
    "JWT_SECRET": "change-me-jwt-secret",
    "ADMIN_PASSWORD": "admin123",
}


def validate_settings(s: "Settings") -> list:
    """Returns warnings; raises in PRODUCTION mode when defaults are unsafe."""
    problems = []
    for key, default in _DEFAULT_SECRETS.items():
        if getattr(s, key) == default:
            problems.append(f"{key} is using its insecure default value")
    if not 1 <= s.TARGET_FPS <= 60:
        raise ValueError(f"TARGET_FPS out of range: {s.TARGET_FPS}")
    if not 10 <= s.JPEG_QUALITY <= 100:
        raise ValueError(f"JPEG_QUALITY out of range: {s.JPEG_QUALITY}")
    if s.JWT_EXPIRES_MINUTES < 5:
        raise ValueError("JWT_EXPIRES_MINUTES must be >= 5")
    if s.PRODUCTION and problems:
        raise ValueError("Refusing to start in PRODUCTION mode: "
                         + "; ".join(problems))
    return problems


settings = Settings()
