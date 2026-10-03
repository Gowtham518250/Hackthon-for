import hashlib
import json
import math
import re
from collections import Counter

from .config import settings
from .db import all_, jl
from .embeddings import embed_query
from .vector_index import semantic_search

try:
    import redis
except ImportError:
    redis = None

TOKEN_RE = re.compile(r"\b\w+\b")
_CACHE_TTL_SECONDS = 60
_redis = None


def _cache_client():
    global _redis
    if _redis is not None:
        return _redis
    if not settings.redis_url or redis is None:
        return None
    try:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
        _redis.ping()
        return _redis
    except Exception:
        _redis = None
        return None


def _cache_key(user_id, query, limit):
    version = "0"
    client = _cache_client()
    if client:
        try:
            version = client.get(f"deepsearch:search:version:{user_id}") or "0"
        except Exception:
            pass

    digest = hashlib.sha256(
        f"{user_id}|{version}|{limit}|{query.strip().lower()}".encode("utf-8")
    ).hexdigest()
    return f"deepsearch:search:{digest}"


def toks(value: str) -> list[str]:
    return TOKEN_RE.findall(value.lower())


def bm25ish(query: str, doc: str) -> float:
    q = set(toks(query))
    d = toks(doc)
    if not d:
        return 0.0
    counts = Counter(d)
    return sum(
        (1 + math.log1p(counts[token]))
        for token in q
        if counts[token]
    ) / (1 + math.log1p(len(d)))


def _minmax(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    low = min(scores.values())
    high = max(scores.values())
    if high - low < 1e-9:
        return {
            key: 1.0 if high > 0 else 0.0
            for key in scores
        }
    return {
        key: (value - low) / (high - low)
        for key, value in scores.items()
    }


def _query_features(query: str) -> dict:
    q = query.lower().strip()
    tokens = [token for token in toks(q) if len(token) > 1]
    phrase = q if len(tokens) >= 2 else ""
    top_match = re.search(r"\btop\s+(\d{1,2})\b", q)

    return {
        "tokens": tokens,
        "token_set": set(tokens),
        "phrase": phrase,
        "requested_count": int(top_match.group(1)) if top_match else None,
        "difficulty": any(
            word in tokens
            for word in ("hard", "difficult", "difficulty")
        ),
    }


def _exact_relevance(query: str, content: str, source_ref: str) -> tuple[float, list[str]]:
    q = _query_features(query)
    lower = content.lower()
    reasons = []

    if q["phrase"] and q["phrase"] in lower:
        reasons.append("exact phrase")

    matches = sum(1 for token in q["token_set"] if token in lower)
    coverage = matches / max(1, len(q["token_set"]))

    if coverage >= 0.75:
        reasons.append("high term coverage")
    elif coverage >= 0.4:
        reasons.append("term match")

    if source_ref and source_ref.lower() in lower:
        reasons.append("source match")

    difficulty_markers = {
        "hard", "difficult", "difficulty", "easy", "medium"
    }
    if q["difficulty"] and any(marker in lower for marker in difficulty_markers):
        reasons.append("difficulty evidence")

    phrase_bonus = 1.0 if q["phrase"] and q["phrase"] in lower else 0.0
    return min(1.0, 0.35 * phrase_bonus + 0.65 * coverage), reasons


def bump_search_version(user_id):
    client = _cache_client()
    if not client:
        return
    try:
        client.incr(f"deepsearch:search:version:{user_id}")
    except Exception:
        pass


def search(user_id, query, limit=20):
    client = _cache_client()
    cache_key = _cache_key(user_id, query, limit)

    if client:
        try:
            cached = client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    rows = all_(
        "SELECT c.*, f.name FROM chunks c "
        "JOIN files f ON f.id=c.file_id WHERE c.user_id=?",
        (user_id,),
    )

    if not rows:
        return []

    features = _query_features(query)

    lexical_scores = {
        row["id"]: bm25ish(query, row["content"])
        for row in rows
    }

    semantic_scores = {}
    try:
        query_vector = embed_query(query)
        semantic_hits = semantic_search(
            user_id,
            query_vector,
            limit=min(120, max(60, limit * 6)),
        )
        semantic_scores = {
            item["chunk_id"]: item["score"]
            for item in semantic_hits
        }
    except Exception:
        semantic_scores = {}

    candidate_ids = set(
        sorted(
            lexical_scores,
            key=lexical_scores.get,
            reverse=True,
        )[: max(100, limit * 8)]
    )
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

    by_id = {row["id"]: row for row in rows}
    ranked = []

    for chunk_id in candidate_ids:
        row = by_id.get(chunk_id)
        if not row:
            continue

        lexical = lexical_norm.get(chunk_id, 0.0)
        semantic = semantic_norm.get(chunk_id, 0.0)
        exact, reasons = _exact_relevance(
            query,
            row["content"],
            row["source_ref"],
        )

        # Meaning + exact terminology + query coverage.
        score = (
            0.52 * semantic
            + 0.28 * lexical
            + 0.20 * exact
        )

        ranked.append(
            {
                "score": score,
                "row": row,
                "lexical_score": lexical,
                "semantic_score": semantic,
                "exact_score": exact,
                "reasons": reasons,
            }
        )

    ranked.sort(key=lambda item: item["score"], reverse=True)

    # Lightweight result diversification: don't let one huge source consume
    # every slot when other files also contain strong evidence.
    diversified = []
    file_counts = Counter()
    for item in ranked:
        file_id = item["row"]["file_id"]
        if file_counts[file_id] >= 4 and len(diversified) < limit:
            continue
        diversified.append(item)
        file_counts[file_id] += 1
        if len(diversified) >= limit:
            break

    max_score = diversified[0]["score"] if diversified else 1.0
    results = []

    for item in diversified:
        row = item["row"]
        normalized = (
            item["score"] / max_score
            if max_score > 0
            else 0.0
        )
        results.append(
            {
                "score": round(min(0.99, max(0.0, normalized)), 3),
                "file_id": row["file_id"],
                "file_name": row["name"],
                "chunk_id": row["id"],
                "content": row["content"][:900],
                "source_ref": row["source_ref"],
                "metadata": jl(row["metadata"], {}),
                "retrieval": "hybrid-semantic-lexical-reranked",
                "match_reasons": item["reasons"] or ["semantic relevance"],
                "signals": {
                    "semantic": round(item["semantic_score"], 3),
                    "lexical": round(item["lexical_score"], 3),
                    "exact": round(item["exact_score"], 3),
                },
            }
        )

    if client:
        try:
            client.setex(
                cache_key,
                _CACHE_TTL_SECONDS,
                json.dumps(results),
            )
        except Exception:
            pass

    return results
