# Document to Excel Converter (Azure Document Intelligence)

Converts documents and images containing tables — including handwritten content — into Excel sheets.  
Cells where the model has **low confidence** (common with handwritten text like `O` vs `0`, `B` vs `8`) are **highlighted in red** with a tooltip showing the confidence score.

Pages with no tables (plain text, handwritten notes, printed paragraphs) are also extracted via OCR and written to their own sheet.

## Supported input formats

| Format | Extension |
|---|---|
| PDF | `.pdf` |
| JPEG image | `.jpg`, `.jpeg` |
| PNG image | `.png` |
| BMP image | `.bmp` |
| TIFF image | `.tiff`, `.tif` |
| HEIF image | `.heif` |

## How it works

1. Sends the document to **Azure Document Intelligence** using the `prebuilt-layout` model
2. The Layout model extracts all tables and returns per-word confidence scores
3. Pages with tables → structured Excel sheet with rows, columns, merged cells
4. Pages with no tables → OCR text extracted line-by-line into a single-column sheet
5. Any cell with a word below the confidence threshold is flagged red

## Why Azure Document Intelligence (Layout model)?

| Feature | Azure Doc Intelligence | GPT-4 Vision | Azure Computer Vision |
|---|---|---|---|
| Per-word confidence scores | ✅ | ❌ | Partial |
| Native table extraction | ✅ | Manual parsing | ❌ |
| Handwritten + printed mix | ✅ | ✅ | ✅ |
| Merged cell support | ✅ | ❌ | ❌ |
| Plain text / OCR fallback | ✅ | ✅ | ✅ |
| Image input (JPG/PNG etc.) | ✅ | ✅ | ✅ |
| Cost per page | Low | High | Medium |

> **Note on GitHub Copilot / OpenAI models:** These are code assistants or general-purpose LLMs.
> They do not expose per-character confidence scores, making them unsuitable for the red-highlight
> feature. Use Azure Document Intelligence for structured document extraction.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in your Azure credentials in .env
```

### Azure Resource

Create an **Azure AI Services** or **Document Intelligence** resource in the Azure portal, then copy the endpoint and key into `.env`.

## Usage

```bash
# From a PDF
python main.py invoice.pdf

# From a scanned image (JPG, PNG, TIFF, etc.)
python main.py scan.jpg
python main.py handwritten_table.png

# Custom output path
python main.py report.pdf output/report_extracted.xlsx
```

## Output

- Pages with tables → one sheet per table (e.g. `Page1`, `Page2_T1`, `Page2_T2`)
- Pages with only plain text / OCR → one sheet per page labelled as `Plain text (OCR)`
- A summary row at the top of each sheet shows page number, row/col count, and flagged cell count
- **Red cells** = low confidence — verify these manually (especially `O/0`, `B/8`, `l/1`)
- Hover over a red cell to see the exact confidence score and a reminder to verify

## Configuration

| Variable | Default | Description |
|---|---|---|
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | — | Your Azure endpoint URL |
| `AZURE_DOCUMENT_INTELLIGENCE_KEY` | — | Your Azure API key |
| `CONFIDENCE_THRESHOLD` | `0.80` | Flag cells below this score (0.0–1.0) |

Tune the threshold in `.env`:
- Lower (e.g. `0.70`) → fewer flags, only very uncertain text highlighted
- Higher (e.g. `0.90`) → more flags, stricter review
