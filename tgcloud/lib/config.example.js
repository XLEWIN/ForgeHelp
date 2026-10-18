// Configuration for the Telegram Serverless build — TEMPLATE.
//
// Copy this file to `config.js` (same folder) and fill in real values:
//     cp tgcloud/lib/config.example.js tgcloud/lib/config.js
//
// `config.js` is gitignored (it holds API keys) but IS deployed by
// `npx tgcloud push`, which reads your disk — same trust model as the
// Python bot's gitignored help/helpbot/settings.py.
//
// The bot TOKEN is deliberately absent: the platform owns bot
// authentication on Serverless — handlers call `api.*` directly.

// ── Telegram ─────────────────────────────────────────────────────────────
/** Telegram user ids allowed to use owner-ish helpers (/keymenu). */
export const OWNER_IDS = [];

/** Dev group chat id where /bug report cards are posted (0 = feature off). */
export const BUG_REPORT_CHAT_ID = 0;

/** Public support contact shown in help pages. */
export const SUPPORT_URL = 'https://t.me/keczt';
export const SUPPORT_LABEL = '@keczt';

// ── AI provider ──────────────────────────────────────────────────────────
/** auto | groq | openrouter | openai | none */
export const AI_PROVIDER = 'auto';

export const GROQ_API_KEY = '';
export const GROQ_MODEL = 'llama-3.3-70b-versatile';
export const GROQ_BASE_URL = 'https://api.groq.com/openai/v1';

/** Ordered failover keys: 1st → 2nd → 3rd when one errors. */
export const OPENROUTER_API_KEYS = [];
export const OPENROUTER_MODEL = 'openai/gpt-4o-mini';
export const OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1';

export const OPENAI_API_KEY = '';
export const OPENAI_MODEL = 'gpt-4o-mini';
export const OPENAI_BASE_URL = 'https://api.openai.com/v1';

/** Per-answer limits (seconds / tokens / context chars). */
export const AI_TIMEOUT = 45;
export const AI_MAX_TOKENS = 800;
export const CONTEXT_CHAR_BUDGET = 6000;

/** Fraction of a question's content words that must exist in the docs
 *  before a non-AI fallback treats it as a Forge question. */
export const OFF_TOPIC_COVERAGE = 0.8;

/** Recent question/answer turns replayed to the model per chat. */
export const HISTORY_TURNS = 6;

// ── Behaviour ────────────────────────────────────────────────────────────
/** Per-user minimum gap between AI answers, answers per window, window size. */
export const RATE_GAP_SECONDS = 1.5;
export const RATE_WINDOW_SECONDS = 300;
export const RATE_MAX_PER_WINDOW = 20;

/** Groups: "mention" = answer on mention/reply/command only;
 *  "all" = answer every message. */
export const GROUP_MODE = 'mention';

/** Owner check helper. */
export function isOwner(userId) {
  return OWNER_IDS.includes(Number(userId));
}
