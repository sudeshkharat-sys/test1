# Document to Excel Converter (PaddleOCR — free, no API key)

Converts documents and images containing tables — including handwritten content — into Excel sheets.  
Cells where the model has **low confidence** (common with handwritten text like `O` vs `0`, `B` vs `8`) are **highlighted in red** with a tooltip showing the confidence score.

Runs **completely offline on your machine**. No Azure account, no API key, no cost.

## Supported input formats

| Format | Extension |
|---|---|
| PDF | `.pdf` |
| JPEG image | `.jpg`, `.jpeg` |
| PNG image | `.png` |
| BMP image | `.bmp` |
| TIFF image | `.tiff`, `.tif` |

## How it works

1. PDF pages are converted to images internally (200 DPI) using PyMuPDF
2. **PaddleOCR PPStructure** detects table regions and extracts structure (rows, cols, merged cells)
3. A second OCR pass collects per-word confidence scores across the full page
4. Cells with a word below the confidence threshold are flagged red in Excel
5. Pages with no tables → plain OCR text extracted into a single-column sheet

## Why PaddleOCR?

| Feature | PaddleOCR | Tesseract | EasyOCR | Azure Doc Intelligence |
|---|---|---|---|---|
| Per-word confidence scores | ✅ | Partial | ✅ | ✅ |
| Native table extraction | ✅ | ❌ | ❌ | ✅ |
| Handwriting support | Good | Poor | Good | Best |
| Merged cell (rowspan/colspan) | ✅ | ❌ | ❌ | ✅ |
| Cost | Free | Free | Free | Paid (500 pages/month free) |
| Runs offline | ✅ | ✅ | ✅ | ❌ |

## Setup

### 1. Install Python 3.10+

Download from **python.org** — tick **"Add Python to PATH"** during install.

### 2. Create virtual environment

```cmd
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac / Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **First run** will automatically download PaddleOCR models (~500 MB). Internet required only for this step.

### 4. Configure threshold (optional)

```bash
cp .env.example .env
```

Edit `.env` to adjust the confidence threshold (default is 0.80).

## Usage

```bash
# From a PDF
python main.py invoice.pdf

# From a scanned image
python main.py scan.jpg
python main.py handwritten_table.png

# Custom output path
python main.py report.pdf output/report_extracted.xlsx
```

## Output

- Pages with tables → one sheet per table (`Page1`, `Page2_T1`, `Page2_T2`, …)
- Pages with only text → `Plain text (OCR)` sheet with one line per row
- **Red cells** = low confidence — verify manually (`O/0`, `B/8`, `l/1` are common mistakes)
- Hover over a red cell to see the exact confidence percentage

## Configuration

| Variable | Default | Description |
|---|---|---|
| `CONFIDENCE_THRESHOLD` | `0.80` | Flag cells below this score (0.0–1.0) |

- Lower (e.g. `0.70`) → fewer flags
- Higher (e.g. `0.90`) → stricter, more flags
