#!/usr/bin/env python3
"""Fetches new bank/card statement attachments from Gmail via IMAP and stages
them locally for the dashboard's "Pending statements" panel.

Runs standalone — does not import server.py, does not start Flask, does not
give any AI/Claude Code session access to the mailbox. Intended to be run
daily by a launchd LaunchAgent (see the .plist file), or by hand:

    .venv/bin/python3 fetch_statements.py

Requires mail_config.json (see mail_config.example.json for the shape) with
a Gmail app-specific password — generate one at
https://myaccount.google.com/apppasswords (requires 2-Step Verification).
"""
import email
import imaplib
import json
import os
import re
import sys
from datetime import datetime, timedelta

DIRECTORY = os.path.dirname(os.path.abspath(__file__))
MAIL_CONFIG_PATH = os.path.join(DIRECTORY, "mail_config.json")
SUBJECTS_PATH = os.path.join(DIRECTORY, "statement_subjects.json")
STATE_PATH = os.path.join(DIRECTORY, ".fetched_state.json")
INCOMING_DIR = os.path.join(DIRECTORY, "incoming_statements")
MANIFEST_PATH = os.path.join(INCOMING_DIR, "manifest.json")

ATTACHMENT_EXTS = (".pdf", ".xlsx", ".xls")


def log(msg):
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)


def load_mail_config():
    if not os.path.exists(MAIL_CONFIG_PATH):
        raise RuntimeError(
            f"{MAIL_CONFIG_PATH} not found — copy mail_config.example.json to "
            "mail_config.json and fill in your Gmail address + app password."
        )
    with open(MAIL_CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    try:
        os.chmod(MAIL_CONFIG_PATH, 0o600)
    except OSError:
        pass
    config.setdefault("imap_host", "imap.gmail.com")
    config.setdefault("imap_port", 993)
    config.setdefault("mailbox", "INBOX")
    config.setdefault("search_window_days", 10)
    return config


def load_subject_map():
    with open(SUBJECTS_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    subject_map = {}
    for subject, value in raw.items():
        if isinstance(value, dict):
            subject_map[subject] = {"account": value["account"], "from_domain": value.get("from_domain")}
        else:
            subject_map[subject] = {"account": value, "from_domain": None}
    return subject_map


def load_state():
    if not os.path.exists(STATE_PATH):
        return {"uidvalidity": None, "processed_uids": []}
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def load_manifest():
    if not os.path.exists(MANIFEST_PATH):
        return {}
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(manifest):
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def get_uidvalidity(M):
    typ, data = M.response("UIDVALIDITY")
    if data and data[0]:
        try:
            return int(data[0])
        except (TypeError, ValueError):
            return None
    return None


def connect(config):
    M = imaplib.IMAP4_SSL(config["imap_host"], config["imap_port"])
    M.login(config["email"], config["app_password"])
    M.select(config["mailbox"], readonly=True)
    return M


def save_attachment(part, uid, account, subject, received):
    filename = part.get_filename()
    if not filename or not filename.lower().endswith(ATTACHMENT_EXTS):
        return None
    date_prefix = received.strftime("%Y%m%d") if received else datetime.now().strftime("%Y%m%d")
    saved_name = f"{date_prefix}_{slugify(account)}_{uid}_{filename}"
    path = os.path.join(INCOMING_DIR, saved_name)
    payload = part.get_payload(decode=True)
    if payload is None:
        return None
    with open(path, "wb") as f:
        f.write(payload)
    return saved_name


def fetch_new_statements(config=None):
    """Returns a summary dict: {matched, saved, errors}. Importable so both
    the CLI entry point below and an optional manual "check now" server route
    can trigger the same logic."""
    summary = {"matched": 0, "saved": 0, "errors": []}
    try:
        config = config or load_mail_config()
        subject_map = load_subject_map()
    except Exception as e:
        log(f"ERROR: config load failed: {e}")
        summary["errors"].append(str(e))
        return summary

    os.makedirs(INCOMING_DIR, exist_ok=True)
    state = load_state()

    try:
        M = connect(config)
    except imaplib.IMAP4.error as e:
        log(
            f"ERROR: IMAP login failed ({e}) — check mail_config.json's app_password, "
            "and confirm IMAP is enabled in Gmail Settings > Forwarding and POP/IMAP."
        )
        summary["errors"].append(str(e))
        return summary
    except OSError as e:
        log(f"ERROR: could not connect to {config['imap_host']}:{config['imap_port']} ({e})")
        summary["errors"].append(str(e))
        return summary

    try:
        uidvalidity = get_uidvalidity(M)
        if uidvalidity is not None and state.get("uidvalidity") != uidvalidity:
            log(f"UIDVALIDITY changed ({state.get('uidvalidity')} -> {uidvalidity}) — resetting dedup state.")
            state = {"uidvalidity": uidvalidity, "processed_uids": []}
        processed = set(state.get("processed_uids", []))

        since = (datetime.now() - timedelta(days=config["search_window_days"])).strftime("%d-%b-%Y")
        manifest = load_manifest()

        for subject, meta in subject_map.items():
            account = meta["account"]
            typ, data = M.uid("search", None, "SINCE", since, "SUBJECT", f'"{subject}"')
            if typ != "OK" or not data or not data[0]:
                continue
            uids = data[0].split()
            for uid_bytes in uids:
                uid = uid_bytes.decode()
                if uid in processed:
                    continue
                summary["matched"] += 1
                typ, msg_data = M.uid("fetch", uid_bytes, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    log(f"WARNING: could not fetch uid {uid} for subject '{subject}'")
                    processed.add(uid)
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                received = None
                try:
                    received = email.utils.parsedate_to_datetime(msg.get("Date"))
                except (TypeError, ValueError):
                    pass

                any_saved = False
                for part in msg.walk():
                    saved_name = save_attachment(part, uid, account, subject, received)
                    if saved_name:
                        manifest[saved_name] = {
                            "account": account,
                            "subject": subject,
                            "received": received.isoformat() if received else None,
                        }
                        summary["saved"] += 1
                        any_saved = True
                        log(f"Saved {saved_name} (subject: '{subject}')")
                if not any_saved:
                    log(f"Subject '{subject}' matched uid {uid} but had no .pdf/.xlsx/.xls attachment — skipping.")
                processed.add(uid)

        save_manifest(manifest)
        state["processed_uids"] = sorted(processed)
        save_state(state)
    finally:
        try:
            M.logout()
        except Exception:
            pass

    log(f"Done — matched {summary['matched']}, saved {summary['saved']} new attachment(s).")
    return summary


if __name__ == "__main__":
    result = fetch_new_statements()
    sys.exit(1 if result["errors"] else 0)
