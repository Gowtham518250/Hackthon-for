import uuid
import hashlib
import httpx
import logging
import os
import re
import time
import tempfile
import threading
from collections import defaultdict, deque
from datetime import timedelta, timezone
from pathlib import Path

import jwt
from fastapi import BackgroundTasks, FastAPI, UploadFile, File, Depends, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from .config import settings
from .db import init_db, one, all_, exe, jd, jl, now, is_postgres
from .security import hash_password, verify_password, create_token, decode
from .email_service import send_email, otp_email
from .otp import (
    OTP_EXPIRE_MINUTES,
    OTP_MAX_ATTEMPTS,
    OTP_RESEND_SECONDS,
    hash_otp,
    new_otp,
    parse_iso,
    utcnow,
    iso,
)
from .ingest import extract
from .chunking import chunk_document
from .search import search, bump_search_version
from .ai_service import answer_with_guardrails
from .storage import storage
from .embeddings import embed_texts, embedding_status
from .vector_index import add_embeddings
from .guardrails import (
    GuardrailViolation,
    MAX_UPLOAD_BYTES,
    guard_ai_query,
    inspect_zip_container,
    validate_query,
    validate_upload,
)
from .evaluation import run_benchmark, corpus_snapshot, compare_snapshots
from .job_queue import enqueue_job, start_worker, worker_status

logger = logging.getLogger("deepsearch")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="DeepSearch API", version="1.3.0")

# Render can expose the static site under the primary hostname while an
# environment variable may still contain an older/custom origin. Keep the
# configured origin, the current production hostname, local development, and
# other Render HTTPS hosts explicitly allowed so browser fetches never fail
# before reaching FastAPI.
_ALLOWED_ORIGINS = {
    settings.frontend_origin.rstrip("/"),
    "https://hackthon-for.onrender.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}
_ALLOWED_ORIGIN_REGEX = r"https://[a-z0-9-]+(?:-[a-z0-9-]+)*\.onrender\.com"

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(origin for origin in _ALLOWED_ORIGINS if origin),
    allow_origin_regex=_ALLOWED_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
if settings.storage_backend.lower() == "local":
    Path(settings.local_storage_dir).mkdir(parents=True, exist_ok=True)

_RATE: dict[str, deque[float]] = defaultdict(deque)


def _wake_ingestion_service() -> None:
    hostname = os.getenv("INGESTION_WORKER_EXTERNAL_HOST", "").strip()
    token = os.getenv("INGESTION_WORKER_WAKE_TOKEN", "").strip()
    if not hostname:
        logger.warning("Ingestion worker external hostname is not configured")
        return

    try:
        # Free Render web services cannot receive private-network traffic, but
        # they do wake when their public URL receives an HTTP request. Keep
        # this request best-effort: the queued Redis job remains durable while
        # the worker spins up.
        headers = {"X-Worker-Wake-Token": token} if token else {}
        with httpx.Client(timeout=2.5, follow_redirects=True) as client:
            response = client.get(f"https://{hostname}/wake", headers=headers)
            logger.info(
                "Ingestion worker wake request status=%s",
                response.status_code,
            )
    except Exception as exc:
        logger.info(
            "Ingestion worker wake-up request did not complete immediately: %s",
            exc,
        )


def rate_limit(request: Request, bucket: str, limit: int) -> None:
    now_ts = __import__("time").time()
    key = f"{bucket}:{request.client.host if request.client else 'unknown'}"
    q = _RATE[key]
    while q and now_ts - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(
            429,
            "Too many requests. Please wait a minute and try again.",
        )
    q.append(now_ts)


@app.on_event("startup")
def startup():
    # The ingestion worker runs as a separate Render background worker so
    # OCR/embedding memory spikes cannot restart the public API process.
    init_db()


class Register(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class Login(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class Query(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=20, ge=1, le=50)


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = None
    file_id: str | None = None


class AIAnswerRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=8, ge=1, le=12)


class DeepSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=20, ge=1, le=20)


class VerifyRegistrationRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6)


class VerifyResetRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    reset_token: str = Field(min_length=20)
    new_password: str = Field(min_length=8, max_length=128)


async def user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentication required")
    try:
        p = decode(authorization.split(" ", 1)[1].strip(), "access")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")
    u = one("SELECT * FROM users WHERE id=?", (p["sub"],))
    if not u:
        raise HTTPException(401, "User not found")
    return u


@app.get("/")
def root_health():
    return {"service": "deepsearch", "status": "ok"}


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "deepsearch",
        "version": "1.3.1",
        "cors": {
            "configured_frontend_origin": settings.frontend_origin,
            "production_origin": "https://hackthon-for.onrender.com",
        },
        "database": "postgresql" if is_postgres() else "sqlite",
        "storage": storage.backend,
        "embeddings": embedding_status(),
        "retrieval": "hybrid-bm25-faiss",
        "guardrails": {
            "prompt_injection": True,
            "grounded_answers": True,
            "citation_validation": True,
            "secret_redaction": True,
            "upload_limits": True,
            "rate_limits": True,
            "llm_provider": "groq",
            "llm_model": settings.groq_model,
            "email_provider": settings.email_provider,
            "email_configured": bool(
                settings.email_provider == "brevo"
                and settings.brevo_api_key
                and settings.brevo_sender_email
            ),
            "email_missing": (
                [
                    name
                    for name, value in (
                        ("BREVO_API_KEY", settings.brevo_api_key),
                        ("BREVO_SENDER_EMAIL", settings.brevo_sender_email),
                    )
                    if not value
                ]
                if settings.email_provider == "brevo"
                else []
            ),
            "otp": "email_otp_10m_5_attempts",
        },
        "ingestion_worker": worker_status(),
    }


@app.post("/api/auth/register")
def register(b: Register, request: Request):
    rate_limit(request, "register", 10)
    email = b.email.lower().strip()

    existing = one(
        "SELECT * FROM users WHERE email=?",
        (email,),
    )

    if existing:
        if bool(existing.get("is_verified", 0)):
            raise HTTPException(
                409,
                "This email is already registered. Please sign in.",
            )

        # A previous registration may have created an unverified account.
        # Reuse it and issue a fresh verification OTP rather than trapping
        # the user behind an "email already exists" error.
        _create_and_send_otp(
            existing["id"],
            email,
            "EMAIL_VERIFICATION",
        )
        return {
            "message": "Your account already exists but is not verified. A fresh verification OTP has been sent.",
            "verification_required": True,
            "email": email,
            "redirect": "/check-email",
        }

    uid = str(uuid.uuid4())

    exe(
        "INSERT INTO users VALUES(?,?,?,?,?,?)",
        (
            uid,
            email,
            b.full_name.strip(),
            hash_password(b.password),
            0,
            now(),
        ),
    )

    try:
        _create_and_send_otp(
            uid,
            email,
            "EMAIL_VERIFICATION",
        )
    except Exception:
        # Do not leave an unusable unverified account behind when the
        # configured email provider is unavailable.
        try:
            exe("DELETE FROM users WHERE id=?", (uid,))
        except Exception:
            logger.exception("Could not roll back failed registration")
        raise

    return {
        "message": "Account created. A 6-digit verification OTP has been sent.",
        "verification_required": True,
        "email": email,
        "redirect": "/check-email",
    }


@app.post("/api/auth/login")
def login(b: Login, request: Request):
    rate_limit(request, "login", 8)
    u = one("SELECT * FROM users WHERE email=?", (b.email.lower(),))
    if not u or not verify_password(b.password, u["password_hash"]):
        raise HTTPException(401, "Invalid credentials")

    if not bool(u.get("is_verified", 0)):
        raise HTTPException(
            403,
            "Please verify your email before signing in.",
        )

    access, _, _ = create_token(
        u["id"],
        "access",
        timedelta(minutes=settings.access_minutes),
    )
    return {
        "access_token": access,
        "token_type": "bearer",
        "user": {
            "id": u["id"],
            "email": u["email"],
            "full_name": u["full_name"],
        },
    }


def _find_latest_otp(user_id: str, purpose: str):
    return one(
        """
        SELECT * FROM otp_challenges
        WHERE user_id=? AND purpose=? AND used=0
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (user_id, purpose),
    )


def _create_and_send_otp(
    user_id: str,
    email: str,
    purpose: str,
) -> bool:
    now_dt = utcnow()
    existing = _find_latest_otp(user_id, purpose)

    if existing:
        try:
            age = (now_dt - parse_iso(existing["created_at"])).total_seconds()
            if age < OTP_RESEND_SECONDS:
                raise HTTPException(
                    429,
                    f"Please wait {max(1, int(OTP_RESEND_SECONDS - age))} seconds before requesting another OTP.",
                )
        except HTTPException:
            raise
        except Exception:
            pass

    otp = new_otp()
    subject, body = otp_email(
        otp,
        "Email Verification" if purpose == "EMAIL_VERIFICATION" else "Password Reset",
    )

    logger.info(
        "OTP email requested purpose=%s recipient=%s provider=%s",
        purpose,
        email,
        settings.email_provider,
    )

    if not send_email(email, subject, body):
        logger.error(
            "OTP email was not accepted by the configured provider purpose=%s recipient=%s",
            purpose,
            email,
        )
        raise HTTPException(
            503,
            "We could not send the OTP email. Please try Resend OTP and check the backend email delivery logs.",
        )

    logger.info(
        "OTP email accepted by provider purpose=%s recipient=%s",
        purpose,
        email,
    )

    exe(
        """
        UPDATE otp_challenges
        SET used=1
        WHERE user_id=? AND purpose=? AND used=0
        """,
        (user_id, purpose),
    )

    exe(
        """
        INSERT INTO otp_challenges
            (id,user_id,email,purpose,otp_hash,expires_at,attempts,used,created_at,
             reset_jti,reset_expires_at,reset_used)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            str(uuid.uuid4()),
            user_id,
            email,
            purpose,
            hash_otp(otp),
            iso(now_dt + timedelta(minutes=OTP_EXPIRE_MINUTES)),
            0,
            0,
            iso(now_dt),
            None,
            None,
            0,
        ),
    )
    return True


@app.post("/api/auth/verify-registration")
def verify_registration(data: VerifyRegistrationRequest):
    normalized = str(data.email).lower().strip()
    user_row = one("SELECT * FROM users WHERE email=?", (normalized,))
    if not user_row:
        raise HTTPException(404, "Account not found.")

    challenge = _find_latest_otp(user_row["id"], "EMAIL_VERIFICATION")
    if not challenge:
        raise HTTPException(400, "No active verification OTP. Request a new OTP.")

    expires_at = parse_iso(challenge["expires_at"])
    if utcnow() > expires_at:
        exe("UPDATE otp_challenges SET used=1 WHERE id=?", (challenge["id"],))
        raise HTTPException(400, "OTP expired. Request a new OTP.")

    attempts = int(challenge.get("attempts") or 0)
    if attempts >= OTP_MAX_ATTEMPTS:
        exe("UPDATE otp_challenges SET used=1 WHERE id=?", (challenge["id"],))
        raise HTTPException(429, "Too many incorrect OTP attempts. Request a new OTP.")

    if hash_otp(data.otp) != challenge["otp_hash"]:
        exe(
            "UPDATE otp_challenges SET attempts=attempts+1 WHERE id=?",
            (challenge["id"],),
        )
        raise HTTPException(400, "Invalid OTP.")

    exe(
        "UPDATE users SET is_verified=1 WHERE id=?",
        (user_row["id"],),
    )
    exe(
        "UPDATE otp_challenges SET used=1 WHERE id=?",
        (challenge["id"],),
    )

    access, _, _ = create_token(
        user_row["id"],
        "access",
        timedelta(minutes=settings.access_minutes),
    )

    return {
        "message": "Email verified successfully.",
        "access_token": access,
        "token_type": "bearer",
        "user": {
            "id": user_row["id"],
            "email": user_row["email"],
            "full_name": user_row["full_name"],
        },
    }


class ResendRegistrationOtpRequest(BaseModel):
    email: EmailStr


@app.post("/api/auth/resend-registration-otp")
def resend_registration_otp(data: ResendRegistrationOtpRequest, request: Request):
    rate_limit(request, "registration_otp", 6)
    normalized = str(data.email).lower().strip()
    user_row = one("SELECT * FROM users WHERE email=?", (normalized,))
    if not user_row:
        raise HTTPException(404, "Account not found.")

    if bool(user_row.get("is_verified", 0)):
        return {"message": "Email is already verified.", "already_verified": True}

    _create_and_send_otp(user_row["id"], normalized, "EMAIL_VERIFICATION")
    return {
        "message": "A new verification OTP has been sent.",
        "email_sent": True,
    }


@app.post("/api/auth/forgot-password")
def forgot_password(data: ForgotPasswordRequest, request: Request):
    rate_limit(request, "forgot_password", 6)
    normalized = str(data.email).lower().strip()
    user_row = one("SELECT * FROM users WHERE email=?", (normalized,))

    # Match a production-safe generic response: do not reveal whether the
    # email exists.
    if user_row:
        _create_and_send_otp(user_row["id"], normalized, "PASSWORD_RESET")

    return {
        "message": "If an account exists for that email, a 6-digit OTP has been sent.",
    }


@app.post("/api/auth/verify-reset-otp")
def verify_reset_otp(data: VerifyResetRequest):
    normalized = str(data.email).lower().strip()
    user_row = one("SELECT * FROM users WHERE email=?", (normalized,))
    if not user_row:
        raise HTTPException(400, "Invalid or expired OTP.")

    challenge = _find_latest_otp(user_row["id"], "PASSWORD_RESET")
    if not challenge:
        raise HTTPException(400, "Invalid or expired OTP.")

    if utcnow() > parse_iso(challenge["expires_at"]):
        exe("UPDATE otp_challenges SET used=1 WHERE id=?", (challenge["id"],))
        raise HTTPException(400, "OTP expired. Request a new OTP.")

    attempts = int(challenge.get("attempts") or 0)
    if attempts >= OTP_MAX_ATTEMPTS:
        exe("UPDATE otp_challenges SET used=1 WHERE id=?", (challenge["id"],))
        raise HTTPException(429, "Too many incorrect OTP attempts. Request a new OTP.")

    if hash_otp(data.otp) != challenge["otp_hash"]:
        exe(
            "UPDATE otp_challenges SET attempts=attempts+1 WHERE id=?",
            (challenge["id"],),
        )
        raise HTTPException(400, "Invalid OTP.")

    reset_token, reset_jti, reset_exp = create_token(
        user_row["id"],
        "password_reset",
        timedelta(minutes=10),
    )

    exe(
        """
        UPDATE otp_challenges
        SET used=1, reset_jti=?, reset_expires_at=?, reset_used=0
        WHERE id=?
        """,
        (
            reset_jti,
            iso(reset_exp),
            challenge["id"],
        ),
    )

    return {
        "message": "OTP verified.",
        "reset_token": reset_token,
    }


@app.post("/api/auth/reset-password")
def reset_password(data: ResetPasswordRequest):
    try:
        payload = decode(data.reset_token, "password_reset")
    except jwt.PyJWTError:
        raise HTTPException(400, "Reset authorization is invalid or expired.")

    challenge = one(
        """
        SELECT * FROM otp_challenges
        WHERE user_id=? AND reset_jti=? AND reset_used=0
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (payload["sub"], payload.get("jti")),
    )
    if not challenge:
        raise HTTPException(400, "Reset authorization is invalid or already used.")

    if challenge.get("reset_expires_at") and utcnow() > parse_iso(
        challenge["reset_expires_at"]
    ):
        raise HTTPException(400, "Reset authorization expired. Request a new OTP.")

    exe(
        "UPDATE users SET password_hash=? WHERE id=?",
        (hash_password(data.new_password), payload["sub"]),
    )
    exe(
        "UPDATE otp_challenges SET reset_used=1 WHERE id=?",
        (challenge["id"],),
    )

    return {
        "message": "Password reset successfully. Please sign in again.",
    }


@app.get("/api/auth/me")
def me(u=Depends(user)):
    return {
        "user": {
            "id": u["id"],
            "email": u["email"],
            "full_name": u["full_name"],
        }
    }


def _update_upload_job(job_id: str, **fields) -> None:
    allowed = {"file_id", "status", "stage", "progress", "error", "result", "updated_at"}
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return
    if "updated_at" not in clean:
        clean["updated_at"] = now()
    assignments = ", ".join(f"{key}=?" for key in clean)
    params = tuple(clean.values()) + (job_id,)
    exe(f"UPDATE upload_jobs SET {assignments} WHERE id=?", params)


def _job_heartbeat(job_id: str, stop_event: threading.Event) -> None:
    while not stop_event.wait(20):
        _update_upload_job(job_id, updated_at=now())


def _run_queued_job(job_id: str) -> None:
    row = one(
        """
        SELECT j.id, j.file_id, j.user_id, j.name, j.status,
               f.mime_type, f.path
        FROM upload_jobs j
        JOIN files f ON f.id=j.file_id
        WHERE j.id=?
        """,
        (job_id,),
    )
    if not row:
        logger.warning("Queued ingestion job %s no longer exists", job_id)
        return

    if row["status"] != "queued":
        return

    claimed = one(
        """
        SELECT id
        FROM upload_jobs
        WHERE id=? AND status='queued'
        """,
        (job_id,),
    )
    if not claimed:
        return

    exe(
        """
        UPDATE upload_jobs
        SET status='processing', stage='extracting', progress=25,
            error=NULL, updated_at=?
        WHERE id=? AND status='queued'
        """,
        (now(), job_id),
    )

    stop_heartbeat = threading.Event()
    heartbeat = threading.Thread(
        target=_job_heartbeat,
        args=(job_id, stop_heartbeat),
        name=f"deepsearch-heartbeat-{job_id[:8]}",
        daemon=True,
    )
    heartbeat.start()

    try:
        _process_upload_job(
            job_id,
            row["user_id"],
            row["file_id"],
            row["name"],
            row["mime_type"],
            row["path"],
        )
    finally:
        stop_heartbeat.set()


def _process_upload_job(
    job_id: str,
    user_id: str,
    file_id: str,
    safe_name: str,
    mime_type: str,
    uploaded_uri: str,
) -> None:
    started_at = time.perf_counter()
    dest: Path | None = None
    try:
        ext = Path(safe_name).suffix.lower()
        _update_upload_job(
            job_id,
            status="processing",
            stage="extracting",
            progress=25,
        )

        # Make retries idempotent. A restarted worker may have left partial
        # chunks behind; always rebuild the file's searchable state.
        exe(
            "DELETE FROM chunks WHERE file_id=? AND user_id=?",
            (file_id, user_id),
        )
        exe(
            """
            UPDATE files
            SET status=?, ocr_used=?, page_count=?, chunk_count=?
            WHERE id=? AND user_id=?
            """,
            ("processing", 0, 0, 0, file_id, user_id),
        )

        with tempfile.TemporaryDirectory(prefix="deepsearch-job-") as tmp:
            dest = Path(tmp) / f"{file_id}{ext}"
            storage.download_file(uploaded_uri, dest)

            extract_started = time.perf_counter()
            text, refs, ocr, pages = extract(dest)
            extract_ms = (time.perf_counter() - extract_started) * 1000

            if not text.strip():
                _update_upload_job(
                    job_id,
                    status="failed",
                    stage="failed",
                    progress=0,
                    error="No extractable text was found in this file.",
                )
                exe(
                    "UPDATE files SET status=?, ocr_used=?, page_count=?, chunk_count=? WHERE id=? AND user_id=?",
                    ("failed", int(ocr), pages, 0, file_id, user_id),
                )
                return

            _update_upload_job(job_id, stage="chunking", progress=45)

            chunk_records = chunk_document(text, refs)
            chunks = [record[0] for record in chunk_records]

            if not chunks:
                _update_upload_job(
                    job_id,
                    status="failed",
                    stage="failed",
                    progress=0,
                    error="No extractable retrieval chunks were created.",
                )
                exe(
                    "UPDATE files SET status=?, ocr_used=?, page_count=?, chunk_count=? WHERE id=? AND user_id=?",
                    ("failed", int(ocr), pages, 0, file_id, user_id),
                )
                return

            _update_upload_job(job_id, stage="indexing", progress=60)

            embedding_started = time.perf_counter()
            vectors: list[list[float]] = []
            try:
                vectors = embed_texts(chunks)
            except Exception as exc:
                logger.warning("Embedding generation failed for %s: %s", safe_name, exc)
            embedding_ms = (time.perf_counter() - embedding_started) * 1000

            embedding_pairs: list[tuple[str, list[float]]] = []
            for i, chunk in enumerate(chunks):
                chunk_id = str(uuid.uuid4())
                _, source_ref, chunk_meta = chunk_records[i]
                embedding = vectors[i] if i < len(vectors) else None
                metadata = {
                    **chunk_meta,
                    "guardrails": ["document_is_untrusted_data_only"],
                    "retrieval": "faiss_semantic_plus_bm25",
                    "embedding_model": settings.embedding_model_repo if embedding else None,
                }
                exe(
                    """
                    INSERT INTO chunks
                        (id, file_id, user_id, content, source_ref, metadata, embedding)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        file_id,
                        user_id,
                        chunk,
                        source_ref,
                        jd(metadata),
                        jd(embedding) if embedding else None,
                    ),
                )
                if embedding:
                    embedding_pairs.append((chunk_id, embedding))

            exe(
                "UPDATE files SET status=?, ocr_used=?, page_count=?, chunk_count=? WHERE id=? AND user_id=?",
                ("indexed", int(ocr), pages, len(chunks), file_id, user_id),
            )

            if embedding_pairs:
                add_embeddings(user_id, embedding_pairs)
            bump_search_version(user_id)

            result = {
                "file_id": file_id,
                "name": safe_name,
                "status": "indexed",
                "chunks": len(chunks),
                "embedding_chunks": len(embedding_pairs),
                "storage": storage.backend,
                "performance": {
                    "processing_ms": round((time.perf_counter() - started_at) * 1000, 1),
                    "extraction_ms": round(extract_ms, 1),
                    "embedding_ms": round(embedding_ms, 1),
                    "ocr_used": bool(ocr),
                },
            }
            _update_upload_job(
                job_id,
                status="complete",
                stage="ready",
                progress=100,
                result=jd(result),
            )
            logger.info(
                "Upload job complete job=%s file=%s chunks=%s vectors=%s",
                job_id,
                safe_name,
                len(chunks),
                len(embedding_pairs),
            )

    except Exception as exc:
        logger.exception("Upload job failed job=%s file=%s", job_id, safe_name)
        try:
            exe(
                "UPDATE files SET status=? WHERE id=? AND user_id=?",
                ("failed", file_id, user_id),
            )
        except Exception:
            logger.exception("Could not mark failed upload file")
        _update_upload_job(
            job_id,
            status="failed",
            stage="failed",
            progress=0,
            error=str(exc)[:500],
        )


def _find_duplicate_file(
    user_id: str,
    content_hash: str,
    extension: str,
):
    existing = one(
        """
        SELECT id, name, status, created_at
        FROM files
        WHERE user_id=? AND content_hash=?
        LIMIT 1
        """,
        (user_id, content_hash),
    )
    if existing:
        return existing

    # Hash legacy PDFs that were uploaded before content_hash was introduced.
    # This keeps the new duplicate protection effective after deployment.
    if extension != ".pdf":
        return None

    legacy = all_(
        """
        SELECT id, name, status, created_at, path
        FROM files
        WHERE user_id=?
          AND LOWER(name) LIKE ?
          AND (content_hash IS NULL OR content_hash='')
        ORDER BY created_at ASC
        """,
        (user_id, "%.pdf"),
    )

    for row in legacy:
        # Legacy records created while Render used ephemeral local storage
        # cannot be reconstructed after a restart. Do not repeatedly attempt
        # to read those dead paths during duplicate checks.
        if (
            storage.backend == "database"
            and not str(row.get("path") or "").startswith("db://")
        ):
            continue

        try:
            with tempfile.TemporaryDirectory(prefix="deepsearch-dedupe-") as tmp:
                destination = Path(tmp) / f"{row['id']}.pdf"
                storage.download_file(row["path"], destination)
                legacy_hash = hashlib.sha256(destination.read_bytes()).hexdigest()

            exe(
                "UPDATE files SET content_hash=? WHERE id=? AND user_id=?",
                (legacy_hash, row["id"], user_id),
            )

            if legacy_hash == content_hash:
                return {**row, "content_hash": legacy_hash}
        except Exception:
            logger.warning(
                "Could not hash legacy file id=%s name=%s during duplicate check",
                row["id"],
                row["name"],
                exc_info=True,
            )

    return None


@app.post("/api/files/upload")
async def upload(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    u=Depends(user),
):
    rate_limit(request, "upload", 20)

    uploaded_uri = ""
    dest: Path | None = None
    ext = ""
    content_hash = ""
    try:
        safe_name = validate_upload(file.filename or "", 1)
        raw = await file.read(MAX_UPLOAD_BYTES + 1)
        safe_name = validate_upload(safe_name, len(raw))

        if len(raw) > MAX_UPLOAD_BYTES:
            raise GuardrailViolation(
                "file_too_large",
                "Uploaded file exceeds the size limit.",
            )

        ext = Path(safe_name).suffix.lower()
        content_hash = hashlib.sha256(raw).hexdigest()

        # Exact-content deduplication is intentionally scoped to each user's
        # private workspace. A file with a different name but identical bytes
        # is still the same upload.
        existing = _find_duplicate_file(
            u["id"],
            content_hash,
            ext,
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Duplicate file: this file is already uploaded as "
                    f"'{existing['name']}' "
                    f"(status: {existing['status']}, id: {existing['id']}). "
                    "Use the existing file instead of uploading it again."
                ),
            )

        fid = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        mime_type = file.content_type or "application/octet-stream"

        dest = Path(settings.upload_dir) / f"{fid}{ext}"
        dest.write_bytes(raw)

        inspect_zip_container(dest)

        storage_key = f"{u['id']}/{fid}/{safe_name}"
        uploaded_uri = storage.upload_file(
            dest,
            storage_key,
            mime_type,
        )

        created_at = now()
        exe(
            """
            INSERT INTO files
                (id,user_id,name,mime_type,path,status,ocr_used,page_count,
                 chunk_count,created_at,content_hash)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                fid,
                u["id"],
                safe_name,
                mime_type,
                uploaded_uri,
                "processing",
                0,
                0,
                0,
                created_at,
                content_hash,
            ),
        )
        exe(
            """
            INSERT INTO upload_jobs
                (id,user_id,file_id,name,status,stage,progress,error,result,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                job_id,
                u["id"],
                fid,
                safe_name,
                "queued",
                "uploaded",
                10,
                None,
                None,
                created_at,
                created_at,
            ),
        )

        queued = enqueue_job(job_id)
        if queued:
            _wake_ingestion_service()
        else:
            background_tasks.add_task(
                _process_upload_job,
                job_id,
                u["id"],
                fid,
                safe_name,
                mime_type,
                uploaded_uri,
            )

        return {
            "job_id": job_id,
            "file_id": fid,
            "name": safe_name,
            "status": "queued" if queued else "processing",
            "stage": "uploaded",
            "progress": 10,
            "queue": "redis" if queued else "background-fallback",
        }

    except HTTPException:
        if uploaded_uri:
            storage.delete(uploaded_uri)
        raise
    except GuardrailViolation as exc:
        if uploaded_uri:
            storage.delete(uploaded_uri)
        logger.warning("Upload blocked [%s]: %s", exc.code, exc)
        raise HTTPException(400, str(exc))
    except Exception as exc:
        if uploaded_uri:
            storage.delete(uploaded_uri)

        # Protect against the small race where two identical uploads arrive
        # at the same time and the database unique index wins the race.
        message = str(exc).lower()
        if content_hash and (
            "duplicate key value" in message
            or "unique constraint" in message
            or "content_hash" in message
        ):
            duplicate = _find_duplicate_file(
                u["id"],
                content_hash,
                ext,
            )
            if duplicate:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Duplicate file: this file is already uploaded as "
                        f"'{duplicate['name']}' "
                        f"(status: {duplicate['status']}, id: {duplicate['id']}). "
                        "Use the existing file instead of uploading it again."
                    ),
                ) from exc

        logger.exception("Upload request failed")
        raise HTTPException(500, "The file could not be uploaded right now.") from exc
    finally:
        if dest is not None:
            dest.unlink(missing_ok=True)


@app.get("/api/files/upload-jobs/{job_id}")
def upload_job_status(job_id: str, u=Depends(user)):
    row = one(
        "SELECT id,file_id,name,status,stage,progress,error,result,created_at,updated_at "
        "FROM upload_jobs WHERE id=? AND user_id=?",
        (job_id, u["id"]),
    )
    if not row:
        raise HTTPException(404, "Upload job not found")

    result = jl(row.get("result") or "{}", {})
    return {
        "job_id": row["id"],
        "file_id": row["file_id"],
        "name": row["name"],
        "status": row["status"],
        "stage": row["stage"],
        "progress": int(row.get("progress") or 0),
        "error": row.get("error"),
        "result": result,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@app.get("/api/files")
def files(u=Depends(user)):
    return {
        "files": all_(
            "SELECT id,name,mime_type,status,ocr_used,page_count,chunk_count,created_at "
            "FROM files WHERE user_id=? ORDER BY created_at DESC",
            (u["id"],),
        )
    }


@app.post("/api/search")
def do_search(b: Query, request: Request, u=Depends(user)):
    rate_limit(request, "search", 60)
    query = validate_query(b.query)
    return {
        "query": query,
        "results": search(u["id"], query, min(b.limit, 50)),
        "guardrails": ["query_length_limit", "rate_limit"],
    }


@app.get("/api/corpus/stats")
def corpus_stats(u=Depends(user)):
    counts = one(
        "SELECT COUNT(*) AS files, COALESCE(SUM(chunk_count),0) AS chunks "
        "FROM files WHERE user_id=?",
        (u["id"],),
    )
    embedded = one(
        "SELECT COUNT(*) AS embedded_chunks FROM chunks "
        "WHERE user_id=? AND embedding IS NOT NULL",
        (u["id"],),
    )
    return {
        "files": int(counts["files"] or 0),
        "chunks": int(counts["chunks"] or 0),
        "embedded_chunks": int(embedded["embedded_chunks"] or 0),
        "semantic_ready": int(embedded["embedded_chunks"] or 0) > 0,
    }


@app.get("/api/files/{file_id}")
def file_detail(file_id: str, u=Depends(user)):
    row = one(
        "SELECT id,name,mime_type,status,ocr_used,page_count,chunk_count,created_at "
        "FROM files WHERE id=? AND user_id=?",
        (file_id, u["id"]),
    )
    if not row:
        raise HTTPException(404, "File not found")
    return {"file": row}


@app.get("/api/files/{file_id}/chunks")
def file_chunks(file_id: str, limit: int = 50, u=Depends(user)):
    limit = max(1, min(limit, 100))
    exists = one(
        "SELECT id FROM files WHERE id=? AND user_id=?",
        (file_id, u["id"]),
    )
    if not exists:
        raise HTTPException(404, "File not found")
    rows = all_(
        "SELECT id,content,source_ref,metadata FROM chunks "
        "WHERE file_id=? AND user_id=? ORDER BY id LIMIT ?",
        (file_id, u["id"], limit),
    )
    for row in rows:
        row["metadata"] = jl(row["metadata"], {})
    return {"file_id": file_id, "chunks": rows}


@app.post("/api/files/{file_id}/reindex")
def reindex_file(file_id: str, u=Depends(user)):
    row = one(
        "SELECT id,name,mime_type,path FROM files WHERE id=? AND user_id=?",
        (file_id, u["id"]),
    )
    if not row:
        raise HTTPException(404, "File not found")

    started_at = time.perf_counter()
    temp_path = None
    try:
        suffix = Path(row["name"]).suffix.lower()
        with tempfile.TemporaryDirectory(prefix="deepsearch-reindex-") as tmp:
            temp_path = Path(tmp) / f"{file_id}{suffix}"
            try:
                storage.download_file(row["path"], temp_path)
            except FileNotFoundError as exc:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "The original file is no longer available because it "
                        "was uploaded before persistent storage was enabled. "
                        "Please upload the file again to rebuild its index."
                    ),
                ) from exc

            extract_started = time.perf_counter()
            text, refs, ocr, pages = extract(temp_path)
            extract_ms = (time.perf_counter() - extract_started) * 1000

            chunk_records = chunk_document(text, refs)
            chunks = [record[0] for record in chunk_records]
            if not chunks:
                raise GuardrailViolation(
                    "no_extractable_content",
                    "No extractable text was found while re-indexing this file.",
                )

            embedding_started = time.perf_counter()
            vectors: list[list[float]] = []
            try:
                vectors = embed_texts(chunks)
            except Exception as exc:
                logger.warning("Embedding generation failed during reindex for %s: %s", row["name"], exc)
            embedding_ms = (time.perf_counter() - embedding_started) * 1000

            exe(
                "DELETE FROM chunks WHERE file_id=? AND user_id=?",
                (file_id, u["id"]),
            )

            embedding_pairs: list[tuple[str, list[float]]] = []
            for i, chunk in enumerate(chunks):
                chunk_id = str(uuid.uuid4())
                _, source_ref, chunk_meta = chunk_records[i]
                embedding = vectors[i] if i < len(vectors) else None
                metadata = {
                    **chunk_meta,
                    "guardrails": ["document_is_untrusted_data_only"],
                    "retrieval": "faiss_semantic_plus_bm25",
                    "embedding_model": settings.embedding_model_repo if embedding else None,
                }
                exe(
                    """
                    INSERT INTO chunks
                        (id, file_id, user_id, content, source_ref, metadata, embedding)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        file_id,
                        u["id"],
                        chunk,
                        source_ref,
                        jd(metadata),
                        jd(embedding) if embedding else None,
                    ),
                )
                if embedding:
                    embedding_pairs.append((chunk_id, embedding))

            exe(
                "UPDATE files SET status=?, ocr_used=?, page_count=?, chunk_count=? WHERE id=? AND user_id=?",
                ("indexed", int(ocr), pages, len(chunks), file_id, u["id"]),
            )

            from .vector_index import rebuild_user_index
            rebuild_user_index(u["id"])
            bump_search_version(u["id"])

            return {
                "file_id": file_id,
                "name": row["name"],
                "status": "reindexed",
                "chunks": len(chunks),
                "embedding_chunks": len(embedding_pairs),
                "performance": {
                    "processing_ms": round((time.perf_counter() - started_at) * 1000, 1),
                    "extraction_ms": round(extract_ms, 1),
                    "embedding_ms": round(embedding_ms, 1),
                    "ocr_used": bool(ocr),
                },
            }
    except GuardrailViolation as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Re-index failed for %s", file_id)
        raise HTTPException(500, "The file could not be re-indexed right now.") from exc


@app.delete("/api/files/{file_id}")
def delete_file(file_id: str, u=Depends(user)):
    row = one(
        "SELECT id,path FROM files WHERE id=? AND user_id=?",
        (file_id, u["id"]),
    )
    if not row:
        raise HTTPException(404, "File not found")

    try:
        storage.delete(row["path"])
    except Exception:
        logger.warning("Could not remove stored original for %s", file_id)

    exe(
        "DELETE FROM chunks WHERE file_id=? AND user_id=?",
        (file_id, u["id"]),
    )
    exe(
        "DELETE FROM files WHERE id=? AND user_id=?",
        (file_id, u["id"]),
    )

    from .vector_index import rebuild_user_index
    rebuild_user_index(u["id"])
    bump_search_version(u["id"])
    return {"success": True, "file_id": file_id}


@app.post("/api/deep-search")
async def deep_search(b: DeepSearchRequest, request: Request, u=Depends(user)):
    rate_limit(request, "deep_search", 20)
    query = guard_ai_query(b.query)
    results = search(u["id"], query, min(b.limit, 20))
    answer = await answer_with_guardrails(query, results[:12])

    exe(
        """
        INSERT INTO search_history
            (id,user_id,query,answer,confidence,citations,result_count,created_at)
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            str(uuid.uuid4()),
            u["id"],
            query,
            str(answer.get("answer") or ""),
            float(answer.get("confidence") or 0),
            jd(answer.get("citations") or []),
            len(results),
            now(),
        ),
    )

    return {
        "query": query,
        "results": results,
        "answer": answer,
        "result_count": len(results),
        "engine": {
            "retrieval": "hybrid-semantic-lexical-reranked",
            "generation": "groq",
            "grounding": True,
            "citations": True,
        },
    }


def _chat_scope(file_id: str | None, user_id: str) -> tuple[str, str | None, str]:
    if file_id:
        file_row = one(
            "SELECT id,name,status,chunk_count FROM files WHERE id=? AND user_id=?",
            (file_id, user_id),
        )
        if not file_row:
            raise HTTPException(404, "File not found")
        return "file", file_row["id"], file_row["name"]
    return "common", None, "All files"


@app.get("/api/chats")
def list_chats(file_id: str | None = None, u=Depends(user)):
    scope_type, scoped_file_id, scope_title = _chat_scope(file_id, u["id"])
    thread = one(
        """
        SELECT id,title,scope_type,file_id,created_at,updated_at
        FROM chat_threads
        WHERE user_id=? AND scope_type=? AND
              ((file_id=? ) OR (file_id IS NULL AND ? IS NULL))
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (u["id"], scope_type, scoped_file_id, scoped_file_id),
    )
    if not thread:
        thread_id = str(uuid.uuid4())
        created = now()
        title = scope_title if scope_type == "file" else "All files"
        exe(
            """
            INSERT INTO chat_threads
                (id,user_id,scope_type,file_id,title,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                thread_id,
                u["id"],
                scope_type,
                scoped_file_id,
                title,
                created,
                created,
            ),
        )
        thread = {
            "id": thread_id,
            "title": title,
            "scope_type": scope_type,
            "file_id": scoped_file_id,
            "created_at": created,
            "updated_at": created,
        }

    messages = all_(
        """
        SELECT id,role,content,citations,confidence,created_at
        FROM chat_messages
        WHERE thread_id=? AND user_id=?
        ORDER BY created_at ASC
        """,
        (thread["id"], u["id"]),
    )
    for item in messages:
        item["citations"] = jl(item.get("citations") or "[]", [])

    return {
        "thread": thread,
        "scope": {
            "type": scope_type,
            "file_id": scoped_file_id,
            "title": scope_title,
        },
        "messages": messages,
    }


@app.post("/api/chats/message")
async def chat_message(data: ChatMessageRequest, request: Request, u=Depends(user)):
    rate_limit(request, "chat", 20)
    query = guard_ai_query(data.message)
    scope_type, scoped_file_id, scope_title = _chat_scope(data.file_id, u["id"])

    if scoped_file_id:
        readiness = one(
            "SELECT status,chunk_count FROM files WHERE id=? AND user_id=?",
            (scoped_file_id, u["id"]),
        )
        if readiness and int(readiness.get("chunk_count") or 0) == 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This file is still being indexed. "
                    "Please wait until the ingestion pipeline reaches "
                    "'Search ready' before asking questions."
                ),
            )

    thread = None
    if data.thread_id:
        thread = one(
            """
            SELECT * FROM chat_threads
            WHERE id=? AND user_id=? AND scope_type=?
              AND ((file_id=? ) OR (file_id IS NULL AND ? IS NULL))
            """,
            (
                data.thread_id,
                u["id"],
                scope_type,
                scoped_file_id,
                scoped_file_id,
            ),
        )
        if not thread:
            raise HTTPException(404, "Chat thread not found")

    if not thread:
        created = now()
        thread_id = str(uuid.uuid4())
        exe(
            """
            INSERT INTO chat_threads
                (id,user_id,scope_type,file_id,title,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                thread_id,
                u["id"],
                scope_type,
                scoped_file_id,
                scope_title,
                created,
                created,
            ),
        )
        thread = {
            "id": thread_id,
            "title": scope_title,
            "scope_type": scope_type,
            "file_id": scoped_file_id,
            "created_at": created,
            "updated_at": created,
        }

    exe(
        """
        INSERT INTO chat_messages
            (id,thread_id,user_id,role,content,citations,confidence,created_at)
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            str(uuid.uuid4()),
            thread["id"],
            u["id"],
            "user",
            query,
            "[]",
            0,
            now(),
        ),
    )

    results = search(
        u["id"],
        query,
        20,
        file_ids=[scoped_file_id] if scoped_file_id else None,
    )

    if not results and scoped_file_id and re.search(
        r"\b(what (?:is|does) (?:this|the)?\s*(?:file|document|pdf|sheet)|what.?s (?:this|the)?\s*(?:file|document|pdf|sheet)|what\s+(?:file|document|pdf|sheet)\s+contains|summar(?:ize|ise)|overview)\b",
        query,
        re.I,
    ):
        fallback_rows = all_(
            """
            SELECT c.*, f.name
            FROM chunks c JOIN files f ON f.id=c.file_id
            WHERE c.user_id=? AND c.file_id=?
            ORDER BY c.id
            LIMIT 12
            """,
            (u["id"], scoped_file_id),
        )
        results = [
            {
                "score": 0.5,
                "file_id": row["file_id"],
                "file_name": row["name"],
                "chunk_id": row["id"],
                "content": row["content"][:1100],
                "source_ref": row["source_ref"],
                "metadata": jl(row.get("metadata") or "{}", {}),
                "retrieval": "file-scoped-summary-fallback",
                "match_reasons": ["file-scoped overview"],
                "signals": {"semantic": 0.0, "lexical": 0.0, "exact": 0.5},
            }
            for row in fallback_rows
        ]

    answer = await answer_with_guardrails(query, results[:12])

    exe(
        """
        INSERT INTO chat_messages
            (id,thread_id,user_id,role,content,citations,confidence,created_at)
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            str(uuid.uuid4()),
            thread["id"],
            u["id"],
            "assistant",
            str(answer.get("answer") or ""),
            jd(answer.get("citations") or []),
            float(answer.get("confidence") or 0),
            now(),
        ),
    )
    exe(
        "UPDATE chat_threads SET updated_at=? WHERE id=? AND user_id=?",
        (now(), thread["id"], u["id"]),
    )

    return {
        "thread": thread,
        "message": {
            "role": "assistant",
            "content": answer.get("answer") or "",
            "citations": answer.get("citations") or [],
            "confidence": float(answer.get("confidence") or 0),
        },
        "results": results,
        "scope": {
            "type": scope_type,
            "file_id": scoped_file_id,
            "title": scope_title,
        },
    }


@app.get("/api/history")
def get_history(limit: int = 50, u=Depends(user)):
    limit = max(1, min(limit, 100))
    rows = all_(
        """
        SELECT id,query,answer,confidence,citations,result_count,created_at
        FROM search_history
        WHERE user_id=?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (u["id"], limit),
    )
    for row in rows:
        row["citations"] = jl(row.get("citations") or "[]", [])
    return {"history": rows}


@app.delete("/api/history/{history_id}")
def delete_history(history_id: str, u=Depends(user)):
    row = one("SELECT id FROM search_history WHERE id=? AND user_id=?", (history_id, u["id"]))
    if not row:
        raise HTTPException(404, "History item not found")
    exe("DELETE FROM search_history WHERE id=? AND user_id=?", (history_id, u["id"]))
    return {"success": True, "id": history_id}


@app.get("/api/evaluation/benchmark")
def evaluation_benchmark(limit: int = 6, u=Depends(user)):
    return run_benchmark(u["id"], max(1, min(limit, 8)))


class EvaluationSnapshotRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=10)


class EvaluationCompareRequest(BaseModel):
    before: dict
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=10)


@app.post("/api/evaluation/snapshot")
def evaluation_snapshot(data: EvaluationSnapshotRequest, u=Depends(user)):
    query = validate_query(data.query)
    return corpus_snapshot(u["id"], query, data.limit)


@app.post("/api/evaluation/compare")
def evaluation_compare(data: EvaluationCompareRequest, u=Depends(user)):
    query = validate_query(data.query)
    after = corpus_snapshot(u["id"], query, data.limit)
    comparison = compare_snapshots(data.before, after)
    return {"before": data.before, "after": after, "comparison": comparison}


@app.post("/api/ai/answer")
async def ai_answer(b: AIAnswerRequest, request: Request, u=Depends(user)):
    rate_limit(request, "ai", 20)
    try:
        query = guard_ai_query(b.query)
        results = search(u["id"], query, min(b.limit, 12))
        answer = await answer_with_guardrails(query, results)
        return {
            "query": query,
            "answer": answer,
            "evidence_count": len(results),
            "model_access": bool(settings.groq_api_key),
            "provider": "groq",
            "model": settings.groq_model,
        }
    except GuardrailViolation as exc:
        logger.warning("AI request blocked [%s]: %s", exc.code, exc)
        raise HTTPException(400, str(exc))
