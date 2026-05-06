"""
Writes extracted table data to an Excel workbook.
Cells with low confidence are highlighted in red with a note showing the confidence score.
"""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter

from pdf_processor import TableData

RED_FILL = PatternFill(start_color="FFCCCC", end_color="FFCCCC", fill_type="solid")
RED_FONT = Font(color="CC0000", bold=True)
HEADER_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
HEADER_FONT = Font(bold=True)
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)


def write_to_excel(tables: list[TableData], output_path: str) -> None:
    """Write all tables to separate sheets in an Excel workbook."""
    wb = Workbook()
    wb.remove(wb.active)  # remove default empty sheet

    if not tables:
        ws = wb.create_sheet("No Tables Found")
        ws["A1"] = "No tables were detected in the PDF."
        wb.save(output_path)
        return

    # Group tables by page
    pages: dict[int, list[TableData]] = {}
    for table in tables:
        pages.setdefault(table.page, []).append(table)

    for page_num in sorted(pages):
        page_tables = pages[page_num]
        for idx, table in enumerate(page_tables, start=1):
            sheet_name = f"Page{page_num}" if len(page_tables) == 1 else f"Page{page_num}_T{idx}"
            ws = wb.create_sheet(title=sheet_name[:31])
            _write_table(ws, table)

    wb.save(output_path)
    print(f"Saved: {output_path}")


def _write_table(ws, table: TableData) -> None:
    # Offset rows/cols by 1 because openpyxl is 1-indexed
    ROW_OFFSET = 2
    COL_OFFSET = 1

    low_conf_count = 0

    for cell in table.cells:
        excel_row = cell.row + ROW_OFFSET
        excel_col = cell.col + COL_OFFSET

        xl_cell = ws.cell(row=excel_row, column=excel_col, value=cell.text)
        xl_cell.border = THIN_BORDER
        xl_cell.alignment = Alignment(wrap_text=True, vertical="center")

        if cell.row == 0:
            xl_cell.fill = HEADER_FILL
            xl_cell.font = HEADER_FONT

        if cell.is_low_confidence:
            xl_cell.fill = RED_FILL
            xl_cell.font = RED_FONT
            xl_cell.comment = Comment(
                text=f"Low confidence: {cell.min_confidence:.0%}\n"
                     "Possible misread (e.g. O vs 0, B vs 8). Please verify.",
                author="PDF Converter",
            )
            low_conf_count += 1

        # Merge spanned cells
        if cell.row_span > 1 or cell.col_span > 1:
            end_row = excel_row + cell.row_span - 1
            end_col = excel_col + cell.col_span - 1
            ws.merge_cells(
                start_row=excel_row,
                start_column=excel_col,
                end_row=end_row,
                end_column=end_col,
            )

    # Auto-size columns
    for col_idx in range(1, table.col_count + COL_OFFSET + 1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = 20

    # Summary row at top
    summary = ws.cell(row=1, column=1)
    kind = "Plain text (OCR)" if table.is_plain_text else "Table"
    summary.value = (
        f"{kind}  |  Page {table.page}  |  "
        f"{table.row_count} rows × {table.col_count} cols  |  "
        f"{low_conf_count} low-confidence cell(s) highlighted in red"
    )
    summary.font = Font(italic=True, color="595959")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(table.col_count, 4))
