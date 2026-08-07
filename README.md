# Spend Analyser

A personal spend-tracking tool. Upload bank/credit-card statements — or let a
daily background script pull them from Gmail — and it auto-categorizes every
transaction into one CSV ledger, with a local dashboard for monthly
summaries, category charts, spend trends, and budgets.

## Quick start

Already set up? From the project directory:

```
.venv/bin/python3 server.py
```

Open **http://127.0.0.1:8765/**. Ctrl+C to stop.

Editing `server.py` auto-restarts the server (Flask's debug reloader);
editing `spend_analyser.html` just needs a page refresh. (Occasionally an
edit to the `app.run(...)` line itself doesn't get picked up automatically —
if the server doesn't seem to reflect a recent change, stop and restart it by
hand.)

First time here? Jump to [Setting up from a fresh clone](#setting-up-from-a-fresh-clone).

## Using it

Everything lives across three tabs.

**Dashboard** — the main view: a summary strip (income / spend / net / top
category) for the selected month, a transactions table you can search or
filter by category, account, or a Savings-vs-Credit-Card toggle, a Budget &
Planning table, a Backup panel, and spend charts. Pick a category in the
filter and a chart appears showing its monthly trend over the last 12
months, plus which account it moved through.

**Pending Statements** — two ways to get a statement in: a "Manual upload"
panel at the top of this tab, or the daily email fetch staging one
automatically further down (or trigger it early with "Check email now").
Each staged file can be **Previewed** (see what's in it before committing),
**Uploaded**, or **Deleted**.

**Statement Formats** — a sandbox to test whether a file parses correctly
*before* committing to anything (no ledger writes). On success, you can
register the email subject line that should auto-route future statements
like it to a given account. On failure, you get the raw extracted text and a
one-click copy button to hand to a Claude Code chat for a new parser.

### Uploading a statement

Type an account label — it must end in `"Credit Card"` or `"Saving Account
Statement"` (that's how the dashboard tells the two apart) — then pick a
`.csv`, `.xlsx`, `.xls`, or `.pdf` file. An encrypted file prompts for a
password. Re-uploading the same statement is always safe; duplicates are
detected automatically by content, not by re-checking a row ID.

### Categories

`Food & Dining, Groceries, Transport, Shopping, Bills & Utilities, Rent,
Entertainment, Health & Fitness, Subscriptions, Travel, Insurance,
Loan / EMI, Investments, Dividend, Bank Charges, Salary / Income, Cashback,
Self Transfer, Family Transfer, Credit Card Bill, Settlement, Transfers,
Others`

Only `Salary / Income`, `Dividend`, and `Cashback` count toward Income.
Everything else counts as Spend **except** `Self Transfer` and `Family
Transfer` (money moving between your own or family accounts — not real
spend or income). A refund or reversal that lands inside a spend category
nets against that category's debits rather than being ignored or counted as
income — see [How credits inside a spend category are handled](#how-credits-inside-a-spend-category-are-handled)
for why.

## Setting up from a fresh clone

Three files are deliberately git-ignored because they're personal to one
person's accounts, not portable app config — you'll need to create your own:

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp category_rules.example.json category_rules.json
cp statement_subjects.example.json statement_subjects.json
cp mail_config.example.json mail_config.json
```

Then:

- **`category_rules.json`** — add your own name to `Self Transfer`, family
  members to `Family Transfer`, friends you split costs with to
  `Settlement`, etc.
- **`statement_subjects.json`** and **`mail_config.json`** — only needed for
  the email-fetcher / Pending Statements workflow. Skip both if you'll only
  ever upload files by hand. `mail_config.json` needs a Gmail address and an
  app-specific password (generate one at
  myaccount.google.com/apppasswords — requires 2-Step Verification).

`transactions.csv` doesn't need creating — the server creates it the first
time you successfully upload a statement.

By default the server binds `127.0.0.1` (this machine only, no auth needed).
To let other devices on the same wifi reach the dashboard, change
`host="127.0.0.1"` to `host="0.0.0.0"` in the `app.run(...)` call at the
bottom of `server.py`. There is **no authentication** anywhere in this app,
so only do that on a trusted home network — anyone on it could then view and
edit your transactions, upload statements, and manage pending files.

## Scheduling the daily email fetch (macOS)

Optional — only needed if you want `fetch_statements.py` to run automatically
every morning instead of relying on "Check email now" or running it by hand.
macOS `launchd` (not cron) is used because it reliably catches up on a missed
run after the machine wakes from sleep.

```
cp com.spendanalyser.fetchstatements.plist.example \
   ~/Library/LaunchAgents/com.spendanalyser.fetchstatements.plist
```

Edit that copy: replace every `/ABSOLUTE/PATH/TO/spend-analyser` with the
real absolute path to this project directory (`pwd` from inside it will tell
you), and adjust `Hour`/`Minute` under `StartCalendarInterval` if 7:00 AM
doesn't suit you. Then:

```
launchctl load ~/Library/LaunchAgents/com.spendanalyser.fetchstatements.plist
launchctl start com.spendanalyser.fetchstatements   # optional: run once now to test
```

To stop it: `launchctl unload
~/Library/LaunchAgents/com.spendanalyser.fetchstatements.plist`. Logs from
the scheduled run go to `fetch_statements.log` (not runs triggered by the
dashboard's "Check email now" button — those log to `server.py`'s own
console instead, since that path runs in-process rather than as a separate
subprocess).

---

## Reference

Deeper detail on how things work internally — skip this unless you're
debugging something or extending the app.

### File-by-file

- **`server.py`** — the Flask backend. Serves the dashboard and the ledger,
  parses/categorizes/dedups uploaded statements, and hosts the
  pending-statements and statement-formats workflows.
- **`spend_analyser.html`** — the dashboard UI: a single file, vanilla JS +
  Chart.js + PapaParse loaded from a CDN.
- **`transactions.csv`** — the single source of truth ledger. Columns: `id,
  date, description, amount, account, category`. Amount is signed: negative
  = spend, positive = income/credit. Both the server and the dashboard read
  and write this same file directly — there is no database.
- **`category_rules.json`** — keyword → category mapping used to
  auto-categorize a transaction from its description at upload time (first
  matching category wins; falls back to "Others"). The dashboard has its own
  copy of these same rules baked into `spend_analyser.html`'s `RULES` object
  (used when it re-parses the CSV client-side) — if you edit
  `category_rules.json`, update `RULES` to match.
- **`fetch_statements.py`** — standalone script (doesn't import `server.py`,
  doesn't start Flask, no AI/Claude Code session ever touches the mailbox)
  that logs into Gmail over IMAP, matches new emails by subject-line
  substring against `statement_subjects.json`, and saves any `.pdf`/`.xlsx`/
  `.xls` attachments into `incoming_statements/` with a `manifest.json` entry
  so the Pending Statements tab can pre-fill the account label. Passwords
  are never stored — you still enter them by hand when uploading a pending
  file. Dedup is via IMAP `UID`+`UIDVALIDITY` pairs in `.fetched_state.json`,
  so re-running it is always safe.
- **`mail_config.json`** (git-ignored, `chmod 600`) — Gmail address + app
  password, IMAP host/port/mailbox, and `search_window_days` (how many days
  back to search each run — kept narrow deliberately, see Known
  limitations).
- **`statement_subjects.json`** — flat `"subject substring": "account
  label"` map. Add a new bank/card by adding an entry here (or via the
  Statement Formats tab) — no code change needed, as long as an existing
  parser already handles that statement's layout.
- **`incoming_statements/`** (git-ignored) — where fetched attachments land
  until uploaded or deleted; `manifest.json` inside it tracks per-file
  metadata.
- **`.fetched_state.json`** (git-ignored) — IMAP dedup bookkeeping only. It
  does **not** contain transaction data — if something seems missing, check
  `incoming_statements/manifest.json` (pending) or `transactions.csv`
  (committed), not this file.
- **`.venv`** — Python virtualenv (Flask, openpyxl, msoffcrypto-tool,
  pdfplumber, pikepdf).
- **`com.spendanalyser.fetchstatements.plist.example`** — template for the
  macOS LaunchAgent, see Scheduling above.

### PDF statement format detection

The server auto-detects which of several known PDF layouts a statement is,
by checking for an **exact header phrase** in the extracted text — not loose
keyword sniffing, since disclaimer boilerplate (or, in one real case, a
donut-chart label pdfplumber glued onto a transaction line) can contain
stray matching text:

1. `"date mode particulars"` → ICICI Bank savings-account layout: narration
   wraps both before and after the date/amount line.
2. `"date serno"` → ICICI Bank credit card layout (e.g. Sapphiro): single
   line per transaction, reward-points column, trailing `CR` marks a credit.
3. `"transaction details"` + `"withdrawal deposits balance"` → Axis Bank
   savings/salary account layout: two trailing numbers (amount + running
   balance), direction inferred from which way the balance moved.
4. `"narration withdrawals deposits"` → bank/savings-account layout: 3
   numeric columns (withdrawal, deposit, closing balance), narration can
   wrap onto continuation lines.
5. `"merchant category"` → Axis-style credit card layout (Magnus/Horizon):
   single amount column with a trailing `Dr`/`Cr` suffix instead of a sign.
6. Otherwise → generic fallback: single amount column, credits marked with a
   leading `+`, debits unsigned.

Adding a new bank format: detect it by an exact, table-header-specific
phrase (never generic keywords that could appear elsewhere in the
document), and reconcile the new parser's total against the statement's own
printed summary before trusting it — don't assume it's correct just because
it produced rows. Use the Statement Formats tab to check first; if nothing
matches, it hands you the raw extracted text and a one-click "copy for
Claude" button.

### Excluded transactions

Some transactions are dropped entirely at ingestion (`EXCLUDE_KEYWORDS` in
`server.py`) because they're self-repayment — e.g. paying your own credit
card bill from your own bank account is debt repayment, not real spend or
income, so counting it would inflate/deflate the dashboard's figures:

- `bppy cc payment`
- `bbps payment received`

This is distinct from the **Credit Card Bill** category, which is the
corresponding debit on the *paying* bank account (real money leaving a
tracked account) — that one stays in the ledger and counts as spend.

### How credits inside a spend category are handled

A spend category can still contain a positive-amount row — a refund, a
reversal (e.g. a failed autopay bouncing back as a credit), or someone
paying back their share of a Settlement. These are netted against that
category's debits, not ignored and not auto-reclassified as income: every
place a category total is computed (summary spend, trend chart, budget
actual/average, the per-category history chart) sums the signed amounts
within the category first, then takes the absolute value at the end. Real
income should still be categorized as `Salary / Income`, `Dividend`, or
`Cashback` by hand — those are the only categories counted toward the
dashboard's Income figure.

## Known limitations

- No multi-currency support — amounts are plain numbers, always formatted
  with `₹`.
- Single local CSV, no multi-user support, no auth on the server — safe by
  default (`127.0.0.1`-only), but see the LAN note under Setup if you ever
  turn that on.
- Budgets live in the browser's `localStorage`, not `transactions.csv` — they
  don't travel with a CSV backup and are per-browser, not per-ledger.
- Dedup is content-based (date/description/amount/account) — editing a
  transaction's description after import means re-uploading the original
  statement would no longer be recognized as a duplicate.
- PDF parsing only handles the 6 layouts above; anything else needs the
  Statement Formats tab's "copy for Claude" flow rather than the upload form
  succeeding outright.
- The email fetcher's `search_window_days` is deliberately narrow (default
  1 in the example config) — a multi-day sleep gap at the scheduled fetch
  time could miss an email entirely; IMAP UID dedup means widening the
  window afterward won't retroactively catch it. Use "Check now" if you
  suspect this happened.
- No automated tests — verify a new/changed parser manually by reconciling
  against the statement's own totals before trusting it.
