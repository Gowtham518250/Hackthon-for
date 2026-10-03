import math
import re
from collections import Counter

from .db import all_, jl
from .vector_index import semantic_search
from .embeddings import embed_query

TOKEN_RE = re.compile(r"\b\w+\b")


def toks(s):
    return TOKEN_RE.findall(s.lower())


def bm25ish(query, doc):
    q = set(toks(query))
    d = toks(doc)
    if not d:
        return 0.0
    counts = Counter(d)
    return sum((1 + math.log1p(counts[t])) for t in q if counts[t]) / (
        1 + math.log1p(len(d))
    )


def _minmax(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    low = min(scores.values())
    high = max(scores.values())
    if high - low < 1e-9:
        return {key: 1.0 if high > 0 else 0.0 for key in scores}
    return {
        key: (value - low) / (high - low)
        for key, value in scores.items()
    }


def search(user_id, query, limit=20):
    rows = all_(
        "SELECT c.*, f.name FROM chunks c "
        "JOIN files f ON f.id=c.file_id WHERE c.user_id=?",
        (user_id,),
    )

    if not rows:
        return []

    lexical_scores = {
        row["id"]: bm25ish(query, row["content"])
        for row in rows
    }

    lexical_positive = {
        key: value
        for key, value in lexical_scores.items()
        if value > 0
    }

    semantic_scores = {}
    try:
        query_vector = embed_query(query)
        for item in semantic_search(
            user_id,
            query_vector,
            limit=min(100, max(50, limit * 5)),
        ):
            semantic_scores[item["chunk_id"]] = item["score"]
    except Exception:
        # Semantic indexing failure must not take down ordinary search.
        semantic_scores = {}

    candidate_ids = set(lexical_positive)
    candidate_ids.update(semantic_scores)

    if not candidate_ids:
        return []

    lexical_norm = _minmax(
        {key: lexical_scores[key] for key in candidate_ids}
    )

    semantic_norm = {
        key: max(0.0, min(1.0, (value + 1.0) / 2.0))
        for key, value in semantic_scores.items()
        if key in candidate_ids
    }

    # Hybrid retrieval: semantic meaning gets slightly more weight while
    # lexical relevance protects exact names, IDs, dates and numbers.
    ranked = []
    by_id = {row["id"]: row for row in rows}
    for chunk_id in candidate_ids:
        lexical = lexical_norm.get(chunk_id, 0.0)
        semantic = semantic_norm.get(chunk_id, 0.0)
        score = (0.60 * semantic) + (0.40 * lexical)

        row = by_id.get(chunk_id)
        if not row:
            continue

        ranked.append((score, row))

    ranked.sort(key=lambda item: item[0], reverse=True)

    return [
        {
            "score": round(min(0.99, max(0.0, s)), 3),
            "file_id": row["file_id"],
            "file_name": row["name"],
            "chunk_id": row["id"],
            "content": row["content"][:700],
            "source_ref": row["source_ref"],
            "metadata": jl(row["metadata"], {}),
            "retrieval": "hybrid_semantic_bm25",
        }
        for s, row in ranked[:limit]
    ]
