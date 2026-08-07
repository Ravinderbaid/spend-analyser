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

See README.md for full usage details (file purposes, upload flow, PDF format
detection, excluded transactions, category list, email fetcher, known
limitations).

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
- `category_rules.json` and the `RULES` object embedded in
  `spend_analyser.html` are two separate copies of the same keyword rules —
  if one is edited, check whether the other needs the same change.
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
