// PokeAPI client — the only outbound HTTP in the dex stack (ports data.py's
// _fetch_json / _get_species_data / _get_evolution_chain / _get_encounters).
//
// Rules kept from the original, plus DB persistence for cold starts:
//   • 10 s timeout per request (aiohttp total=10 in the Python source)
//   • failures return null and are NEVER cached (a blipped call must not
//     pin "No evolution data" / "No location data" — data.py comment)
//   • at most 2 requests per user action (species + chain; encounters 1)
//   • only pokeapi.co endpoints (allowlist in pokecache.js)
//   • successes go through: isolate memory → poke_api_cache row → live.

import { db, fetch } from 'sdk';
import { eq, sql } from 'sdk/db';
import { pokeApiCache } from '../schema.js';
import {
  CACHE_MAX_AGE_MS, CACHE_TTL_MS, allowedUrl, encounterKey, evoKey,
  isFresh, speciesKey,
} from './pokecache.js';

const FETCH_TIMEOUT_MS = 10_000;

/** Hard cap on a single response body. Real payloads are tiny (species
 *  ~60 KB, evolution chains ~40 KB, encounters ≤ ~300 KB) — this only
 *  stops a hostile or broken response from exhausting isolate memory.
 *  Checked on the decompressed body (web fetch decodes transparently). */
const MAX_RESPONSE_CHARS = 2 * 1024 * 1024;

/** Per-isolate hot layer (the original's dict caches). */
const mem = new Map();

function guard(ms) {
  try {
    return AbortSignal.timeout(ms);
  } catch (_) {
    return undefined; // no AbortSignal.timeout — send unguarded
  }
}

/** GET JSON with the original's timeout + null-on-failure contract. */
async function httpJson(url) {
  if (!allowedUrl(url)) {
    console.debug('pokeapi: blocked non-allowlisted url');
    return null;
  }
  try {
    const res = await fetch(url, { signal: guard(FETCH_TIMEOUT_MS) });
    if (!res || !res.ok) {
      console.debug(`pokeapi: ${url} → ${res ? res.status : 'no response'}`);
      return null;
    }
    const text = await res.text();
    if (text.length > MAX_RESPONSE_CHARS) {
      console.debug(`pokeapi: ${url} → response too large (${text.length})`);
      return null;
    }
    return JSON.parse(text); // invalid JSON throws → caught below → null
  } catch (e) {
    console.debug('pokeapi: fetch failed', e);
    return null;
  }
}

/** Read through memory → DB (fresh rows only). Returns null on miss. */
async function cacheGet(key) {
  const hot = mem.get(key);
  if (hot && isFresh(hot.at)) return hot.data;
  try {
    const row = await db.select().from(pokeApiCache).where(eq(pokeApiCache.key, key)).get();
    if (row && isFresh(row.fetchedAt)) {
      const data = JSON.parse(row.json);
      mem.set(key, { data, at: row.fetchedAt });
      return data;
    }
  } catch (e) {
    console.debug('pokeapi: cache read failed', e);
  }
  return null;
}

/** Success-only write + opportunistic prune of rows past CACHE_MAX_AGE_MS. */
async function cachePut(key, data) {
  const at = Date.now();
  mem.set(key, { data, at });
  try {
    await db.insert(pokeApiCache).values({ key, json: JSON.stringify(data), fetchedAt: at })
      .onConflictDoUpdate({
        target: pokeApiCache.key,
        set: { json: JSON.stringify(data), fetchedAt: at },
      })
      .run();
    await db.delete(pokeApiCache)
      .where(sql`${pokeApiCache.fetchedAt} < ${at - CACHE_MAX_AGE_MS}`)
      .run();
  } catch (e) {
    console.debug('pokeapi: cache write failed', e);
  }
}

async function cachedJson(key, url) {
  const hit = await cacheGet(key);
  if (hit !== null && hit !== undefined) return hit;
  const data = await httpJson(url);
  if (data === null || data === undefined) return null; // never cache failures
  await cachePut(key, data);
  return data;
}

/** pokemon-species record (forms/varieties, evolution-chain URL). */
export function getSpecies(nameOrId) {
  const key = speciesKey(nameOrId);
  return cachedJson(key, `https://pokeapi.co/api/v2/pokemon-species/${encodeURIComponent(String(nameOrId).toLowerCase().trim())}`);
}

/** Evolution chain document, resolved through the species record
 *  (one species fetch when the caller already has it — the original
 *  fetched species twice here; we reuse the caller's copy). */
export async function getEvolutionChain(speciesId, speciesRecord) {
  let species = speciesRecord;
  if (!species) species = await getSpecies(speciesId);
  const url = species && species.evolution_chain && species.evolution_chain.url;
  if (!url) return null;
  return cachedJson(evoKey(speciesId), url);
}

/** Encounter/area list for a pokemon id (empty array is valid data and
 *  IS cached; null means the call failed and is not). */
export function getEncounters(pokemonId) {
  return cachedJson(encounterKey(pokemonId),
    `https://pokeapi.co/api/v2/pokemon/${Number(pokemonId)}/encounters`);
}

export { CACHE_TTL_MS };
