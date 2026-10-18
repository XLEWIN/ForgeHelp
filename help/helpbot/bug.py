"""``/bug`` — one-tap bug reports to the developers' group chat.

Flow:

1. A player sends ``/bug <text>`` (or replies to a message with it).
2. A **card** lands in ``BUG_REPORT_CHAT_ID``: reporter link, id, chat
   type, time, the escaped report in a blockquote — plus two buttons:
   **Send reply** / **Dismiss**.
3. A developer *replies* to that card (text or media — it is stored,
   not forwarded yet) and taps **Send reply**.
4. The stored reply is delivered to the reporting user as a message
   from **Developers of Forge**, replying to their original /bug
   message. **Dismiss** closes the card instead.

Pending reports + stored replies persist in a small JSON file under
``LOG_DIR`` so they survive restarts (Railway redeploys included).
"""

from __future__ import annotations

import html
import json
import logging
import time
from typing import Optional

from telegram import Update
from telegram.constants import ChatType
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

from . import config
from .emojis import E
from .rich import (DANGER, SUCCESS, colored_kb_dict, edit_message_html,
                   send_text)

LOGGER = logging.getLogger(__name__)

#: Where pending reports + stored replies live between restarts.
STATE = config.LOG_DIR / "bug_reports.json"
#: Keep at most this many reports (oldest dropped first).
_MAX_REPORTS = 200

_reports: dict[str, dict] = {}    # "gc:card_mid" → report
_replies: dict[str, dict] = {}    # "gc:card_mid" → last dev reply
_seq = 0                          # report counter (survives via _save)
_loaded = False


def _fmt_ts(ts: float) -> str:
    """Wall-clock in the bot's fixed UTC+5:30 offset."""
    when = time.gmtime(ts + 5.5 * 3600)
    return time.strftime("%d %b %Y, %H:%M", when) + " UTC+5:30"


def _load() -> None:
    global _seq
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    except Exception:                             # noqa: BLE001 — start fresh
        LOGGER.debug("bug state unreadable; starting fresh", exc_info=True)
        return
    _reports.update({k: v for k, v in (data.get("reports") or {}).items()
                     if isinstance(k, str) and isinstance(v, dict)})
    _replies.update({k: v for k, v in (data.get("replies") or {}).items()
                     if isinstance(k, str) and isinstance(v, dict)})
    try:
        _seq = max(_seq, int(data.get("seq") or 0))
    except (TypeError, ValueError):
        pass


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    _load()


def _save() -> None:
    """Atomic write; prunes the oldest reports beyond _MAX_REPORTS."""
    global _seq
    while len(_reports) > _MAX_REPORTS:
        oldest = min(_reports, key=lambda k: _reports[k].get("ts") or 0)
        _reports.pop(oldest, None)
        _replies.pop(oldest, None)
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"reports": _reports, "replies": _replies, "seq": _seq},
                       ensure_ascii=False),
            encoding="utf-8")
        tmp.replace(STATE)
    except OSError:
        LOGGER.debug("could not persist bug state", exc_info=True)


def _card_html(seq: int, name: str, uid: int, chat_kind: str,
               ts: float, body: str) -> str:
    """The GC card (classic HTML — every user string escaped)."""
    text = html.escape(body)
    return (
        f"{E.CROSS} <b>Bug report #{seq}</b>\n"
        f"━━━━━━━━━━━━\n"
        f"{E.USER} <b>{html.escape(name or 'Unknown trainer')}</b> · "
        f"id <code>{uid}</code> · {html.escape(chat_kind)}\n"
        f"{E.CHAT} {_fmt_ts(ts)}\n\n"
        f"<blockquote>{text}</blockquote>\n\n"
        f"<i>Reply to this message with your answer, then tap "
        f"<b>Send reply</b>. Tap <b>Dismiss</b> to close it.</i>"
    )


def _rows(uid: int, orig_mid: int) -> list[list[tuple]]:
    return [[
        ("Send reply", f"bug|send|{uid}|{orig_mid}", SUCCESS, "chat"),
        ("Dismiss", f"bug|drop|{uid}|{orig_mid}", DANGER, "cross"),
    ]]


def _done_html(report: Optional[dict], base_html: str, footer: str) -> str:
    return (report.get("html") if report else base_html) + f"\n\n{footer}"


def is_bug_card_reply(message) -> bool:
    """True when *message* replies to one of our bug cards.

    Used to keep the group AI quiet on those replies (the dedicated
    reply handler stores them instead).
    """
    if message is None or not config.BUG_REPORT_CHAT_ID:
        return False
    target = message.reply_to_message
    if target is None:
        return False
    _ensure_loaded()
    return f"{message.chat_id}:{target.message_id}" in _reports


async def cmd_bug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """``/bug <text>`` (or as a reply) → report card in the dev group."""
    if not config.BUG_REPORT_CHAT_ID:
        return                              # no dev group configured
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if message is None or chat is None:
        return

    body = " ".join(context.args).strip()
    if not body and message.reply_to_message is not None:
        quoted = (message.reply_to_message.text
                  or message.reply_to_message.caption or "").strip()
        body = quoted
    if not body:
        await message.reply_html(
            f"{E.CHAT} <b>Report a bug to the Developers of Forge</b>\n\n"
            f"Usage: <code>/bug what went wrong</code>\n"
            f"…or reply to a message with <code>/bug</code> to include it.")
        return
    body = body[:1500]

    name = (user.full_name if user else "") or "Unknown trainer"
    uid = user.id if user else 0
    dm = chat.id if chat.type == ChatType.PRIVATE else uid
    kind = "private" if chat.type == ChatType.PRIVATE else str(chat.type)

    _ensure_loaded()
    global _seq
    _seq += 1
    seq = _seq
    card = _card_html(seq, name, uid, kind, time.time(), body)

    sent = await send_text(context.bot, config.BUG_REPORT_CHAT_ID, card,
                           reply_markup=colored_kb_dict(
                               _rows(uid, message.message_id)))
    if not sent or "message_id" not in sent:
        await message.reply_html(
            f"{E.CROSS} I couldn't reach the Developers right now — "
            f"please try again in a moment.")
        LOGGER.warning("bug card delivery failed (seq %s)", seq)
        return

    key = f"{config.BUG_REPORT_CHAT_ID}:{sent['message_id']}"
    _reports[key] = {
        "uid": uid, "dm": dm, "orig_mid": message.message_id,
        "name": name, "kind": kind, "ts": time.time(), "seq": seq,
        "html": card, "done": False,
    }
    _save()
    await message.reply_html(
        f"{E.CHECK} <b>Bug report #{seq} delivered.</b>\n"
        f"The Developers of Forge will reply to you here.")


async def on_bug_reply(update: Update,
                       context: ContextTypes.DEFAULT_TYPE) -> None:
    """Store a developer's reply to a bug card until Send is tapped."""
    message = update.effective_message
    if message is None or message.reply_to_message is None:
        return
    if message.from_user and message.from_user.is_bot:
        return
    _ensure_loaded()
    key = f"{message.chat_id}:{message.reply_to_message.message_id}"
    if key not in _reports:
        return                              # not (or no longer) a bug card

    text = (message.text or message.caption or "").strip()
    has_media = bool(message.photo or message.video or message.document
                     or message.audio or message.voice or message.sticker
                     or message.video_note)
    if not text and not has_media:
        return
    _replies[key] = {
        "mid": message.message_id,
        "text": text[:3500],
        "media": not bool(text),
        "from": (message.from_user.full_name if message.from_user else "?"),
        "ts": time.time(),
    }
    _save()
    try:
        await message.reply_html(
            f"{E.CHECK} Reply stored — tap <b>Send reply</b> on the report "
            f"card to deliver it to the trainer.")
    except TelegramError:
        LOGGER.debug("could not confirm stored reply", exc_info=True)


async def _send_dm(bot, chat_id: int, text: str, reply_to: int):
    """Deliver to the reporter, replying to their original /bug message.

    Falls back to a standalone message when that message is gone.
    """
    try:
        return await bot.send_message(
            chat_id, text, parse_mode="HTML",
            reply_parameters={"message_id": reply_to})
    except BadRequest:
        return await bot.send_message(chat_id, text, parse_mode="HTML")


async def on_bug_button(update: Update,
                        context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send reply / Dismiss on a bug card."""
    query = update.callback_query
    if query is None:
        return
    data = (query.data or "").split("|")
    action = data[1] if len(data) > 1 else ""
    try:
        uid = int(data[2]) if len(data) > 2 else 0
        orig = int(data[3]) if len(data) > 3 else 0
    except ValueError:
        uid = orig = 0
    msg = query.message
    if msg is None:
        await query.answer()
        return

    _ensure_loaded()
    key = f"{msg.chat_id}:{msg.message_id}"
    report = _reports.get(key)
    who = html.escape(query.from_user.full_name if query.from_user else "?")

    if action == "drop":
        await query.answer("Dismissed.")
        footer = f"{E.CROSS} Dismissed by {who} · {_fmt_ts(time.time())}"
        await edit_message_html(context.bot, msg.chat_id, msg.message_id,
                                _done_html(report, msg.text or "", footer),
                                reply_markup={"inline_keyboard": []})
        if report:
            report["done"] = True
            _replies.pop(key, None)
            _save()
        return

    if action != "send":
        await query.answer()
        return

    reply = _replies.get(key)
    if not reply:
        await query.answer(
            "Reply to this report first, then tap Send reply.",
            show_alert=True)
        return
    if report and report.get("done"):
        await query.answer("This report was already handled.",
                           show_alert=True)
        return

    dm = (report or {}).get("dm") or uid
    orig_mid = (report or {}).get("orig_mid") or orig
    header = f"{E.CHAT} <b>Developers of Forge</b>\n\n"
    try:
        if reply.get("text"):
            await _send_dm(context.bot, dm, header + reply["text"], orig_mid)
        else:
            head = await _send_dm(
                context.bot, dm,
                header + "A Developer replied to your bug report:", orig_mid)
            head_id = head["message_id"] if isinstance(head, dict) else None
            kwargs = ({"reply_parameters": {"message_id": head_id}}
                      if head_id else {})
            await context.bot.copy_message(
                chat_id=dm, from_chat_id=msg.chat_id,
                message_id=reply["mid"], **kwargs)
    except TelegramError as exc:
        LOGGER.warning("bug reply delivery failed (dm=%s): %s", dm, exc)
        await query.answer(f"Delivery failed: {str(exc)[:90]}",
                           show_alert=True)
        return

    name = html.escape((report or {}).get("name") or "the reporter")
    if report:
        report["done"] = True
        _replies.pop(key, None)
        _save()
    footer = f"{E.CHECK} Reply delivered to {name} · {_fmt_ts(time.time())}"
    await edit_message_html(context.bot, msg.chat_id, msg.message_id,
                            _done_html(report, msg.text or "", footer),
                            reply_markup={"inline_keyboard": []})
    await query.answer("Delivered to the reporter.")
