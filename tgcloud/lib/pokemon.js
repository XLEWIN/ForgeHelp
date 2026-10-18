// Offline Pokédex — port of help/helpbot/pokemon.py over the bundled
// compact subset (tools/build_dex.mjs → dexdata.js). SDK-free: pure data
// lookups + stat math, safe to import from tools/test_pure.mjs.
//
// No filesystem, no runtime JSON: the dumps are compiled into dexdata.js
// because the platform deploys only .js modules under tgcloud/.

import { MOVES, MONS, TYPE_CHART } from './dexdata.js';

// ── Stat names ───────────────────────────────────────────────────────────

export const STAT_MAP = {
  hp: 'HP', attack: 'ATK', defense: 'DEF',
  sp_atk: 'SP.ATK', sp_def: 'SP.DEF', speed: 'SPD',
};
export const STAT_ORDER = ['hp', 'attack', 'defense', 'sp_atk', 'sp_def', 'speed'];

/** Game max level shown on /poke headers. */
export const MAX_LEVEL = 100;

/** (nature, +stat, -stat) pairs used by /build recommendations. */
export const NATURE_TABLE = {
  Adamant: ['attack', 'sp_atk'],
  Jolly: ['speed', 'sp_atk'],
  Modest: ['sp_atk', 'attack'],
  Timid: ['speed', 'attack'],
  Impish: ['defense', 'sp_atk'],
  Bold: ['defense', 'attack'],
  Careful: ['sp_def', 'sp_atk'],
  Calm: ['sp_def', 'attack'],
};

export const CATEGORY_TITLES = {
  levelup: 'Level-up moves',
  tm: 'TM moves',
  tutor: 'Tutor moves',
  egg: 'Egg moves',
};

// ── Indexes ──────────────────────────────────────────────────────────────
// Built once per isolate. `wrapped` entries expose Python-shaped fields
// (base_stats, ev_yields, moves, …) so the UI port reads the same as the
// Python source.

const BY_ID = new Map();
const BY_NAME = new Map();

function wrap(entry) {
  const s = entry.s;
  return {
    id: entry.i,
    name: entry.n,
    types: entry.t,
    base_stats: {
      hp: s[0], attack: s[1], defense: s[2],
      sp_atk: s[3], sp_def: s[4], speed: s[5],
    },
    ev_yields: {
      hp: entry.v[0], attack: entry.v[1], defense: entry.v[2],
      sp_atk: entry.v[3], sp_def: entry.v[4], speed: entry.v[5],
    },
    catch_rate: entry.c,
    gender_rate: entry.g,
    is_legendary: entry.L,
    is_mythical: entry.M,
    abilities: (entry.a || []).map(([abilityName, hidden]) => ({
      name: abilityName, hidden: Boolean(hidden),
    })),
    _raw: entry,
  };
}

let built = false;

function ensureIndexes() {
  if (built) return;
  for (const entry of MONS) {
    const w = wrap(entry);
    BY_ID.set(entry.i, w);
    BY_NAME.set(String(entry.n).toLowerCase(), w);
  }
  registerArceusForms();
  built = true;
}

/** Synthesize Arceus elemental form entries (port of _register_arceus_forms).
 *  Forms share base 493's stats/moves; each has its own name + types. */
function registerArceusForms() {
  const base = BY_ID.get(493);
  if (!base) return;
  const home = 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/home';
  const art = 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/493.png';
  for (const t of ['Normal', 'Fire', 'Water', 'Grass', 'Electric', 'Ice',
    'Fighting', 'Poison', 'Ground', 'Flying', 'Psychic', 'Bug',
    'Rock', 'Ghost', 'Dragon', 'Dark', 'Steel', 'Fairy']) {
    const formName = t === 'Normal' ? 'Arceus' : `Arceus (${t})`;
    const slug = t.toLowerCase();
    const entry = { ...base, name: formName, types: [t], art };
    entry.art = t === 'Normal' ? `${home}/493.png` : `${home}/493-${slug}.png`;
    BY_NAME.set(formName.toLowerCase(), entry);
    BY_NAME.set(`arceus-${slug}`, entry);
  }
}

/** True when the bundled dex is present (dexdata.js is part of the build). */
export function ready() {
  ensureIndexes();
  return MONS.length > 0;
}

export function count() {
  ensureIndexes();
  return BY_ID.size;
}

// ── Lookups ──────────────────────────────────────────────────────────────

export function getPokemonData(pokemonId) {
  if (!ready()) return null;
  const id = Number(pokemonId);
  return Number.isFinite(id) ? (BY_ID.get(id) || null) : null;
}

export function getPokemonByName(name) {
  if (!ready() || !name) return null;
  return BY_NAME.get(String(name).toLowerCase()) || null;
}

function norm(s) {
  return String(s)
    .replace(/-/g, ' ').replace(/\./g, ' ').replace(/'/g, '')
    .split(/\s+/).filter(Boolean).join(' ');
}

/** Exact match, then prefix/normalized variants (port of get_pokemon_by_name_fuzzy). */
export function getPokemonByNameFuzzy(name) {
  if (!ready() || !name) return null;
  const direct = getPokemonByName(name);
  if (direct) return direct;
  const low = String(name).toLowerCase().trim();
  if (!low) return null;
  const nlow = norm(low);
  const variants = [low, nlow, low.replace(/-/g, ''), nlow.replace(/ /g, '')];
  for (const [key, entry] of BY_NAME) {
    if (variants.some((v) => key.startsWith(v)) || variants.includes(norm(key))) {
      return entry;
    }
  }
  // Numeric id fallback ("445", "#445").
  const digits = low.replace(/^\D+|\D+$/g, '');
  if (digits && /^\d+$/.test(digits)) return getPokemonData(Number(digits));
  return null;
}

/** Official artwork URL (PNG) — constructed from the dex id (no sprite
 *  fields are bundled); forms may carry their own `art`. */
export function artworkUrl(pokemon, shiny = false) {
  if (!pokemon) return '';
  if (!shiny && pokemon.art) return pokemon.art;
  const id = pokemon.id;
  const base = 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork';
  return shiny ? `${base}/shiny/${id}.png` : `${base}/${id}.png`;
}

// ── Display helpers (ported from Forge data.py / pokemon_data.py) ────────

export function statAbbr(stat) {
  return STAT_MAP[stat] || String(stat).toUpperCase();
}

/** Min/max at level 50 (0 IV/0 EV neg nature vs 31 IV/252 EV pos nature). */
export function calculateStatRange(base, stat) {
  let minStat;
  let maxStat;
  if (stat === 'hp') {
    minStat = Math.floor((2 * base) * 50 / 100) + 50 + 10;
    maxStat = Math.floor((2 * base + 31 + 63) * 50 / 100) + 50 + 10;
  } else {
    minStat = Math.floor(((2 * base + 0 + 0) * 50 / 100 + 5) * 0.9);
    maxStat = Math.floor(((2 * base + 31 + 63) * 50 / 100 + 5) * 1.1);
  }
  return [minStat, maxStat];
}

const NATURES_BY_TOP = {
  hp: ['Hardy', 'Docile', 'Serious', 'Bashful'],
  attack: ['Adamant', 'Lonely', 'Naughty', 'Brave'],
  defense: ['Bold', 'Impish', 'Relaxed', 'Lax'],
  sp_atk: ['Modest', 'Mild', 'Rash', 'Quiet'],
  sp_def: ['Calm', 'Gentle', 'Careful', 'Sassy'],
  speed: ['Timid', 'Jolly', 'Hasty', 'Naive'],
};

export function bestNatures(baseStats) {
  const bs = baseStats || {};
  let top = 'hp';
  for (const s of STAT_ORDER) {
    if ((bs[s] || 0) > (bs[top] || 0)) top = s;
  }
  // Python: max() keeps the FIRST maximal stat (stable) — same result.
  return NATURES_BY_TOP[top] || NATURES_BY_TOP.hp;
}

/** Pick the standard competitive nature for a build category. */
export function natureFor(buildKey, baseStats) {
  const bs = baseStats || {};
  if (buildKey === 'atk') {
    return Number(bs.speed || 0) >= 100 ? 'Jolly' : 'Adamant';
  }
  if (buildKey === 'spatk') {
    return Number(bs.speed || 0) >= 100 ? 'Timid' : 'Modest';
  }
  if (buildKey === 'def') return 'Bold';
  if (buildKey === 'spdef') return 'Calm';
  if (buildKey === 'atkspatk') return 'Naive'; // +SPE -DEF mixed attacker
  if (buildKey === 'bulk') return 'Bold';
  return 'Hardy';
}

/** Competitive stat value at level 100 (Forge-style formula). */
export function statAt100(base, stat, iv = 31, ev = 252, naturePlus = false, natureMinus = false) {
  if (stat === 'hp') return Math.floor((2 * base + iv + Math.floor(ev / 4)) * 100 / 100) + 100 + 10;
  let val = Math.floor((2 * base + iv + Math.floor(ev / 4)) * 100 / 100) + 5;
  if (naturePlus) val = Math.floor(val * 1.1);
  else if (natureMinus) val = Math.floor(val * 0.9);
  return val;
}

/** Classic 252/252/4 spreads per build category. */
export function recommendedEvs(buildKey) {
  const spreads = {
    atk: { attack: 252, speed: 252, hp: 4 },
    spatk: { sp_atk: 252, speed: 252, hp: 4 },
    def: { hp: 252, defense: 252, sp_def: 4 },
    spdef: { hp: 252, sp_def: 252, defense: 4 },
    atkspatk: { attack: 252, sp_atk: 252, speed: 4 },
    bulk: { hp: 252, defense: 128, sp_def: 128 },
  };
  return { ...(spreads[buildKey] || spreads.atk) };
}

/** Sensible held-item shortlist per category (Forge shop staples). */
export function heldItemsFor(buildKey) {
  const items = {
    atk: ['Life Orb', 'Choice Band', 'Choice Scarf', 'Loaded Dice'],
    spatk: ['Choice Specs', 'Life Orb', 'Choice Scarf', 'Expert Belt'],
    def: ['Leftovers', 'Rocky Helmet', 'Sitrus Berry', 'Flame Orb'],
    spdef: ['Leftovers', 'Assault Vest', 'Sitrus Berry', 'Poison Barb'],
    atkspatk: ['Life Orb', 'Expert Belt', 'Choice Scarf', 'Silk Scarf'],
    bulk: ['Leftovers', 'Rocky Helmet', 'Sitrus Berry', 'Eviolite'],
  };
  return [...(items[buildKey] || items.atk)];
}

export function evYieldDisplay(evYields) {
  const ev = evYields || {};
  const parts = [];
  for (const stat of STAT_ORDER) {
    const val = ev[stat] || 0;
    if (val > 0) parts.push(`${val} ${statAbbr(stat)}`);
  }
  return parts.length ? parts.join(', ') : 'None';
}

export function genderDisplay(genderRate) {
  const rate = Number(genderRate);
  if (!Number.isFinite(rate)) return 'Unknown';
  if (rate === -1) return 'Genderless';
  const male = (8 - rate) / 8 * 100;
  const female = rate / 8 * 100;
  return `${male.toFixed(0)}% male / ${female.toFixed(0)}% female`;
}

export function dexNumber(pokemonId) {
  const id = Number(pokemonId);
  if (!Number.isFinite(id)) return String(pokemonId);
  return `#${String(id).padStart(4, '0')}`;
}

/** "Blaze / Solar Power (hidden)" — hidden abilities flagged in place. */
export function abilitiesDisplay(pokemon) {
  const list = (pokemon && pokemon.abilities) || [];
  if (!list.length) return '—';
  return list.map((a) => (a.hidden ? `${a.name} (hidden)` : a.name)).join(' / ');
}

// ── Type weakness (port of forge.data.get_type_effectiveness) ────────────
// TYPE_CHART.effectiveness is keyed by DEFENDING type: {weak, resist,
// immune} list ATTACKING types (×2, ×0.5, ×0). Multipliers multiply across
// both defending types, so dual types yield 4× / 0.25× correctly.

export function typeEffectiveness(defendingTypes) {
  const eff = (TYPE_CHART && TYPE_CHART.effectiveness) || {};
  const allTypes = (TYPE_CHART && TYPE_CHART.types) || [];
  const multipliers = {};
  for (const t of allTypes) multipliers[t] = 1.0;
  for (const dtype of defendingTypes || []) {
    const data = eff[dtype] || {};
    for (const t of data.weak || []) multipliers[t] = (multipliers[t] ?? 1.0) * 2.0;
    for (const t of data.resist || []) multipliers[t] = (multipliers[t] ?? 1.0) * 0.5;
    for (const t of data.immune || []) multipliers[t] = 0.0;
  }
  const weak = Object.keys(multipliers).filter((t) => multipliers[t] >= 2.0);
  const resist = Object.keys(multipliers).filter((t) => multipliers[t] > 0 && multipliers[t] <= 0.5);
  const immune = Object.keys(multipliers).filter((t) => multipliers[t] === 0.0);
  return { weak, resist, immune, multipliers };
}

export { TYPE_CHART };

// ── Move views ───────────────────────────────────────────────────────────

function moveTuple(idx) {
  const m = MOVES[idx];
  if (!m) return null;
  return {
    name: m[0], type: m[1], power: m[2], accuracy: m[3], category: m[4],
    pp: m[5] ?? null, description: m[6] || '',
  };
}

/** category: levelup | tm | tutor | egg — rows shaped like the Python
 *  dump entries ({name,type,power,accuracy,category[,level]}). */
export function movesFor(pokemon, category) {
  const raw = pokemon && pokemon._raw;
  if (!raw) return [];
  const out = [];
  if (category === 'levelup') {
    // Flat [level, moveIdx] pairs.
    for (let k = 0; k + 1 < raw.lv.length; k += 2) {
      const t = moveTuple(raw.lv[k + 1]);
      if (!t) continue;
      t.level = raw.lv[k];
      out.push(t);
    }
    return out;
  }
  let idxs;
  if (category === 'tm') idxs = raw.tm;
  else if (category === 'tutor') idxs = raw.tu;
  else if (category === 'egg') idxs = raw.eg;
  else return [];
  for (const idx of idxs) {
    const t = moveTuple(idx);
    if (t) out.push(t);
  }
  return out;
}

/** Flat move rows for /mv: {name,type,power,accuracy,category,source}
 *  with source "Lv.X" | "TM" | "Tutor" | "Egg" (port of all_move_rows). */
const ROW_CACHE = new Map();

export function allMoveRows(pokemon) {
  const raw = pokemon && pokemon._raw;
  if (!raw) return [];
  const pid = raw.i;
  const cached = ROW_CACHE.get(pid);
  if (cached) return cached;
  const rows = [];
  const seen = new Set();
  const push = (m, source) => {
    if (!m || !m.name) return;
    const key = `${m.name}|${source}`;
    if (seen.has(key)) return;
    seen.add(key);
    rows.push({
      name: m.name,
      type: m.type || 'Normal',
      power: m.power ?? null,
      accuracy: m.accuracy ?? null,
      category: m.category || 'Status',
      source,
    });
  };
  for (const m of movesFor(pokemon, 'levelup')) {
    // level 0 = "no fixed level" (evolved/initial) — label as Lv.1.
    push(m, m.level ? `Lv.${m.level}` : 'Lv.1');
  }
  for (const m of movesFor(pokemon, 'tm')) push(m, 'TM');
  for (const m of movesFor(pokemon, 'tutor')) push(m, 'Tutor');
  for (const m of movesFor(pokemon, 'egg')) push(m, 'Egg');
  ROW_CACHE.set(pid, rows);
  return rows;
}

// ── Move-name lookup (/mv <move> — the move half of the command) ─────────

/** name (lowercased) -> move index. Built once per isolate. */
let MOVE_INDEX = null;

function ensureMoveIndex() {
  if (MOVE_INDEX) return;
  MOVE_INDEX = new Map();
  for (let i = 0; i < MOVES.length; i += 1) {
    MOVE_INDEX.set(MOVES[i][0].toLowerCase(), i);
  }
}

/** Exact move lookup by name (case-insensitive). */
export function getMoveByName(name) {
  if (!name) return null;
  ensureMoveIndex();
  const idx = MOVE_INDEX.get(String(name).toLowerCase().trim());
  if (idx === undefined) return null;
  return { idx, ...moveTuple(idx) };
}

/** Exact → normalized → prefix → contains (ordered; never a pokemon). */
export function getMoveByNameFuzzy(query) {
  if (!query) return null;
  ensureMoveIndex();
  const low = String(query).toLowerCase().trim();
  if (!low) return null;
  const exact = MOVE_INDEX.get(low);
  if (exact !== undefined) return { idx: exact, ...moveTuple(exact) };
  // Alphanumeric skeleton matches across spacing/punct variants:
  // "flame thrower" → flamethrower, "u turn" → u-turn, "mud-slap" → mudslap.
  const skel = (s) => s.replace(/[^a-z0-9]/g, '');
  const qskel = skel(low);
  for (const [key, idx] of MOVE_INDEX) {
    if (skel(key) === qskel) return { idx, ...moveTuple(idx) };
  }
  // Prefix, then substring — first in dex order wins.
  for (const [key, idx] of MOVE_INDEX) {
    if (key.startsWith(low) || skel(key).startsWith(qskel)) {
      return { idx, ...moveTuple(idx) };
    }
  }
  for (const [key, idx] of MOVE_INDEX) {
    if (key.includes(low) || skel(key).includes(qskel)) {
      return { idx, ...moveTuple(idx) };
    }
  }
  return null;
}

/** Learnset info for a move card: totals + a few level-up examples.
 *  One linear pass over the 1025-entry table (sub-millisecond, no cache
 *  needed — /mv is a low-traffic query). */
export function moveLearners(moveIdx) {
  const out = { total: 0, levelUpCount: 0, tmCount: 0, tutorCount: 0, eggCount: 0, levelUp: [] };
  for (const entry of MONS) {
    let learns = false;
    for (let k = 0; k + 1 < entry.lv.length; k += 2) {
      if (entry.lv[k + 1] === moveIdx) {
        learns = true;
        out.levelUpCount += 1;
        if (out.levelUp.length < 6) {
          out.levelUp.push({ name: entry.n, level: entry.lv[k] || 1 });
        }
        break;
      }
    }
    if (entry.tm.includes(moveIdx)) { learns = true; out.tmCount += 1; }
    if (entry.tu.includes(moveIdx)) { learns = true; out.tutorCount += 1; }
    if (entry.eg.includes(moveIdx)) { learns = true; out.eggCount += 1; }
    if (learns) out.total += 1;
  }
  return out;
}
