"""
Extracts tables and plain text from documents using Azure Document Intelligence.

Supported inputs: PDF, JPG, JPEG, PNG, BMP, TIFF, HEIF
- Pages with tables  → extracted as structured TableData (Layout model)
- Pages with no tables → plain text extracted as a single-column TableData (Read model)

All cells include per-word confidence scores. Low-confidence cells are flagged
for manual review (common with handwritten ambiguities like O/0 and B/8).
"""

from dataclasses import dataclass, field
from pathlib import Path

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential

import config

# Azure Document Intelligence supported MIME types
SUPPORTED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".heif": "image/heif",
}


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
    # True when this "table" is actually plain OCR text (no table detected on page)
    is_plain_text: bool = False


def analyze_document(file_path: str) -> list[TableData]:
    """
    Analyze any supported document (PDF or image) and return tables + plain-text pages.

    For pages that contain tables, structured CellData is returned.
    For pages with no tables (plain text / OCR), text is returned as a
    single-column table so it still appears in the Excel output.
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    client = DocumentIntelligenceClient(
        endpoint=config.ENDPOINT,
        credential=AzureKeyCredential(config.KEY),
    )

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    # prebuilt-layout handles tables, handwriting, and plain text in one call
    poller = client.begin_analyze_document(
        model_id="prebuilt-layout",
        body=AnalyzeDocumentRequest(bytes_source=file_bytes),
        content_type="application/json",
    )
    result = poller.result()

    # Build a per-page word→confidence lookup
    page_word_confidence: dict[int, dict[str, list[float]]] = {}
    if result.pages:
        for page in result.pages:
            wc: dict[str, list[float]] = {}
            if page.words:
                for word in page.words:
                    key = word.content.strip()
                    wc.setdefault(key, []).append(word.confidence or 1.0)
            page_word_confidence[page.page_number] = wc

    # Track which pages already have a table so we know which are plain-text only
    pages_with_tables: set[int] = set()
    tables: list[TableData] = []

    if result.tables:
        for table in result.tables:
            page_num = table.bounding_regions[0].page_number if table.bounding_regions else 1
            pages_with_tables.add(page_num)
            wc = page_word_confidence.get(page_num, {})

            table_data = TableData(
                page=page_num,
                row_count=table.row_count,
                col_count=table.column_count,
            )
            for cell in table.cells:
                cell_text = cell.content.strip() if cell.content else ""
                min_conf = _min_confidence_for_text(cell_text, wc)
                table_data.cells.append(
                    CellData(
                        row=cell.row_index,
                        col=cell.column_index,
                        row_span=cell.row_span or 1,
                        col_span=cell.column_span or 1,
                        text=cell_text,
                        min_confidence=min_conf,
                        is_low_confidence=min_conf < config.CONFIDENCE_THRESHOLD,
                    )
                )
            tables.append(table_data)

    # For pages that had no tables, emit plain OCR text as a single-column table
    if result.pages:
        for page in result.pages:
            if page.page_number in pages_with_tables:
                continue
            lines = page.lines or []
            if not lines:
                continue

            wc = page_word_confidence.get(page.page_number, {})
            plain = TableData(
                page=page.page_number,
                row_count=len(lines),
                col_count=1,
                is_plain_text=True,
            )
            for row_idx, line in enumerate(lines):
                line_text = line.content.strip()
                min_conf = _min_confidence_for_text(line_text, wc)
                plain.cells.append(
                    CellData(
                        row=row_idx,
                        col=0,
                        row_span=1,
                        col_span=1,
                        text=line_text,
                        min_confidence=min_conf,
                        is_low_confidence=min_conf < config.CONFIDENCE_THRESHOLD,
                    )
                )
            tables.append(plain)

    # Return in page order
    tables.sort(key=lambda t: t.page)
    return tables


def _min_confidence_for_text(text: str, word_confidence: dict[str, list[float]]) -> float:
    """Return the minimum confidence among all words in the given text string."""
    if not text:
        return 1.0
    confidences: list[float] = []
    for word in text.split():
        scores = word_confidence.get(word.strip(), [])
        if scores:
            confidences.append(scores.pop(0))  # consume one entry to handle duplicate words
    return min(confidences) if confidences else 1.0
