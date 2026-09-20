#!/usr/bin/env python3
"""
gmail_fetch.py -- production fetch leg for the jev-inbox-triage demo.

Reads the inbox through the Gmail API with the ``gmail.readonly`` scope
ONLY, tracks every message ID it has already forwarded (deterministic
dedupe), and POSTs only new messages to the pipeline's ``/inbox`` endpoint.

ABSOLUTE RULE: this script is read-only against Gmail. It never marks
messages read, never adds or removes labels, never archives, never reports
spam, never deletes, never sends. The readonly scope is the enforcement:
the Gmail API rejects any mutating call made with these credentials.

Configuration (environment only -- no credentials in this file):

    GMAIL_TOKEN_PATH    Path to a Google OAuth token.json holding a refresh
                        token (created once via the standard OAuth flow).
    GMAIL_LABEL_IDS     Label IDs to poll, comma-separated. Default: INBOX.
    JEV_INBOX_ENDPOINT  Pipeline endpoint. Default: http://127.0.0.1:8080/inbox
    JEV_INBOX_STATE     Dedupe state file. Default: ./data/gmail_fetch_seen.json

Requires: google-api-python-client, google-auth-oauthlib
    pip install google-api-python-client google-auth-oauthlib
"""
import base64
import json
import os
import sys
import urllib.request

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]  # read-only, full stop


def load_state(path):
    try:
        with open(path) as f:
            return set(json.load(f).get("seen_ids", []))
    except (OSError, ValueError):
        return set()


def save_state(path, seen):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"seen_ids": sorted(seen)}, f)


def gmail_service(token_path):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    return build("gmail", "v1", credentials=creds)


def header_value(headers, name):
    name = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name:
            return h.get("value", "")
    return ""


def body_text(payload):
    """Best-effort plain-text extraction, trimmed for the judgment call."""
    parts = [payload] + payload.get("parts", [])
    for part in parts:
        if part.get("mimeType", "").startswith("text/plain") and part.get("body", {}).get("data"):
            text = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "replace")
            return text[:4000]
    return ""


def to_event(message):
    payload = message.get("payload", {})
    headers = payload.get("headers", [])
    return {
        "id": message["id"],
        "sender": header_value(headers, "From"),
        "subject": header_value(headers, "Subject"),
        "headers": {
            "Date": header_value(headers, "Date"),
            "Message-Id": header_value(headers, "Message-Id"),
            "List-Unsubscribe": header_value(headers, "List-Unsubscribe"),
        },
        "body": body_text(payload),
    }


def post_event(endpoint, event):
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(event).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status


def main():
    token_path = os.environ.get("GMAIL_TOKEN_PATH")
    if not token_path:
        print("GMAIL_TOKEN_PATH is not set -- refusing to run.", file=sys.stderr)
        sys.exit(1)
    endpoint = os.environ.get("JEV_INBOX_ENDPOINT", "http://127.0.0.1:8080/inbox")
    state_path = os.environ.get("JEV_INBOX_STATE", "./data/gmail_fetch_seen.json")
    label_ids = [l for l in os.environ.get("GMAIL_LABEL_IDS", "INBOX").split(",") if l]

    seen = load_state(state_path)
    service = gmail_service(token_path)

    new = 0
    page_token = None
    while True:
        result = (
            service.users()
            .messages()
            .list(userId="me", labelIds=label_ids, maxResults=50, pageToken=page_token)
            .execute()
        )
        for ref in result.get("messages", []):
            if ref["id"] in seen:
                continue
            # Read-only fetch: messages.get only.
            full = (
                service.users()
                .messages()
                .get(userId="me", id=ref["id"], format="full")
                .execute()
            )
            event = to_event(full)
            post_event(endpoint, event)
            seen.add(ref["id"])
            new += 1
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    save_state(state_path, seen)
    print(f"forwarded {new} new message(s); {len(seen)} id(s) tracked")


if __name__ == "__main__":
    main()
