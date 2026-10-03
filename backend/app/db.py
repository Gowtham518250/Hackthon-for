import sqlite3, json
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from .config import settings
DB_PATH=settings.database_url.replace("sqlite:///","") if settings.database_url.startswith("sqlite:///") else str(Path(settings.upload_dir).parent/"deepsearch.db")
Path(DB_PATH).parent.mkdir(parents=True,exist_ok=True)
SCHEMA="""
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,full_name TEXT NOT NULL,password_hash TEXT NOT NULL,is_verified INTEGER DEFAULT 0,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS refresh_tokens(jti TEXT PRIMARY KEY,user_id TEXT NOT NULL,token_hash TEXT NOT NULL,expires_at TEXT NOT NULL,revoked_at TEXT);
CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,name TEXT NOT NULL,mime_type TEXT NOT NULL,path TEXT NOT NULL,status TEXT NOT NULL,ocr_used INTEGER DEFAULT 0,page_count INTEGER DEFAULT 0,chunk_count INTEGER DEFAULT 0,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,file_id TEXT NOT NULL,user_id TEXT NOT NULL,content TEXT NOT NULL,source_ref TEXT NOT NULL,metadata TEXT NOT NULL,embedding TEXT);
"""
def now():return datetime.now(timezone.utc).isoformat()
@contextmanager
def con():
 c=sqlite3.connect(DB_PATH);c.row_factory=sqlite3.Row
 try:yield c;c.commit()
 finally:c.close()
def init_db():
 with con() as c:c.executescript(SCHEMA)
def one(q,p=()):
 with con() as c:
  r=c.execute(q,p).fetchone();return dict(r) if r else None
def all_(q,p=()):
 with con() as c:return [dict(x) for x in c.execute(q,p).fetchall()]
def exe(q,p=()):
 with con() as c:c.execute(q,p)
def jd(x):return json.dumps(x,ensure_ascii=False)
def jl(x,default):
 try:return json.loads(x)
 except Exception:return default
