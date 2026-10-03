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


def _cache_key(user_id, query, limit, file_ids=None):
    version = "0"
    client = _cache_client()
    if client:
        try:
            version = client.get(f"deepsearch:search:version:{user_id}") or "0"
        except Exception:
            pass
    scope = ",".join(sorted(str(item) for item in (file_ids or [])))
    digest = hashlib.sha256(
        f"{user_id}|{version}|{limit}|{scope}|{query.strip().lower()}".encode("utf-8")
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
        return {key: 1.0 if high > 0 else 0.0 for key in scores}
    return {key: (value - low) / (high - low) for key, value in scores.items()}


def _query_features(query: str) -> dict:
    q = query.lower().strip()
    tokens = toks(q)
    top_match = re.search(r"\btop\s+(\d{1,2})\b", q)

    requested_difficulty = None
    if re.search(r"\b(hard|difficult)\b", q):
        requested_difficulty = "Hard"
    elif re.search(r"\bmedium\b", q):
        requested_difficulty = "Medium"
    elif re.search(r"\beasy\b", q):
        requested_difficulty = "Easy"

    return {
        "tokens": tokens,
        "token_set": set(tokens),
        "phrase": q if len(tokens) >= 2 else "",
        "requested_count": int(top_match.group(1)) if top_match else None,
        "difficulty": requested_difficulty,
    }


def _exact_relevance(query: str, content: str, metadata: dict, source_ref: str) -> tuple[float, list[str]]:
    features = _query_features(query)
    lower = content.lower()
    reasons = []

    if features["phrase"] and features["phrase"] in lower:
        reasons.append("exact phrase")

    matches = sum(
        1 for token in features["token_set"]
        if len(token) > 1 and token in lower
    )
    coverage = matches / max(1, len(features["token_set"]))

    if coverage >= 0.75:
        reasons.append("high term coverage")
    elif coverage >= 0.4:
        reasons.append("term match")

    if features["difficulty"] and metadata.get("difficulty") == features["difficulty"]:
        reasons.append(f"{features['difficulty']} difficulty")
    if source_ref and source_ref.lower() in lower:
        reasons.append("source match")

    exact = 0.0
    if features["phrase"] and features["phrase"] in lower:
        exact += 0.35
    exact += 0.45 * coverage
    if features["difficulty"] and metadata.get("difficulty") == features["difficulty"]:
        exact += 0.20

    return min(1.0, exact), reasons


def bump_search_version(user_id):
    client = _cache_client()
    if not client:
        return
    try:
        client.incr(f"deepsearch:search:version:{user_id}")
    except Exception:
        pass


def search(user_id, query, limit=20, file_ids=None):
    features = _query_features(query)
    effective_limit = features["requested_count"] or limit
    effective_limit = max(1, min(effective_limit, 50))

    client = _cache_client()
    cache_key = _cache_key(user_id, query, effective_limit, file_ids)

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
    if file_ids:
        allowed = {str(file_id) for file_id in file_ids}
        rows = [row for row in rows if str(row["file_id"]) in allowed]
    if not rows:
        return []

    # Difficulty-specific queries should preferentially/strictly retrieve
    # structured rows carrying that exact difficulty label.
    if features["difficulty"]:
        target_rows = [
            row for row in rows
            if jl(row["metadata"], {}).get("difficulty") == features["difficulty"]
        ]
        if target_rows:
            rows = target_rows

    lexical_scores = {
        row["id"]: bm25ish(query, row["content"])
        for row in rows
    }

    semantic_scores = {}
    try:
        query_vector = embed_query(query)
        semantic_scores = {
            item["chunk_id"]: item["score"]
            for item in semantic_search(
                user_id,
                query_vector,
                limit=min(120, max(60, effective_limit * 6)),
            )
            if item["chunk_id"] in {row["id"] for row in rows}
        }
    except Exception:
        semantic_scores = {}

    # Always keep lexical candidates, then add semantic candidates.
    lexical_candidates = sorted(
        lexical_scores,
        key=lexical_scores.get,
        reverse=True,
    )[: max(100, effective_limit * 8)]

    candidate_ids = set(lexical_candidates)
    candidate_ids.update(semantic_scores)

    if not candidate_ids:
        return []

    lexical_norm = _minmax({key: lexical_scores[key] for key in candidate_ids})
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

        metadata = jl(row["metadata"], {})
        exact, reasons = _exact_relevance(
            query,
            row["content"],
            metadata,
            row["source_ref"],
        )

        score = (
            0.50 * semantic_norm.get(chunk_id, 0.0)
            + 0.25 * lexical_norm.get(chunk_id, 0.0)
            + 0.25 * exact
        )

        # For a specific difficulty request, exact metadata agreement gets
        # a deterministic boost so the model never sees unrelated levels.
        if features["difficulty"] == metadata.get("difficulty"):
            score += 0.08

        ranked.append({
            "score": score,
            "row": row,
            "semantic_score": semantic_norm.get(chunk_id, 0.0),
            "lexical_score": lexical_norm.get(chunk_id, 0.0),
            "exact_score": exact,
            "reasons": reasons,
        })

    ranked.sort(key=lambda item: item["score"], reverse=True)

    diversified = []
    file_counts = Counter()

    for item in ranked:
        file_id = item["row"]["file_id"]
        if file_counts[file_id] >= 4 and len(diversified) < effective_limit:
            continue
        diversified.append(item)
        file_counts[file_id] += 1
        if len(diversified) >= effective_limit:
            break

    max_score = diversified[0]["score"] if diversified else 1.0
    results = []

    for item in diversified:
        row = item["row"]
        metadata = jl(row["metadata"], {})
        normalized = item["score"] / max_score if max_score > 0 else 0.0

        results.append({
            "score": round(min(0.99, max(0.0, normalized)), 3),
            "file_id": row["file_id"],
            "file_name": row["name"],
            "chunk_id": row["id"],
            "content": row["content"][:1100],
            "source_ref": row["source_ref"],
            "metadata": metadata,
            "retrieval": "hybrid-semantic-lexical-reranked",
            "match_reasons": item["reasons"] or ["semantic relevance"],
            "signals": {
                "semantic": round(item["semantic_score"], 3),
                "lexical": round(item["lexical_score"], 3),
                "exact": round(item["exact_score"], 3),
            },
        })

    if client:
        try:
            client.setex(cache_key, _CACHE_TTL_SECONDS, json.dumps(results))
        except Exception:
            pass

    return results
