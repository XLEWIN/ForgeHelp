"""Template for the help bot's settings.

Copy this file to ``settings.py`` (same folder) and edit values there:

    cp help/helpbot/settings.example.py help/helpbot/settings.py

``settings.py`` is gitignored so your token and API keys never leave
this machine. Every option below is already set to its default — you
only *need* to fill in ``TOKEN``.
"""

from __future__ import annotations

# ── Telegram ─────────────────────────────────────────────────────────────
#: The help bot's OWN token from @BotFather — never the main bot's token.
TOKEN = ""

#: Telegram user ids allowed to use owner-ish helpers (usually empty).
OWNER_IDS: list[int] = []

#: Optional socks5/https proxy URL for Telegram traffic.
PROXY = ""

# ── AI provider ──────────────────────────────────────────────────────────
#: auto | groq | openrouter | openai | none
AI_PROVIDER = "auto"

GROQ_API_KEY = ""
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

OPENROUTER_API_KEY = ""
OPENROUTER_MODEL = "openai/gpt-4o-mini"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

OPENAI_API_KEY = ""
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_BASE_URL = "https://api.openai.com/v1"

#: Per-answer limits.
AI_TIMEOUT = 45
AI_MAX_TOKENS = 700
CONTEXT_CHAR_BUDGET = 6000

#: Off-topic detection (only used when no AI key is configured).
OFF_TOPIC_SCORE = 1.4
OFF_TOPIC_COVERAGE = 0.8

#: Recent question/answer turns the AI remembers per chat.
HISTORY_TURNS = 6

# ── Behaviour ────────────────────────────────────────────────────────────
#: Per-user minimum gap between AI answers, and answers per window.
RATE_GAP_SECONDS = 1.5
RATE_WINDOW_SECONDS = 300
RATE_MAX_PER_WINDOW = 20

#: Groups: "mention" = answer on mention/reply/command only;
#: "all" = answer every message.
GROUP_MODE = "mention"

# ── Deployment ───────────────────────────────────────────────────────────
#: Empty = long polling. Set a public https:// URL to serve webhooks
#: (Railway/Render/VPS+nginx).
WEBHOOK_URL = ""
WEBHOOK_LISTEN = "0.0.0.0"
WEBHOOK_PORT = 8080
#: Local path Telegram should call. Empty = the path inside WEBHOOK_URL.
WEBHOOK_PATH = ""
#: X-Telegram-Bot-Api-Secret-Token value (recommended in prod).
WEBHOOK_SECRET = ""

#: Hard network timeouts for Bot API calls (seconds).
HTTP_READ_TIMEOUT = 20
HTTP_WRITE_TIMEOUT = 20
HTTP_CONNECT_TIMEOUT = 15
HTTP_POOL_TIMEOUT = 10

#: Crash-resilience: outer restart loop around polling.
#: 0 = restart forever; N > 0 = give up after N consecutive failures.
RESTART_ON_FAILURE = 0
RESTART_BACKOFF_START = 5.0
RESTART_BACKOFF_MAX = 300.0
#: Telegram bootstrap (getUpdates / setWebhook) retries per attempt.
BOOTSTRAP_RETRIES = 3

# ── Logging ──────────────────────────────────────────────────────────────
#: False = console only (containers); True = also help/logs/helpbot.log.
LOG_FILE = True
#: Empty = help/logs.
LOG_DIR = ""
