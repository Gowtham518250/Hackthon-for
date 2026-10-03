import re

SOURCE_MARKER = re.compile(r"\[\[SOURCE:\s*(.*?)\s*\]\]", re.IGNORECASE)
NUMBERED_ITEM = re.compile(
    r"(?m)(?=^\s*(?:\d{1,3}\s*[.)]|q(?:uestion)?\s*\d{1,3}\s*[:.)-]))"
)
PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")


def _clean(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _window(text: str, max_chars: int = 900, overlap: int = 120):
    text = _clean(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    numbered = [_clean(x) for x in re.split(NUMBERED_ITEM, text) if _clean(x)]
    pieces = numbered if len(numbered) > 1 else [
        x.strip() for x in PARAGRAPH_SPLIT.split(text) if x.strip()
    ]

    output = []
    current = ""
    for piece in pieces:
        if len(piece) <= max_chars and len(current) + len(piece) + 2 <= max_chars:
            current = f"{current}\n\n{piece}".strip()
            continue

        if current:
            output.append(current)
            current = ""

        if len(piece) <= max_chars:
            current = piece
            continue

        start = 0
        while start < len(piece):
            end = min(len(piece), start + max_chars)
            segment = piece[start:end].strip()
            if segment:
                output.append(segment)
            if end >= len(piece):
                break
            start = max(start + 1, end - overlap)

    if current:
        output.append(current)
    return output


def chunk_document(text: str, default_refs=None):
    default_refs = default_refs or ["document"]
    matches = list(SOURCE_MARKER.finditer(text))
    sections = []

    if matches:
        for i, match in enumerate(matches):
            source_ref = match.group(1).strip() or default_refs[min(i, len(default_refs) - 1)]
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = _clean(text[start:end])
            if body:
                sections.append((source_ref, body))
    else:
        body = _clean(text)
        if body:
            sections.append((default_refs[0], body))

    chunks = []
    index = 0
    for source_ref, body in sections:
        for piece in _window(body):
            chunks.append((piece, source_ref, {"index": index, "source_ref": source_ref}))
            index += 1
    return chunks
