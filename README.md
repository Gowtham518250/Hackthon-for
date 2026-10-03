# DeepSearch Cloud File Manager

AI-powered deep search across a bounded private corpus of PDF, Word, Excel, CSV, text and image files.

## Production architecture

```
User
  ↓
React / Vite frontend
  ↓
FastAPI backend
  ├── PostgreSQL → users, file metadata, chunks, embeddings
  ├── S3-compatible object storage → original uploaded documents
  ├── FAISS + all-MiniLM-L6-v2 → semantic retrieval
  ├── BM25-style lexical retrieval → exact terms / numbers / names
  ├── Groq → guarded evidence-grounded explanations
  └── Render Key Value / Redis → optional shared search cache
```

## Upload and indexing flow

```
Upload
  ↓
Validate + archive-bomb checks
  ↓
Persist original → S3 / R2 / MinIO
  ↓
Extract text
  ↓
Chunk + source references
  ↓
Generate all-MiniLM-L6-v2 embeddings
  ↓
Store chunks + embeddings in PostgreSQL
  ↓
Add vectors to per-user FAISS index
  ↓
Hybrid search (FAISS + lexical)
  ↓
Guarded Groq explanation + citations
```

The FAISS indexes are rebuilt from persisted embeddings when needed, so the application does not depend on Render's ephemeral filesystem for vector persistence.

## Object storage

Set:

```env
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=...
S3_REGION=auto
S3_BUCKET=...
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
```

The adapter is S3-compatible and works with AWS S3, Cloudflare R2, MinIO, and compatible providers.

## Render

The repository now includes a root `render.yaml` Blueprint defining:

- FastAPI backend
- React static site
- Render PostgreSQL
- Render Key Value

Secrets such as `GROQ_API_KEY` and S3 credentials are intentionally declared as `sync: false` and must be entered in Render rather than committed to Git.

## Local development

Backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The default development configuration uses SQLite + local object storage. Production should use PostgreSQL + S3-compatible storage.

## Current implementation

- Authentication foundation
- File upload limits and document guardrails
- S3-compatible persistent original-file storage
- PostgreSQL-compatible data layer
- all-MiniLM-L6-v2 ONNX embeddings
- FAISS per-user indexes
- Hybrid lexical + semantic retrieval
- Groq guarded answers
- Evidence citations
