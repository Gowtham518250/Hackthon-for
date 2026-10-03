import json
from threading import RLock

import faiss
import numpy as np

from .db import all_

_CACHE: dict[str, tuple[faiss.IndexFlatIP, list[str]]] = {}
_LOCK = RLock()


def _build_user_index(user_id: str):
    rows = all_(
        "SELECT id, embedding FROM chunks "
        "WHERE user_id=? AND embedding IS NOT NULL",
        (user_id,),
    )

    vectors = []
    chunk_ids = []

    for row in rows:
        try:
            vector = np.asarray(json.loads(row["embedding"]), dtype=np.float32)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if vector.ndim != 1 or vector.size == 0:
            continue
        vectors.append(vector)
        chunk_ids.append(row["id"])

    if not vectors:
        return None

    matrix = np.vstack(vectors).astype(np.float32)
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)

    return index, chunk_ids


def rebuild_user_index(user_id: str) -> None:
    with _LOCK:
        built = _build_user_index(user_id)
        if built is None:
            _CACHE.pop(user_id, None)
        else:
            _CACHE[user_id] = built


def add_embeddings(user_id: str, embeddings: list[tuple[str, list[float]]]) -> None:
    if not embeddings:
        return

    with _LOCK:
        existing = _CACHE.get(user_id)
        if existing is None:
            built = _build_user_index(user_id)
            if built is None:
                dimension = len(embeddings[0][1])
                index = faiss.IndexFlatIP(dimension)
                chunk_ids: list[str] = []
            else:
                index, chunk_ids = built
        else:
            index, chunk_ids = existing

        matrix = np.asarray(
            [vector for _, vector in embeddings],
            dtype=np.float32,
        )
        if matrix.ndim != 2 or matrix.shape[0] == 0:
            return

        if index.d != matrix.shape[1]:
            raise ValueError("Embedding dimension does not match the FAISS index.")

        index.add(matrix)
        chunk_ids.extend(chunk_id for chunk_id, _ in embeddings)
        _CACHE[user_id] = (index, chunk_ids)


def semantic_search(user_id: str, query_embedding: list[float], limit: int = 50):
    with _LOCK:
        existing = _CACHE.get(user_id)
        if existing is None:
            built = _build_user_index(user_id)
            if built is None:
                return []
            _CACHE[user_id] = built
            existing = built

        index, chunk_ids = existing
        if index.ntotal == 0:
            return []

        vector = np.asarray([query_embedding], dtype=np.float32)
        k = min(max(1, limit), index.ntotal)
        distances, positions = index.search(vector, k)

        output = []
        for score, position in zip(distances[0], positions[0]):
            if position < 0 or position >= len(chunk_ids):
                continue
            output.append(
                {
                    "chunk_id": chunk_ids[position],
                    "score": float(score),
                }
            )
        return output
