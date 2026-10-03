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
