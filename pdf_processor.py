"""
Extracts tables and plain text from PDFs and images.

Supported inputs: PDF, JPG, JPEG, PNG, BMP, TIFF
- Digital PDFs  → pdfplumber (fast, no OCR needed)
- Scanned PDFs / Images → EasyOCR + img2table

First run downloads EasyOCR models (~100 MB) automatically.
"""

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import fitz  # PyMuPDF

import config

SUPPORTED_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif",
}

_ocr_reader = None


def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        print("Loading EasyOCR models (first run downloads ~100 MB)...")
        _ocr_reader = easyocr.Reader(["en"], gpu=False)
    return _ocr_reader


@dataclass
class CellData:
    row: int
    col: int
    row_span: int
    col_span: int
    text: str
    min_confidence: float
    is_low_confidence: bool = False


@dataclass
class TableData:
    page: int
    row_count: int
    col_count: int
    cells: list[CellData] = field(default_factory=list)
    is_plain_text: bool = False


def analyze_document(file_path: str) -> list[TableData]:
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    if ext == ".pdf":
        return _analyze_pdf(file_path)
    img = cv2.imread(file_path)
    if img is None:
        raise ValueError(f"Could not read image: {file_path}")
    return _analyze_image_array(img, page_num=1)


# ── PDF ───────────────────────────────────────────────────────────────────────

def _analyze_pdf(pdf_path: str) -> list[TableData]:
    import pdfplumber
    results = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            page_results = _process_pdfplumber_page(page, page_num)
            if not page_results:
                # Scanned page — render to image and OCR
                img = _pdf_page_to_image(pdf_path, page_num - 1)
                page_results = _analyze_image_array(img, page_num)
            results.extend(page_results)
    return results


def _process_pdfplumber_page(page, page_num: int) -> list[TableData]:
    results = []

    for raw_table in page.extract_tables() or []:
        if not raw_table:
            continue
        row_count = len(raw_table)
        col_count = max((len(r) for r in raw_table), default=0)
        if not row_count or not col_count:
            continue
        td = TableData(page=page_num, row_count=row_count, col_count=col_count)
        for r_idx, row in enumerate(raw_table):
            for c_idx in range(col_count):
                text = (row[c_idx] if c_idx < len(row) else None) or ""
                td.cells.append(CellData(
                    row=r_idx, col=c_idx,
                    row_span=1, col_span=1,
                    text=text.strip(),
                    min_confidence=1.0,
                ))
        results.append(td)

    if not results:
        text = page.extract_text() or ""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines:
            td = TableData(page=page_num, row_count=len(lines), col_count=1, is_plain_text=True)
            for r_idx, line in enumerate(lines):
                td.cells.append(CellData(
                    row=r_idx, col=0, row_span=1, col_span=1,
                    text=line, min_confidence=1.0,
                ))
            results.append(td)

    return results


def _pdf_page_to_image(pdf_path: str, page_index: int) -> np.ndarray:
    doc = fitz.open(pdf_path)
    pix = doc[page_index].get_pixmap(dpi=200)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    doc.close()
    if pix.n == 4:
        return cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


# ── Image ─────────────────────────────────────────────────────────────────────

def _analyze_image_array(img: np.ndarray, page_num: int) -> list[TableData]:
    try:
        return _img2table_extract(img, page_num)
    except Exception:
        return _easyocr_plain_text(img, page_num)


def _img2table_extract(img: np.ndarray, page_num: int) -> list[TableData]:
    import tempfile
    from img2table.document import Image as Img2Image
    from img2table.ocr import EasyOCR as Img2EasyOCR

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    cv2.imwrite(tmp_path, img)

    try:
        ocr = Img2EasyOCR(reader=_get_ocr_reader())
        doc = Img2Image(src=tmp_path)
        extracted = doc.extract_tables(
            ocr=ocr, implicit_rows=True, borderless_tables=True, min_confidence=50
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    results = []
    for table in (extracted or []):
        td = _img2table_to_tabledata(table, page_num)
        if td:
            results.append(td)

    if not results:
        results = _easyocr_plain_text(img, page_num)
    return results


def _img2table_to_tabledata(table, page_num: int) -> TableData | None:
    try:
        df = table.df
        if df is None or df.empty:
            return None
        rows = df.fillna("").values.tolist()
        row_count = len(rows)
        col_count = max((len(r) for r in rows), default=0)
        td = TableData(page=page_num, row_count=row_count, col_count=col_count)
        for r_idx, row in enumerate(rows):
            for c_idx, cell in enumerate(row):
                text = str(cell).strip() if cell is not None else ""
                td.cells.append(CellData(
                    row=r_idx, col=c_idx, row_span=1, col_span=1,
                    text=text, min_confidence=1.0,
                ))
        return td
    except Exception:
        return None


def _easyocr_plain_text(img: np.ndarray, page_num: int) -> list[TableData]:
    reader = _get_ocr_reader()
    ocr_results = reader.readtext(img)
    lines = [(text.strip(), float(conf)) for (_, text, conf) in ocr_results if text.strip()]
    if not lines:
        return []
    td = TableData(page=page_num, row_count=len(lines), col_count=1, is_plain_text=True)
    for r_idx, (text, conf) in enumerate(lines):
        td.cells.append(CellData(
            row=r_idx, col=0, row_span=1, col_span=1,
            text=text, min_confidence=conf,
            is_low_confidence=conf < config.CONFIDENCE_THRESHOLD,
        ))
    return [td]
