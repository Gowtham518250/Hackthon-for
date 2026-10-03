from pathlib import Path

import pandas as pd
import fitz
from docx import Document

try:
    from rapidocr_onnxruntime import RapidOCR

    _OCR = RapidOCR()
except Exception:
    _OCR = None


def _ocr_image(image_bytes: bytes) -> str:
    if _OCR is None:
        return ""
    try:
        result, _ = _OCR(image_bytes)
        if not result:
            return ""
        lines = []
        for item in result:
            if len(item) >= 2:
                lines.append(str(item[1]))
        return "\n".join(lines).strip()
    except Exception:
        return ""


def extract(path: Path):
    ext = path.suffix.lower()
    text = ""
    refs = []
    ocr = False
    pages = 0

    if ext == ".pdf":
        doc = fitz.open(path)
        pages = len(doc)

        for i, page in enumerate(doc):
            page_text = (page.get_text("text") or "").strip()

            # OCR scanned pages when normal PDF text extraction is empty.
            if not page_text:
                try:
                    pix = page.get_pixmap(
                        matrix=fitz.Matrix(1.5, 1.5),
                        alpha=False,
                    )
                    page_text = _ocr_image(pix.tobytes("png"))
                    if page_text:
                        ocr = True
                except Exception:
                    page_text = ""

            if page_text:
                text += f"\n{page_text}"
                refs.append(f"page {i + 1}")

    elif ext == ".docx":
        document = Document(path)
        paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
        tables = [
            " | ".join(cell.text.strip() for cell in row.cells)
            for table in document.tables
            for row in table.rows
        ]
        text = "\n".join(paragraphs + [row for row in tables if row])

        # DOCX content is already text-extractable. Embedded-image OCR can be
        # added later without changing the object-storage/indexing pipeline.
        refs = ["document"]

    elif ext in {".xlsx", ".xls"}:
        sheets = pd.read_excel(path, sheet_name=None)
        frames = []
        for sheet_name, frame in sheets.items():
            if not frame.empty:
                frames.append(
                    f"Sheet: {sheet_name}\n"
                    + frame.to_csv(index=True)
                )
        text = "\n".join(frames)
        refs = list(sheets.keys()) or ["table"]

    elif ext == ".csv":
        frame = pd.read_csv(path)
        text = frame.to_csv(index=True)
        refs = ["table"]

    elif ext in {".jpg", ".jpeg", ".png"}:
        text = _ocr_image(path.read_bytes())
        ocr = bool(text)
        refs = ["image"] if text else []

    elif ext in {".txt", ".md"}:
        text = path.read_text(errors="ignore")
        refs = ["text"]

    return text, refs, ocr, pages
