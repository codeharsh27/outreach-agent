"""
followup.py — Automated 4-Day Follow-Up Engine
Generates short, natural follow-up draft cards for sent emails after 4 days.
"""
import os
import time
from datetime import datetime, timezone, timedelta
from agents.tracker import verify_connection, _sb, update_draft_status
from agents.config import YOUR_NAME, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

def check_and_create_due_followups():
    """Find sends from 4+ days ago that don't have a follow-up record yet."""
    try:
        sb = _sb()
        four_days_ago = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
        
        # Get sent emails from 4+ days ago
        sends_res = sb.table("sends") \
            .select("id, draft_id, sent_at") \
            .eq("status", "sent") \
            .lte("sent_at", four_days_ago) \
            .execute()
        
        sent_rows = sends_res.data or []
        if not sent_rows:
            return

        # Check existing follow-ups
        existing_res = sb.table("follow_ups").select("send_id").execute()
        existing_send_ids = {r["send_id"] for r in (existing_res.data or [])}

        created = 0
        for send_row in sent_rows:
            send_id = send_row["id"]
            if send_id in existing_send_ids:
                continue
            
            # Queue follow-up due now
            sb.table("follow_ups").insert({
                "send_id": send_id,
                "due_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending"
            }).execute()
            created += 1

        if created:
            print(f"  📅 Queued {created} follow-ups due today!")
    except Exception as e:
        print(f"  [followup] check error: {e}")


def generate_followup_text(company_name: str, contact_name: str, original_subject: str) -> dict:
    """Generate short 2-sentence natural follow-up email."""
    subject = f"Re: {original_subject.replace('Re: ', '')}"
    body = (
        f"Hi {contact_name},\n\n"
        f"Quick bump on this — wanted to see if you had a chance to look at my note regarding {company_name}'s tech stack?\n\n"
        f"If you're open to it, happy to send over a 2-minute breakdown.\n\n"
        f"Harsh Mule\n"
        f"Building [SideDoor](https://sidedoor-chi.vercel.app/) | [Portfolio](https://harshmule.vercel.app/)\n"
        f"Socials: [X](https://x.com/codeharsh27) | [LinkedIn](https://www.linkedin.com/in/harshmule27/) | [Github](https://github.com/codeharsh27)"
    )
    return {"subject": subject, "body": body}


def run():
    """Run follow-up check and print stats."""
    verify_connection()
    check_and_create_due_followups()


if __name__ == "__main__":
    run()
