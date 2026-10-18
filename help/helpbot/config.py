"""Configuration for the help bot.

Primary source: ``helpbot/settings.py`` — open that file and edit values
directly.

Environment fallback (containers / Railway): when ``settings.py`` is
missing or a key is empty there, the same name is read from the process
environment. Lists are comma-separated, booleans accept
``1/true/yes/on``. A non-empty ``settings.py`` value always wins.

``settings.py`` is gitignored (it holds your token and API keys);
``settings.example.py`` is the committed template showing every option
and its default.

Nothing in here is ever printed, logged or sent to the model.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

try:
    from . import settings as _settings
except ImportError:                                  # pragma: no cover
    _settings = None

if _settings is None and not os.environ.get("TOKEN", "").strip():
    raise SystemExit(
        "help/helpbot/settings.py is missing (and no TOKEN env var).\n"
        "Create it from the template:\n"
        "  cp help/helpbot/settings.example.py help/helpbot/settings.py\n"
        "then put your bot token in TOKEN = \"...\" "
        "(or export TOKEN=... when running in a container)."
    )

LOGGER = logging.getLogger(__name__)

HELP_DIR = Path(__file__).resolve().parent.parent
ROOT = HELP_DIR.parent
KNOWLEDGE_DIR = HELP_DIR / "knowledge"


def _env_value(name: str, default):
    """Coerce env var *name* to *default*'s type; None when unset/bad."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    raw = raw.strip()
    try:
        if isinstance(default, str):
            return raw
        if isinstance(default, bool):
            return raw.lower() in ("1", "true", "yes", "on")
        if isinstance(default, int):
            return int(raw)
        if isinstance(default, float):
            return float(raw)
        if isinstance(default, list):
            items = [s.strip() for s in raw.replace("\n", ",").split(",")
                     if s.strip()]
            if items and all(s.lstrip("-").isdigit() for s in items):
                return [int(s) for s in items]
            return items
    except ValueError:
        LOGGER.warning("env %s does not fit the default type; ignored", name)
    return None


def _get(name: str, default):
    """Read a setting: settings.py value → environment → default.

    Empty values in settings.py ("" / []) count as "unset" so a
    template checked out in a container still picks up env vars.
    """
    value = getattr(_settings, name, None) if _settings is not None else None
    if value is None or value == "" or value == []:
        env = _env_value(name, default)
        if env is not None:
            return env
        return default
    return value


def _has(name: str) -> bool:
    """True when settings.py defines a non-empty value for *name*."""
    if _settings is None:
        return False
    value = getattr(_settings, name, None)
    return value is not None and value != "" and value != []


# ── Telegram ─────────────────────────────────────────────────────────────
#: The help bot's OWN token (create a second bot with @BotFather).
TOKEN = _get("TOKEN", "")

#: Whitespace-separated Telegram user ids that may use owner-ish helpers.
OWNER_IDS = {int(x) for x in _get("OWNER_IDS", [])}

PROXY = _get("PROXY", "") or None

#: Dev group chat where /bug report cards land (0 = feature disabled).
BUG_REPORT_CHAT_ID = int(_get("BUG_REPORT_CHAT_ID", 0) or 0)

# ── Pokémon dex (offline gen_*.json) ─────────────────────────────────────
#: Folder holding Forge's gen_01..09.json. Empty = auto-search
#: (sibling forge-main, then help/data/generations).
POKEMON_DATA_DIR = _get("POKEMON_DATA_DIR", "") or ""

# ── AI provider ──────────────────────────────────────────────────────────
#: auto | groq | openrouter | openai | none
AI_PROVIDER = str(_get("AI_PROVIDER", "auto")).lower()

GROQ_API_KEY = _get("GROQ_API_KEY", "")
GROQ_MODEL = _get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_BASE_URL = _get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

#: Primary OpenRouter key (legacy single-key setting — kept for logs
#: and env-based setups). See openrouter_keys() for the failover list.
OPENROUTER_API_KEY = _get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = _get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_BASE_URL = _get("OPENROUTER_BASE_URL",
                           "https://openrouter.ai/api/v1")

OPENAI_API_KEY = _get("OPENAI_API_KEY", "")
OPENAI_MODEL = _get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = _get("OPENAI_BASE_URL", "https://api.openai.com/v1")


def openrouter_keys() -> list[str]:
    """Ordered OpenRouter failover keys: 1st → 2nd → 3rd on error.

    ``OPENROUTER_API_KEYS`` is tried first (in its own order);
    ``OPENROUTER_API_KEY`` is appended when it adds anything new, so a
    plain single-key setup keeps working unchanged. Duplicates drop out.
    """
    keys: list[str] = []
    for candidate in (list(_get("OPENROUTER_API_KEYS", []) or []) +
                      [_get("OPENROUTER_API_KEY", "")]):
        key = str(candidate or "").strip()
        if key and key not in keys:
            keys.append(key)
    return keys


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


def _webhook_port() -> int:
    """WEBHOOK_PORT, or the platform's $PORT when settings.py is absent."""
    if _has("WEBHOOK_PORT"):
        try:
            return int(_get("WEBHOOK_PORT", 8080))
        except (TypeError, ValueError):
            LOGGER.warning("WEBHOOK_PORT is not a number; using 8080")
    port_env = os.environ.get("PORT", "").strip()
    if port_env.isdigit():
        return int(port_env)
    return int(_get("WEBHOOK_PORT", 8080))


WEBHOOK_PORT = _webhook_port()
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


# ── provider view (delegates to keyvault; display only) ──────────────────

def provider_chain() -> list[tuple[str, str, str, dict[str, str]]]:
    """Ordered [(name, base_url, model, headers)] candidates for answers.

    The real failover chain (OpenRouter 1st → 2nd → 3rd, then OpenAI,
    then Groq) lives in ``keyvault`` — this view is for /about, CLI
    status and selftests, without health filtering.
    """
    from . import keyvault
    return [(k.label, k.base, k.model, dict(k.headers))
            for k in keyvault.chain()]


def provider_settings() -> tuple[str, str, str, dict[str, str]] | None:
    """Primary provider (first in the chain), or None when unconfigured."""
    chain = provider_chain()
    return chain[0] if chain else None


def format_chain(chain: list[tuple[str, str, str, dict[str, str]]]) -> str:
    """Compact status line: ``openrouter×3:openai/gpt-4o-mini → …``.

    Never includes credentials.
    """
    groups: list[list] = []
    for name, _base, model, _headers in chain:
        provider = name.split(" #")[0].strip().lower()
        if groups and groups[-1][0] == provider and groups[-1][1] == model:
            groups[-1][2] += 1
        else:
            groups.append([provider, model, 1])
    return " → ".join(f"{p}×{n}:{m}" if n > 1 else f"{p}:{m}"
                      for p, m, n in groups)


def describe() -> str:
    """One-line status for /about — never includes credentials."""
    chain = provider_chain()
    ai = format_chain(chain) if chain else "not configured — short fallback replies"
    return f"ai={ai} knowledge={KNOWLEDGE_DIR.name}"


def all_api_keys() -> list[str]:
    """Every configured credential — for log redaction only."""
    keys = [TOKEN, GROQ_API_KEY, OPENAI_API_KEY, *openrouter_keys()]
    return [k for k in keys if k and len(k) > 8]
