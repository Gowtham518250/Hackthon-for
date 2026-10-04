import logging
import threading
import time
import uuid
import tempfile
from pathlib import Path

from .config import settings
from .db import one, exe, jd, now
from .storage import storage
from .ingest import extract
from .chunking import chunk_document
from .embeddings import embed_texts
from .job_queue import worker_status

logger = logging.getLogger("deepsearch.ingestion_worker")

_HEARTBEAT_SECONDS = 20


def _update_upload_job(job_id: str, **fields) -> None:
    allowed = {
        "file_id",
        "status",
        "stage",
        "progress",
        "error",
        "result",
        "updated_at",
    }
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return
    clean.setdefault("updated_at", now())
    assignments = ", ".join(f"{key}=?" for key in clean)
    params = tuple(clean.values()) + (job_id,)
    exe(f"UPDATE upload_jobs SET {assignments} WHERE id=?", params)


def _job_heartbeat(job_id: str, stop_event: threading.Event) -> None:
    while not stop_event.wait(_HEARTBEAT_SECONDS):
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

    claimed = one(
        """
        UPDATE upload_jobs
        SET status='processing', stage='extracting', progress=25,
            error=NULL, updated_at=?
        WHERE id=? AND status='queued'
        RETURNING id
        """,
        (now(), job_id),
    )
    if not claimed:
        return

    logger.info(
        "External ingestion worker claimed job=%s file=%s",
        job_id,
        row["name"],
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

    try:
        ext = Path(safe_name).suffix.lower()
        _update_upload_job(
            job_id,
            status="processing",
            stage="extracting",
            progress=25,
        )

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

            logger.info(
                "External worker starting extraction job=%s file=%s",
                job_id,
                safe_name,
            )
            extract_started = time.perf_counter()
            text, refs, ocr, pages = extract(
                dest,
                progress_callback=lambda progress: _update_upload_job(
                    job_id,
                    stage="extracting",
                    progress=progress,
                ),
            )
            extract_ms = (time.perf_counter() - extract_started) * 1000
            logger.info(
                "External worker extraction complete job=%s file=%s pages=%s ocr=%s extraction_ms=%.1f",
                job_id,
                safe_name,
                pages,
                bool(ocr),
                extract_ms,
            )

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

            # Release OCR resources before loading the embedding/FAISS stack.
            try:
                from .ingest import release_ocr_engine
                release_ocr_engine()
            except Exception:
                logger.exception("Could not release OCR resources")

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
                logger.warning(
                    "Embedding generation failed for %s: %s",
                    safe_name,
                    exc,
                )
            embedding_ms = (time.perf_counter() - embedding_started) * 1000

            from .vector_index import add_embeddings
            from .search import bump_search_version

            embedding_pairs: list[tuple[str, list[float]]] = []
            for i, chunk in enumerate(chunks):
                chunk_id = str(uuid.uuid4())
                _, source_ref, chunk_meta = chunk_records[i]
                embedding = vectors[i] if i < len(vectors) else None
                metadata = {
                    **chunk_meta,
                    "guardrails": ["document_is_untrusted_data_only"],
                    "retrieval": "faiss_semantic_plus_bm25",
                    "embedding_model": (
                        settings.embedding_model_repo if embedding else None
                    ),
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
                    "processing_ms": round(
                        (time.perf_counter() - started_at) * 1000,
                        1,
                    ),
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
                "External ingestion complete job=%s file=%s chunks=%s vectors=%s",
                job_id,
                safe_name,
                len(chunks),
                len(embedding_pairs),
            )

    except Exception as exc:
        logger.exception(
            "External ingestion failed job=%s file=%s",
            job_id,
            safe_name,
        )
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


def run_worker_status() -> dict:
    return worker_status()
