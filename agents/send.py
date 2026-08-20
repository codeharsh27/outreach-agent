"""
send.py — Timezone-aware Gmail Dispatch Engine
Fixes applied:
- V2: CRLF regex sanitization for email subject and recipient headers to prevent header injection
- V4: Unhandled Google OAuth RefreshError handling with graceful fallback & alert
- V7: Environment variable fallback for GMAIL_TOKEN_JSON in CI runners
- V8: Row-level atomic status locking ("sending") to prevent parallel send race conditions
- V9: Cap inter-send delays in CI (GITHUB_ACTIONS=true) to prevent job timeouts
"""
import base64
import json
import os
import random
import re
import time
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import pytz
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build

from agents.config import GMAIL_SENDER, GMAIL_TOKEN, GMAIL_CREDS, SEND_DAYS
from agents.tracker import queue_send, mark_sent, _sb

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# Expanded timezone mappings
COUNTRY_TZ = {
    "US": "America/New_York",
    "USA": "America/New_York",
    "United States": "America/New_York",
    "India": "Asia/Kolkata",
    "IN": "Asia/Kolkata",
    "UK": "Europe/London",
    "United Kingdom": "Europe/London",
    "Germany": "Europe/Berlin",
    "DE": "Europe/Berlin",
    "France": "Europe/Paris",
    "Canada": "America/Toronto",
}


def _sanitize_header(text: str) -> str:
    """Fix V2: Strip CRLF characters to prevent MIME header injection."""
    if not text:
        return ""
    return re.sub(r'[\r\n]', '', str(text)).strip()


def get_gmail_service():
    """Fix V4 & V7: Secure, non-blocking Gmail authentication for local & CI environments."""
    creds = None

    # Load from token.json or env variable GMAIL_TOKEN_JSON
    if GMAIL_TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN), SCOPES)
    elif os.getenv("GMAIL_TOKEN_JSON"):
        try:
            info = json.loads(os.getenv("GMAIL_TOKEN_JSON"))
            creds = Credentials.from_authorized_user_info(info, SCOPES)
        except Exception as e:
            print(f"❌ Error parsing GMAIL_TOKEN_JSON from env: {e}")

    if not creds:
        raise RuntimeError(
            "Gmail credentials not found!\n"
            "Run 'python3 scripts/setup_gmail.py' locally or set GMAIL_TOKEN_JSON in GitHub Secrets."
        )

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            print(f"❌ Gmail OAuth token refresh failed: {e}")
            raise RuntimeError("Gmail token expired/revoked. Re-authenticate via 'python3 scripts/setup_gmail.py'")

    return build("gmail", "v1", credentials=creds)


def detect_timezone(company: dict) -> str:
    hq = company.get("hq_country", "")
    return COUNTRY_TZ.get(hq, "Asia/Kolkata")


def build_email(to: str, subject: str, body: str, signature_html: str = "") -> dict:
    """Fix V2: Build MIME message payload with sanitized subject and headers."""
    clean_to = _sanitize_header(to)
    clean_subject = _sanitize_header(subject)

    html_body_content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', body)
    paragraphs = html_body_content.strip().split("\n\n")
    html_paragraphs = "".join(f"<p>{p.replace('\n', '<br>')}</p>" for p in paragraphs if p.strip())

    if signature_html:
        html_content = f"<div>{html_paragraphs}</div><br><div>{signature_html}</div>"
    else:
        html_content = f"<div>{html_paragraphs}</div>"

    plain_body = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", body)

    msg = MIMEMultipart("alternative")
    msg["From"] = GMAIL_SENDER
    msg["To"] = clean_to
    msg["Subject"] = clean_subject

    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}


def send_email(service, draft_id: int, to: str, subject: str,
               body: str, company: dict) -> bool:
    """Send one email with sending state locks."""
    tz_name = detect_timezone(company)
    scheduled_for = datetime.now(timezone.utc)

    # Queue send in tracker (status = 'sending')
    send_id = queue_send(draft_id, "email", scheduled_for.isoformat())
    if not send_id:
        print(f"    ⚠️ Draft {draft_id} is already being sent by another process")
        return False

    try:
        signature_html = ""
        try:
            send_as = service.users().settings().sendAs().list(userId="me").execute()
            for send_as_obj in send_as.get("sendAs", []):
                if send_as_obj.get("isDefault"):
                    signature_html = send_as_obj.get("signature", "")
        except Exception:
            pass

        message_payload = build_email(to, subject, body, signature_html)
        service.users().messages().send(userId="me", body=message_payload).execute()
        mark_sent(send_id)
        print(f"    ✅ Email sent to {_sanitize_header(to)}")
        return True
    except Exception as e:
        try:
            _sb().table("sends").update({"status": "failed", "error": str(e)}).eq("id", send_id).execute()
        except Exception:
            pass
        print(f"    ❌ Send failed: {e}")
        return False


def run(approved_draft_ids: list):
    """Send all approved drafts with CI delay capping."""
    if not approved_draft_ids:
        print("   No approved drafts to send")
        return

    print(f"\n📨 Sending {len(approved_draft_ids)} approved emails...")
    try:
        service = get_gmail_service()
    except Exception as e:
        print(f"❌ Cannot initialize Gmail service: {e}")
        return

    sent_count = 0
    is_ci = os.getenv("GITHUB_ACTIONS") == "true"

    for i, draft_id in enumerate(approved_draft_ids):
        try:
            res = _sb().table("drafts") \
                .select("*, companies(name, domain, hq_country), contacts(name, email)") \
                .eq("id", draft_id) \
                .limit(1) \
                .execute()

            if not res.data:
                continue

            row = res.data[0]
            co  = row.pop("companies", {}) or {}
            ct  = row.pop("contacts", {}) or {}
        except Exception as e:
            print(f"   Error fetching draft {draft_id}: {e}")
            continue

        company = {
            "domain":     co.get("domain"),
            "hq_country": co.get("hq_country"),
            "name":       co.get("name"),
        }

        print(f"\n  [{i+1}/{len(approved_draft_ids)}] {co.get('name')} → {ct.get('email')}")

        success = send_email(
            service=service,
            draft_id=draft_id,
            to=ct.get("email", ""),
            subject=row.get("email_subject", ""),
            body=row.get("email_body", ""),
            company=company,
        )

        if success:
            sent_count += 1

        # Fix V9: Cap delay in CI (5-15s) vs local (120-480s) to prevent job timeouts
        if i < len(approved_draft_ids) - 1:
            delay = random.randint(5, 15) if is_ci else random.randint(120, 480)
            print(f"    ⏳ Waiting {delay}s before next send...")
            time.sleep(delay)

    print(f"\n✅ Send complete: {sent_count}/{len(approved_draft_ids)} sent")


if __name__ == "__main__":
    try:
        res = _sb().table("drafts").select("id").eq("status", "approved").execute()
        approved = [r["id"] for r in (res.data or [])]
        run(approved)
    except Exception as e:
        print(f"Error: {e}")
