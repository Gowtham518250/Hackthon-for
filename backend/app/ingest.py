from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import fitz
from PIL import Image
from docx import Document

try:
    from rapidocr import RapidOCR
    _OCR = RapidOCR()
except Exception:
    _OCR = None


def _ocr_image(image_bytes: bytes) -> str:
    if _OCR is None:
        return ""
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        result = _OCR(np.asarray(image))
        if hasattr(result, "txts"):
            values = result.txts or ()
        elif isinstance(result, tuple) and result:
            values = getattr(result[0], "txts", None) or result[0]
        else:
            values = result or []
        if isinstance(values, str):
            return values.strip()
        return "\n".join(str(value) for value in values if value).strip()
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
            if not page_text:
                try:
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                    page_text = _ocr_image(pix.tobytes("png"))
                    if page_text:
                        ocr = True
                except Exception:
                    page_text = ""
            if page_text:
                text += f"\n\n[[SOURCE:page {i + 1}]]\n{page_text}\n"
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
        refs = ["document"]

    elif ext in {".xlsx", ".xls"}:
        sheets = pd.read_excel(path, sheet_name=None)
        frames = []
        for sheet_name, frame in sheets.items():
            if not frame.empty:
                frames.append(f"\n\n[[SOURCE:sheet {sheet_name}]]\n" + frame.to_csv(index=True))
        text = "\n".join(frames)
        refs = [f"sheet {name}" for name in sheets] or ["table"]

    elif ext == ".csv":
        frame = pd.read_csv(path)
        text = "\n\n[[SOURCE:table]]\n" + frame.to_csv(index=True)
        refs = ["table"]

    elif ext in {".jpg", ".jpeg", ".png"}:
        text = _ocr_image(path.read_bytes())
        ocr = bool(text)
        refs = ["image"]

    elif ext in {".txt", ".md"}:
        text = path.read_text(errors="ignore")
        refs = ["text"]

    return text, refs, ocr, pages
