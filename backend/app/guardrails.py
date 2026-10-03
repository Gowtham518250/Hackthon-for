import re
import zipfile
from pathlib import Path
from typing import Any

MAX_QUERY_CHARS = 1000
MAX_ANSWER_CHARS = 5000
MAX_CONTEXT_CHARS = 12000
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_ZIP_UNCOMPRESSED_BYTES = 150 * 1024 * 1024
MAX_ZIP_MEMBERS = 2500

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all|any|the)\s+(previous|prior|above)\s+instructions",
    r"disregard\s+(all|any|the)\s+(previous|prior|above)",
    r"(system|developer)\s+prompt",
    r"reveal\s+(the\s+)?(system|developer)\s+instructions",
    r"show\s+(me\s+)?(your|the)\s+(hidden|secret)\s+(prompt|instructions|rules)",
    r"bypass\s+(the\s+)?(safety|guardrails|policy)",
    r"override\s+(the\s+)?(system|developer)",
    r"you\s+are\s+now\s+(a|an)\s+",
]

SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I | re.S), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[REDACTED_JWT]"),
    (re.compile(r"\b(?:password|passwd|secret)\s*[:=]\s*[^\s,;]+", re.I), r"\1=[REDACTED]"),
]

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".csv", ".jpg", ".jpeg", ".png", ".txt", ".md"}
ZIP_LIKE_EXTENSIONS = {".docx", ".xlsx", ".xlsm", ".pptx"}

class GuardrailViolation(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)

def validate_query(query: str) -> str:
    if not isinstance(query, str):
        raise GuardrailViolation("invalid_query", "Search query must be text.")
    query = query.strip()
    if not query:
        raise GuardrailViolation("empty_query", "Search query cannot be empty.")
    if len(query) > MAX_QUERY_CHARS:
        raise GuardrailViolation("query_too_long", f"Search query must be at most {MAX_QUERY_CHARS} characters.")
    return query

def detect_prompt_injection(text: str) -> list[str]:
    findings: list[str] = []
    normalized = text.lower()
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, normalized):
            findings.append(pattern)
    return findings

def guard_ai_query(query: str) -> str:
    query = validate_query(query)
    if detect_prompt_injection(query):
        raise GuardrailViolation(
            "prompt_injection",
            "The AI explanation request looks like an attempt to override system instructions. Search itself remains available; ask a document question instead.",
        )
    return query

def redact_sensitive(text: str) -> str:
    redacted = text
    for pattern, replacement in SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted[:MAX_ANSWER_CHARS]

def validate_upload(filename: str, size_bytes: int) -> str:
    if not filename:
        raise GuardrailViolation("missing_filename", "A file name is required.")
    safe_name = Path(filename).name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise GuardrailViolation("unsupported_file_type", f"Unsupported file type: {suffix or 'unknown'}.")
    if size_bytes <= 0:
        raise GuardrailViolation("empty_file", "The uploaded file is empty.")
    if size_bytes > MAX_UPLOAD_BYTES:
        raise GuardrailViolation("file_too_large", f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.")
    return safe_name

def inspect_zip_container(path: Path) -> None:
    if path.suffix.lower() not in ZIP_LIKE_EXTENSIONS:
        return
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ZIP_MEMBERS:
                raise GuardrailViolation("archive_bomb", "Document contains too many internal entries.")
            total_uncompressed = sum(i.file_size for i in infos)
            if total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
                raise GuardrailViolation("archive_bomb", "Document expands beyond the safe uncompressed-size limit.")
    except zipfile.BadZipFile as exc:
        raise GuardrailViolation("invalid_container", "The uploaded Office document is not a valid archive.") from exc

def safe_evidence_context(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    budget = MAX_CONTEXT_CHARS
    for item in results:
        evidence = redact_sensitive(str(item.get("content", "")))
        if not evidence or budget <= 0:
            continue
        evidence = evidence[:budget]
        budget -= len(evidence)
        safe.append({
            "file_id": item.get("file_id"),
            "file_name": item.get("file_name"),
            "source_ref": item.get("source_ref"),
            "score": item.get("score", 0),
            "evidence": evidence,
            "document_contains_possible_instructions": bool(detect_prompt_injection(evidence)),
        })
    return safe

def validate_ai_citations(citations: Any, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed = {(r.get("file_id"), r.get("source_ref")) for r in results}
    valid: list[dict[str, Any]] = []
    if not isinstance(citations, list):
        return valid
    for c in citations:
        if not isinstance(c, dict):
            continue
        key = (c.get("file_id"), c.get("source_ref"))
        if key in allowed:
            valid.append({
                "file_id": c.get("file_id"),
                "file_name": c.get("file_name"),
                "source_ref": c.get("source_ref"),
            })
    return valid

def grounded_fallback(query: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "answer": "I couldn't find supporting evidence in your indexed files.",
            "confidence": 0,
            "citations": [],
            "guardrails": ["grounded_only", "no_evidence_no_claim"],
        }
    top = results[:3]
    snippets = []
    citations = []
    for r in top:
        snippets.append(f"{r.get('file_name')} ({r.get('source_ref')}): {r.get('content','').strip()}")
        citations.append({
            "file_id": r.get("file_id"),
            "file_name": r.get("file_name"),
            "source_ref": r.get("source_ref"),
        })
    answer = "Based only on retrieved evidence:\n\n" + "\n\n".join(snippets)
    return {
        "answer": redact_sensitive(answer),
        "confidence": round(float(top[0].get("score", 0)) * 100, 1),
        "citations": citations,
        "guardrails": ["grounded_only", "no_evidence_no_claim", "secret_redaction"],
    }
