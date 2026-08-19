"""
Telegram approval gate.
Sends pending drafts to your phone in batches of 5.
You tap Approve / Edit / Skip — agent waits for your response.
"""
import asyncio
import sqlite3
import time
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes
from agents.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TRACKER_DB
from agents.tracker import get_pending_drafts, update_draft_status


# ── Format a draft message for Telegram ──────────────────────────

def format_draft_message(draft: dict) -> str:
    """Format a draft into a readable Telegram message with separated sections."""
    company = draft.get("company_name", "Unknown")
    contact = draft.get("contact_name", "Unknown")
    email = draft.get("email", "")
    domain = draft.get("domain", "")
    subject = draft.get("email_subject", "")
    body = draft.get("email_body", "")
    linkedin = draft.get("linkedin_msg", "")
    x_reply = draft.get("x_reply_text", "")
    x_url = draft.get("x_reply_url", "")

    header = f"🏢 <b>{company}</b>  ·  {contact}\n📧 {email}" + (f"  ·  {domain}" if domain else "")
    
    lines = [
        header,
        "",
        "━━━━━━ <b>EMAIL DRAFT</b> ━━━━━━",
        f"<b>Subject:</b> {subject}",
        "",
        body,
    ]

    if linkedin:
        lines += [
            "",
            "━━━━━━ <b>LINKEDIN (copy-paste)</b> ━━━━━━",
            f"<code>{linkedin}</code>"
        ]

    if x_reply:
        lines += [
            "",
            "━━━━━━ <b>X REPLY</b> ━━━━━━"
        ]
        if x_url:
            lines.append(f"Tweet → <a href='{x_url}'>{x_url}</a>")
        lines.append(f"<code>{x_reply}</code>")

    return "\n".join(lines)


def approval_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard: Approve / Skip."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve & Send Email", callback_data=f"approve:{draft_id}"),
        InlineKeyboardButton("❌ Skip", callback_data=f"skip:{draft_id}"),
    ]])


# ── Async send + wait for approval ───────────────────────────────

async def send_batch_for_approval(drafts: list) -> list:
    """
    Send up to 5 drafts to Telegram, wait for approval/skip on each.
    Returns list of approved draft IDs.
    """
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    approved_ids = []
    pending_msg_ids = {}  # draft_id → telegram message_id

    # Send all drafts in the batch
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=f"📬 <b>{len(drafts)} new outreach drafts ready for review</b>",
        parse_mode="HTML"
    )

    for draft in drafts:
        draft_id = draft["id"]
        msg_text = format_draft_message(dict(draft))

        msg = await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg_text,
            parse_mode="HTML",
            reply_markup=approval_keyboard(draft_id),
            disable_web_page_preview=True,
        )
        pending_msg_ids[draft_id] = msg.message_id
        update_draft_status(draft_id, "pending", str(msg.message_id))
        await asyncio.sleep(0.5)

    # Poll for responses (max 10 minutes per batch)
    print(f"   Waiting for Telegram approval (10 min timeout)...")
    deadline = time.time() + 600
    decided = set()

    while len(decided) < len(drafts) and time.time() < deadline:
        try:
            updates = await bot.get_updates(timeout=10, offset=-1)
            for update in updates:
                if not update.callback_query:
                    continue
                cb = update.callback_query
                data = cb.data or ""

                if ":" not in data:
                    continue
                action, draft_id_str = data.split(":", 1)
                draft_id = int(draft_id_str)

                if draft_id in decided:
                    continue
                decided.add(draft_id)

                if action == "approve":
                    update_draft_status(draft_id, "approved")
                    approved_ids.append(draft_id)
                    await cb.answer("✅ Approved!")
                    await bot.edit_message_reply_markup(
                        chat_id=TELEGRAM_CHAT_ID,
                        message_id=pending_msg_ids[draft_id],
                        reply_markup=None
                    )
                    await bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID,
                        text=f"✅ Approved → queued for send"
                    )
                elif action == "skip":
                    update_draft_status(draft_id, "skipped")
                    await cb.answer("Skipped")
                    await bot.edit_message_reply_markup(
                        chat_id=TELEGRAM_CHAT_ID,
                        message_id=pending_msg_ids[draft_id],
                        reply_markup=None
                    )

        except Exception as e:
            print(f"   [Telegram poll] {e}")
            await asyncio.sleep(5)

    # Auto-skip anything not decided
    for draft in drafts:
        if draft["id"] not in decided:
            update_draft_status(draft["id"], "skipped")

    return approved_ids


# ── Main approval run ─────────────────────────────────────────────

def run() -> list:
    """
    Send all pending drafts to Telegram in batches of 5.
    Returns list of approved draft IDs.
    """
    print("\n📱 Running Telegram approval gate...")
    drafts = get_pending_drafts()

    if not drafts:
        print("   No pending drafts to review")
        return []

    print(f"   {len(drafts)} drafts to review")

    approved = []
    # Process in batches of 5
    for i in range(0, len(drafts), 5):
        batch = list(drafts[i:i+5])
        print(f"\n   Sending batch {i//5 + 1} ({len(batch)} drafts)...")
        batch_approved = asyncio.run(send_batch_for_approval(batch))
        approved.extend(batch_approved)
        if i + 5 < len(drafts):
            print("   Waiting 30s before next batch...")
            time.sleep(30)

    print(f"\n✅ Approval complete: {len(approved)}/{len(drafts)} approved")
    return approved


if __name__ == "__main__":
    approved = run()
    print(f"Approved draft IDs: {approved}")
