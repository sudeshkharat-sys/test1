"""
PDF to Excel converter using Azure Document Intelligence.

Usage:
    python main.py <input.pdf> [output.xlsx]

Low-confidence cells (e.g. ambiguous handwritten characters like O/0 or B/8)
are highlighted in red with a comment showing the confidence score.
"""

import sys
from pathlib import Path

from pdf_processor import analyze_pdf
from excel_writer import write_to_excel


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python main.py <input.pdf> [output.xlsx]")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"Error: file not found: {pdf_path}")
        sys.exit(1)

    output_path = sys.argv[2] if len(sys.argv) > 2 else pdf_path.with_suffix(".xlsx")

    print(f"Analyzing: {pdf_path}")
    tables = analyze_pdf(str(pdf_path))

    if not tables:
        print("No tables detected in the PDF.")
    else:
        print(f"Found {len(tables)} table(s) across {len({t.page for t in tables})} page(s).")

    write_to_excel(tables, str(output_path))


if __name__ == "__main__":
    main()
