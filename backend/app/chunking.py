import re

SOURCE_MARKER = re.compile(r"\[\[SOURCE:\s*(.*?)\s*\]\]", re.IGNORECASE)
PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")
NUMBERED_ITEM = re.compile(
    r"(?m)(?=^\s*(?:\d{1,3}\s*[.)]|q(?:uestion)?\s*\d{1,3}\s*[:.)-]))"
)

# Handles both normal line-separated lists and PDF-extracted table rows where
# the entire table becomes one long line:
# "36 Valid Parentheses Easy Stack LeetCode #20 37 Min Stack Medium ..."
PROBLEM_ROW = re.compile(
    r"(?P<number>\d{1,3})\s+"
    r"(?P<name>.*?)\s+"
    r"(?P<difficulty>Easy|Medium|Hard)\s+"
    r"(?P<details>.*?)"
    r"(?=\s+\d{1,3}\s+[^#]|$)",
    re.IGNORECASE | re.DOTALL,
)
LEETCODE = re.compile(r"LeetCode\s+#?\s*(\d+)", re.IGNORECASE)


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

    pieces = [_clean(x) for x in re.split(NUMBERED_ITEM, text) if _clean(x)]
    if len(pieces) <= 1:
        pieces = [x.strip() for x in PARAGRAPH_SPLIT.split(text) if x.strip()]

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


def _structured_problem_rows(section: str, source_ref: str):
    matches = list(PROBLEM_ROW.finditer(_clean(section)))
    if len(matches) < 2:
        return []

    rows = []
    for match in matches:
        number = int(match.group("number"))
        name = _clean(match.group("name"))
        difficulty = match.group("difficulty").title()
        details = _clean(match.group("details"))

        # Avoid treating headings such as "100 DSA Problems ..." as rows.
        if len(name) < 2 or len(name) > 140:
            continue

        link = LEETCODE.search(details)
        leetcode = f"LeetCode #{link.group(1)}" if link else ""
        pattern = LEETCODE.sub("", details).strip(" |,-")

        content_parts = [
            f"Problem {number}: {name}",
            f"Difficulty: {difficulty}",
        ]
        if pattern:
            content_parts.append(f"Pattern: {pattern}")
        if leetcode:
            content_parts.append(leetcode)
        content_parts.append(f"Source: {source_ref}")

        rows.append(
            (
                "\n".join(content_parts),
                source_ref,
                {
                    "index": len(rows),
                    "source_ref": source_ref,
                    "problem_number": number,
                    "problem_name": name,
                    "difficulty": difficulty,
                    "pattern": pattern,
                    "leetcode": leetcode,
                    "structured_type": "problem_row",
                },
            )
        )

    return rows


def chunk_document(text: str, default_refs=None):
    default_refs = default_refs or ["document"]
    matches = list(SOURCE_MARKER.finditer(text))

    if matches:
        sections = []
        for i, match in enumerate(matches):
            source_ref = (
                match.group(1).strip()
                or default_refs[min(i, len(default_refs) - 1)]
            )
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = _clean(text[start:end])
            if body:
                sections.append((source_ref, body))
    else:
        body = _clean(text)
        sections = [(default_refs[0], body)] if body else []

    chunks = []
    index = 0

    for source_ref, body in sections:
        structured = _structured_problem_rows(body, source_ref)
        pieces = structured or [
            (
                piece,
                source_ref,
                {
                    "index": index,
                    "source_ref": source_ref,
                    "structured_type": "text_chunk",
                },
            )
            for piece in _window(body)
        ]

        for content, ref, metadata in pieces:
            metadata["index"] = index
            chunks.append((content, ref, metadata))
            index += 1

    return chunks
