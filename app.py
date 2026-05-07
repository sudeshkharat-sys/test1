"""
Streamlit UI for the PDF / Image → Excel converter.

Run with:
    streamlit run app.py
"""

import io
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from pdf_processor import analyze_document, SUPPORTED_EXTENSIONS, TableData
from excel_writer import write_to_excel

# ── page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PDF → Excel",
    page_icon="📄",
    layout="wide",
)

st.title("📄 PDF / Image → Excel Converter")
st.caption("Upload a PDF or image. Tables are extracted and exported to Excel.")

# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    confidence_threshold = st.slider(
        "Low-confidence threshold",
        min_value=0.0,
        max_value=1.0,
        value=0.80,
        step=0.05,
        help="Cells below this OCR confidence are highlighted red in the Excel output.",
    )
    st.divider()
    st.markdown("**Supported formats**")
    st.markdown(", ".join(sorted(SUPPORTED_EXTENSIONS)))

# ── helpers ───────────────────────────────────────────────────────────────────

def table_to_df(table: TableData) -> pd.DataFrame:
    """Convert a TableData into a pandas DataFrame for preview."""
    grid: dict[tuple[int, int], str] = {}
    for cell in table.cells:
        grid[(cell.row, cell.col)] = cell.text

    rows = []
    for r in range(table.row_count):
        rows.append([grid.get((r, c), "") for c in range(table.col_count)])

    if rows and not table.is_plain_text:
        df = pd.DataFrame(rows[1:], columns=rows[0])
    else:
        df = pd.DataFrame(rows, columns=[f"Col {c + 1}" for c in range(table.col_count)])
    return df


def build_excel(tables: list[TableData]) -> bytes:
    """Run write_to_excel into an in-memory buffer and return raw bytes."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name
    write_to_excel(tables, tmp_path)
    with open(tmp_path, "rb") as f:
        data = f.read()
    Path(tmp_path).unlink(missing_ok=True)
    return data


# ── main flow ─────────────────────────────────────────────────────────────────

uploaded = st.file_uploader(
    "Choose a file",
    type=[ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS],
    label_visibility="collapsed",
)

if uploaded is None:
    st.info("Upload a PDF or image to get started.")
    st.stop()

# Save upload to a temp file so PaddleOCR can read it by path
suffix = Path(uploaded.name).suffix
with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
    tmp.write(uploaded.read())
    tmp_path = tmp.name

st.divider()

# ── process ───────────────────────────────────────────────────────────────────
with st.spinner("Running OCR — this may take a minute on first run (model download ~500 MB)…"):
    try:
        # Temporarily override the config threshold from the slider
        import config as _cfg
        _cfg.CONFIDENCE_THRESHOLD = confidence_threshold

        results = analyze_document(tmp_path)
    except Exception as exc:
        st.error(f"Processing failed: {exc}")
        Path(tmp_path).unlink(missing_ok=True)
        st.stop()

Path(tmp_path).unlink(missing_ok=True)

# ── summary ───────────────────────────────────────────────────────────────────
tables = [r for r in results if not r.is_plain_text]
plain_pages = [r for r in results if r.is_plain_text]

col1, col2, col3 = st.columns(3)
col1.metric("Tables found", len(tables))
col2.metric("Plain-text pages", len(plain_pages))
total_low = sum(
    sum(1 for c in t.cells if c.is_low_confidence) for t in results
)
col3.metric("Low-confidence cells", total_low, help="Will be highlighted red in Excel")

# ── preview ───────────────────────────────────────────────────────────────────
if not results:
    st.warning("Nothing was extracted from the file.")
else:
    st.subheader("Preview")

    for idx, table in enumerate(results):
        kind = "Plain text" if table.is_plain_text else "Table"
        label = f"{kind} — Page {table.page}"
        if not table.is_plain_text:
            label += f"  ({table.row_count} rows × {table.col_count} cols)"

        with st.expander(label, expanded=(idx == 0)):
            df = table_to_df(table)
            low_conf_cells: set[tuple[int, int]] = set()
            if not table.is_plain_text and table.cells:
                # row 0 is the header; data rows start at index 1
                for cell in table.cells:
                    if cell.is_low_confidence and cell.row > 0:
                        low_conf_cells.add((cell.row - 1, cell.col))

            def highlight_low_conf(data: pd.DataFrame) -> pd.DataFrame:
                styles = pd.DataFrame("", index=data.index, columns=data.columns)
                for r, c in low_conf_cells:
                    if r < len(styles) and c < len(styles.columns):
                        styles.iloc[r, c] = "background-color: #ffcccc; color: #cc0000"
                return styles

            st.dataframe(
                df.style.apply(highlight_low_conf, axis=None),
                use_container_width=True,
            )

# ── download ──────────────────────────────────────────────────────────────────
st.divider()
if results:
    excel_bytes = build_excel(results)
    out_name = Path(uploaded.name).stem + ".xlsx"
    st.download_button(
        label="⬇️ Download Excel",
        data=excel_bytes,
        file_name=out_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
