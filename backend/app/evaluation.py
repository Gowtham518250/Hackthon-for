import hashlib
import math
import time
from collections import Counter

from .db import all_, jl, one
from .search import bm25ish, search


STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "about",
    "what", "where", "when", "which", "your", "have", "has", "are", "was",
    "were", "will", "can", "does", "did", "find", "show", "give", "information",
    "document", "documents", "file", "files", "page", "section", "using",
    "related", "details", "content", "their", "then", "than", "over", "under",
    "also", "only", "more", "most", "some", "such", "how", "why",
}


def _clean_terms(text: str, limit: int = 7) -> list[str]:
    terms = []
    seen = set()
    for token in text.lower().replace("_", " ").split():
        token = "".join(ch for ch in token if ch.isalnum() or ch in {"-", "#"})
        if len(token) < 4 or token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        terms.append(token)
        if len(terms) >= limit:
            break
    return terms


def keyword_baseline(user_id: str, query: str, limit: int = 10) -> tuple[list[dict], float]:
    started = time.perf_counter()
    rows = all_(
        "SELECT c.*, f.name FROM chunks c "
        "JOIN files f ON f.id=c.file_id WHERE c.user_id=?",
        (user_id,),
    )
    scored = []
    q_tokens = set(query.lower().split())
    for row in rows:
        lexical = bm25ish(query, row["content"])
        text = row["content"].lower()
        exact = sum(1 for token in q_tokens if len(token) > 1 and token in text)
        score = lexical + (0.02 * exact)
        scored.append((score, row))
    scored.sort(key=lambda x: x[0], reverse=True)
    output = []
    for rank, (score, row) in enumerate(scored[:limit], 1):
        output.append(
            {
                "rank": rank,
                "score": round(float(score), 4),
                "chunk_id": row["id"],
                "file_id": row["file_id"],
                "file_name": row["name"],
                "source_ref": row["source_ref"],
                "content": row["content"][:900],
            }
        )
    return output, (time.perf_counter() - started) * 1000


def _metrics(results: list[dict], gold_ids: set[str], k: int = 5) -> dict:
    top = results[:k]
    hits = [idx + 1 for idx, item in enumerate(top) if item["chunk_id"] in gold_ids]
    relevant = sum(1 for item in top if item["chunk_id"] in gold_ids)
    precision = relevant / max(1, len(top))
    recall = relevant / max(1, len(gold_ids))
    mrr = 1.0 / hits[0] if hits else 0.0

    dcg = 0.0
    for idx, item in enumerate(top, 1):
        if item["chunk_id"] in gold_ids:
            dcg += 1.0 / math.log2(idx + 1)
    ideal_hits = min(k, len(gold_ids))
    idcg = sum(1.0 / math.log2(idx + 1) for idx in range(1, ideal_hits + 1))
    ndcg = dcg / idcg if idcg else 0.0

    return {
        "precision_at_5": round(precision * 100, 1),
        "recall_at_5": round(recall * 100, 1),
        "mrr": round(mrr, 3),
        "ndcg_at_5": round(ndcg, 3),
        "relevant_hits_at_5": relevant,
        "gold_count": len(gold_ids),
    }


def build_benchmark_cases(user_id: str, limit: int = 6) -> list[dict]:
    rows = all_(
        "SELECT c.id,c.file_id,c.content,c.source_ref,c.metadata,f.name "
        "FROM chunks c JOIN files f ON f.id=c.file_id "
        "WHERE c.user_id=? ORDER BY f.created_at DESC, c.id ASC",
        (user_id,),
    )
    cases = []
    used_files = set()

    # Prefer structured DSA-style chunks when available because they make a
    # particularly clear judge scenario (difficulty + pattern + problem).
    for row in rows:
        if len(cases) >= limit:
            break
        meta = jl(row.get("metadata") or "{}", {})
        if not meta.get("difficulty") and not meta.get("pattern"):
            continue
        if row["file_id"] in used_files and len(used_files) < 3:
            continue
        difficulty = meta.get("difficulty") or ""
        pattern = meta.get("pattern") or ""
        name = meta.get("name") or row["content"][:80]
        query = "Find"
        if difficulty:
            query += f" {difficulty}"
        if pattern:
            query += f" {pattern}"
        query += f" problems related to {name}"
        cases.append(
            {
                "id": f"case-{len(cases)+1}",
                "query": query,
                "gold_chunk_ids": [row["id"]],
                "gold_preview": row["content"][:180],
                "file_name": row["name"],
                "source_ref": row["source_ref"],
                "basis": "structured metadata",
            }
        )
        used_files.add(row["file_id"])

    # Fill remaining cases from representative corpus chunks.
    for row in rows:
        if len(cases) >= limit:
            break
        if row["file_id"] in used_files and len(cases) < max(3, limit // 2):
            continue
        terms = _clean_terms(row["content"], 6)
        if len(terms) < 3:
            continue
        query = "Find information about " + " ".join(terms[:5])
        cases.append(
            {
                "id": f"case-{len(cases)+1}",
                "query": query,
                "gold_chunk_ids": [row["id"]],
                "gold_preview": row["content"][:180],
                "file_name": row["name"],
                "source_ref": row["source_ref"],
                "basis": "representative corpus chunk",
            }
        )
        used_files.add(row["file_id"])

    return cases


def run_benchmark(user_id: str, limit: int = 6) -> dict:
    cases = build_benchmark_cases(user_id, limit)
    if not cases:
        return {
            "cases": [],
            "status": "needs_corpus",
            "message": "Upload at least one representative document before running the benchmark.",
        }

    case_results = []
    hybrid_metrics = []
    baseline_metrics = []
    for case in cases:
        hybrid_started = time.perf_counter()
        hybrid = search(user_id, case["query"], 10)
        hybrid_ms = (time.perf_counter() - hybrid_started) * 1000
        hybrid_rows = [
            {
                "rank": idx + 1,
                "score": item.get("score", 0),
                "chunk_id": item["chunk_id"],
                "file_id": item["file_id"],
                "file_name": item["file_name"],
                "source_ref": item["source_ref"],
                "content": item["content"],
            }
            for idx, item in enumerate(hybrid[:10])
        ]
        baseline, baseline_ms = keyword_baseline(user_id, case["query"], 10)
        gold = set(case["gold_chunk_ids"])
        hm = _metrics(hybrid_rows, gold)
        bm = _metrics(baseline, gold)
        hybrid_metrics.append(hm)
        baseline_metrics.append(bm)
        case_results.append(
            {
                **case,
                "hybrid": {"results": hybrid_rows[:5], "latency_ms": round(hybrid_ms, 1), **hm},
                "baseline": {"results": baseline[:5], "latency_ms": round(baseline_ms, 1), **bm},
                "winner_by_first_relevant_rank": (
                    "DeepSearch" if (hm["mrr"] > bm["mrr"]) else
                    "Keyword baseline" if (bm["mrr"] > hm["mrr"]) else
                    "Tie"
                ),
            }
        )

    def avg(key, rows):
        return round(sum(item[key] for item in rows) / max(1, len(rows)), 3)

    def avg_pct(key, rows):
        return round(sum(item[key] for item in rows) / max(1, len(rows)), 1)

    baseline_summary = {
        "precision_at_5": avg_pct("precision_at_5", baseline_metrics),
        "recall_at_5": avg_pct("recall_at_5", baseline_metrics),
        "mrr": avg("mrr", baseline_metrics),
        "ndcg_at_5": avg("ndcg_at_5", baseline_metrics),
        "cases": len(cases),
        "avg_latency_ms": round(sum(c["baseline"]["latency_ms"] for c in case_results) / len(case_results), 1),
    }
    hybrid_summary = {
        "precision_at_5": avg_pct("precision_at_5", hybrid_metrics),
        "recall_at_5": avg_pct("recall_at_5", hybrid_metrics),
        "mrr": avg("mrr", hybrid_metrics),
        "ndcg_at_5": avg("ndcg_at_5", hybrid_metrics),
        "cases": len(cases),
        "avg_latency_ms": round(sum(c["hybrid"]["latency_ms"] for c in case_results) / len(case_results), 1),
    }

    return {
        "status": "ok",
        "benchmark_type": "corpus-derived single-gold benchmark",
        "baseline": {
            "name": "Keyword-only baseline",
            "description": "Lexical BM25-style matching without embeddings or reranking.",
            "summary": baseline_summary,
        },
        "deepsearch": {
            "name": "DeepSearch hybrid",
            "description": "Semantic + lexical + exact signals with reranking and structured metadata.",
            "summary": hybrid_summary,
        },
        "cases": case_results,
        "limitations": [
            "Gold labels are generated from representative indexed chunks; use curated labels for formal research evaluation.",
            "Metrics are corpus-local and intended for comparative hackathon demonstration.",
            "Latency includes retrieval work only and varies with deployment resources.",
        ],
    }


def corpus_snapshot(user_id: str, query: str, limit: int = 5) -> dict:
    files = all_(
        "SELECT id,name,chunk_count,created_at FROM files WHERE user_id=? ORDER BY created_at DESC",
        (user_id,),
    )
    stats = one(
        "SELECT COUNT(*) AS files, COALESCE(SUM(chunk_count),0) AS chunks "
        "FROM files WHERE user_id=?",
        (user_id,),
    )
    fingerprint_src = "|".join(f"{r['id']}:{r['chunk_count']}" for r in files)
    fingerprint = hashlib.sha256(fingerprint_src.encode()).hexdigest()[:12]
    started = time.perf_counter()
    hybrid = search(user_id, query, limit)
    hybrid_ms = (time.perf_counter() - started) * 1000
    baseline, baseline_ms = keyword_baseline(user_id, query, limit)
    return {
        "captured_at": time.time(),
        "corpus": {
            "files": int(stats["files"] or 0),
            "chunks": int(stats["chunks"] or 0),
            "fingerprint": fingerprint,
        },
        "query": query,
        "hybrid": hybrid,
        "baseline": baseline,
        "latency_ms": {
            "hybrid": round(hybrid_ms, 1),
            "baseline": round(baseline_ms, 1),
        },
        "top_file_ids": [r["file_id"] for r in hybrid[:limit]],
        "files": files[:12],
    }


def compare_snapshots(before: dict, after: dict) -> dict:
    before_ids = [r.get("file_id") for r in before.get("hybrid", [])]
    after_ids = [r.get("file_id") for r in after.get("hybrid", [])]
    before_chunks = [r.get("chunk_id") for r in before.get("hybrid", [])]
    after_chunks = [r.get("chunk_id") for r in after.get("hybrid", [])]
    new_result_chunks = [x for x in after_chunks if x not in before_chunks]
    removed_result_chunks = [x for x in before_chunks if x not in after_chunks]
    return {
        "corpus_changed": before.get("corpus", {}).get("fingerprint") != after.get("corpus", {}).get("fingerprint"),
        "file_delta": after.get("corpus", {}).get("files", 0) - before.get("corpus", {}).get("files", 0),
        "chunk_delta": after.get("corpus", {}).get("chunks", 0) - before.get("corpus", {}).get("chunks", 0),
        "new_result_files": [x for x in after_ids if x not in before_ids],
        "new_result_chunks": new_result_chunks,
        "removed_result_chunks": removed_result_chunks,
        "top_result_before": (before.get("hybrid") or [{}])[0],
        "top_result_after": (after.get("hybrid") or [{}])[0],
        "score_delta": round(
            ((after.get("hybrid") or [{}])[0].get("score", 0))
            - ((before.get("hybrid") or [{}])[0].get("score", 0)),
            3,
        ),
    }
