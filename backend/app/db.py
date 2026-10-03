import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover
    psycopg2 = None
    RealDictCursor = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_verified INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS refresh_tokens(
    jti TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS files(
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    path TEXT NOT NULL,
    status TEXT NOT NULL,
    ocr_used INTEGER DEFAULT 0,
    page_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    content_hash TEXT
);

CREATE TABLE IF NOT EXISTS file_blobs(
    object_key TEXT PRIMARY KEY,
    content BYTEA NOT NULL,
    content_type TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks(
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    metadata TEXT NOT NULL,
    embedding TEXT
);

CREATE TABLE IF NOT EXISTS otp_challenges(
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    email TEXT NOT NULL,
    purpose TEXT NOT NULL,
    otp_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    reset_jti TEXT,
    reset_expires_at TEXT,
    reset_used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS search_history(
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    query TEXT NOT NULL,
    answer TEXT NOT NULL,
    confidence REAL DEFAULT 0,
    citations TEXT NOT NULL,
    result_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS upload_jobs(
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    file_id TEXT,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    result TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_threads(
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    file_id TEXT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages(
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations TEXT NOT NULL,
    confidence REAL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def is_postgres() -> bool:
    return settings.database_url.startswith(("postgresql://", "postgres://"))


def _qmark_to_pyformat(query: str) -> str:
    # The application uses DB-agnostic ? placeholders. psycopg2 uses %s.
    return query.replace("?", "%s") if is_postgres() else query


@contextmanager
def con():
    if is_postgres():
        if psycopg2 is None:
            raise RuntimeError("psycopg2-binary is required for PostgreSQL.")
        connection = psycopg2.connect(settings.database_url)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return

    db_path = settings.database_url.replace("sqlite:///", "", 1)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _cursor(connection):
    if is_postgres():
        return connection.cursor(cursor_factory=RealDictCursor)
    return connection.cursor()


def init_db():
    with con() as connection:
        cursor = _cursor(connection)
        try:
            for statement in SCHEMA.split(";"):
                statement = statement.strip()
                if statement:
                    cursor.execute(statement)

            # Backward-compatible migration for existing databases created
            # before content hashing was introduced.
            if is_postgres():
                cursor.execute(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name='files' AND column_name='content_hash'
                    """
                )
                has_hash = cursor.fetchone() is not None
            else:
                cursor.execute("PRAGMA table_info(files)")
                has_hash = any(row[1] == "content_hash" for row in cursor.fetchall())

            if not has_hash:
                cursor.execute("ALTER TABLE files ADD COLUMN content_hash TEXT")

            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                idx_files_user_content_hash
                ON files(user_id, content_hash)
                """
            )
        finally:
            cursor.close()


def now():
    return datetime.now(timezone.utc).isoformat()


def one(query, params=()):
    with con() as connection:
        cursor = _cursor(connection)
        try:
            cursor.execute(_qmark_to_pyformat(query), params)
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            cursor.close()


def all_(query, params=()):
    with con() as connection:
        cursor = _cursor(connection)
        try:
            cursor.execute(_qmark_to_pyformat(query), params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            cursor.close()


def exe(query, params=()):
    with con() as connection:
        cursor = _cursor(connection)
        try:
            cursor.execute(_qmark_to_pyformat(query), params)
        finally:
            cursor.close()


def jd(value):
    return json.dumps(value, ensure_ascii=False)


def jl(value, default):
    try:
        return json.loads(value)
    except Exception:
        return default
