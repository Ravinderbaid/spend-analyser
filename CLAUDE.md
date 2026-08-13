# Spend Analyser

Personal spend-tracking tool: Flask backend (`server.py`) ingests bank/card
statements (CSV/Excel/PDF) into a single CSV ledger (`transactions.csv`),
`spend_analyser.html` is the 3-tab dashboard (Dashboard / Pending Statements /
Statement Formats) that reads/writes it. A standalone `fetch_statements.py`
script (no AI/Claude Code session involved) fetches statement attachments
from Gmail via IMAP daily and stages them as "pending" for review.

## Start command

```
.venv/bin/python3 server.py
```

Open http://127.0.0.1:8765/. Runs with Flask's debug reloader — editing
`server.py` restarts it automatically most of the time; if a change (e.g. to
the `app.run(...)` host/port line itself) doesn't seem to take effect after a
few seconds, do a manual stop/restart rather than assuming the code is wrong.

Currently bound to `127.0.0.1` only (local machine). To let other devices on
the same wifi reach it, change `host="127.0.0.1"` to `host="0.0.0.0"` at the
bottom of `server.py` — there is no authentication anywhere in this app, so
only do this on a trusted home network, and switch it back when done.

See README.md for usage/setup (aimed at day-1 users). This file has
implementation detail aimed at whoever's extending the code.

## Files

`server.py` Flask backend + all parsers · `pdf_ocr.py` generic OCR
mechanics (image rendering, word-position row/column reconstruction) used
by the HSBC layout below — no bank-specific or password logic, just
pdfplumber-page-to-Tesseract-words · `spend_analyser.html` dashboard UI
(vanilla JS, Chart.js, PapaParse) · `transactions.csv` the ledger (`id, date,
description, amount, account, category`; amount signed, negative=spend) ·
`category_rules.json` keyword→category rules (git-ignored, personal —
served to the browser via `/rules` rather than duplicated in the HTML) ·
`fetch_statements.py` standalone IMAP fetcher, never imported by
`server.py` · `mail_config.json` Gmail creds (git-ignored) ·
`statement_subjects.json` email-subject→account-label map ·
`incoming_statements/` staged attachments + `manifest.json` ·
`.fetched_state.json` IMAP UID dedup only, no transaction data ·
`com.spendanalyser.fetchstatements.plist.example` launchd template.

## PDF layout dispatch

Each checked via an exact header-phrase substring on the extracted text (see
rule below for why), in this order in `read_pdf_rows()`:

1. `"date mode particulars"` → ICICI savings — narration wraps before/after
   the date/amount line (`parse_icici_statement_lines`).
2. `"date serno"` → ICICI credit card (e.g. Sapphiro) — single line/txn,
   reward-points column, trailing `CR` = credit
   (`parse_icici_card_statement_lines`).
3. `"transaction details"` + `"withdrawal deposits balance"` → Axis
   savings/salary — 2 trailing numbers (amount + running balance), direction
   inferred from balance movement (`parse_axis_savings_statement_lines`).
4. `"narration withdrawals deposits"` → bank-statement 3-column layout
   (withdrawal/deposit/balance) (`parse_bank_statement_lines`).
5. `"merchant category"` → Axis-style card (Magnus/Horizon) — trailing
   `Dr`/`Cr` suffix (`parse_axis_statement_lines`).
6. Else → generic fallback, single amount column, leading `+`/blank sign
   (`parse_statement_lines`).

`extract_pdf_lines()` does the raw pikepdf-decrypt + pdfplumber-extract +
`(cid:9)`-tab-glyph stripping shared by all of the above; `read_pdf_rows()`
just adds the dispatch on top.

**OCR fallback** Only triggered when `extract_pdf_lines()`
returns no text at all — some banks (seen: HSBC) render every statement
line as a raster image with zero real text layer, which no amount of
keyword tuning can fix. In that case `read_pdf_rows()` calls
`pdf_ocr.ocr_pdf_words()` (600dpi render + Tesseract word-bounding-boxes —
300dpi was measured to silently drop small amounts) and, if the OCR'd text
contains both `"HSBC"` and `"savings account-res"`, routes to
`parse_hsbc_savings_ocr_pages()`. That parser doesn't trust Tesseract's own
reading order (observed reading an entire Deposits column before moving to
Withdrawals, scrambling row alignment) — it clusters words into visual rows
by y-position and classifies each into Date/Details/Deposits/Withdrawals/
Balance by x-position against that page's own header row, then recomputes
the running balance from scratch rather than trusting the OCR'd Balance
cell, so a single misread digit in an amount can self-heal via balance-diff
instead of silently producing a wrong figure. Needs the `tesseract` binary
(`brew install tesseract`) in addition to the `pytesseract` pip package —
without it, `ocr_pdf_words()` returns `[]` and this layout is skipped like
any other unrecognized format, rather than erroring.

## Rules for working in this repo

- `transactions.csv` is the single source of truth ledger. Don't invent a
  separate data store or cache — both the server and the dashboard read/write
  this one file directly.
- Use the `.venv` interpreter (`.venv/bin/python3`), not system `python3` —
  `openpyxl`, `msoffcrypto-tool`, `pdfplumber`, `pikepdf` are only installed
  there. A bare system Python will serve the dashboard but Excel/PDF uploads
  will fail.
- New PDF statement format support must be detected via an **exact
  header-phrase match** on the extracted text (e.g. `"narration withdrawals
  deposits"`, `"merchant category"`, `"date serno"`), not loose/generic
  keyword sniffing — disclaimer boilerplate can incidentally contain generic
  keywords, and picking the parser with the most matched rows is also
  unreliable. Also watch for stray text from charts/graphics on the same PDF
  page getting glued onto a transaction line by pdfplumber (seen with a
  donut-chart "NN%" label prefixing a transaction line) — don't assume a
  parser bug means the whole approach is wrong before checking for this.
- Before trusting any new or modified statement parser, reconcile its parsed
  total against the statement's own printed summary/total. Don't assume a
  parser is correct just because it produced rows.
- `category_rules.json` is the single source of truth for keyword→category
  rules — the browser fetches it via `GET /rules` (see `loadRules()` in
  `spend_analyser.html`) rather than keeping its own copy, since the file
  is git-ignored (personal keywords) but `spend_analyser.html` isn't.
- `EXCLUDE_KEYWORDS` in `server.py` intentionally drops self-repayment
  transactions (e.g. paying your own credit card from your own bank account)
  at ingestion — don't "fix" this by re-including them without understanding
  why they're excluded.
- Account labels are validated (`validate_account_label()` server-side,
  `accountLabelError()` client-side) to always end with either `"Credit
  Card"` or `"Saving Account Statement"` — this is what lets the dashboard's
  account-type filter (Savings/Credit Card) work off the name alone with no
  separate stored field. Any new account label, anywhere it's entered, must
  follow this convention.
- Wherever a category total is computed (summary spend, trend chart, budget
  actual/average, per-category history chart), **net the signed amounts
  within that category first, then take the absolute value at the end** —
  don't filter to `amount<0` and drop credits, and don't sum
  `Math.abs(amount)` per row. A credit inside a spend category (refund,
  reversal, a friend repaying a Settlement) should offset that category's
  debits, not be ignored or double-counted as extra spend. It also should NOT
  be auto-moved to Salary/Income — the user categorizes real income manually,
  and bank-failure/retry reversal credits aren't income.
- Dedup on upload is content-based (date + description + amount + account),
  not by row id — ids are randomly generated per parse and can't be used for
  identity.
- Don't add a database, auth layer, or multi-user support speculatively —
  the architecture is intentionally a single local CSV for one user on one
  machine.
