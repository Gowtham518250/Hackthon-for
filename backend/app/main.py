import uuid
import logging
from collections import defaultdict, deque
from datetime import timedelta, timezone
from pathlib import Path

import jwt
from fastapi import FastAPI, UploadFile, File, Depends, Header, HTTPException, Request
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

logger = logging.getLogger("deepsearch")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="DeepSearch API", version="1.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
if settings.storage_backend.lower() == "local":
    Path(settings.local_storage_dir).mkdir(parents=True, exist_ok=True)

_RATE: dict[str, deque[float]] = defaultdict(deque)


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


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "deepsearch",
        "version": "1.3.0",
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
            "otp": "email_otp_10m_5_attempts",
        },
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

    if not send_email(email, subject, body):
        raise HTTPException(
            503,
            "We could not send the OTP email. Check the email provider configuration.",
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


@app.post("/api/files/upload")
async def upload(request: Request, file: UploadFile = File(...), u=Depends(user)):
    rate_limit(request, "upload", 20)

    uploaded_uri = ""
    dest: Path | None = None

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
        fid = str(uuid.uuid4())

        # Local file is temporary ingestion workspace only.
        dest = Path(settings.upload_dir) / f"{fid}{ext}"
        dest.write_bytes(raw)

        inspect_zip_container(dest)

        # Persist the original file before extraction. S3-compatible storage is
        # production storage; local storage is only a development fallback.
        storage_key = f"{u['id']}/{fid}/{safe_name}"
        uploaded_uri = storage.upload_file(
            dest,
            storage_key,
            file.content_type or "application/octet-stream",
        )

        text, refs, ocr, pages = extract(dest)

        # Retrieval-sized chunks preserve page/sheet provenance and keep
        # numbered question banks as individual retrievable items.
        chunk_records = chunk_document(text, refs)
        chunks = [record[0] for record in chunk_records]

        if not chunks:
            storage.delete(uploaded_uri)
            uploaded_uri = ""
            raise GuardrailViolation(
                "no_extractable_content",
                "No extractable text was found in this file.",
            )

        # Embeddings use the same all-MiniLM-L6-v2 model family as Retail Mind.
        # If model download/inference is temporarily unavailable, retain the
        # document for lexical search rather than rejecting the upload.
        vectors: list[list[float]] = []
        try:
            vectors = embed_texts(chunks)
        except Exception as exc:
            logger.warning(
                "Embedding generation failed for %s: %s",
                safe_name,
                exc,
            )

        embedding_pairs: list[tuple[str, list[float]]] = []

        for i, chunk in enumerate(chunks):
            chunk_id = str(uuid.uuid4())
            _, source_ref, chunk_meta = chunk_records[i]
            metadata = {
                **chunk_meta,
                "guardrails": ["document_is_untrusted_data_only"],
                "retrieval": "faiss_semantic_plus_bm25",
                "embedding_model": (
                    settings.embedding_model_repo if vectors else None
                ),
            }
            embedding = vectors[i] if i < len(vectors) else None

            exe(
                """
                INSERT INTO chunks
                    (id, file_id, user_id, content, source_ref, metadata, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    fid,
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
            "INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                fid,
                u["id"],
                safe_name,
                file.content_type or "application/octet-stream",
                uploaded_uri,
                "indexed",
                int(ocr),
                pages,
                len(chunks),
                now(),
            ),
        )

        if embedding_pairs:
            add_embeddings(u["id"], embedding_pairs)

        # Invalidate shared search-cache entries by advancing the per-user
        # corpus version. Cached queries from the old corpus are then ignored.
        bump_search_version(u["id"])

        return {
            "file_id": fid,
            "name": safe_name,
            "status": "indexed",
            "chunks": len(chunks),
            "embedding_chunks": len(embedding_pairs),
            "storage": storage.backend,
            "guardrails": {
                "size_limit_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
                "archive_bomb_check": ext in {
                    ".docx",
                    ".xlsx",
                    ".xlsm",
                    ".pptx",
                },
                "content_treated_as_untrusted_data": True,
            },
        }

    except GuardrailViolation as exc:
        if uploaded_uri:
            storage.delete(uploaded_uri)
        logger.warning("Upload blocked [%s]: %s", exc.code, exc)
        raise HTTPException(400, str(exc))
    except Exception as exc:
        if uploaded_uri:
            storage.delete(uploaded_uri)
        try:
            exe(
                "DELETE FROM chunks WHERE file_id=? AND user_id=?",
                (fid, u["id"]),
            )
            exe(
                "DELETE FROM files WHERE id=? AND user_id=?",
                (fid, u["id"]),
            )
        except Exception:
            logger.exception("Could not clean up failed indexing records")
        logger.exception("Upload/indexing failed")
        raise HTTPException(
            500,
            "The file could not be indexed right now.",
        ) from exc
    finally:
        if dest is not None:
            dest.unlink(missing_ok=True)


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
