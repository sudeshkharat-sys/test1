# PDF to Excel Converter (Azure Document Intelligence)

Converts PDFs containing tables — including handwritten content — into Excel sheets.  
Cells where the model has **low confidence** (common with handwritten text like `O` vs `0`, `B` vs `8`) are **highlighted in red** with a tooltip showing the confidence score.

## How it works

1. Sends the PDF to **Azure Document Intelligence** using the `prebuilt-layout` model
2. The Layout model extracts all tables and returns per-word confidence scores
3. Any cell containing a word below the confidence threshold is flagged
4. An Excel file is generated with flagged cells highlighted in red

## Why Azure Document Intelligence (Layout model)?

| Feature | Azure Doc Intelligence | GPT-4 Vision | Azure Computer Vision |
|---|---|---|---|
| Per-word confidence scores | ✅ | ❌ | Partial |
| Native table extraction | ✅ | Manual parsing | ❌ |
| Handwritten + printed mix | ✅ | ✅ | ✅ |
| Merged cell support | ✅ | ❌ | ❌ |
| Cost per page | Low | High | Medium |

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
python main.py invoice.pdf
# Output: invoice.xlsx

python main.py report.pdf output/report_extracted.xlsx
```

## Output

- Each table gets its own sheet (e.g. `Page1`, `Page2_T1`, `Page2_T2`)
- A summary row at the top shows row/col count and number of flagged cells
- **Red cells** = low confidence — verify these manually (especially `O/0`, `B/8`, `l/1`)
- Hover over a red cell to see the exact confidence score

## Configuration

| Variable | Default | Description |
|---|---|---|
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | — | Your Azure endpoint URL |
| `AZURE_DOCUMENT_INTELLIGENCE_KEY` | — | Your Azure API key |
| `CONFIDENCE_THRESHOLD` | `0.80` | Flag cells below this score (0.0–1.0) |

Lower the threshold (e.g. `0.70`) for fewer flags; raise it (e.g. `0.90`) to be more strict.
