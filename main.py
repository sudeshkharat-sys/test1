"""
Document to Excel converter using Azure Document Intelligence.

Supported inputs: PDF, JPG, JPEG, PNG, BMP, TIFF, HEIF

Usage:
    python main.py <input_file> [output.xlsx]

- Pages with tables  → structured table in Excel
- Pages with plain text / handwriting (no table) → OCR text in single-column sheet
- Low-confidence cells are highlighted in red with a tooltip (common with
  handwritten ambiguities like O/0, B/8, l/1)
"""

import sys
from pathlib import Path

from pdf_processor import analyze_document, SUPPORTED_EXTENSIONS
from excel_writer import write_to_excel


def main() -> None:
    if len(sys.argv) < 2:
        exts = ", ".join(SUPPORTED_EXTENSIONS)
        print(f"Usage: python main.py <input_file> [output.xlsx]")
        print(f"Supported formats: {exts}")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        print(f"Error: unsupported file type '{input_path.suffix}'")
        print(f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}")
        sys.exit(1)

    output_path = sys.argv[2] if len(sys.argv) > 2 else str(input_path.with_suffix(".xlsx"))

    print(f"Analyzing: {input_path}")
    results = analyze_document(str(input_path))

    tables = [r for r in results if not r.is_plain_text]
    plain_pages = [r for r in results if r.is_plain_text]

    print(f"Found {len(tables)} table(s) and {len(plain_pages)} plain-text page(s).")

    if not results:
        print("Nothing extracted from the document.")

    write_to_excel(results, output_path)


if __name__ == "__main__":
    main()
