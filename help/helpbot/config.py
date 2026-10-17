"""Configuration for the help bot.

All settings live in ``helpbot/settings.py`` — open that file and edit
values directly. Nothing is read from environment variables.

``settings.py`` is gitignored (it holds your token and API keys);
``settings.example.py`` is the committed template showing every option
and its default.

Nothing in here is ever printed, logged or sent to the model.
"""

from __future__ import annotations

import logging
from pathlib import Path

try:
    from . import settings
except ImportError as exc:                      # pragma: no cover
    raise SystemExit(
        "help/helpbot/settings.py is missing. Create it from the template:\n"
        "  cp help/helpbot/settings.example.py help/helpbot/settings.py\n"
        "then put your bot token in TOKEN = \"...\"."
    ) from exc

LOGGER = logging.getLogger(__name__)

HELP_DIR = Path(__file__).resolve().parent.parent
ROOT = HELP_DIR.parent
KNOWLEDGE_DIR = HELP_DIR / "knowledge"


def _get(name: str, default):
    """Read a setting, tolerating a template that lacks newer keys."""
    return getattr(settings, name, default)


# ── Telegram ─────────────────────────────────────────────────────────────
#: The help bot's OWN token (create a second bot with @BotFather).
TOKEN = _get("TOKEN", "")

#: Whitespace-separated Telegram user ids that may use owner-ish helpers.
OWNER_IDS = {int(x) for x in _get("OWNER_IDS", [])}

PROXY = _get("PROXY", "") or None

# ── AI provider ──────────────────────────────────────────────────────────
#: auto | groq | openrouter | openai | none
AI_PROVIDER = str(_get("AI_PROVIDER", "auto")).lower()

GROQ_API_KEY = _get("GROQ_API_KEY", "")
GROQ_MODEL = _get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_BASE_URL = _get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

OPENROUTER_API_KEY = _get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = _get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_BASE_URL = _get("OPENROUTER_BASE_URL",
                           "https://openrouter.ai/api/v1")

OPENAI_API_KEY = _get("OPENAI_API_KEY", "")
OPENAI_MODEL = _get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = _get("OPENAI_BASE_URL", "https://api.openai.com/v1")

#: Per-answer limits.
AI_TIMEOUT = int(_get("AI_TIMEOUT", 45))
AI_MAX_TOKENS = int(_get("AI_MAX_TOKENS", 700))
CONTEXT_CHAR_BUDGET = int(_get("CONTEXT_CHAR_BUDGET", 6000))
#: Below this BM25 score a question looks unrelated to Forge (only used
#: when no AI provider is configured — with an AI the model decides).
OFF_TOPIC_SCORE = float(_get("OFF_TOPIC_SCORE", 1.4))
#: Fraction of a question's content words that must exist in the docs
#: before a non-AI fallback treats it as a Forge question. Measured on
#: 31 questions: real players score 0.86+, unrelated ones 0.75-.
OFF_TOPIC_COVERAGE = float(_get("OFF_TOPIC_COVERAGE", 0.8))
#: Recent question/answer turns replayed to the model for follow-ups.
HISTORY_TURNS = int(_get("HISTORY_TURNS", 6))

# ── Behaviour ────────────────────────────────────────────────────────────
#: Per-user minimum gap between AI answers, and answers per window.
RATE_GAP_SECONDS = float(_get("RATE_GAP_SECONDS", 1.5))
RATE_WINDOW_SECONDS = int(_get("RATE_WINDOW_SECONDS", 300))
RATE_MAX_PER_WINDOW = int(_get("RATE_MAX_PER_WINDOW", 20))

#: Groups: answer only when the bot is mentioned, replied to, or the
#: message is a command. Set to "all" to also answer plain messages.
GROUP_MODE = str(_get("GROUP_MODE", "mention")).lower()

# ── Deployment ───────────────────────────────────────────────────────────
#: Set WEBHOOK_URL to run behind a public HTTPS endpoint instead of
#: long polling (Railway/Render/VPS+nginx). Empty = polling.
WEBHOOK_URL = _get("WEBHOOK_URL", "")
WEBHOOK_LISTEN = _get("WEBHOOK_LISTEN", "0.0.0.0")
WEBHOOK_PORT = int(_get("WEBHOOK_PORT", 8080))
#: Local path Telegram should call. Defaults to the path inside the URL.
WEBHOOK_PATH = _get("WEBHOOK_PATH", "")
#: Optional X-Telegram-Bot-Api-Secret-Token value (recommended in prod).
WEBHOOK_SECRET = _get("WEBHOOK_SECRET", "")

#: Hard network timeouts for Bot API calls (seconds).
HTTP_TIMEOUTS = {
    "read_timeout": float(_get("HTTP_READ_TIMEOUT", 20)),
    "write_timeout": float(_get("HTTP_WRITE_TIMEOUT", 20)),
    "connect_timeout": float(_get("HTTP_CONNECT_TIMEOUT", 15)),
    "pool_timeout": float(_get("HTTP_POOL_TIMEOUT", 10)),
}

#: Crash-resilience: outer restart loop around polling.
#: 0 = restart forever (recommended behind a service manager is 0 anyway),
#: N > 0 = give up after N consecutive failures.
RESTART_ON_FAILURE = int(_get("RESTART_ON_FAILURE", 0))
RESTART_BACKOFF_START = float(_get("RESTART_BACKOFF_START", 5.0))
RESTART_BACKOFF_MAX = float(_get("RESTART_BACKOFF_MAX", 300.0))
#: Telegram bootstrap (getUpdates / setWebhook) retries per attempt.
#: Finite on purpose: the outer restart loop in bot.main() already
#: retries forever *with logging*, so an unreachable webhook URL cannot
#: hang silently here. Set -1 for PTB's infinite inner retry.
BOOTSTRAP_RETRIES = int(_get("BOOTSTRAP_RETRIES", 3))

#: Logging: set LOG_FILE = False to disable the file (containers/stdout
#: only). LOG_DIR empty = help/logs.
LOG_FILE = bool(_get("LOG_FILE", True))
LOG_DIR = Path(_get("LOG_DIR", "") or (HELP_DIR / "logs"))


def provider_chain() -> list[tuple[str, str, str, dict[str, str]]]:
    """Ordered [(name, base_url, model, headers)] candidates for answers.

    With ``AI_PROVIDER = "auto"`` every configured provider is returned
    in preference order — Groq first, then OpenRouter, then OpenAI — so a
    rate-limited primary falls through to the next automatically.
    Returns an empty list when no key is configured, which switches the
    bot to short friendly fallback replies.
    """
    wanted = AI_PROVIDER
    candidates: dict[str, tuple[str, str, str, dict[str, str]]] = {
        "groq": (GROQ_BASE_URL, GROQ_MODEL, GROQ_API_KEY, {}),
        "openrouter": (OPENROUTER_BASE_URL, OPENROUTER_MODEL, OPENROUTER_API_KEY,
                       {"HTTP-Referer": "https://t.me/forge",
                        "X-Title": "Forge Help Bot"}),
        "openai": (OPENAI_BASE_URL, OPENAI_MODEL, OPENAI_API_KEY, {}),
    }
    order = (["groq", "openrouter", "openai"]
             if wanted in ("", "auto") else [wanted])
    chain: list[tuple[str, str, str, dict[str, str]]] = []
    for name in order:
        spec = candidates.get(name)
        if not spec:
            if wanted not in ("", "auto", "none") and name == wanted:
                LOGGER.warning("AI_PROVIDER=%s is not a known provider.", wanted)
            continue
        base, model, key, headers = spec
        if not key:
            continue
        headers = dict(headers)
        headers["Authorization"] = f"Bearer {key}"
        chain.append((name, base, model, headers))
    if wanted not in ("", "auto", "none") and not chain:
        LOGGER.warning("AI_PROVIDER=%s has no API key configured.", wanted)
    return chain


def provider_settings() -> tuple[str, str, str, dict[str, str]] | None:
    """Primary provider (first in the chain), or None when unconfigured."""
    chain = provider_chain()
    return chain[0] if chain else None


def describe() -> str:
    """One-line status for /about — never includes credentials."""
    chain = provider_chain()
    if chain:
        ai = " → ".join(f"{name}:{model}" for name, _b, model, _h in chain)
    else:
        ai = "not configured — short fallback replies"
    return f"ai={ai} knowledge={KNOWLEDGE_DIR.name}"
