"""
approve.py — Telegram Approval Gate & Interactive Bot
Fixes applied:
- V3: Telegram callback authentication (ensures effective_user.id matches TELEGRAM_CHAT_ID)
- V6: 4,000-character payload truncation to prevent Telegram 4096-char payload crashes
- V20: Rate-limit sleep (1.1s) per card to prevent Telegram HTTP 429 flood blocks
"""
import asyncio
import html
import os
import sys
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from agents.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from agents.tracker import (
    get_pending_drafts, update_draft_status,
    update_draft_body, get_draft_by_id, _sb,
)


def _verify_user_id(user_id: int | str) -> bool:
    """Fix V3: Ensure callback/message originates strictly from TELEGRAM_CHAT_ID."""
    if not TELEGRAM_CHAT_ID:
        return True
    return str(user_id) == str(TELEGRAM_CHAT_ID)


def format_draft_message(draft: dict) -> str:
    """Fix V6: Format draft card with strict HTML escaping and 4,000-character length truncation."""
    company = html.escape(str(draft.get("company_name", "Unknown")))
    contact = html.escape(str(draft.get("contact_name", "Unknown")))
    email   = html.escape(str(draft.get("email", "")))
    domain  = html.escape(str(draft.get("domain", "")))
    subject = html.escape(str(draft.get("email_subject", "")))
    body    = html.escape(str(draft.get("email_body", "")))

    header = f"🏢 <b>{company}</b>  ·  {contact}\n📧 {email}"
    if domain:
        header += f"  ·  {domain}"

    full_text = "\n".join([
        header,
        "",
        "━━━━━━ <b>EMAIL DRAFT</b> ━━━━━━",
        f"<b>Subject:</b> {subject}",
        "",
        body,
    ])

    # Fix V6: Truncate at 4,000 chars to avoid Telegram 4096-char payload crashes
    if len(full_text) > 4000:
        full_text = full_text[:3950] + "\n\n<i>[...body truncated for length]</i>"

    return full_text


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


async def push_all_drafts_to_telegram():
    """Fix V20: Stream all pending cards to Telegram with 1.1s sleep to respect rate limits."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("   Telegram credentials not configured — skipping push.")
        return []

    bot    = Bot(token=TELEGRAM_BOT_TOKEN)
    drafts = get_pending_drafts(limit=50)

    if not drafts:
        print("   No pending drafts to push to Telegram.")
        return []

    print(f"   Pushing {len(drafts)} drafts to Telegram app...")
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=(
                f"🌅 <b>Good morning! {len(drafts)} outreach drafts ready for review.</b>\n"
                f"Tap <b>[✅ Approve]</b> to queue email, <b>[✏️ Edit]</b> to customize, or <b>[❌ Skip]</b>."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        print(f"   Error sending Telegram header: {e}")

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
            # Fix V20: Sleep 1.1s between messages to avoid Telegram HTTP 429 limit (1 msg/sec)
            await asyncio.sleep(1.1)
        except Exception as e:
            print(f"   [Telegram push ({draft.get('company_name', '')})] Error: {e}")

    print(f"✅ Pushed {sent_count} draft cards to Telegram!")
    return drafts


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fix V3: Authenticated inline callback handler."""
    query = update.callback_query
    await query.answer()

    # Fix V3: Verify sender identity
    if not _verify_user_id(update.effective_user.id):
        print(f"⚠️ Security: Unauthorized callback query from user ID {update.effective_user.id}")
        return

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
    """Fix V3: Authenticated edit reply handler."""
    if not _verify_user_id(update.effective_user.id):
        return

    draft_id    = context.user_data.get("editing_draft_id")
    orig_msg_id = context.user_data.get("editing_msg_id")

    if not draft_id or not update.message or not update.message.text:
        return

    new_text = update.message.text.strip()
    update_draft_body(draft_id, new_text)

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


def run_daemon():
    """Run persistent Telegram polling daemon to listen for edit/approval callbacks."""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN unset.")
        return

    print("🤖 Starting Telegram polling daemon... Press Ctrl+C to exit.")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_reply))
    app.run_polling()


def run() -> list:
    """Push pending drafts to Telegram."""
    print("\n📱 Running Telegram approval push...")
    asyncio.run(push_all_drafts_to_telegram())
    try:
        res = _sb().table("drafts").select("id").eq("status", "approved").execute()
        return [r["id"] for r in (res.data or [])]
    except Exception:
        return []


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "daemon":
        run_daemon()
    else:
        approved = run()
        print(f"Approved draft IDs: {approved}")
