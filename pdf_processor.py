"""
Extracts tables from a PDF using Azure Document Intelligence (Layout model).
Returns structured cell data with per-word confidence scores.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential

import config


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


def analyze_pdf(pdf_path: str) -> list[TableData]:
    """Analyze a PDF file and return all extracted tables with confidence data."""
    client = DocumentIntelligenceClient(
        endpoint=config.ENDPOINT,
        credential=AzureKeyCredential(config.KEY),
    )

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    poller = client.begin_analyze_document(
        model_id="prebuilt-layout",
        body=AnalyzeDocumentRequest(bytes_source=pdf_bytes),
        content_type="application/json",
    )
    result = poller.result()

    # Build a word-to-confidence lookup from the full document word list
    word_confidence: dict[str, list[float]] = {}
    if result.pages:
        for page in result.pages:
            if page.words:
                for word in page.words:
                    key = word.content.strip()
                    word_confidence.setdefault(key, []).append(word.confidence or 1.0)

    tables: list[TableData] = []
    if not result.tables:
        return tables

    for table in result.tables:
        page_num = 1
        if table.bounding_regions:
            page_num = table.bounding_regions[0].page_number

        table_data = TableData(
            page=page_num,
            row_count=table.row_count,
            col_count=table.column_count,
        )

        for cell in table.cells:
            cell_text = cell.content.strip() if cell.content else ""
            min_conf = _min_confidence_for_cell(cell_text, word_confidence)

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

    return tables


def _min_confidence_for_cell(cell_text: str, word_confidence: dict[str, list[float]]) -> float:
    """Return the minimum confidence among all words found in this cell's text."""
    if not cell_text:
        return 1.0

    words = cell_text.split()
    confidences: list[float] = []
    for word in words:
        scores = word_confidence.get(word.strip(), [])
        if scores:
            confidences.append(scores.pop(0))  # consume one match to handle duplicates

    return min(confidences) if confidences else 1.0
