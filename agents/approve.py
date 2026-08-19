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


import html

# ── Format a draft message for Telegram ──────────────────────────

def format_draft_message(draft: dict) -> str:
    """Format a draft into a readable Telegram message with separated sections."""
    company = html.escape(str(draft.get("company_name", "Unknown")))
    contact = html.escape(str(draft.get("contact_name", "Unknown")))
    email = html.escape(str(draft.get("email", "")))
    domain = html.escape(str(draft.get("domain", "")))
    subject = html.escape(str(draft.get("email_subject", "")))
    body = html.escape(str(draft.get("email_body", "")))
    linkedin = html.escape(str(draft.get("linkedin_msg", "")))
    x_reply = html.escape(str(draft.get("x_reply_text", "")))
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
    """Inline keyboard: Approve / Edit / Skip."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve & Send Email", callback_data=f"approve:{draft_id}"),
            InlineKeyboardButton("✏️ Edit Email", callback_data=f"edit:{draft_id}"),
        ],
        [
            InlineKeyboardButton("❌ Skip Draft", callback_data=f"skip:{draft_id}")
        ]
    ])


# ── Interactive Telegram Edit & Approval Handler ────────────────

async def push_all_drafts_to_telegram():
    """
    Push ALL pending draft cards to Telegram chat in one smooth stream.
    Adds inline buttons [✅ Approve], [✏️ Edit], [❌ Skip] to every card.
    """
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    drafts = get_pending_drafts(limit=50)

    if not drafts:
        print("   No pending drafts to push to Telegram.")
        return []

    print(f"   Pushing {len(drafts)} drafts to Telegram app...")
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=f"🌅 <b>Good morning! {len(drafts)} outreach drafts ready for review</b>\nTap <b>[✅ Approve]</b> to queue email, <b>[✏️ Edit]</b> to customize, or <b>[❌ Skip]</b>.",
        parse_mode="HTML"
    )

    sent_count = 0
    for draft in drafts:
        draft = dict(draft)
        draft_id = draft["id"]
        msg_text = format_draft_message(draft)

        try:
            msg = await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=msg_text,
                parse_mode="HTML",
                reply_markup=approval_keyboard(draft_id),
                disable_web_page_preview=True,
            )
            update_draft_status(draft_id, "pending", str(msg.message_id))
            sent_count += 1
            await asyncio.sleep(0.4)  # Smooth rate-limited stream
        except Exception as e:
            print(f"   [Telegram push ({draft.get('company_name')})] Error: {e}")

    print(f"✅ Pushed {sent_count} draft cards to Telegram!")
    return drafts


# ── Interactive Callback & Text Handler for Editing ──────────────

def update_draft_body(draft_id: int, new_body: str):
    """Update email_body for a draft in the database."""
    conn = sqlite3.connect(str(TRACKER_DB))
    try:
        conn.execute("UPDATE drafts SET email_body=? WHERE id=?", (new_body, draft_id))
        conn.commit()
    finally:
        conn.close()


def get_draft_by_id(draft_id: int) -> dict | None:
    """Fetch single draft by ID with company and contact info."""
    conn = sqlite3.connect(str(TRACKER_DB))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("""
            SELECT d.*, co.name as company_name, co.domain,
                   ct.name as contact_name, ct.email, ct.linkedin_url, ct.twitter_url
            FROM drafts d
            JOIN companies co ON co.id = d.company_id
            JOIN contacts  ct ON ct.id = d.contact_id
            WHERE d.id = ?
        """, (draft_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks: approve, edit, skip."""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if ":" not in data:
        return
    action, draft_id_str = data.split(":", 1)
    draft_id = int(draft_id_str)

    if action == "approve":
        update_draft_status(draft_id, "approved")
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"✅ <b>Approved!</b> Queued for timezone-aware Gmail dispatch.",
            parse_mode="HTML"
        )
    elif action == "skip":
        update_draft_status(draft_id, "skipped")
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"❌ Draft skipped.",
            parse_mode="HTML"
        )
    elif action == "edit":
        # Store draft ID in user_data for editing
        context.user_data["editing_draft_id"] = draft_id
        context.user_data["editing_msg_id"] = query.message.message_id
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"✏️ <b>Editing Draft #{draft_id}</b>\nPlease reply to this message with your new email text:",
            parse_mode="HTML"
        )


async def handle_edit_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text reply when user provides edited email text."""
    draft_id = context.user_data.get("editing_draft_id")
    orig_msg_id = context.user_data.get("editing_msg_id")

    if not draft_id or not update.message or not update.message.text:
        return

    new_text = update.message.text.strip()
    update_draft_body(draft_id, new_text)

    # Fetch updated draft and update original card
    updated_draft = get_draft_by_id(draft_id)
    if updated_draft and orig_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=update.message.chat_id,
                message_id=orig_msg_id,
                text=format_draft_message(updated_draft),
                parse_mode="HTML",
                reply_markup=approval_keyboard(draft_id),
                disable_web_page_preview=True,
            )
        except Exception as e:
            print(f"Edit update error: {e}")

    await update.message.reply_text("✅ Draft updated! Review card above and tap [✅ Approve & Send Email].")
    context.user_data.clear()


# ── Main approval run ─────────────────────────────────────────────

def run() -> list:
    """Push all draft cards to Telegram immediately."""
    print("\n📱 Running Telegram approval push...")
    asyncio.run(push_all_drafts_to_telegram())

    # Return list of currently approved draft IDs ready to send
    conn = sqlite3.connect(str(TRACKER_DB))
    approved_ids = [r[0] for r in conn.execute("SELECT id FROM drafts WHERE status='approved'").fetchall()]
    conn.close()
    return approved_ids


if __name__ == "__main__":
    approved = run()
    print(f"Approved draft IDs: {approved}")
