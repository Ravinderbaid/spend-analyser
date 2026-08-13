"""Generic OCR fallback for PDFs with no text layer at all (seen: HSBC
Premier statements, which render every line as a raster image instead of
real text — pdfplumber's normal page.extract_text() gets nothing from
these). Knows nothing about banks, passwords, or decryption — server.py
owns that; this module just turns an already-open pdfplumber page into
word-level bounding-box data, and provides the row/column reconstruction
helpers needed to read it as a table.

Needs the `tesseract` binary installed separately (`brew install
tesseract`) plus the `pytesseract` pip package — both optional. Every
function here degrades to returning [] / None if either is missing, since
OCR is an optional capability, not a hard dependency for the rest of the
app.
"""
import re

try:
    import pytesseract
except ImportError:
    pytesseract = None

AMOUNT_RE = re.compile(r"^[\d,]+\.\d{2}$")


def ocr_pdf_words(pdfplumber_doc):
    """Render each page of an already-open pdfplumber Document at 600dpi
    (300dpi was measured, on a real statement, to silently drop some small
    amounts) and OCR it into word-level bounding-box data. Returns a list
    of pages, each a list of {"text","left","top","width","height"} dicts."""
    if pytesseract is None:
        return []
    pages = []
    for page in pdfplumber_doc.pages:
        try:
            image = page.to_image(resolution=600).original
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except pytesseract.TesseractNotFoundError:
            return []
        words = []
        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            if not text:
                continue
            words.append({
                "text": text, "left": data["left"][i], "top": data["top"][i],
                "width": data["width"][i], "height": data["height"][i],
            })
        pages.append(words)
    return pages


def cluster_rows(words):
    """Group OCR'd words into visual table rows by y-position. This is what
    lets a caller ignore Tesseract's own reading order, which was observed
    on a real statement to read an entire table column top-to-bottom before
    moving to the next column rather than row-by-row — trusting that order
    would silently pair the wrong amount with the wrong transaction."""
    rows = []
    for w in sorted(words, key=lambda w: w["top"]):
        cy = w["top"] + w["height"] / 2
        placed = False
        for row in rows:
            if abs(row["y"] - cy) < 12:
                row["words"].append(w)
                row["y"] = (row["y"] * len(row["words"]) + cy) / (len(row["words"]) + 1)
                placed = True
                break
        if not placed:
            rows.append({"y": cy, "words": [w]})
    rows.sort(key=lambda r: r["y"])
    return rows


def classify_row(row_words, boundaries):
    """Assign each word in a visual row to a column by x-position against
    `boundaries` (ascending x cutoffs between columns, len(boundaries) + 1
    columns total) — computed by the caller from that page's own header
    row, not from word order, which OCR doesn't preserve reliably across
    columns. Returns one joined text string per column."""
    buckets = [[] for _ in range(len(boundaries) + 1)]
    for w in sorted(row_words, key=lambda w: w["left"]):
        x = w["left"]
        i = 0
        while i < len(boundaries) and x >= boundaries[i]:
            i += 1
        buckets[i].append(w["text"])
    return tuple(" ".join(b) for b in buckets)


def parse_amount(s):
    s = s.strip()
    if not AMOUNT_RE.match(s):
        return None
    return float(s.replace(",", ""))
