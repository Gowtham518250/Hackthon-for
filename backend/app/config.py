import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_TEMP_DIR = Path(tempfile.gettempdir()) / "deepsearch"


@dataclass(frozen=True)
class Settings:
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    jwt_secret: str = os.getenv("JWT_SECRET", "CHANGE-ME")
    access_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
    refresh_days: int = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./deepsearch.db")

    # Local directory is temporary only. Production persistence comes from
    # S3-compatible object storage.
    upload_dir: str = os.getenv("UPLOAD_DIR", str(DEFAULT_TEMP_DIR))
    local_storage_dir: str = os.getenv(
        "LOCAL_STORAGE_DIR",
        str(BASE_DIR / "storage"),
    )

    # S3-compatible object storage: AWS S3, Cloudflare R2, MinIO, etc.
    storage_backend: str = os.getenv("STORAGE_BACKEND", "local")
    s3_endpoint_url: str = os.getenv("S3_ENDPOINT_URL", "")
    s3_region: str = os.getenv("S3_REGION", "auto")
    s3_bucket: str = os.getenv("S3_BUCKET", "")
    s3_access_key_id: str = os.getenv("S3_ACCESS_KEY_ID", "")
    s3_secret_access_key: str = os.getenv("S3_SECRET_ACCESS_KEY", "")

    # Same Groq setup as Retail Mind.
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

    embedding_model_repo: str = os.getenv(
        "EMBEDDING_MODEL_REPO",
        "Xenova/all-MiniLM-L6-v2",
    )
    redis_url: str = os.getenv("REDIS_URL", "")

    # Transactional email: same HTTPS Brevo configuration used by Retail Mind.
    email_provider: str = os.getenv("EMAIL_PROVIDER", "brevo").strip().lower()
    brevo_api_url: str = os.getenv(
        "BREVO_API_URL",
        "https://api.brevo.com/v3/smtp/email",
    )
    brevo_api_key: str = os.getenv("BREVO_API_KEY", "").strip()
    brevo_sender_email: str = os.getenv("BREVO_SENDER_EMAIL", "").strip()
    brevo_sender_name: str = os.getenv("BREVO_SENDER_NAME", "DeepSearch").strip()
    email_timeout_seconds: float = float(
        os.getenv("EMAIL_HTTP_TIMEOUT_SECONDS", "10")
    )

    debug: bool = os.getenv("DEBUG", "true").lower() == "true"


settings = Settings()
