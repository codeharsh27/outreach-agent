"""
Telegram approval gate — email only.
Streams pending draft cards to your phone with inline buttons:
  [✅ Approve & Send Email]  [✏️ Edit Email]  [❌ Skip Draft]

LinkedIn and X sections removed — this agent handles email only.
"""
import asyncio
import html
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from agents.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from agents.tracker import (
    get_pending_drafts, update_draft_status,
    update_draft_body, get_draft_by_id, _sb,
)


# ── Format a draft card for Telegram (email only) ─────────────────

def format_draft_message(draft: dict) -> str:
    """Format a draft into a clean Telegram message — email section only."""
    company = html.escape(str(draft.get("company_name", "Unknown")))
    contact = html.escape(str(draft.get("contact_name", "Unknown")))
    email   = html.escape(str(draft.get("email", "")))
    domain  = html.escape(str(draft.get("domain", "")))
    subject = html.escape(str(draft.get("email_subject", "")))
    body    = html.escape(str(draft.get("email_body", "")))

    header = f"🏢 <b>{company}</b>  ·  {contact}\n📧 {email}"
    if domain:
        header += f"  ·  {domain}"

    return "\n".join([
        header,
        "",
        "━━━━━━ <b>EMAIL DRAFT</b> ━━━━━━",
        f"<b>Subject:</b> {subject}",
        "",
        body,
    ])


def approval_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve & Send Email", callback_data=f"approve:{draft_id}"),
            InlineKeyboardButton("✏️ Edit Email",          callback_data=f"edit:{draft_id}"),
        ],
        [
            InlineKeyboardButton("❌ Skip Draft", callback_data=f"skip:{draft_id}"),
        ],
    ])


# ── Stream all pending cards to Telegram ─────────────────────────

async def push_all_drafts_to_telegram():
    """Push ALL pending draft cards to Telegram in one smooth stream."""
    bot    = Bot(token=TELEGRAM_BOT_TOKEN)
    drafts = get_pending_drafts(limit=50)

    if not drafts:
        print("   No pending drafts to push to Telegram.")
        return []

    print(f"   Pushing {len(drafts)} drafts to Telegram app...")
    await bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=(
            f"🌅 <b>Good morning! {len(drafts)} outreach drafts ready for review.</b>\n"
            f"Tap <b>[✅ Approve]</b> to queue email, <b>[✏️ Edit]</b> to customize, or <b>[❌ Skip]</b>."
        ),
        parse_mode="HTML",
    )

    sent_count = 0
    for draft in drafts:
        draft    = dict(draft)
        draft_id = draft["id"]
        try:
            msg = await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=format_draft_message(draft),
                parse_mode="HTML",
                reply_markup=approval_keyboard(draft_id),
                disable_web_page_preview=True,
            )
            update_draft_status(draft_id, "pending", str(msg.message_id))
            sent_count += 1
            await asyncio.sleep(0.4)  # Smooth rate-limited stream
        except Exception as e:
            print(f"   [Telegram push ({draft.get('company_name', '')})] Error: {e}")

    print(f"✅ Pushed {sent_count} draft cards to Telegram!")
    return drafts


# ── Callback handlers (Approve / Edit / Skip) ─────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button taps: approve, edit, skip."""
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
            text="✅ <b>Approved!</b> Queued for timezone-aware Gmail dispatch.",
            parse_mode="HTML",
        )

    elif action == "skip":
        update_draft_status(draft_id, "skipped")
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ Draft skipped.",
            parse_mode="HTML",
        )

    elif action == "edit":
        context.user_data["editing_draft_id"] = draft_id
        context.user_data["editing_msg_id"]   = query.message.message_id
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"✏️ <b>Editing Draft #{draft_id}</b>\nReply with your updated email text:",
            parse_mode="HTML",
        )


async def handle_edit_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text reply when user provides edited email body."""
    draft_id    = context.user_data.get("editing_draft_id")
    orig_msg_id = context.user_data.get("editing_msg_id")

    if not draft_id or not update.message or not update.message.text:
        return

    new_text = update.message.text.strip()
    update_draft_body(draft_id, new_text)

    # Refresh the original card with updated body
    updated = get_draft_by_id(draft_id)
    if updated and orig_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=update.message.chat_id,
                message_id=orig_msg_id,
                text=format_draft_message(updated),
                parse_mode="HTML",
                reply_markup=approval_keyboard(draft_id),
                disable_web_page_preview=True,
            )
        except Exception as e:
            print(f"   [Edit refresh] {e}")

    await update.message.reply_text(
        "✅ Draft updated! Tap [✅ Approve & Send Email] on the card above."
    )
    context.user_data.clear()


# ── Main approval run ─────────────────────────────────────────────

def run() -> list:
    """Push all pending draft cards to Telegram immediately."""
    print("\n📱 Running Telegram approval push...")
    asyncio.run(push_all_drafts_to_telegram())

    # Return approved draft IDs ready to send
    try:
        res = _sb().table("drafts").select("id").eq("status", "approved").execute()
        return [r["id"] for r in (res.data or [])]
    except Exception:
        return []


if __name__ == "__main__":
    approved = run()
    print(f"Approved draft IDs: {approved}")
