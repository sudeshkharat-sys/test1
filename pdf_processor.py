"""
Extracts tables and plain text using PaddleOCR — free, runs locally, no API key needed.

Supported inputs: PDF, JPG, JPEG, PNG, BMP, TIFF
- Pages with tables  → structured TableData with row/col/span info
- Pages with no tables → plain text lines as single-column TableData

All cells include per-word confidence scores used for red-highlighting in Excel.

First run will download PaddleOCR models (~500 MB) automatically.
"""

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import fitz  # PyMuPDF
from paddleocr import PPStructure, PaddleOCR
from bs4 import BeautifulSoup

import config

SUPPORTED_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif",
}

# Engines are heavy — load once and reuse across calls
_structure_engine: PPStructure | None = None
_ocr_engine: PaddleOCR | None = None


def _get_engines() -> tuple[PPStructure, PaddleOCR]:
    global _structure_engine, _ocr_engine
    if _structure_engine is None:
        print("Loading PaddleOCR models (first run downloads ~500 MB)...")
        _structure_engine = PPStructure(table=True, ocr=True, lang="en", show_log=False)
        _ocr_engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    return _structure_engine, _ocr_engine


@dataclass
class CellData:
    row: int
    col: int
    row_span: int
    col_span: int
    text: str
    min_confidence: float  # lowest word-level confidence in this cell
    is_low_confidence: bool = False


@dataclass
class TableData:
    page: int
    row_count: int
    col_count: int
    cells: list[CellData] = field(default_factory=list)
    is_plain_text: bool = False


def analyze_document(file_path: str) -> list[TableData]:
    """Analyze a document or image and return tables + plain-text pages."""
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    structure_engine, ocr_engine = _get_engines()

    if ext == ".pdf":
        images = _pdf_to_images(file_path)
    else:
        img = cv2.imread(file_path)
        if img is None:
            raise ValueError(f"Could not read image: {file_path}")
        images = [img]

    all_tables: list[TableData] = []
    for page_num, img in enumerate(images, start=1):
        page_results = _process_image(img, page_num, structure_engine, ocr_engine)
        all_tables.extend(page_results)

    return all_tables


def _pdf_to_images(pdf_path: str) -> list[np.ndarray]:
    """Convert each PDF page to a BGR numpy array at 200 DPI."""
    doc = fitz.open(pdf_path)
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        elif pix.n == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        images.append(img)
    doc.close()
    return images


def _process_image(
    img: np.ndarray,
    page_num: int,
    structure_engine: PPStructure,
    ocr_engine: PaddleOCR,
) -> list[TableData]:
    """Run structure + OCR analysis on one page image."""
    structure_results = structure_engine(img.copy())

    # Full-page OCR to get per-word confidence scores
    ocr_results = ocr_engine.ocr(img.copy(), cls=True)
    word_confidence: dict[str, list[float]] = {}
    if ocr_results and ocr_results[0]:
        for line in ocr_results[0]:
            if line and len(line) == 2:
                text, conf = line[1]
                word_confidence.setdefault(text.strip(), []).append(float(conf))

    tables: list[TableData] = []
    text_lines: list[tuple[str, float]] = []

    for region in (structure_results or []):
        rtype = region.get("type", "")
        res = region.get("res", {})

        if rtype == "table":
            html = res.get("html", "") if isinstance(res, dict) else ""
            if html:
                table_data = _table_from_html(html, page_num, word_confidence)
                if table_data:
                    tables.append(table_data)
        else:
            # Text / title / list regions — collect lines with confidence
            lines = res if isinstance(res, list) else []
            for line in lines:
                if isinstance(line, list) and len(line) == 2:
                    text_conf = line[1]
                    if isinstance(text_conf, (list, tuple)) and len(text_conf) == 2:
                        text, conf = text_conf
                        if text.strip():
                            text_lines.append((text.strip(), float(conf)))

    # Emit a plain-text sheet only for pages that have no tables
    if text_lines and not tables:
        plain = TableData(
            page=page_num,
            row_count=len(text_lines),
            col_count=1,
            is_plain_text=True,
        )
        for row_idx, (text, conf) in enumerate(text_lines):
            plain.cells.append(CellData(
                row=row_idx, col=0, row_span=1, col_span=1,
                text=text, min_confidence=conf,
                is_low_confidence=conf < config.CONFIDENCE_THRESHOLD,
            ))
        return [plain]

    return tables


def _table_from_html(
    html: str,
    page_num: int,
    word_confidence: dict[str, list[float]],
) -> TableData | None:
    """Convert a PaddleOCR HTML table string into a TableData with confidence scores."""
    cells = _parse_html_table(html)
    if not cells:
        return None

    max_row = max(row + rs for row, _, rs, _, _ in cells)
    max_col = max(col + cs for _, col, _, cs, _ in cells)

    table_data = TableData(page=page_num, row_count=max_row, col_count=max_col)
    for row, col, row_span, col_span, text in cells:
        min_conf = _min_confidence_for_text(text, word_confidence)
        table_data.cells.append(CellData(
            row=row, col=col,
            row_span=row_span, col_span=col_span,
            text=text,
            min_confidence=min_conf,
            is_low_confidence=min_conf < config.CONFIDENCE_THRESHOLD,
        ))
    return table_data


def _parse_html_table(html: str) -> list[tuple[int, int, int, int, str]]:
    """
    Parse an HTML table into (row, col, rowspan, colspan, text) tuples.
    Uses a grid-fill algorithm to correctly handle merged cells.
    """
    soup = BeautifulSoup(html, "lxml")
    rows_raw = soup.find_all("tr")
    if not rows_raw:
        return []

    occupied: set[tuple[int, int]] = set()
    cells: list[tuple[int, int, int, int, str]] = []

    for row_idx, tr in enumerate(rows_raw):
        col_idx = 0
        for td in tr.find_all(["td", "th"]):
            while (row_idx, col_idx) in occupied:
                col_idx += 1

            text = td.get_text(strip=True)
            rowspan = max(1, int(td.get("rowspan", 1)))
            colspan = max(1, int(td.get("colspan", 1)))

            for r in range(row_idx, row_idx + rowspan):
                for c in range(col_idx, col_idx + colspan):
                    occupied.add((r, c))

            cells.append((row_idx, col_idx, rowspan, colspan, text))
            col_idx += colspan

    return cells


def _min_confidence_for_text(text: str, word_confidence: dict[str, list[float]]) -> float:
    if not text:
        return 1.0
    confidences: list[float] = []
    for word in text.split():
        scores = word_confidence.get(word.strip(), [])
        if scores:
            confidences.append(scores.pop(0))
    return min(confidences) if confidences else 1.0
