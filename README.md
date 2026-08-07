# Spend Analyser

A personal spend-tracking tool. Upload bank/credit-card statements (CSV, Excel,
or PDF) — or let a daily background script fetch them from Gmail for you — and
it auto-categorizes each transaction with keyword rules, appending everything
into one flat CSV ledger (`transactions.csv`) that a local 3-tab dashboard
reads to show monthly summaries, category charts, a spend trend, and a simple
budget/planning view.

## Setting up from a fresh clone

Three files are deliberately git-ignored because they're personal to one
person's accounts, not portable app config — you'll need to create your own:

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp category_rules.example.json category_rules.json      # then edit: add your own
                                                          # name to Self Transfer, family
                                                          # members to Family Transfer, etc.
cp statement_subjects.example.json statement_subjects.json   # only needed for the
                                                          # email-fetcher/Pending Statements
                                                          # workflow — skip if you'll only
                                                          # ever upload files by hand
cp mail_config.example.json mail_config.json             # same — only needed for the
                                                          # email fetcher; fill in your own
                                                          # Gmail address + app password
```

`transactions.csv` doesn't need creating — the server creates it the first
time you upload a statement.

## How to start it

From the project directory:

```
.venv/bin/python3 server.py
```

Then open **http://127.0.0.1:8765/** (equivalently
`http://localhost:8765/spend_analyser.html`).

It runs Flask in debug mode with the auto-reloader on, so editing `server.py`
restarts the server automatically most of the time — no need to manually
stop/start it while making code changes. (Occasionally a change doesn't get
picked up, particularly edits to the `app.run(...)` line itself — if the
server doesn't seem to reflect a recent change after a few seconds, stop and
restart it by hand.) The dashboard HTML (`spend_analyser.html`) is just served
as a static file, so browser-side changes just need a page refresh.

By default the server binds `127.0.0.1` (this machine only). To let other
devices on the same wifi reach the dashboard, change `host="127.0.0.1"` to
`host="0.0.0.0"` in the `app.run(...)` call at the bottom of `server.py` and
restart. There is **no authentication** anywhere in this app, so only do this
on a trusted home network — anyone on that network could view and edit your
transactions, upload statements, and manage pending files.

## How to stop it

Ctrl+C in the terminal it's running in.

## What each file is for

- **`server.py`** — the Flask backend. Serves the dashboard and the ledger,
  parses/categorizes/dedups uploaded statements, and hosts the daily-fetch
  "pending statements" and "statement formats" workflows described below.
- **`spend_analyser.html`** — the dashboard UI (single file, vanilla JS +
  Chart.js + PapaParse loaded from a CDN). Three tabs:
  - **Dashboard** — data-file status strip with "Reload from disk"; a
    summary strip (income/spend/net/top category) for the selected month; a
    transactions table (search, category filter, account filter, and a
    Savings/Credit Card segmented toggle; inline category edit; delete;
    click a description cell to expand/collapse its full text) with a month
    ← → nav and CSV export; when a category is picked in the filter, a chart
    panel appears beside the table showing that category's monthly totals
    for the last 12 months plus a "by account" breakdown donut; a Budget &
    Planning table (set a monthly budget per category, or use the suggested
    3-month average, with a progress bar); a Backup panel (downloads a dated
    snapshot CSV); and two more charts (this month by category, 12-month
    spend trend).
  - **Pending Statements** — a "Manual upload" panel (account label + file
    picker, password field appears if a file turns out encrypted) for adding
    a statement yourself, above the list of files `fetch_statements.py` (see
    below) already fetched and is waiting for you to confirm an account
    label (and password, if encrypted) for before they're committed to the
    ledger. Each fetched item has Preview (see the transactions it contains
    without committing), Upload, and Delete. A "Check email now" button
    triggers an immediate fetch instead of waiting for the next scheduled
    run, and the tab shows a badge with the pending count.
  - **Statement Formats** — a sandbox to test whether the current parsers can
    handle a given file (via a read-only dry-run, no ledger writes) before
    committing to anything. On success, shows a transaction preview and a
    form to register a new email-subject → account-label mapping (see
    `statement_subjects.json` below) directly from the browser. On failure,
    shows the raw extracted PDF text and a "Copy details for Claude" button
    so an unrecognized layout can be pasted into a Claude Code chat to get a
    new parser built, without re-attaching the file.
- **`transactions.csv`** — the single source of truth ledger. Columns: `id,
  date, description, amount, account, category`. Amount is signed: negative =
  spend, positive = income/credit. Both the server and the dashboard read and
  write this same file directly — there is no database. `account` values must
  end in either `"Credit Card"` or `"Saving Account Statement"` (enforced on
  every entry path) so the dashboard can tell savings accounts and credit
  cards apart from the label alone.
- **`category_rules.json`** — keyword → category mapping used by the server
  to auto-categorize a transaction from its description at upload time (first
  matching category wins; falls back to "Others"). The dashboard also has its
  own copy of these same rules baked into `spend_analyser.html`'s `RULES`
  object (used when the dashboard re-parses the CSV client-side) — if you
  edit `category_rules.json`, update `RULES` to match.
- **`fetch_statements.py`** — standalone script (does not import `server.py`,
  does not start Flask, no AI/Claude Code session ever touches the mailbox)
  that logs into Gmail over IMAP, matches new emails by subject-line
  substring against `statement_subjects.json`, and saves any `.pdf`/`.xlsx`/
  `.xls` attachments into `incoming_statements/` with a `manifest.json` entry
  (account/subject/received) so the Pending Statements tab can pre-fill the
  account label. Statement passwords are never stored — you still enter them
  by hand when uploading a pending file. Dedup is via IMAP `UID`+
  `UIDVALIDITY` pairs in `.fetched_state.json`, so re-running it is safe.
  Runs daily via a macOS `launchd` LaunchAgent
  (`~/Library/LaunchAgents/com.spendanalyser.fetchstatements.plist`); can
  also be run by hand (`.venv/bin/python3 fetch_statements.py`) or triggered
  from the dashboard's "Check email now" button. When run by the button
  (in-process inside `server.py`), its log lines print to `server.py`'s own
  console, not to `fetch_statements.log` — that file only gets populated by
  the launchd-run subprocess, whose stdout/stderr the `.plist` redirects
  there.
- **`mail_config.json`** (git-ignored, `chmod 600`) — real Gmail address + a
  16-ish-character app-specific password (generate one at
  myaccount.google.com/apppasswords), IMAP host/port/mailbox, and
  `search_window_days` (how many days back to search on each run — kept
  narrow deliberately; see Known limitations). `mail_config.example.json` is
  the committed template with no real secrets.
- **`statement_subjects.json`** — flat `"subject substring": "account label"`
  map, same editable-config spirit as `category_rules.json`. Add a new
  bank/card by adding an entry here (or via the Statement Formats tab) — no
  code change needed, as long as an existing parser already handles that
  statement's PDF/Excel layout.
- **`incoming_statements/`** (git-ignored) — where fetched attachments land
  until uploaded or deleted via the Pending Statements tab; `manifest.json`
  inside it tracks per-file metadata.
- **`.fetched_state.json`** (git-ignored) — `fetch_statements.py`'s internal
  IMAP dedup bookkeeping only (`{uidvalidity, processed_uids}`). It does
  **not** contain any transaction data — if something seems missing, check
  `incoming_statements/manifest.json` (pending) or `transactions.csv`
  (committed), not this file.
- **`.venv`** — Python virtualenv with Flask, openpyxl, msoffcrypto-tool,
  pdfplumber, and pikepdf installed.
- **`com.spendanalyser.fetchstatements.plist.example`** — template for the
  macOS `launchd` LaunchAgent that runs `fetch_statements.py` daily (see
  "Scheduling the daily email fetch" below). This is optional — the "Check
  email now" button and manual upload work fine without it.

## Scheduling the daily email fetch (macOS)

Optional — only needed if you want `fetch_statements.py` to run automatically
every morning instead of relying on the dashboard's "Check email now" button
or running it by hand. macOS `launchd` (not cron) is used because it reliably
catches up on a missed run after the machine wakes from sleep.

```
cp com.spendanalyser.fetchstatements.plist.example \
   ~/Library/LaunchAgents/com.spendanalyser.fetchstatements.plist
```

Then edit that copy and replace every `/ABSOLUTE/PATH/TO/spend-analyser` with
the real absolute path to this project directory on your machine (`pwd` from
inside it will tell you). Adjust the `Hour`/`Minute` under
`StartCalendarInterval` if 7:00 AM doesn't suit you. Then:

```
launchctl load ~/Library/LaunchAgents/com.spendanalyser.fetchstatements.plist
launchctl start com.spendanalyser.fetchstatements   # optional: run once immediately to test
```

To stop it: `launchctl unload
~/Library/LaunchAgents/com.spendanalyser.fetchstatements.plist`. Logs from
the scheduled run go to `fetch_statements.log` in the project directory (not
git-tracked) — but *not* runs triggered from the dashboard's "Check email
now" button, which log to `server.py`'s own console instead (see the
`fetch_statements.py` entry above).

## Uploading a statement

In the Pending Statements tab's "Manual upload" panel (or a fetched pending
item further down that same tab): type an account label first — required,
and it must end with `"Credit Card"` or `"Saving Account Statement"`
(autocompletes from previously-used labels via
`/accounts`) — then choose a `.csv`, `.xlsx`, `.xls`, or `.pdf` file. If the
file is password-protected (encrypted Excel or PDF), a password field appears
after the first attempt — enter it and retry. Newly parsed transactions are
deduped against the existing ledger by content signature (date + description
+ amount + account, not by row id) before being appended, so re-uploading the
same statement is safe.

The Statement Formats tab's own account field is the one exception — it's
only a dry run for testing a parser (`/format-check` never writes to the
ledger), so it's optional and not suffix-validated. The suffix rule only
applies again once you use that same tab's "Save mapping" form to register a
real account label into `statement_subjects.json`.

## PDF statement formats

The server auto-detects which of several known PDF layouts a statement is, by
checking for an **exact header phrase** in the extracted text (not loose
keyword sniffing, since disclaimer boilerplate — or, in one real case, a
donut-chart label pdfplumber glued onto a transaction line — can contain
stray matching text):

1. Contains `"date mode particulars"` → ICICI Bank savings-account layout:
   narration wraps both before and after the date/amount line.
2. Contains `"date serno"` → ICICI Bank credit card layout (e.g. Sapphiro):
   single line per transaction, reward-points column, trailing `CR` marks a
   credit.
3. Contains `"transaction details"` and `"withdrawal deposits balance"` →
   Axis Bank savings/salary account layout: two trailing numbers (amount +
   running balance), direction inferred from which way the balance moved.
4. Contains `"narration withdrawals deposits"` → bank/savings-account layout:
   3 numeric columns (withdrawal, deposit, closing balance) per transaction,
   narration can wrap onto continuation lines.
5. Contains `"merchant category"` → Axis-style credit card layout (Magnus/
   Horizon): single amount column with a trailing `Dr`/`Cr` suffix instead of
   a sign.
6. Otherwise → generic fallback: single amount column, credits marked with a
   leading `+`, debits unsigned.

If a new bank format ever needs to be added, follow the same approach: detect
it by an exact, table-header-specific phrase (not generic keywords that could
appear elsewhere in the document), and validate the new parser by
reconciling its parsed total against the statement's own printed
summary/total — don't assume a parser is correct just because it produced
rows. Use the Statement Formats tab to check first — if it can't find any
rows, it shows the raw extracted PDF text and a one-click "copy for Claude"
button to bring to a Claude Code chat.

## Excluded transactions

Some transactions are dropped entirely at ingestion (in `server.py`,
`EXCLUDE_KEYWORDS`) because they're self-repayment (e.g. paying your own
credit card bill from your own bank account) — debt repayment, not real
spend or income, so counting them would inflate/deflate the dashboard's
income and spend figures:

- `bppy cc payment`
- `bbps payment received`

This is distinct from the **Credit Card Bill** category, which is the
corresponding debit on the *paying* bank account (real money leaving a
tracked account) — that one stays in the ledger and counts as spend.

## How credits inside a spend category are handled

A spend category can still contain a positive-amount row — a refund, a
reversal (e.g. a failed autopay bounced back as a credit), or someone paying
back their share of a Settlement. These are **netted against that category's
debits**, not ignored and not auto-reclassified as income: every place a
category total is computed (summary spend, trend chart, budget actual/
average, the per-category history chart) sums the signed amounts within the
category first, then takes the absolute value at the end. Real income should
still be categorized as `Salary / Income`, `Dividend`, or `Cashback` by hand —
those are the only categories counted toward the dashboard's Income figure.

## Categories

`Food & Dining, Groceries, Transport, Shopping, Bills & Utilities, Rent,
Entertainment, Health & Fitness, Subscriptions, Travel, Insurance,
Loan / EMI, Investments, Dividend, Bank Charges, Salary / Income, Cashback,
Self Transfer, Family Transfer, Credit Card Bill, Settlement, Transfers,
Others`

Income (counted in the dashboard's Income figure): `Salary / Income,
Dividend, Cashback`. Everything else counts as spend **except** `Self
Transfer` and `Family Transfer` (money moving between the user's own/family
accounts, not real spend or income — excluded from both totals).

## Known limitations

- No multi-currency support — amounts are treated as plain numbers and the
  dashboard always formats them with `₹`.
- Single local CSV, no multi-user support, no auth on the server — safe by
  default (binds `127.0.0.1`), but see "How to start it" above about the
  trade-off if you turn on LAN access.
- Budgets are stored in the browser's `localStorage`, not in
  `transactions.csv` — they don't travel with the CSV backup and are
  per-browser, not per-ledger.
- Dedup is content-based (date/description/amount/account) — editing a
  transaction's description after import means a re-upload of the original
  statement would no longer be recognized as a duplicate.
- PDF parsing only handles the 6 layouts described above; anything else
  needs to be handled manually via the Statement Formats tab's
  "copy for Claude" flow instead of the upload form succeeding outright.
- The email fetcher's `search_window_days` is deliberately narrow (default
  in `mail_config.example.json` is 1) — if the machine is asleep across a
  multi-day gap at the scheduled fetch time, an email could be missed
  entirely (IMAP UID dedup means it won't be picked up later just by
  widening the window afterwards unless you also clear its processed-UID
  entry). Use "Check now" or widen `search_window_days` if you suspect this
  happened.
- No automated tests in the repo — verify a new/changed parser manually by
  reconciling against the statement's own totals before trusting it.
