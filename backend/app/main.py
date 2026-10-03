import uuid
import logging
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path

import jwt
from fastapi import FastAPI, UploadFile, File, Depends, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from .config import settings
from .db import init_db, one, all_, exe, jd, jl, now
from .security import hash_password, verify_password, create_token, decode
from .ingest import extract
from .search import search
from .ai_service import answer_with_guardrails
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

app = FastAPI(title="DeepSearch API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

_RATE: dict[str, deque[float]] = defaultdict(deque)

def rate_limit(request: Request, bucket: str, limit: int) -> None:
    now_ts = __import__("time").time()
    key = f"{bucket}:{request.client.host if request.client else 'unknown'}"
    q = _RATE[key]
    while q and now_ts - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Too many requests. Please wait a minute and try again.")
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
    return {"status": "ok", "service": "deepsearch", "version": "1.1.0", "guardrails": {
        "prompt_injection": True,
        "grounded_answers": True,
        "citation_validation": True,
        "secret_redaction": True,
        "upload_limits": True,
        "rate_limits": True,
    }}

@app.post("/api/auth/register")
def register(b: Register, request: Request):
    rate_limit(request, "register", 10)
    e = b.email.lower()
    if one("SELECT id FROM users WHERE email=?", (e,)):
        raise HTTPException(409, "Account exists")
    uid = str(uuid.uuid4())
    exe(
        "INSERT INTO users VALUES(?,?,?,?,?,?)",
        (uid, e, b.full_name.strip(), hash_password(b.password), 0, now()),
    )
    return {"message": "Account created. Complete email verification before production use."}

@app.post("/api/auth/login")
def login(b: Login, request: Request):
    rate_limit(request, "login", 8)
    u = one("SELECT * FROM users WHERE email=?", (b.email.lower(),))
    if not u or not verify_password(b.password, u["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    access, _, _ = create_token(u["id"], "access", timedelta(minutes=settings.access_minutes))
    return {
        "access_token": access,
        "user": {"id": u["id"], "email": u["email"], "full_name": u["full_name"]},
    }

@app.get("/api/auth/me")
def me(u=Depends(user)):
    return {"user": {"id": u["id"], "email": u["email"], "full_name": u["full_name"]}}

@app.post("/api/files/upload")
async def upload(file: UploadFile = File(...), request: Request = None, u=Depends(user)):
    rate_limit(request, "upload", 20)
    try:
        safe_name = validate_upload(file.filename or "", 1)
        raw = await file.read(MAX_UPLOAD_BYTES + 1)
        safe_name = validate_upload(safe_name, len(raw))
        if len(raw) > MAX_UPLOAD_BYTES:
            raise GuardrailViolation("file_too_large", "Uploaded file exceeds the size limit.")

        ext = Path(safe_name).suffix.lower()
        fid = str(uuid.uuid4())
        dest = Path(settings.upload_dir) / f"{fid}{ext}"
        dest.write_bytes(raw)

        inspect_zip_container(dest)
        text, refs, ocr, pages = extract(dest)

        chunks = [x.strip() for x in text.split("\\n\\n") if x.strip()]
        if not chunks:
            chunks = [text[:4000]] if text else []

        if not chunks:
            dest.unlink(missing_ok=True)
            raise GuardrailViolation("no_extractable_content", "No extractable text was found in this file.")

        for i, c in enumerate(chunks):
            metadata = {"index": i, "guardrails": ["document_is_untrusted_data_only"]}
            exe(
                "INSERT INTO chunks VALUES(?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    fid,
                    u["id"],
                    c,
                    refs[min(i, len(refs) - 1)] if refs else "document",
                    jd(metadata),
                    None,
                ),
            )

        exe(
            "INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                fid,
                u["id"],
                safe_name,
                file.content_type or "application/octet-stream",
                str(dest),
                "indexed",
                int(ocr),
                pages,
                len(chunks),
                now(),
            ),
        )

        return {
            "file_id": fid,
            "name": safe_name,
            "status": "indexed",
            "chunks": len(chunks),
            "guardrails": {
                "size_limit_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
                "archive_bomb_check": ext in {".docx", ".xlsx", ".xlsm", ".pptx"},
                "content_treated_as_untrusted_data": True,
            },
        }
    except GuardrailViolation as exc:
        logger.warning("Upload blocked [%s]: %s", exc.code, exc)
        raise HTTPException(400, str(exc))

@app.get("/api/files")
def files(u=Depends(user)):
    return {
        "files": all_(
            "SELECT id,name,mime_type,status,ocr_used,page_count,chunk_count,created_at FROM files WHERE user_id=? ORDER BY created_at DESC",
            (u["id"],),
        )
    }

@app.post("/api/search")
def do_search(b: Query, request: Request, u=Depends(user)):
    rate_limit(request, "search", 60)
    query = validate_query(b.query)
    return {"query": query, "results": search(u["id"], query, min(b.limit, 50)), "guardrails": ["query_length_limit", "rate_limit"]}

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
