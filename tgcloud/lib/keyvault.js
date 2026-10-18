// AI API-key vault: ordered failover, per-key health, masked views —
// port of help/helpbot/keyvault.py, with stats persisted in the
// database (keyStats) because each invocation is a fresh isolate.
//
// Failover order (AI_PROVIDER = "auto"): OpenRouter 1st → 2nd → 3rd,
// then OpenAI, then Groq. The chain is walked in order inside one answer;
// the first success wins. A 429 pauses that key 60s, an auth error
// (401/402/403) pauses it 5 minutes — during a pause the next key is
// tried instead.
//
// Raw keys never leave this module: display goes through masked() /
// snapshot() only.

// db: health stats; fetch: the /chat/completions ping and tests (the
// platform SDK's HTTP client — there is no global fetch in the isolate).
import { db, fetch } from 'sdk';
import { eq } from 'sdk/db';
import { keyStats } from '../schema.js';
import * as cfg from './config.js';

/** Seconds a rate-limited key (429) steps aside. */
export const COOLDOWN_429 = 60_000; // ms
/** Seconds a rejected/unpaid key (401/402/403) steps aside. */
export const COOLDOWN_AUTH = 300_000; // ms

/** OpenRouter wants an app referer; every OpenRouter key gets these
 *  (identical training — only the token differs between keys). */
const OPENROUTER_HEADERS = {
  'HTTP-Referer': 'https://t.me/forge',
  'X-Title': 'Forge Help Bot',
};

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

/** `sk-or-v1-…888c7` — at most first 9 + last 4 characters. */
export function mask(key) {
  if (!key) return '';
  if (key.length <= 14) return `…${key.slice(-2)}`;
  return `${key.slice(0, 9)}…${key.slice(-4)}`;
}

/** Static key specs in failover order (no stats). */
export function allSpecs() {
  const specs = [];
  const seen = new Set();
  let orN = 0;
  for (const raw of cfg.OPENROUTER_API_KEYS || []) {
    const key = String(raw || '').trim();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    orN += 1;
    specs.push({
      id: `or${orN}`,
      label: `OpenRouter #${orN}`,
      provider: 'openrouter',
      key,
      base: cfg.OPENROUTER_BASE_URL,
      model: cfg.OPENROUTER_MODEL,
      headers: { ...OPENROUTER_HEADERS },
    });
  }
  if (cfg.OPENAI_API_KEY) {
    specs.push({
      id: 'oa1', label: 'OpenAI', provider: 'openai', key: cfg.OPENAI_API_KEY,
      base: cfg.OPENAI_BASE_URL, model: cfg.OPENAI_MODEL, headers: {},
    });
  }
  if (cfg.GROQ_API_KEY) {
    specs.push({
      id: 'gq1', label: 'Groq', provider: 'groq', key: cfg.GROQ_API_KEY,
      base: cfg.GROQ_BASE_URL, model: cfg.GROQ_MODEL, headers: {},
    });
  }
  return specs;
}

/** Keys allowed by AI_PROVIDER, in failover order (port of _wanted). */
function wantedSpecs() {
  const wanted = (cfg.AI_PROVIDER || 'auto').toLowerCase();
  const specs = allSpecs();
  if (wanted === 'none') return [];
  if (wanted === '' || wanted === 'auto') return specs;
  return specs.filter((s) => s.provider === wanted);
}

// ── health stats (database-backed) ───────────────────────────────────────

async function loadStats() {
  const rows = await db.select().from(keyStats).all();
  const map = new Map();
  for (const r of rows) map.set(r.keyId, r);
  return map;
}

function stateOf(stat) {
  const now = Date.now();
  const uses = stat?.uses || 0;
  const cooldownUntil = stat?.cooldownUntil || 0;
  const lastOk = stat?.lastOk || 0;
  const lastErrorAt = stat?.lastErrorAt || 0;
  const lastError = stat?.lastError || '';
  if (cooldownUntil > now) return 'cooling';
  if (uses === 0) return 'new';
  if (lastError && lastErrorAt >= lastOk) return 'failing';
  return 'healthy';
}

/** Live keys for one answer: failover order, cooling keys skipped.
 *  When *every* key is cooling, the full list is returned anyway —
 *  trying a cooling key still beats failing the answer outright. */
export async function chain() {
  const keys = wantedSpecs();
  if (!keys.length) return [];
  const stats = await loadStats();
  const live = keys.filter((k) => stateOf(stats.get(k.id)) !== 'cooling');
  return (live.length ? live : keys).map((k) => ({ ...k, stat: stats.get(k.id) || null }));
}

/** Book one call outcome against *spec* (updates stats + cooldowns). */
export async function record(spec, ok, error = '') {
  const now = Date.now();
  const row = (await db.select().from(keyStats).where(eq(keyStats.keyId, spec.id)).get()) || {
    keyId: spec.id, uses: 0, ok: 0, fail: 0, lastUsed: null, lastOk: null,
    lastError: '', lastErrorAt: null, cooldownUntil: null,
  };
  row.uses = (row.uses || 0) + 1;
  row.lastUsed = now;
  if (ok) {
    row.ok = (row.ok || 0) + 1;
    row.lastOk = now;
    row.cooldownUntil = null;
  } else {
    row.fail = (row.fail || 0) + 1;
    row.lastError = String(error || 'error').trim().slice(0, 160);
    row.lastErrorAt = now;
    const low = row.lastError.toLowerCase();
    if (low.includes('429') || low.includes('rate limit') || low.includes('rate_limit')) {
      row.cooldownUntil = now + COOLDOWN_429;
    } else if (low.includes('401') || low.includes('402') || low.includes('403')) {
      row.cooldownUntil = now + COOLDOWN_AUTH;
    }
  }
  await db.insert(keyStats).values(row)
    .onConflictDoUpdate({ target: keyStats.keyId, set: row })
    .run();
}

/** Masked per-key view for /keymenu — never contains a raw key. */
export async function snapshot() {
  const specs = allSpecs();
  const stats = await loadStats();
  const now = Date.now();
  return specs.map((k) => {
    const s = stats.get(k.id) || null;
    const cooldownUntil = s?.cooldownUntil || 0;
    return {
      id: k.id,
      label: k.label,
      provider: k.provider,
      model: k.model,
      masked: mask(k.key),
      state: stateOf(s),
      uses: s?.uses || 0,
      ok: s?.ok || 0,
      fail: s?.fail || 0,
      lastUsed: s?.lastUsed || 0,
      lastOk: s?.lastOk || 0,
      cooldownLeft: Math.max(0, cooldownUntil - now),
      lastError: s?.lastError || '',
    };
  });
}

/** Ordered [(name, base, model)] candidates for /about — no health
 *  filtering, never includes credentials (port of provider_chain). */
export function chainSpec() {
  return allSpecs().map((k) => ({ label: k.label, base: k.base, model: k.model }));
}

/** Compact status line: `openrouter×3:openai/gpt-4o-mini → …` (never
 *  includes credentials — port of format_chain). */
export function formatChain(chainList) {
  const groups = [];
  for (const { label, model } of chainList) {
    const provider = label.split(' #')[0].trim().toLowerCase();
    const last = groups[groups.length - 1];
    if (last && last.provider === provider && last.model === model) {
      last.n += 1;
    } else {
      groups.push({ provider, model, n: 1 });
    }
  }
  return groups
    .map(({ provider, model, n }) => (n > 1 ? `${provider}×${n}:${model}` : `${provider}:${model}`))
    .join(' → ');
}

/** 1-token ping against one key. Returns [ok, error]; records it. */
export async function testKey(spec) {
  try {
    const res = await fetch(`${spec.base.replace(/\/$/, '')}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': UA,
        ...spec.headers,
        Authorization: `Bearer ${spec.key}`,
      },
      body: JSON.stringify({
        model: spec.model,
        messages: [{ role: 'user', content: 'ping' }],
        max_tokens: 1,
        temperature: 0,
      }),
      // Same guarded timeout as ai.js — see note there.
      signal: typeof AbortSignal === 'function' && AbortSignal.timeout
        ? AbortSignal.timeout(Math.min(cfg.AI_TIMEOUT, 20) * 1000)
        : undefined,
    });
    if (!res.ok) {
      const detail = (await res.text().catch(() => '')).slice(0, 200);
      const err = `HTTP ${res.status} ${detail}`.trim();
      await record(spec, false, err);
      return [false, err];
    }
    await res.json().catch(() => ({}));
  } catch (e) {
    const err = `${e?.name || 'Error'}: ${e?.message || e}`;
    await record(spec, false, err);
    return [false, err];
  }
  await record(spec, true);
  return [true, ''];
}

/** Ping every configured key in parallel (for /keymenu's Test). */
export async function testAll() {
  const specs = allSpecs();
  const results = await Promise.all(specs.map((k) => testKey(k)));
  return specs.map((k, i) => [k, results[i][0], results[i][1]]);
}
