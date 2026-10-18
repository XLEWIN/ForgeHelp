// Persistent bot state — the DB-backed replacements for bot.py's
// in-memory _HISTORY / _SEEN / _STATS dicts. Every call is async.

import { db } from 'sdk';
import { eq, sql } from 'sdk/db';
import { history, rate, counters } from '../schema.js';
import * as cfg from './config.js';
import { stripTags } from './sanitize.js';

// ── conversation history (per chat) ──────────────────────────────────────

/** Recent [[question, plainAnswer], …] turns for a chat. */
export async function getHistory(chatId) {
  const row = await db.select().from(history).where(eq(history.chatId, chatId)).get();
  return Array.isArray(row?.turns) ? row.turns : [];
}

/** Append a turn, keeping the last HISTORY_TURNS (port of _remember). */
export async function remember(chatId, question, answerHtml) {
  const turns = await getHistory(chatId);
  turns.push([question, stripTags(answerHtml)]);
  while (turns.length > cfg.HISTORY_TURNS) turns.shift();
  await db.insert(history).values({ chatId, turns })
    .onConflictDoUpdate({ target: history.chatId, set: { turns, updated: Date.now() } })
    .run();
}

/** Forget the conversation. Returns true when there was something. */
export async function clearHistory(chatId) {
  const existing = await db.select().from(history).where(eq(history.chatId, chatId)).get();
  if (!existing) return false;
  await db.delete(history).where(eq(history.chatId, chatId)).run();
  return true;
}

// ── rate limiting (per user) ─────────────────────────────────────────────

/** Port of bot.py _allowed(): false when the user is over the window cap
 *  or inside the minimum gap; records the hit otherwise. */
export async function allowed(userId) {
  if (!cfg.RATE_MAX_PER_WINDOW) return true;
  if (!userId) return true;
  const now = Date.now();
  const windowMs = cfg.RATE_WINDOW_SECONDS * 1000;
  const gapMs = cfg.RATE_GAP_SECONDS * 1000;
  const row = await db.select().from(rate).where(eq(rate.userId, userId)).get();
  let stamps = Array.isArray(row?.stamps) ? [...row.stamps] : [];
  stamps = stamps.filter((t) => now - t <= windowMs);
  if (stamps.length >= cfg.RATE_MAX_PER_WINDOW) {
    await saveStamps(userId, stamps);
    return false;
  }
  if (stamps.length && now - stamps[stamps.length - 1] < gapMs) {
    await saveStamps(userId, stamps);
    return false;
  }
  stamps.push(now);
  await saveStamps(userId, stamps);
  return true;
}

async function saveStamps(userId, stamps) {
  if (!stamps.length) {
    // Fully stale row — drop it so the table doesn't grow forever.
    await db.delete(rate).where(eq(rate.userId, userId)).run();
    return;
  }
  await db.insert(rate).values({ userId, stamps })
    .onConflictDoUpdate({ target: rate.userId, set: { stamps } })
    .run();
}

// ── /about counters ──────────────────────────────────────────────────────

/** Increment a named counter (port of _STATS bumps). */
export async function bumpStat(name, n = 1) {
  await db.insert(counters).values({ name, value: n })
    .onConflictDoUpdate({
      target: counters.name,
      set: { value: sql`${counters.value} + ${n}` },
    })
    .run();
}

/** All counters as { name: value } (missing ones default to 0). */
export async function getStats() {
  const rows = await db.select().from(counters).all();
  const out = { questions: 0, ai: 0, fallback: 0, offtopic: 0, errors: 0 };
  for (const r of rows) out[r.name] = r.value;
  return out;
}
