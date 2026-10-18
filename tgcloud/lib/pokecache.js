// PokeAPI cache policy — pure helpers (no sdk import) so tools/test_pure.mjs
// can verify keys + freshness without a database. The sdk-facing wrapper
// lives in pokeapi.js.

/** Responses live for 7 days (the original kept them for the process
 *  lifetime; the DB copy survives cold starts, so a short TTL is plenty
 *  and keeps rows bounded). */
export const CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000;

/** Rows older than this are pruned opportunistically on write — a hard
 *  ceiling on table growth even if the TTL logic above is bypassed. */
export const CACHE_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;

export function speciesKey(nameOrId) {
  return `species:${String(nameOrId).toLowerCase().trim()}`;
}

export function evoKey(speciesId) {
  return `evo:${Number(speciesId)}`;
}

export function encounterKey(pokemonId) {
  return `enc:${Number(pokemonId)}`;
}

/** Fresh = written within the TTL. `now` is injectable for tests. */
export function isFresh(fetchedAt, now = Date.now(), ttlMs = CACHE_TTL_MS) {
  const at = Number(fetchedAt);
  if (!Number.isFinite(at)) return false;
  return now - at >= 0 && now - at < ttlMs;
}

/** Only pokeapi.co endpoints are ever fetched (evolution chains are
 *  fetched from a URL the API itself returned — allow just that path). */
export function allowedUrl(url) {
  const s = String(url || '');
  if (s.startsWith('https://pokeapi.co/api/v2/pokemon-species/')) return true;
  if (s.startsWith('https://pokeapi.co/api/v2/pokemon/')) return true;
  if (s.startsWith('https://pokeapi.co/api/v2/evolution-chain/')) return true;
  return false;
}
