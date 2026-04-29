"""Telegram approval bot for the review queue.

Pushes new `pending` drafts to an approver chat with inline buttons:

    [✅ Approve & publish]  [👍 Approve]  [❌ Reject]
    [✏️ Quick edit]         [💬 Discuss with AI]

"Quick edit" prompts the approver for a replacement body (next text message).
"Discuss with AI" starts a free-form conversation: the approver describes the
change in natural language ("make it shorter", "add a stat about latency",
"drop the hashtag #Nemotron") and the LLM returns a proposed revision, which
the approver can then Apply or Discard.

Security / trust model
----------------------
- Only chat ids listed in TELEGRAM_APPROVER_CHAT_IDS can do anything. For group
    chats, also set TELEGRAM_APPROVER_USER_IDS so approval actions require a
    known Telegram user id. Others are ignored.
- Approver messages are treated as UNTRUSTED input to the LLM (wrapped in a
  guarded system prompt) — they direct content, they do NOT override system
  rules.
- Publish still goes through `publish_draft`, which respects DRY_RUN.
"""

from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import approver_chat_ids, approver_user_ids, settings
from .generator import ContentGenerator
from .models import GeneratedPost
from .pipeline import publish_draft
from .review import DraftRecord, ReviewStore

logger = logging.getLogger(__name__)

# user_data keys
MODE_KEY = "mode"            # "quick_edit" | "discuss" | None
DRAFT_KEY = "draft_id"
PROPOSAL_KEY = "proposal"    # GeneratedPost pending approval

POLL_INTERVAL = 10  # fallback if settings.telegram_poll_seconds is invalid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_approver(update: Update) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if not _is_approved_actor(
        chat_id=chat.id if chat else None,
        user_id=user.id if user else None,
        chat_type=getattr(chat, "type", None),
        allowed_chat_ids=approver_chat_ids(),
        allowed_user_ids=approver_user_ids(),
    ):
        logger.warning(
            "Ignoring message from non-approver chat/user %s/%s",
            chat.id if chat else None,
            user.id if user else None,
        )
        return False
    return True


def _is_approved_actor(
    *,
    chat_id: int | None,
    user_id: int | None,
    chat_type: str | None,
    allowed_chat_ids: set[int],
    allowed_user_ids: set[int],
) -> bool:
    if chat_id is None or chat_id not in allowed_chat_ids:
        return False
    if allowed_user_ids:
        return user_id in allowed_user_ids
    return chat_type == "private"


def _draft_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Approve & publish", callback_data=f"ap:{draft_id}"),
                InlineKeyboardButton("👍 Approve", callback_data=f"a:{draft_id}"),
            ],
            [
                InlineKeyboardButton("❌ Reject", callback_data=f"r:{draft_id}"),
                InlineKeyboardButton("✏️ Quick edit", callback_data=f"e:{draft_id}"),
                InlineKeyboardButton("💬 Discuss with AI", callback_data=f"d:{draft_id}"),
            ],
        ]
    )


def _proposal_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Apply revision", callback_data=f"pa:{draft_id}"),
                InlineKeyboardButton("🔁 Keep chatting", callback_data=f"pk:{draft_id}"),
                InlineKeyboardButton("🗑 Discard", callback_data=f"pd:{draft_id}"),
            ]
        ]
    )


def _render_draft(draft: DraftRecord) -> str:
    tags = " ".join(f"#{t.lstrip('#')}" for t in draft.hashtags)
    body = draft.text + ("\n\n" + tags if tags else "")
    image_line = f"\n<i>📷 {html.escape(draft.image_prompt)}</i>" if draft.image_prompt else ""
    return (
        f"<b>{html.escape(draft.platform.upper())}</b> · <code>{draft.id}</code> · "
        f"<i>{draft.status}</i>\n"
        f"<b>Topic:</b> {html.escape(draft.brief.topic)}\n\n"
        f"<pre>{html.escape(body)}</pre>"
        f"{image_line}"
    )


def _render_proposal(current: DraftRecord, proposed: GeneratedPost) -> str:
    tags = " ".join(f"#{t.lstrip('#')}" for t in proposed.hashtags)
    body = proposed.text + ("\n\n" + tags if tags else "")
    return (
        f"<b>Proposed revision for <code>{current.id}</code> ({current.platform})</b>\n\n"
        f"<pre>{html.escape(body)}</pre>\n"
        f"<i>Apply to replace the draft, or keep chatting to iterate.</i>"
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else None
    user_id = update.effective_user.id if update.effective_user else None
    if not _require_approver(update):
        await update.message.reply_text(
            f"This is a private approval bot. Your chat id is <code>{chat_id}</code> "
            f"and your user id is <code>{user_id}</code>. Add the chat id to "
            "TELEGRAM_APPROVER_CHAT_IDS and, for group chats, the user id to "
            "TELEGRAM_APPROVER_USER_IDS.",
            parse_mode=ParseMode.HTML,
        )
        return
    await update.message.reply_text(
        "Ready. New drafts will appear here. Commands:\n"
        "/pending — list pending drafts\n"
        "/show <id> — show one draft\n"
        "/cancel — exit edit/chat mode",
    )


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_approver(update):
        return
    drafts = ReviewStore().list(status="pending", limit=10)
    if not drafts:
        await update.message.reply_text("No pending drafts.")
        return
    for d in drafts:
        await update.message.reply_html(
            _render_draft(d),
            reply_markup=_draft_keyboard(d.id),
        )


async def cmd_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_approver(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /show <draft_id>")
        return
    try:
        d = ReviewStore().get(context.args[0])
    except KeyError:
        await update.message.reply_text("No such draft.")
        return
    await update.message.reply_html(_render_draft(d), reply_markup=_draft_keyboard(d.id))


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_approver(update):
        return
    context.user_data.clear()
    await update.message.reply_text("Exited edit/chat mode.")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not _require_approver(update):
        return
    await query.answer()
    action, _, draft_id = query.data.partition(":")
    store = ReviewStore()
    try:
        draft = store.get(draft_id)
    except KeyError:
        await query.edit_message_text("Draft not found.")
        return

    if action == "a":  # approve
        d = store.approve(draft_id)
        await query.edit_message_text(
            f"👍 Approved <code>{d.id}</code> ({d.platform}). "
            "Publish with: <code>nemo-bot review publish " + d.id + "</code>",
            parse_mode=ParseMode.HTML,
        )
    elif action == "ap":  # approve and publish
        store.approve(draft_id)
        d = publish_draft(draft_id, store)
        if d.status == "published":
            msg = f"✅ Published <code>{d.id}</code>: {html.escape(d.publish_id or '?')}"
        else:
            msg = f"⚠️ Publish failed: {html.escape(d.publish_error or '?')}"
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
    elif action == "r":  # reject
        d = store.reject(draft_id)
        await query.edit_message_text(f"❌ Rejected <code>{d.id}</code>", parse_mode=ParseMode.HTML)
    elif action == "e":  # quick edit
        context.user_data[MODE_KEY] = "quick_edit"
        context.user_data[DRAFT_KEY] = draft_id
        await query.message.reply_text(
            f"✏️ Send the replacement body for {draft_id}. "
            "Hashtags and image_prompt stay as-is. /cancel to abort."
        )
    elif action == "d":  # discuss
        context.user_data[MODE_KEY] = "discuss"
        context.user_data[DRAFT_KEY] = draft_id
        context.user_data.pop(PROPOSAL_KEY, None)
        await query.message.reply_text(
            f"💬 Let's refine {draft_id}. Describe the change — e.g. "
            "\"shorter and add a latency stat\" or \"drop the #Nemotron hashtag\". "
            "I'll propose a revision. /cancel to abort."
        )
    elif action == "pa":  # proposal apply
        proposed: GeneratedPost | None = context.user_data.get(PROPOSAL_KEY)
        if not proposed or context.user_data.get(DRAFT_KEY) != draft_id:
            await query.edit_message_text("No active proposal for this draft.")
            return
        store.edit(
            draft_id,
            text=proposed.text,
            hashtags=proposed.hashtags,
            image_prompt=proposed.image_prompt,
        )
        context.user_data.clear()
        updated = store.get(draft_id)
        await query.edit_message_text(
            "✅ Revision applied.\n\n" + _render_draft(updated),
            parse_mode=ParseMode.HTML,
            reply_markup=_draft_keyboard(draft_id),
        )
    elif action == "pk":  # keep chatting
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "Continue — describe the next change. /cancel to stop.",
        )
    elif action == "pd":  # discard proposal
        context.user_data.pop(PROPOSAL_KEY, None)
        context.user_data.pop(MODE_KEY, None)
        await query.edit_message_text("🗑 Proposal discarded.")
    else:
        logger.warning("Unknown callback action: %s", action)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_approver(update):
        return
    mode = context.user_data.get(MODE_KEY)
    draft_id = context.user_data.get(DRAFT_KEY)
    text = update.message.text or ""
    if not mode or not draft_id:
        await update.message.reply_text(
            "Nothing to do. Use /pending to see drafts, or tap a button on a draft first."
        )
        return

    store = ReviewStore()
    try:
        draft = store.get(draft_id)
    except KeyError:
        context.user_data.clear()
        await update.message.reply_text("Draft disappeared.")
        return

    if mode == "quick_edit":
        if draft.status != "pending":
            await update.message.reply_text(f"Draft is {draft.status}, can't edit.")
            context.user_data.clear()
            return
        store.edit(draft_id, text=text)
        context.user_data.clear()
        updated = store.get(draft_id)
        await update.message.reply_html(
            "✏️ Updated.\n\n" + _render_draft(updated),
            reply_markup=_draft_keyboard(draft_id),
        )
        return

    if mode == "discuss":
        await update.message.chat.send_action("typing")
        try:
            proposed = await asyncio.to_thread(
                ContentGenerator().revise, draft.brief, draft.to_post(), text
            )
        except Exception as err:  # noqa: BLE001
            logger.exception("revise failed: %s", err)
            await update.message.reply_text(f"⚠️ Revision failed: {err}")
            return
        context.user_data[PROPOSAL_KEY] = proposed
        await update.message.reply_html(
            _render_proposal(draft, proposed),
            reply_markup=_proposal_keyboard(draft_id),
        )
        return


# ---------------------------------------------------------------------------
# New-draft poller
# ---------------------------------------------------------------------------


@dataclass
class NotifierConfig:
    interval_seconds: int


async def _poll_new_drafts(app: Application, cfg: NotifierConfig) -> None:
    """Background task: push each unnotified pending draft to every approver chat."""
    store = ReviewStore()
    chat_ids = approver_chat_ids()
    if not chat_ids:
        logger.warning("No approver chat ids configured; nothing will be pushed.")
        return
    while True:
        try:
            drafts = store.list_unnotified_pending(limit=20)
            for d in drafts:
                for chat_id in chat_ids:
                    try:
                        msg = await app.bot.send_message(
                            chat_id=chat_id,
                            text=_render_draft(d),
                            parse_mode=ParseMode.HTML,
                            reply_markup=_draft_keyboard(d.id),
                        )
                        store.mark_notified(d.id, f"{chat_id}:{msg.message_id}")
                    except Exception as err:  # noqa: BLE001
                        logger.exception("Failed to notify chat %s: %s", chat_id, err)
        except Exception as err:  # noqa: BLE001
            logger.exception("Poll loop error: %s", err)
        await asyncio.sleep(cfg.interval_seconds)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def run_telegram_bot() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    approvers = approver_chat_ids()
    if not approvers:
        logger.warning(
            "TELEGRAM_APPROVER_CHAT_IDS is empty. Bot will start in BOOTSTRAP mode: "
            "send /start from Telegram to get your chat id, then add it to .env."
        )

    interval = max(3, int(settings.telegram_poll_seconds or POLL_INTERVAL))

    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("show", cmd_show))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    async def _post_init(application: Application) -> None:
        if approvers:
            application.create_task(
                _poll_new_drafts(application, NotifierConfig(interval_seconds=interval))
            )

    app.post_init = _post_init

    logger.info("Telegram approval bot starting (poll=%ds, approvers=%s)", interval, approvers or "<bootstrap>")
    app.run_polling(close_loop=False)
