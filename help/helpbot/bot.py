"""Telegram handlers for the Forge help bot.

Behaviour:

* **Private chat** — any non-command text is treated as a question.
* **Groups** — only commands, replies to the bot, and messages that
  @mention the bot are answered (set ``GROUP_MODE = "all"`` to widen).
* Everything is rate-limited per user. When no AI provider is configured
  (or every provider fails) answers degrade to a short friendly fallback
  pointing at /help · /commands · /guide — never pasted documentation.

Personality: the AI answers as **Professor Oak** (Pokémon). Premium
custom emoji and light rich HTML/buttons are used in suitable spots —
never overdone.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from collections import deque

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import BadRequest, Conflict, Forbidden, TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

from . import ai, config, logsetup
from .ai import Answer, split_message
from .emojis import E, ui_glyph
from .kb import KnowledgeBase

LOGGER = logging.getLogger(__name__)

_kb = KnowledgeBase()
_STATS = {"questions": 0, "ai": 0, "fallback": 0, "offtopic": 0, "errors": 0}
_SEEN: dict[int, deque[float]] = {}
_USERNAME: str | None = None
#: Exit code to use after a graceful in-handler stop (2 = token conflict).
_STOP_CODE: int | None = None

SEP = "━━━━━━━━━━━━━━"

HELP_TEXT = f"""\
{E.SPARKLE} <b>Professor Oak's Forge Field Guide</b>

Ah, a curious trainer! Ask me anything about the <b>Forge</b> Pokémon \
game — catching, battling, breeding, trading, regions, quests, every \
command — and I'll share what my research notes say.

{E.CHAT} <b>Ask me with</b>
<code>/ask how do I breed eggs?</code>

{SEP}
<b>Commands</b>
/ask &lt;question&gt; — ask me anything (alias: /ai)
/reset — forget this conversation, start fresh
/commands [name] — command index
/guide [topic] — full guides
/search &lt;question&gt; — raw documentation matches
/about — bot status
/help — this message

I remember our last few exchanges, so follow-ups like \
"and what about Johto?" work just fine. Tap a guide below!"""

WELCOME = f"""\
{E.SPARKLE} <b>Welcome, welcome! I'm Professor Oak!</b>

I'm the AI study guide living inside this help bot for \
<b>Forge</b> (@PokeForgebot) — a Pokémon catching, battling and \
trading game here on Telegram.

{E.CHAT} <b>Ask me anything</b>, for example:
• How do shiny odds work?
• Where can I hunt in Johto?
• What does /breedhelp say?

Just type your question, or use <code>/ask &lt;your question&gt;</code>.

{E.ROCKET} /help shows everything I can do — or pick a guide below. \
This is what Pokémon training is all about!"""


# ── plumbing ─────────────────────────────────────────────────────────────

def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


async def send_answer(update: Update, text: str,
                      reply_markup: InlineKeyboardMarkup | None = None) -> None:
    """Send possibly-long HTML, falling back to plain text if unparseable.

    PTB v22 dropped ``quote=``; the default (``do_quote=None``) quotes
    only when the triggering message was itself a reply, which is the
    behaviour we want in groups.
    """
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


def _kb_home_keyboard() -> InlineKeyboardMarkup:
    """Compact home row used under welcome/help (guides live behind /guide)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{ui_glyph('chat')} Ask Oak",
                                 switch_inline_query_current_chat="/ask "),
            InlineKeyboardButton(f"{ui_glyph('gift')} Guides",
                                 callback_data="hp|menu"),
        ],
        [
            InlineKeyboardButton(f"{ui_glyph('star')} Commands",
                                 callback_data="hp|commands"),
            InlineKeyboardButton(f"{ui_glyph('globe')} Support",
                                 url="https://t.me/ForgeSupport"),
        ],
    ])


def _guide_keyboard(extra: list[InlineKeyboardButton] | None = None
                    ) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for stem, title, _size in _kb.guides():
        label = re.sub(r"^\d+-", "", stem).replace("-", " ")
        rows.append([InlineKeyboardButton(
            f"{ui_glyph('gift')} {title or label.title()}",
            callback_data=f"hp|{stem}")])
    rows.append([InlineKeyboardButton(
        f"{ui_glyph('star')} All commands", callback_data="hp|commands")])
    rows.append([
        InlineKeyboardButton(f"{ui_glyph('chat')} Ask Oak",
                             switch_inline_query_current_chat="/ask "),
        InlineKeyboardButton(f"{ui_glyph('cross')} Close",
                             callback_data="hp|close"),
    ])
    if extra:
        rows.append(extra)
    return InlineKeyboardMarkup(rows)


def _answer_keyboard() -> InlineKeyboardMarkup:
    """Light follow-up row under AI answers — not overdone."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{ui_glyph('gift')} Guides",
                             callback_data="hp|menu"),
        InlineKeyboardButton(f"{ui_glyph('star')} Commands",
                             callback_data="hp|commands"),
        InlineKeyboardButton(f"{ui_glyph('cross')} Reset chat",
                             callback_data="hp|reset"),
    ]])


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
    text = (message.text or "").lower()
    if f"@{username}" in text:
        return True
    for entity in message.entities or ():
        if entity.type == "mention" and entity.offset < len(text):
            if text[entity.offset:entity.offset + entity.length] == f"@{username}":
                return True
    return False


# ── answers ──────────────────────────────────────────────────────────────

#: chat id → recent (question, answer) turns fed back to the model so
#: follow-ups like "and Johto?" make sense.
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
    await send_answer(update, result.text, reply_markup=_answer_keyboard())


# ── handlers ─────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_html(
        WELCOME, reply_markup=_kb_home_keyboard())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_html(
        HELP_TEXT, reply_markup=_guide_keyboard())


async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    stats = _kb.stats()
    chain = config.provider_chain()
    mode = (" → ".join(name for name, _b, _m, _h in chain)
            if chain else "no API key — short fallback replies")
    await update.effective_message.reply_html(
        f"{E.SPARKLE} <b>Professor Oak's Forge Help Bot</b>\n"
        f"{SEP}\n"
        f"{E.CHAT} AI: {html.escape(mode)}\n"
        f"{E.STAR} Knowledge: {stats['files']} files · {stats['chunks']} chunks · "
        f"{stats['commands']} command names\n"
        f"{E.FIRE} Answered so far: {_STATS['questions']} "
        f"(AI {_STATS.get('ai', 0)}, fallback {_STATS.get('fallback', 0)}, "
        f"off-topic {_STATS.get('offtopic', 0)})\n\n"
        f"Support: @ForgeSupport · Updates: @ForgeUpdates",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(f"{ui_glyph('globe')} Support",
                                 url="https://t.me/ForgeSupport"),
            InlineKeyboardButton(f"{ui_glyph('gift')} Guides",
                                 callback_data="hp|menu"),
        ]]))


async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = " ".join(context.args).strip()
    if not question:
        await update.effective_message.reply_html(
            f"{E.CHAT} <b>How to ask me</b>\n\n"
            f"Usage: <code>/ask how do I breed eggs?</code>\n\n"
            f"Or just send your question here in DM — I'm always listening!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"{ui_glyph('chat')} Example question",
                    switch_inline_query_current_chat="/ask how do shiny odds work?"),
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
                f"{ui_glyph('star')} Full index", callback_data="hp|commands")]]))


async def cmd_guide(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_html(
            f"{E.GIFT} Pick a guide, trainer:", reply_markup=_guide_keyboard())
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
    for part in split_message(text, limit=3500):
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
    """Forget this chat's conversation so the AI starts fresh."""
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
            await query.message.reply_html(
                f"{E.GIFT} Pick a guide, trainer:",
                reply_markup=_guide_keyboard())
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
        for part in split_message(text, limit=3500):
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
    """Groups: reply-to-bot, @mention, or every message (GROUP_MODE).

    The reply/mention checks happen here rather than in PTB filters —
    v22 has no filters.REPLY_TO_BOT, and we need the mentioned text
    cleaned up anyway before asking the model.
    """
    message = update.effective_message
    if message is None or not message.text or message.text.startswith("/"):
        return

    replied = (message.reply_to_message is not None
               and message.reply_to_message.from_user is not None
               and message.reply_to_message.from_user.id == context.bot.id)
    if replied:
        await on_private_question(update, context)
        return

    username = await _bot_username(context)
    if _mentions_bot(message, username):
        text = re.sub(rf"@{re.escape(username)}\b", "", message.text.strip(),
                      flags=re.IGNORECASE).strip(" ?!.,:")
        await _answer_for(update, context, text or "What can you help with?")
        return

    if config.GROUP_MODE == "all":
        await on_private_question(update, context)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    # Conflict means someone else is polling the same token. PTB would
    # retry forever and spam this handler — stop once, clearly, so the
    # supervisor sees exit code 2 instead of a hot loop.
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
    """Runs after initialize(): confirm identity once, then log it.

    Must be async — PTB awaits ``post_init(app)`` inside its run loop.
    """
    try:
        me = await app.bot.get_me()
        LOGGER.info("running as @%s (id %s)", me.username, me.id)
    except TelegramError as exc:
        LOGGER.warning("could not verify token via getMe: %s", exc)


async def _post_shutdown(_app: Application) -> None:
    """Must be async for the same reason as _post_init."""
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
    app.add_handler(CallbackQueryHandler(on_guide_button, pattern=r"^hp\|"))
    # Private chat: any non-command text is a question.
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
        on_private_question))
    # Groups: one handler decides reply-to-bot / mention / group-mode.
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        on_group_message))
    app.add_error_handler(on_error)
    return app


# ── running ──────────────────────────────────────────────────────────────

def _webhook_kwargs() -> dict:
    """Translate config into run_webhook() arguments."""
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
    """One blocking run: returns only on a clean signal shutdown.

    Each attempt gets a fresh event loop: PTB closes the loop when a run
    ends (or crashes), and a restart must never inherit a closed loop.
    """
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
    """Run the bot with crash-resilient restarts. Returns an exit code."""
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
        # Fail fast with the fix, not a restart loop around a missing dep.
        try:
            import tornado  # noqa: F401  (PTB's webhook transport)
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
                return _STOP_CODE               # stopped from an error handler
            return 0                            # clean shutdown (SIGINT…)
        except Conflict:
            LOGGER.error(
                "HTTP 409: another process is already polling this token. "
                "Stop the other instance (check 'python -m help run', Task "
                "Scheduler or the systemd unit) or use a different token.")
            return 2
        except Forbidden as exc:
            LOGGER.critical("Telegram rejected the token (%s) — check "
                            "TOKEN in help/helpbot/settings.py", exc)
            return 3
        except BadRequest as exc:
            # Telegram resolves and validates the webhook URL at
            # setWebhook time; a bad URL never becomes good on retry.
            if "Bad webhook" in str(exc):
                LOGGER.critical(
                    "Telegram rejected WEBHOOK_URL (%s). It must be a "
                    "public https:// URL whose hostname resolves (set DNS "
                    "before pointing Telegram at it).", exc)
                return 3
            LOGGER.error("Bad Request: %s — retrying in %.0fs", exc, delay,
                         exc_info=True)
        except (KeyboardInterrupt, SystemExit):
            LOGGER.info("interrupted — shutting down")
            return 0
        except Exception as exc:                  # noqa: BLE001 — keep serving
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
