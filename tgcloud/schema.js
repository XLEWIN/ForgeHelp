import { table, integer, text, boolean, json, index, sql } from 'sdk/db';

// Database schema — the serverless port keeps every piece of state the
// Python bot held in memory (history, rate limits, key health, bug
// reports, /about counters) in SQLite instead, because every
// invocation runs in a fresh stateless V8 isolate.
//
// Deploy: `npx tgcloud push` (registers this file).
// Apply:  `npx tgcloud migrate` (creates the tables — interactive).

/** Recent question/answer turns per chat — replaces the in-memory _HISTORY. */
export const history = table('history', {
  chatId: integer('chat_id').primaryKey(),
  turns: json('turns').notNull().default([]),
  updated: integer('updated_at', { mode: 'timestamp_ms' })
    .default(sql`(unixepoch() * 1000)`),
});

/** Per-user rate-limit stamps (ms) — replaces the in-memory _SEEN deque. */
export const rate = table('rate', {
  userId: integer('user_id').primaryKey(),
  stamps: json('stamps').notNull().default([]),
});

/** Per-key AI health — replaces the in-memory keyvault stats cache. */
export const keyStats = table('key_stats', {
  keyId: text('key_id').primaryKey(),
  uses: integer('uses').notNull().default(0),
  ok: integer('ok').notNull().default(0),
  fail: integer('fail').notNull().default(0),
  lastUsed: integer('last_used', { mode: 'timestamp_ms' }),
  lastOk: integer('last_ok', { mode: 'timestamp_ms' }),
  lastError: text('last_error').default(''),
  lastErrorAt: integer('last_error_at', { mode: 'timestamp_ms' }),
  cooldownUntil: integer('cooldown_until', { mode: 'timestamp_ms' }),
}, (t) => ({
  tsIdx: index('idx_key_stats_used').on(t.lastUsed),
}));

/** Pending bug-report cards in the dev group — replaces bug_reports.json. */
export const bugReports = table('bug_reports', {
  key: text('key').primaryKey(),       // "<gc_chat_id>:<card_message_id>"
  uid: integer('uid').notNull(),
  dm: integer('dm').notNull(),         // where the reply is delivered
  origMid: integer('orig_mid').notNull(), // reporter's original /bug message
  name: text('name').notNull(),
  kind: text('kind').notNull(),        // private | group | supergroup
  seq: integer('seq').notNull(),
  ts: integer('ts').notNull(),         // unix seconds (display only)
  html: text('html').notNull(),        // the card body (for the done footer)
  done: boolean('done').notNull().default(false),
}, (t) => ({
  tsIdx: index('idx_reports_ts').on(t.ts),
}));

/** Developer replies stored against a card until Send is tapped. */
export const bugReplies = table('bug_replies', {
  key: text('key').primaryKey(),
  mid: integer('mid').notNull(),       // the dev's message id (media copy)
  text: text('text').default(''),
  media: boolean('media').notNull().default(false),
  fromName: text('from_name').default(''),
  ts: integer('ts').notNull(),
});

/** Monotonic bug-report counter — replaces bug.py's _seq. */
export const bugSeq = table('bug_seq', {
  id: integer('id').primaryKey(),      // always row 1
  seq: integer('seq').notNull().default(0),
});

/** /about statistics — replaces bot.py's in-memory _STATS. */
export const counters = table('counters', {
  name: text('name').primaryKey(),
  value: integer('value').notNull().default(0),
});

/** PokeAPI responses (species / evolution chains / encounters) cached
 *  across cold starts — replaces data.py's in-process dicts.
 *  Apply: npx tgcloud migrate. */
export const pokeApiCache = table('poke_api_cache', {
  key: text('key').primaryKey(),     // "species:charizard" | "evo:6" | "enc:6"
  json: text('json').notNull(),
  fetchedAt: integer('fetched_at', { mode: 'timestamp_ms' }).notNull(),
});
