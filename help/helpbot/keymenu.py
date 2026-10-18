"""``/keymenu`` — owner-only AI key inventory.

Shows every configured key (masked), its health (healthy / cooling /
failing / untested), usage counters and the failover order, with
**Refresh** and **Test all keys** buttons. Only users listed in
``OWNER_IDS`` can open it; everyone else is ignored silently.
"""

from __future__ import annotations

import html
import logging
import time

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from . import config, keyvault
from .emojis import E, ui_tag
from .rich import PRIMARY, SUCCESS, colored_kb_dict, edit_message_html, \
    send_text

LOGGER = logging.getLogger(__name__)

#: Callback prefix — data looks like ``km|refresh`` / ``km|test``.
CB = "km"

_STATE_TAG = {
    "healthy": E.CHECK,
    "cooling": E.WARN,
    "failing": E.CROSS,
    "new": E.SPARKLE,
}
_STATE_WORD = {
    "healthy": "healthy",
    "cooling": "cooling down",
    "failing": "failing",
    "new": "untested",
}


def _is_owner(user) -> bool:
    return bool(user) and user.id in config.OWNER_IDS


def _ago(ts: float) -> str:
    if not ts:
        return "never"
    dt = int(time.time() - ts)
    if dt < 5:
        return "just now"
    if dt < 60:
        return f"{dt}s ago"
    if dt < 3600:
        return f"{dt // 60}m ago"
    if dt < 86400:
        return f"{dt // 3600}h ago"
    return f"{dt // 86400}d ago"


def _rows() -> list[list[tuple]]:
    return [[
        ("Refresh", f"{CB}|refresh", PRIMARY, "rocket"),
        ("Test all keys", f"{CB}|test", SUCCESS, "bolt"),
    ]]


def render() -> str:
    """Classic HTML body — one block per key, masked, in failover order."""
    snap = keyvault.snapshot()
    if not snap:
        return (
            f"{ui_tag('sparkle')} <b>AI key menu</b>\n"
            f"━━━━━━━━━━━━\n"
            f"{E.WARN} No keys configured — set "
            f"<code>OPENROUTER_API_KEYS</code> in settings.py."
        )
    lines = [
        f"{ui_tag('sparkle')} <b>AI key menu</b> — {len(snap)} keys",
        "━━━━━━━━━━━━",
        "",
    ]
    for i, k in enumerate(snap, 1):
        tag = _STATE_TAG.get(k["state"], E.SPARKLE)
        word = _STATE_WORD.get(k["state"], k["state"])
        detail = ""
        if k["state"] == "cooling":
            detail = f" · retry in {int(k['cooldown_left'])}s"
        elif k["state"] == "failing" and k["last_error"]:
            detail = f" · {html.escape(k['last_error'][:70])}"
        lines.append(
            f"{i}. {tag} <b>{html.escape(k['label'])}</b> "
            f"<code>{html.escape(k['masked'])}</code> — {word}{detail}")
        lines.append(
            f"   <code>{html.escape(k['model'])}</code> · {k['uses']} uses · "
            f"{k['ok']} ok · {k['fail']} fail · last {_ago(k['last_used'])}")
    order = " → ".join(str(i) for i in range(1, len(snap) + 1))
    lines += [
        "",
        f"<i>Failover {order}: on failure the next key takes over — "
        f"429 pauses a key 60s, auth errors 5 min.</i>",
    ]
    return "\n".join(lines)


async def cmd_keymenu(update: Update,
                      context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only status card. Silent for everyone else."""
    user = update.effective_user
    message = update.effective_message
    if message is None or not _is_owner(user):
        return
    sent = await send_text(context.bot, message.chat_id, render(),
                           reply_markup=colored_kb_dict(_rows()),
                           reply_to=message.message_id)
    if sent is None:
        LOGGER.warning("keymenu delivery failed (user %s)",
                       user.id if user else "?")


async def on_keymenu_button(update: Update,
                            context: ContextTypes.DEFAULT_TYPE) -> None:
    """Refresh the view / ping every key (owner only)."""
    query = update.callback_query
    if query is None:
        return
    if not _is_owner(query.from_user):
        await query.answer("Owner only.", show_alert=True)
        return
    msg = query.message
    if msg is None:
        await query.answer()
        return

    action = (query.data or "").split("|", 1)[-1]
    if action == "refresh":
        await query.answer("Refreshed.")
        await edit_message_html(context.bot, msg.chat_id, msg.message_id,
                                render(),
                                reply_markup=colored_kb_dict(_rows()))
        return
    if action == "test":
        await query.answer("Testing every key…")
        results = await keyvault.test_all()
        bad = [(k.label, err) for k, ok, err in results if not ok]
        await edit_message_html(context.bot, msg.chat_id, msg.message_id,
                                render(),
                                reply_markup=colored_kb_dict(_rows()))
        summary = (f"{E.CHECK} Tested {len(results)} keys — "
                   f"{len(results) - len(bad)} ok, {len(bad)} failing.")
        if bad:
            summary += "\n" + "\n".join(
                f"{E.CROSS} {html.escape(label)}: "
                f"<code>{html.escape((err or '')[:80])}</code>"
                for label, err in bad[:5])
        try:
            await context.bot.send_message(
                msg.chat_id, summary, parse_mode="HTML")
        except TelegramError:
            LOGGER.debug("keymenu test summary not delivered",
                         exc_info=True)
        return
    await query.answer()
