"""Telegram handlers for the Forge help bot.

Behaviour:

* **Private chat** — any non-command text is treated as a question.
* **Groups** — commands, replies to the bot, and messages that
  @mention the bot are answered. Replying to someone's question with
  ``@Professor_OakBot`` answers THAT question (uses the original text).
* Everything is rate-limited per user.

UI: Rich Messages (sendRichMessage) with premium <tg-emoji> pills, the
same pattern as Forge. Classic HTML + inline keyboards are the fallback.
Personality: the AI answers as **Professor Oak** (Pokémon).
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from collections import deque
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import BadRequest, Conflict, Forbidden, TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

from . import ai, build_ui, config, logsetup
from . import pokedex_ui, pokemon
from .ai import Answer, split_message, strip_plain_emoji
from .emojis import E, ui_tag
from .kb import KnowledgeBase
from .rich import (DANGER, LINK, PRIMARY, SUCCESS, classic_html, colored_kb_dict,
                   pill_label, rows_to_kb, rows_to_pills, send_photo_bytes,
                   send_rich_step)

LOGGER = logging.getLogger(__name__)

_kb = KnowledgeBase()
_STATS = {"questions": 0, "ai": 0, "fallback": 0, "offtopic": 0, "errors": 0}
_SEEN: dict[int, deque[float]] = {}
_USERNAME: str | None = None
#: Exit code to use after a graceful in-handler stop (2 = token conflict).
_STOP_CODE: int | None = None

#: Public support contact (shown everywhere instead of the old handle).
SUPPORT_URL = "https://t.me/keczt"
SUPPORT_LABEL = "@keczt"

SEP = "━━━━━━━━━━━━"


# ── rich page builders ───────────────────────────────────────────────────

def _home_rows() -> list[list[tuple]]:
    """Start/home buttons — premium emoji icons + colored styles."""
    return [
        [
            ("Ask Oak", "hp|ask", SUCCESS, "chat"),
            ("Help Menu", "hp|menu", PRIMARY, "gift"),
        ],
        [("Commands", "hp|commands", PRIMARY, "star")],
        [(f"Support {SUPPORT_LABEL}", SUPPORT_URL, LINK, "globe")],
    ]


def _home_kb() -> InlineKeyboardMarkup:
    """Classic fallback — plain labels, zero unicode emoji."""
    rows = [
        [("Ask Oak", "hp|ask"), ("Help Menu", "hp|menu")],
        [("Commands", "hp|commands")],
        [(f"Support {SUPPORT_LABEL}", SUPPORT_URL)],
    ]
    return rows_to_kb(rows)


def _home_kb_dict() -> dict:
    """Raw colored keyboard for /start photo captions."""
    return colored_kb_dict(_home_rows())


def _guide_rows() -> list[list[tuple]]:
    """Guide pills — premium gift emoji in rich labels."""
    rows: list[list[tuple]] = []
    for stem, title, _size in _kb.guides():
        label = re.sub(r"^\d+-", "", stem).replace("-", " ")
        rows.append([(pill_label("gift", title or label.title()), f"hp|{stem}")])
    rows.append([(pill_label("star", "All commands"), "hp|commands")])
    rows.append([
        (pill_label("chat", "Ask Oak"), "hp|ask", SUCCESS),
        (pill_label("cross", "Close"), "hp|close", DANGER),
    ])
    return rows


def _guide_kb() -> InlineKeyboardMarkup:
    rows: list[list[tuple]] = []
    for stem, title, _size in _kb.guides():
        label = re.sub(r"^\d+-", "", stem).replace("-", " ")
        rows.append([(title or label.title(), f"hp|{stem}")])
    rows.append([("All commands", "hp|commands")])
    rows.append([
        ("Ask Oak", "hp|ask"),
        ("Close", "hp|close"),
    ])
    return rows_to_kb(rows)


def rich_start(name: str, username: str = "Professor_OakBot") -> str:
    """Rich /start — premium title, short blurb, action pills (no photo)."""
    display = html.escape(name or "Trainer")
    who = html.escape(username or "Professor_OakBot")
    return (
        f"<p>{ui_tag('fire')} <b>@{who}</b></p>"
        f"<p>I'm the AI study guide for <b>Forge</b> (@PokeForgebot) — "
        f"a Pokémon catching, battling and trading game here on Telegram. "
        f"Ask me anything about commands, shiny odds, regions, breeding "
        f"and more!</p>"
        f"<p>Type your question, or use "
        f"<code>/ask &lt;your question&gt;</code>. "
        f"/help for the full command list.</p>"
        + rows_to_pills(_home_rows())
    )


def rich_help() -> str:
    """Rich /help body — Oak field guide + guide pills."""
    return (
        f"<h2>{ui_tag('sparkle')} Professor Oak's Forge Field Guide</h2>"
        f"<p>{ui_tag('chat')} Ah, a curious trainer! Ask me anything about "
        f"the <b>Forge</b> Pokémon game — catching, battling, breeding, "
        f"trading, regions, quests, every command — and I'll share what my "
        f"research notes say.</p>"
        f"<h3>{ui_tag('star')} Commands</h3>"
        f"<ul>"
        f"<li><code>/ask &lt;question&gt;</code> — ask me anything "
        f"(alias: /ai)</li>"
        f"<li><code>/reset</code> — forget this conversation, start fresh</li>"
        f"<li><code>/commands [name]</code> — command index</li>"
        f"<li><code>/guide [topic]</code> — full guides</li>"
        f"<li><code>/search &lt;question&gt;</code> — raw documentation "
        f"matches</li>"
        f"<li><code>/mv &lt;pokemon&gt;</code> — all moves with type, "
        f"power, accuracy, source</li>"
        f"<li><code>/poke &lt;pokemon&gt;</code> — Pokédex card with IVs "
        f"and move lists</li>"
        f"<li><code>/build &lt;pokemon&gt;</code> — best nature, EVs, IVs, "
        f"items &amp; moves by role</li>"
        f"<li><code>/about</code> — bot status</li>"
        f"<li><code>/help</code> — this message</li>"
        f"</ul>"
        f"<blockquote>{ui_tag('chat')} I remember our last few exchanges, so "
        f"follow-ups like \"and what about Johto?\" work just fine. Tap a "
        f"guide below!</blockquote>"
        f"<h3>{ui_tag('gift')} Guides</h3>"
        + rows_to_pills(_guide_rows())
    )


def rich_about() -> str:
    stats = _kb.stats()
    chain = config.provider_chain()
    mode = (" → ".join(name for name, _b, _m, _h in chain)
            if chain else "no API key — short fallback replies")
    return (
        f"<h2>{ui_tag('sparkle')} Professor Oak's Forge Help Bot</h2>"
        f"<p>{ui_tag('chat')} AI: {html.escape(mode)}</p>"
        f"<p>{ui_tag('star')} Knowledge: {stats['files']} files · "
        f"{stats['chunks']} chunks · {stats['commands']} command names</p>"
        f"<p>{ui_tag('fire')} Answered so far: {_STATS['questions']} "
        f"(AI {_STATS.get('ai', 0)}, fallback {_STATS.get('fallback', 0)}, "
        f"off-topic {_STATS.get('offtopic', 0)})</p>"
        f"<footer>Support: {SUPPORT_LABEL} · Updates: @ForgeUpdates</footer>"
        + rows_to_pills([
            [(pill_label("globe", f"Support {SUPPORT_LABEL}"), SUPPORT_URL, LINK)],
            [(pill_label("gift", "Help Menu"), "hp|menu")],
        ])
    )


def rich_ask_usage() -> str:
    return (
        f"<h3>{ui_tag('chat')} How to ask me</h3>"
        f"<p>Usage: <code>/ask how do I breed eggs?</code></p>"
        f"<blockquote>Or just send your question here in DM — I'm always "
        f"listening!</blockquote>"
        + rows_to_pills([[
            (pill_label("chat", "Example question"),
             "hp|example", SUCCESS),
        ]])
    )


# ── plumbing ─────────────────────────────────────────────────────────────

def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


async def send_answer(update: Update, text: str,
                      reply_markup: InlineKeyboardMarkup | None = None) -> None:
    """Send possibly-long HTML, falling back to plain text if unparseable."""
    target = update.effective_message
    if target is None:
        return
    parts = split_message(text)
    for i, part in enumerate(parts):
        markup = reply_markup if i == len(parts) - 1 else None
        try:
            await target.reply_html(part, reply_markup=markup)
        except BadRequest as exc:
            LOGGER.debug("HTML rejected (%s); retrying as plain text", exc)
            try:
                await target.reply_text(_strip_tags(part), reply_markup=markup)
            except TelegramError:
                LOGGER.exception("Failed to send fallback message")


async def _send_rich_page(update: Update, rich_body: str,
                          classic_text: str,
                          classic_markup: InlineKeyboardMarkup) -> None:
    """Rich first (with classic markup fallback)."""
    bot = update.get_bot()
    chat_id = update.effective_chat.id
    reply_to = update.effective_message.message_id if update.effective_message else None
    ok = await send_rich_step(
        bot, chat_id, rich_body,
        reply_markup=None,          # pills live in the rich content
        reply_to=reply_to,
        classic_markup=classic_markup,
    )
    if ok:
        return
    # send_rich_step already sent classic HTML — but only if we gave it
    # classic markup and it built the body. When the rich path failed it
    # uses classic_html(rich_body) which strips pills. If that also failed
    # silently, send classic_text ourselves as last resort.
    # Actually send_rich_step always tries classic on rich failure; nothing
    # more to do here unless it returned False after a complete failure —
    # which it swallows. Keep a quiet debug marker.
    LOGGER.debug("rich page sent via classic fallback")


def _welcome_photo_path():
    """Path to the Oak welcome image (bundled, or from forge-main)."""
    bundled = Path(__file__).resolve().parent / "assets" / "welcome.jpg"
    if bundled.is_file():
        return bundled
    # Fallback: forge-main checkout next to this repo.
    forge = config.ROOT.parent / "forge-main" / "forge" / "assets" / "welcome.jpg"
    if forge.is_file():
        return forge
    return None


async def _send_start_rich(update: Update, name: str) -> None:
    """/start — welcome photo + premium caption + colored home buttons."""
    bot = update.get_bot()
    chat_id = update.effective_chat.id
    reply_to = (update.effective_message.message_id
                if update.effective_message else None)
    try:
        me = await bot.get_me()
        username = me.username
    except TelegramError:
        username = "Professor_OakBot"
    display = html.escape(name or "Trainer")
    who = html.escape(username or "Professor_OakBot")
    caption = (
        f"{ui_tag('fire')} <b>Welcome, welcome!</b> I'm <b>Professor Oak</b> "
        f"(@{who}) — the AI study guide for <b>Forge</b> (@PokeForgebot).\n\n"
        f"Hi <b>{display}</b>! Ask me anything about commands, shiny odds, "
        f"regions, breeding and more.\n\n"
        f"Type your question, or use "
        f"<code>/ask &lt;your question&gt;</code>. /help for the full list."
    )
    classic = (
        f"{E.FIRE} <b>Welcome, welcome!</b> I'm <b>Professor Oak</b> "
        f"(@{who}) — the AI study guide for <b>Forge</b> "
        f"(@PokeForgebot).\n\n"
        f"Hi <b>{display}</b>! Ask me anything about commands, shiny odds, "
        f"regions, breeding and more.\n\n"
        f"Type your question, or use "
        f"<code>/ask &lt;your question&gt;</code>. /help for the full list."
    )
    kb = _home_kb_dict()
    path = _welcome_photo_path()
    if path is not None:
        data = path.read_bytes()
        sent = await send_photo_bytes(
            bot, chat_id, data, "welcome.jpg", caption,
            reply_markup=kb, reply_to=reply_to, mime="image/jpeg")
        if sent:
            return
        LOGGER.debug("send welcome photo failed; classic text path")
    await send_rich_step(
        bot, chat_id, rich_start(name, username),
        reply_markup=kb,
        reply_to=reply_to,
        classic_markup=_home_kb(),
        classic_text=classic,
    )


def _allowed(user_id: int | None) -> bool:
    if not config.RATE_MAX_PER_WINDOW:
        return True
    if not user_id:
        return True
    now = time.monotonic()
    window = _SEEN.setdefault(user_id, deque())
    while window and now - window[0] > config.RATE_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= config.RATE_MAX_PER_WINDOW:
        return False
    if window and now - window[-1] < config.RATE_GAP_SECONDS:
        return False
    window.append(now)
    return True


async def _bot_username(context: ContextTypes.DEFAULT_TYPE) -> str:
    global _USERNAME
    if _USERNAME is None:
        me = await context.bot.get_me()
        _USERNAME = me.username.lower()
    return _USERNAME


def _mentions_bot(message, username: str) -> bool:
    text = (message.text or message.caption or "").lower()
    if f"@{username}" in text:
        return True
    for entity in message.entities or message.caption_entities or ():
        if entity.type in ("mention", "text_mention") and entity.offset < len(text):
            if text[entity.offset:entity.offset + entity.length] == f"@{username}":
                return True
    return False


def _strip_mention(text: str, username: str) -> str:
    return re.sub(rf"@{re.escape(username)}\b", "", text or "",
                  flags=re.IGNORECASE).strip(" ?!.,:-")


def _question_from_reply(message, username: str) -> str | None:
    """When the bot is tagged in a reply, prefer the ORIGINAL message text.

    Scenario: user asks "what is a shiny pokemon", someone replies to that
    message with just ``@Professor_OakBot`` — Oak should answer the shiny
    question, not say "what do you mean?".
    """
    original = (message.reply_to_message.text
                or message.reply_to_message.caption or "").strip()
    # Never re-answer the bot's own messages.
    rf = message.reply_to_message.from_user
    if rf and rf.is_bot:
        return None
    own = _strip_mention(message.text or message.caption or "", username)
    if original and (not own or len(own) < 3):
        return original
    if own and original:
        # Tag + extra text: answer the extra text (likely a refinement).
        return own
    return own or original or None


# ── answers ──────────────────────────────────────────────────────────────

_HISTORY: dict[int, deque[tuple[str, str]]] = {}


def _history_for(chat_id: int) -> list[tuple[str, str]]:
    return list(_HISTORY.get(chat_id, ()))


def _remember(chat_id: int, question: str, answer_html: str) -> None:
    store = _HISTORY.setdefault(chat_id, deque())
    store.append((question, _strip_tags(answer_html)))
    while len(store) > config.HISTORY_TURNS:
        store.popleft()


async def _answer_for(update: Update, context: ContextTypes.DEFAULT_TYPE,
                      question: str) -> None:
    user = update.effective_user
    if not _allowed(user.id if user else None):
        await send_answer(
            update,
            f"{E.WARN} One moment, trainer — please wait "
            f"{config.RATE_GAP_SECONDS:g}s between questions "
            f"(up to {config.RATE_MAX_PER_WINDOW} per "
            f"{config.RATE_WINDOW_SECONDS // 60} minutes).")
        return

    _STATS["questions"] += 1
    try:
        await update.effective_chat.send_action(ChatAction.TYPING)
    except TelegramError:
        pass

    chat_id = update.effective_chat.id
    result: Answer = await ai.answer(question, _kb,
                                     history=_history_for(chat_id))
    _STATS[result.mode] = _STATS.get(result.mode, 0) + 1
    if result.mode == "ai":
        _remember(chat_id, question, result.text)
    await send_answer(update, result.text, reply_markup=_answer_kb())


def _answer_kb() -> InlineKeyboardMarkup:
    return rows_to_kb([[
        ("Help Menu", "hp|menu"),
        ("Commands", "hp|commands"),
        ("Reset chat", "hp|reset"),
    ]])


# ── handlers ─────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    name = (user.first_name if user else "") or "Trainer"
    await _send_start_rich(update, name)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_rich_page(update, rich_help(), classic_html(rich_help()),
                          _guide_kb())


async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_rich_page(update, rich_about(), classic_html(rich_about()),
                          rows_to_kb([[
                              (f"Support {SUPPORT_LABEL}", SUPPORT_URL),
                              ("Help Menu", "hp|menu"),
                          ]]))


async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = " ".join(context.args).strip()
    if not question:
        await _send_rich_page(
            update, rich_ask_usage(), classic_html(rich_ask_usage()),
            rows_to_kb([[
                ("Example question", "hp|example"),
            ]]))
        return
    await _answer_for(update, context, question)


async def cmd_commands(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = (context.args[0] if context.args else "").strip().lower()
    if name:
        line = _kb.command_line(name)
        if line:
            await update.effective_message.reply_html(
                html.escape(line) +
                "\n\n<i>Full context: /guide commands · "
                "/search " + html.escape(name) + "</i>")
            return
        hits = _kb.search(f"/{name}", limit=3)
        if hits:
            await send_answer(update, "\n".join(
                f"<blockquote><b>{html.escape(h.chunk.title)}</b>\n"
                f"{html.escape(h.chunk.text[:500])}</blockquote>"
                for h in hits))
            return
        await update.effective_message.reply_html(
            f"{E.CROSS} I have no index entry for /{html.escape(name)}. "
            f"Try /commands or /search.")
        return
    await update.effective_message.reply_html(
        f"{E.STAR} <b>Command index</b> — send /commands &lt;name&gt; for "
        f"one entry.\n\n"
        f"Most asked: /start /help /hunt /myteam /pc /breed /trade "
        f"/daily /weekly /quest /battle /gymbattle /pvp /regions /travel "
        f"/shop /mycoins /mystats /leaderboard /guess",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "Full index", callback_data="hp|commands")]]))


async def cmd_guide(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await _send_rich_page(
            update,
            f"<h3>{ui_tag('gift')} Pick a guide, trainer</h3>"
            + rows_to_pills(_guide_rows()),
            f"{E.GIFT} Pick a guide, trainer:",
            _guide_kb())
        return
    stem = _kb.file_for_term(" ".join(context.args).lower())
    text = _kb.guide_text(stem) if stem else None
    if not text:
        await update.effective_message.reply_html(
            f"{E.CROSS} No guide with that name. Tap /guide with no "
            f"arguments to browse.")
        return
    title = html.escape(_kb.guide_title(stem))
    await update.effective_message.reply_html(f"{E.GIFT} <b>{title}</b>")
    for part in split_message(strip_plain_emoji(text), limit=3500):
        try:
            await update.effective_message.reply_text(part)
        except TelegramError:
            LOGGER.exception("Failed sending guide %s", stem)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args).strip()
    if not query:
        await update.effective_message.reply_text("Usage: /search shiny odds")
        return
    hits = _kb.search(query, limit=5)
    if not hits:
        await update.effective_message.reply_html(
            f"{E.CROSS} Nothing in the knowledge base matched that.")
        return
    parts = [f"{E.STAR} <b>Top matches for</b> <code>{html.escape(query)}</code>\n"]
    for hit in hits:
        snippet = hit.chunk.text[:220].replace("\n", " ")
        parts.append(
            f"<blockquote><b>{html.escape(hit.chunk.title)}</b> "
            f"({html.escape(hit.chunk.source)}, score {hit.score:.1f})\n"
            f"{html.escape(snippet)} …</blockquote>")
    await send_answer(update, "\n".join(parts))


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    had = bool(_HISTORY.pop(chat_id, None))
    await update.effective_message.reply_html(
        f"{E.CHECK} Conversation cleared — ask me anything fresh, trainer!"
        if had else
        f"{E.CHAT} Nothing to clear yet — just ask me anything.")


async def on_guide_button(update: Update,
                          context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    stem = (query.data or "").split("|", 1)[-1]
    await query.answer()
    if stem == "close":
        try:
            await query.message.delete()
        except TelegramError:
            pass
        return
    if stem == "reset":
        had = bool(_HISTORY.pop(update.effective_chat.id, None))
        try:
            await query.message.reply_html(
                f"{E.CHECK} Conversation cleared — ask me anything fresh!"
                if had else
                f"{E.CHAT} Nothing to clear yet.")
        except TelegramError:
            pass
        return
    if stem == "menu":
        try:
            await _send_rich_page(
                update,
                f"<h3>{ui_tag('gift')} Pick a guide, trainer</h3>"
                + rows_to_pills(_guide_rows()),
                f"{E.GIFT} Pick a guide, trainer:",
                _guide_kb())
        except TelegramError:
            pass
        return
    if stem == "commands":
        try:
            await query.message.reply_html(
                f"{E.STAR} <b>Command index</b>\n\n"
                f"Most asked: /start /help /hunt /myteam /pc /breed /trade "
                f"/daily /weekly /quest /battle /gymbattle /pvp /regions "
                f"/travel /shop /mycoins /mystats /leaderboard /guess",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "Help Menu", callback_data="hp|menu")]]))
        except TelegramError:
            pass
        return
    if stem == "ask":
        try:
            await query.message.reply_html(
                f"{E.CHAT} Just type your question, or use "
                f"<code>/ask &lt;question&gt;</code>.\n"
                f"Example: <code>/ask how do shiny odds work?</code>")
        except TelegramError:
            pass
        return
    if stem == "example":
        try:
            await query.message.reply_text("/ask how do shiny odds work?")
        except TelegramError:
            pass
        return
    text = _kb.guide_text(stem)
    if not text:
        try:
            await query.message.reply_html(
                f"{E.CROSS} That guide is gone — try /guide.")
        except TelegramError:
            pass
        return
    try:
        await query.message.reply_html(
            f"{E.GIFT} <b>{html.escape(_kb.guide_title(stem))}</b>")
        for part in split_message(strip_plain_emoji(text), limit=3500):
            await query.message.reply_text(part)
    except TelegramError:
        LOGGER.exception("Failed sending guide %s", stem)


async def on_private_question(update: Update,
                              context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not message.text:
        return
    text = message.text.strip()
    if not text or text.startswith("/"):
        return
    if len(text) < 3:
        return
    await _answer_for(update, context, text)


async def on_group_message(update: Update,
                           context: ContextTypes.DEFAULT_TYPE) -> None:
    """Groups: reply-to-bot, reply+@mention (uses original text), @mention."""
    message = update.effective_message
    if message is None or not message.text or message.text.startswith("/"):
        return

    username = await _bot_username(context)
    replied = (message.reply_to_message is not None
               and message.reply_to_message.from_user is not None
               and message.reply_to_message.from_user.id == context.bot.id)
    mentioned = _mentions_bot(message, username)

    if replied or mentioned:
        question = _question_from_reply(message, username)
        if question and len(question.strip()) >= 2:
            await _answer_for(update, context, question.strip())
            return
        # Tag with nothing usable — fall back to a nudge.
        if mentioned or replied:
            await _answer_for(
                update, context,
                _strip_mention(message.text, username) or
                "What can you help with?")
            return

    if config.GROUP_MODE == "all":
        await on_private_question(update, context)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    if isinstance(error, Conflict):
        global _STOP_CODE
        if _STOP_CODE is None:
            _STOP_CODE = 2
            LOGGER.error(
                "HTTP 409 Conflict: another process is already polling "
                "this token — shutting down. Stop the other instance or "
                "use a different TOKEN in settings.py.")
            try:
                context.application.stop_running()
            except Exception:                  # noqa: BLE001
                LOGGER.debug("stop_running failed", exc_info=True)
        return

    _STATS["errors"] += 1
    LOGGER.exception("Unhandled error", exc_info=error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Something went wrong on my side — try again in a moment.")
        except TelegramError:
            pass


# ── application ──────────────────────────────────────────────────────────

async def _post_init(app: Application) -> None:
    try:
        me = await app.bot.get_me()
        LOGGER.info("running as @%s (id %s)", me.username, me.id)
    except TelegramError as exc:
        LOGGER.warning("could not verify token via getMe: %s", exc)
    # Warm the offline dex off the first-command path so /poke is fast.
    try:
        ok = await asyncio.to_thread(pokemon.ready)
        if ok:
            LOGGER.info("pokedex warmed (%s pokemon)", pokemon.count())
        else:
            LOGGER.warning("pokedex warm-load failed; /mv and /poke disabled")
    except Exception:
        LOGGER.exception("pokedex warm-load raised")


async def _post_shutdown(_app: Application) -> None:
    LOGGER.info("shutdown complete")


def build_app() -> Application:
    _kb.load()
    builder = Application.builder().token(config.TOKEN)
    for name, value in config.HTTP_TIMEOUTS.items():
        if hasattr(builder, name):
            builder = getattr(builder, name)(value)
    if config.PROXY:
        builder = builder.proxy_url(config.PROXY)
    if hasattr(builder, "post_init"):
        builder = builder.post_init(_post_init)
    if hasattr(builder, "post_shutdown"):
        builder = builder.post_shutdown(_post_shutdown)
    app = builder.build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("about", cmd_about))
    app.add_handler(CommandHandler(["ask", "ai"], cmd_ask))
    app.add_handler(CommandHandler("commands", cmd_commands))
    app.add_handler(CommandHandler("guide", cmd_guide))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler(["reset", "new"], cmd_reset))
    app.add_handler(CommandHandler(["mv", "moves"], pokedex_ui.cmd_mv))
    app.add_handler(CommandHandler(["poke", "pokedex", "dex"],
                                   pokedex_ui.cmd_poke))
    app.add_handler(CommandHandler(["build", "set"], build_ui.cmd_build))
    app.add_handler(CallbackQueryHandler(on_guide_button, pattern=r"^hp\|"))
    app.add_handler(CallbackQueryHandler(pokedex_ui.on_poke_button,
                                         pattern=r"^pk\|"))
    app.add_handler(CallbackQueryHandler(build_ui.on_build_button,
                                         pattern=r"^bd\|"))
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
        on_private_question))
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        on_group_message))
    app.add_error_handler(on_error)
    return app


# ── running ──────────────────────────────────────────────────────────────

def _webhook_kwargs() -> dict:
    from urllib.parse import urlparse
    url = config.WEBHOOK_URL
    path = config.WEBHOOK_PATH or urlparse(url).path.strip("/")
    kwargs: dict = {
        "listen": config.WEBHOOK_LISTEN,
        "port": config.WEBHOOK_PORT,
        "url_path": path,
        "webhook_url": url,
        "bootstrap_retries": config.BOOTSTRAP_RETRIES,
        "allowed_updates": Update.ALL_TYPES,
        "drop_pending_updates": True,
    }
    if config.WEBHOOK_SECRET:
        kwargs["secret_token"] = config.WEBHOOK_SECRET
    return kwargs


def _run_once(webhook: bool) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        app = build_app()
        if webhook:
            LOGGER.info("starting WEBHOOK mode on %s:%s (path=%s)",
                        config.WEBHOOK_LISTEN, config.WEBHOOK_PORT,
                        _webhook_kwargs()["url_path"] or "/")
            app.run_webhook(close_loop=False, **_webhook_kwargs())
        else:
            LOGGER.info("starting POLLING mode (groups: %s)", config.GROUP_MODE)
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                bootstrap_retries=config.BOOTSTRAP_RETRIES,
                close_loop=False,
            )
    finally:
        if not loop.is_closed():
            loop.close()


def main(webhook: bool | None = None) -> int:
    if not logging.getLogger().handlers:
        logsetup.configure(log_file=config.LOG_FILE)
    if not config.TOKEN:
        LOGGER.critical(
            "TOKEN is not set. Create a bot with @BotFather and put its "
            "token in help/helpbot/settings.py (TOKEN=\"...\").")
        return 3

    use_webhook = bool(config.WEBHOOK_URL) if webhook is None else webhook
    if use_webhook and not config.WEBHOOK_URL:
        LOGGER.critical("--webhook requested but WEBHOOK_URL is empty.")
        return 3
    if use_webhook:
        try:
            import tornado  # noqa: F401
        except ImportError:
            LOGGER.critical(
                "webhook mode needs PTB's webhook extra: "
                'pip install "python-telegram-bot[webhooks]==22.8" '
                "(or clear WEBHOOK_URL to use polling).")
            return 3

    stats = _kb.stats()
    LOGGER.info("%s", config.describe())
    LOGGER.info("knowledge: %s chunks / %s files / %s command names",
                stats["chunks"], stats["files"], stats["commands"])

    attempt, delay = 0, config.RESTART_BACKOFF_START
    global _STOP_CODE
    _STOP_CODE = None
    while True:
        attempt += 1
        try:
            _run_once(use_webhook)
            if _STOP_CODE is not None:
                return _STOP_CODE
            return 0
        except Conflict:
            LOGGER.error(
                "HTTP 409: another process is already polling this token. "
                "Stop the other instance or use a different token.")
            return 2
        except Forbidden as exc:
            LOGGER.critical("Telegram rejected the token (%s) — check "
                            "TOKEN in help/helpbot/settings.py", exc)
            return 3
        except BadRequest as exc:
            if "Bad webhook" in str(exc):
                LOGGER.critical(
                    "Telegram rejected WEBHOOK_URL (%s). It must be a "
                    "public https:// URL.", exc)
                return 3
            LOGGER.error("Bad Request: %s — retrying in %.0fs", exc, delay,
                         exc_info=True)
        except (KeyboardInterrupt, SystemExit):
            LOGGER.info("interrupted — shutting down")
            return 0
        except Exception as exc:                  # noqa: BLE001
            if config.RESTART_ON_FAILURE and attempt >= config.RESTART_ON_FAILURE:
                LOGGER.critical("giving up after %s consecutive failures",
                                attempt, exc_info=True)
                return 1
            LOGGER.error("run failed (%s: %s) — restarting in %.0fs (attempt %s)",
                         type(exc).__name__, exc, delay, attempt, exc_info=True)
        time.sleep(delay)
        delay = min(delay * 2, config.RESTART_BACKOFF_MAX)


if __name__ == "__main__":
    raise SystemExit(main())
