import re, math
from collections import Counter
from .db import all_, jl

def toks(s):
    return re.findall(r"\b\w+\b", s.lower())

def bm25ish(query, doc):
    q = set(toks(query))
    d = toks(doc)
    c = Counter(d)
    return sum((1 + math.log1p(c[t])) for t in q if c[t]) / (1 + math.log1p(len(d)))

def search(user_id, query, limit=20):
    rows = all_("SELECT c.*, f.name FROM chunks c JOIN files f ON f.id=c.file_id WHERE c.user_id=?", (user_id,))
    ranked = []
    for r in rows:
        score = bm25ish(query, r["content"])
        if score > 0:
            ranked.append((score, r))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [{
        "score": round(min(0.99, s + 0.15), 3),
        "file_id": r["file_id"],
        "file_name": r["name"],
        "chunk_id": r["id"],
        "content": r["content"][:500],
        "source_ref": r["source_ref"],
        "metadata": jl(r["metadata"], {})
    } for s, r in ranked[:limit]]
