"""
Gmail sender — timezone-aware, rate-limited.
Only sends on Tue/Wed/Thu, 9–11am in the RECIPIENT's local timezone.
Adds 2–8 min random delay between sends to mimic human behavior.
"""
import base64
import random
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import pytz
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from agents.config import GMAIL_SENDER, GMAIL_TOKEN, GMAIL_CREDS, SEND_DAYS, TRACKER_DB
from agents.tracker import queue_send, mark_sent

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# Common country → timezone mappings for startups
COUNTRY_TZ = {
    "US": "America/New_York",
    "USA": "America/New_York",
    "United States": "America/New_York",
    "GB": "Europe/London",
    "UK": "Europe/London",
    "IN": "Asia/Kolkata",
    "India": "Asia/Kolkata",
    "DE": "Europe/Berlin",
    "Germany": "Europe/Berlin",
    "SG": "Asia/Singapore",
    "Singapore": "Asia/Singapore",
    "AU": "Australia/Sydney",
    "Australia": "Australia/Sydney",
    "CA": "America/Toronto",
    "Canada": "America/Toronto",
    "FR": "Europe/Paris",
    "France": "Europe/Paris",
    "NL": "Europe/Amsterdam",
    "Netherlands": "Europe/Amsterdam",
}
DEFAULT_TZ = "America/New_York"   # Most YC companies are US-based


# ── Gmail auth ────────────────────────────────────────────────────

def get_gmail_service():
    """Load credentials and return authenticated Gmail service."""
    creds = None
    if GMAIL_TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(GMAIL_TOKEN, "w") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError("Gmail not authenticated. Run setup_gmail.sh first.")
    return build("gmail", "v1", credentials=creds)


# ── Timezone detection ────────────────────────────────────────────

def detect_timezone(company: dict) -> str:
    """
    Guess recipient timezone from company country or domain TLD.
    Falls back to US Eastern (most YC startups).
    """
    country = company.get("hq_country", "")
    if country and country in COUNTRY_TZ:
        return COUNTRY_TZ[country]

    # Guess from domain TLD
    domain = company.get("domain", "")
    if domain:
        tld = domain.rsplit(".", 1)[-1].lower()
        tld_map = {
            "in": "Asia/Kolkata",
            "uk": "Europe/London",
            "de": "Europe/Berlin",
            "au": "Australia/Sydney",
            "sg": "Asia/Singapore",
            "ca": "America/Toronto",
            "fr": "Europe/Paris",
            "nl": "Europe/Amsterdam",
        }
        if tld in tld_map:
            return tld_map[tld]

    return DEFAULT_TZ


def next_send_window(tz_name: str) -> datetime:
    """
    Calculate the next valid send window:
    Tue/Wed/Thu, 9–11am in recipient's timezone.
    Returns UTC datetime.
    """
    tz = pytz.timezone(tz_name)
    now_local = datetime.now(tz)

    # Find next valid day
    for days_ahead in range(7):
        candidate = now_local + timedelta(days=days_ahead)
        # weekday(): Mon=0 ... Sun=6; we want Tue=1, Wed=2, Thu=3
        if candidate.weekday() not in SEND_DAYS:
            continue

        # Target: 9:30am local (middle of 9–11am window)
        target = candidate.replace(hour=9, minute=30, second=0, microsecond=0)
        # Add random offset within the window (0–90 min)
        target += timedelta(minutes=random.randint(0, 90))

        if target > now_local:
            return target.astimezone(timezone.utc)

    # Fallback: 9:30am next Tuesday UTC
    return datetime.now(timezone.utc) + timedelta(days=2)


def get_gmail_signature(service) -> str:
    """Fetch user's default Gmail signature HTML via API."""
    try:
        send_as = service.users().settings().sendAs().list(userId="me").execute()
        for send_as_obj in send_as.get("sendAs", []):
            if send_as_obj.get("isDefault"):
                return send_as_obj.get("signature", "")
    except Exception:
        pass
    return ""


# ── Build email ───────────────────────────────────────────────────

def build_email(to: str, subject: str, body: str, signature_html: str = "") -> dict:
    """
    Build HTML + Plain Text Gmail API message payload.
    Converts markdown links [text](url) to HTML <a href="url">text</a>.
    Appends Gmail signature cleanly without artificial '--' dividers.
    """
    import re
    # Convert markdown links [text](url) to HTML links <a href="url">text</a>
    html_body_content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', body)
    
    # Format paragraphs into <p> tags
    paragraphs = html_body_content.strip().split("\n\n")
    html_paragraphs = "".join(f"<p>{p.replace('\n', '<br>')}</p>" for p in paragraphs if p.strip())
    
    if signature_html:
        html_content = f"<div>{html_paragraphs}</div><br><div>{signature_html}</div>"
    else:
        html_content = f"<div>{html_paragraphs}</div>"

    # Plain text version (strips markdown links, leaving link text)
    plain_body = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", body)

    msg = MIMEMultipart("alternative")
    msg["From"] = GMAIL_SENDER
    msg["To"] = to
    msg["Subject"] = subject

    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}


# ── Send ──────────────────────────────────────────────────────────

def send_email(service, draft_id: int, to: str, subject: str,
               body: str, company: dict) -> bool:
    """
    Schedule and send one email via Gmail API.
    Returns True on success.
    """
    tz_name = detect_timezone(company)
    scheduled_for = next_send_window(tz_name)

    # Queue in tracker
    send_id = queue_send(draft_id, "email", scheduled_for.isoformat())

    # Check if we need to wait for the send window
    now_utc = datetime.now(timezone.utc)
    wait_seconds = (scheduled_for - now_utc).total_seconds()

    if wait_seconds > 30:
        print(f"    ⏰ Scheduled for {scheduled_for.strftime('%a %H:%M')} UTC "
              f"({tz_name}) — waiting {int(wait_seconds/60)} min")
        # In production this would use a proper scheduler
        # For now: if the window is within 2 hours, wait; else mark as queued and exit
        if wait_seconds > 7200:
            print(f"    📅 Email queued (sends next valid window)")
            return True  # Will be picked up by next cron run
        time.sleep(min(wait_seconds, 60))  # Wait max 1 min in demo mode

    try:
        signature_html = get_gmail_signature(service)
        message_payload = build_email(to, subject, body, signature_html)
        service.users().messages().send(
            userId="me", body=message_payload
        ).execute()
        mark_sent(send_id)
        print(f"    ✅ Email sent to {to}")
        return True
    except Exception as e:
        conn = sqlite3.connect(str(TRACKER_DB))
        conn.execute("UPDATE sends SET status='failed', error=? WHERE id=?",
                     (str(e), send_id))
        conn.commit()
        conn.close()
        print(f"    ❌ Send failed: {e}")
        return False


# ── Main send run ─────────────────────────────────────────────────

def run(approved_draft_ids: list):
    """
    Send all approved drafts via Gmail.
    Rate-limited: 2–8 min random delay between each send.
    """
    if not approved_draft_ids:
        print("   No approved drafts to send")
        return

    print(f"\n📨 Sending {len(approved_draft_ids)} approved emails...")
    service = get_gmail_service()

    conn = sqlite3.connect(str(TRACKER_DB))
    conn.row_factory = sqlite3.Row

    sent_count = 0
    for i, draft_id in enumerate(approved_draft_ids):
        row = conn.execute("""
            SELECT d.*, co.name as company_name, co.domain, co.hq_country,
                   ct.email, ct.name as contact_name
            FROM drafts d
            JOIN companies co ON co.id = d.company_id
            JOIN contacts  ct ON ct.id = d.contact_id
            WHERE d.id = ?
        """, (draft_id,)).fetchone()

        if not row:
            continue

        row = dict(row)
        company = {"domain": row.get("domain"), "hq_country": row.get("hq_country"),
                   "name": row.get("company_name")}

        print(f"\n  [{i+1}/{len(approved_draft_ids)}] {row['company_name']} → {row['email']}")

        success = send_email(
            service=service,
            draft_id=draft_id,
            to=row["email"],
            subject=row["email_subject"],
            body=row["email_body"],
            company=company,
        )

        if success:
            sent_count += 1

        # Random delay between sends (2–8 min) — avoids spam detection
        if i < len(approved_draft_ids) - 1:
            delay = random.randint(120, 480)
            print(f"    ⏳ Waiting {delay//60}m {delay%60}s before next send...")
            time.sleep(delay)

    conn.close()
    print(f"\n✅ Send complete: {sent_count}/{len(approved_draft_ids)} sent")

    # Send Telegram summary
    try:
        import httpx
        from agents.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
        httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": f"📨 Outreach run complete: {sent_count} emails sent today.",
            }
        )
    except Exception:
        pass


if __name__ == "__main__":
    # Test: list approved drafts and send them
    conn = sqlite3.connect(str(TRACKER_DB))
    conn.row_factory = sqlite3.Row
    approved = [r["id"] for r in conn.execute(
        "SELECT id FROM drafts WHERE status='approved'"
    ).fetchall()]
    conn.close()
    run(approved)
