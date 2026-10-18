// Generate tgcloud/lib/dexdata.js from the Forge generation dumps
// (sibling forge-main checkout, or POKEMON_DATA_DIR).
//
//   node tools/build_dex.mjs      (or: npm run dex)
//
// Encoding — a compact subset of the dumps; everything /poke /mv /build
// /data display (ported parity with help/helpbot/{pokemon,pokedex_ui,
// build_ui}.py and forge/modules/pokedex/data.py):
//   dropped: flavor_text, genus, height, weight, base_exp, habitat,
//            egg_groups, held_items, cry, sprites (the artwork URL is
//            constructed from the dex id at runtime)
//   global move table [name, type, power, accuracy, category, pp, description]
//   per-mon: i id, n name, t types, s base_stats[], v ev_yields[],
//            c catch_rate, g gender_rate, L legendary, M mythical,
//            a [[abilityName, hidden], …],
//            lv [level, moveIdx, …], tm/tu/eg [moveIdx, …]
//   TYPE_CHART: { types, effectiveness } from data/type_chart.json
//               (powers /data's Weakness view — same JSON the Python
//               bot reads via forge.data.get_type_effectiveness)
// Learnset entries are de-duplicated per source (first wins), matching
// pokemon.all_move_rows' name|source dedupe. A few gen_09 tutor entries
// are bare strings (e.g. "Sunny Day") — they resolve against the global
// move table by name so no learnset row is lost. JSON is valid JS, so the
// emitted module is written as plain literals (no parsing at import).
import { readFileSync, writeFileSync, readdirSync, statSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

const repoRoot = resolve(import.meta.dirname, '..');

// ── locate data dir (same search order as help/helpbot/pokemon.py) ───────
function dataDir() {
  const candidates = [];
  if (String(process.env.POKEMON_DATA_DIR || '').trim()) {
    candidates.push(String(process.env.POKEMON_DATA_DIR).trim());
  }
  candidates.push(join(repoRoot, '..', 'forge-main', 'forge', 'data', 'generations'));
  candidates.push(join(repoRoot, 'data', 'generations'));
  for (const dir of candidates) {
    if (existsSync(dir) && readdirSync(dir).some((f) => f.startsWith('gen_') && f.endsWith('.json'))) {
      return dir;
    }
  }
  return null;
}

const dir = dataDir();
if (!dir) {
  console.error('build_dex: no gen_*.json found — set POKEMON_DATA_DIR ' +
    'or keep the forge-main checkout next to this repo.');
  process.exit(1);
}

// ── read dumps ───────────────────────────────────────────────────────────
const files = readdirSync(dir)
  .filter((f) => /^gen_\d+\.json$/.test(f))
  .sort();
if (!files.length) {
  console.error(`build_dex: no gen_*.json in ${dir}`);
  process.exit(1);
}

const STAT_ORDER = ['hp', 'attack', 'defense', 'sp_atk', 'sp_def', 'speed'];

/** Global move table; name -> index. First seen wins. */
const moves = [];
const moveIndex = new Map();
let moveConflicts = 0;
/** Bare-string learnset entries with no global move row (skipped). */
let unresolvedStrings = 0;

/** `normal`/`FIRE` → `Normal` — the dumps mix type casing across gens. */
function typeCase(t) {
  const s = String(t || 'Normal').toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function moveIdx(m) {
  // Bare-string entries (a handful of gen_09 tutor rows) name a move that
  // already exists as an object elsewhere — resolve by name, never invent
  // stats for it.
  if (typeof m === 'string') {
    const idx = moveIndex.get(m);
    if (idx === undefined) unresolvedStrings += 1;
    return idx === undefined ? -1 : idx;
  }
  const name = m.name || '';
  if (!name) return -1;
  const type = typeCase(m.type);
  let idx = moveIndex.get(name);
  if (idx === undefined) {
    idx = moves.length;
    moves.push([name, type,
      m.power ?? null, m.accuracy ?? null, m.category || 'Status',
      m.pp ?? null, m.description || '']);
    moveIndex.set(name, idx);
    return idx;
  }
  // Same name, different stats → keep the first (global table is shared).
  const prev = moves[idx];
  if (prev[1] !== type || prev[2] !== (m.power ?? null)
      || prev[3] !== (m.accuracy ?? null) || prev[4] !== (m.category || 'Status')) {
    moveConflicts += 1;
  }
  // Extra fields: adopt pp/description when the first sighting lacked them.
  if (prev[5] == null && m.pp != null) prev[5] = m.pp;
  if (!prev[6] && m.description) prev[6] = m.description;
  return idx;
}

let sourceDupes = 0;

function dedupList(list) {
  const seen = new Set();
  const out = [];
  for (const m of list || []) {
    const idx = moveIdx(m);
    if (idx < 0) continue;
    if (seen.has(idx)) {
      sourceDupes += 1;
      continue;
    }
    seen.add(idx);
    out.push(idx);
  }
  return out;
}

const mons = [];
const byId = new Set();
let learnsetDupes = 0;

for (const file of files) {
  const raw = JSON.parse(readFileSync(join(dir, file), 'utf8'));
  const ids = Object.keys(raw.by_id || {}).sort((a, b) => Number(a) - Number(b));
  for (const id of ids) {
    const p = raw.by_id[id];
    if (byId.has(id)) continue;
    byId.add(id);

    // level-up: keep [level, idx] pairs, de-dupe by move index (first wins)
    const lvSeen = new Set();
    const lv = [];
    for (const m of p.moves || []) {
      const idx = moveIdx(m);
      if (idx < 0 || lvSeen.has(idx)) {
        if (idx >= 0) learnsetDupes += 1;
        continue;
      }
      lvSeen.add(idx);
      lv.push(Number(m.level) || 0, idx);
    }

    mons.push({
      i: Number(p.id),
      n: p.name || `#${p.id}`,
      t: (p.types || []).filter(Boolean).map(typeCase),
      s: STAT_ORDER.map((k) => Number(p.base_stats?.[k]) || 0),
      v: STAT_ORDER.map((k) => Number(p.ev_yields?.[k]) || 0),
      c: p.catch_rate ?? null,
      g: p.gender_rate ?? -1,
      L: Boolean(p.is_legendary),
      M: Boolean(p.is_mythical),
      a: (p.abilities || [])
        .filter((x) => x && x.name)
        .map((x) => [x.name, Boolean(x.hidden)]),
      lv,
      tm: dedupList(p.tm_moves),
      tu: dedupList(p.tutor_moves),
      eg: dedupList(p.egg_moves),
    });
  }
}

// ── type chart (data/type_chart.json — powers /data's Weakness view) ─────
const chartPath = join(dir, '..', 'type_chart.json');
let typeChart;
try {
  const chart = JSON.parse(readFileSync(chartPath, 'utf8'));
  if (!Array.isArray(chart.types) || typeof chart.effectiveness !== 'object') {
    throw new Error('unexpected shape (types[] / effectiveness{})');
  }
  typeChart = { types: chart.types, effectiveness: chart.effectiveness };
} catch (e) {
  console.error(`build_dex: cannot read type chart at ${chartPath} — ${e.message}`);
  process.exit(1);
}

// ── emit ─────────────────────────────────────────────────────────────────
const outPath = join(repoRoot, 'tgcloud', 'lib', 'dexdata.js');
mkdirSync(dirname(outPath), { recursive: true });

const counts = {
  mons: mons.length,
  moves: moves.length,
};
const header =
  `// GENERATED by tools/build_dex.mjs — do not edit by hand.\n` +
  `// Offline Pokédex subset: ${counts.mons} pokemon, ${counts.moves} moves + type chart.\n` +
  `// Regenerate: node tools/build_dex.mjs   (source: ${dir.replace(/\\/g, '/')})\n` +
  `//\n` +
  `// MOVES: [name, type, power, accuracy, category, pp, description]\n` +
  `//        (power/accuracy/pp may be null; description is the effect text)\n` +
  `// MONS:  i id, n name, t types, s [hp,atk,def,sp_atk,sp_def,speed],\n` +
  `//        v ev_yields[], c catch_rate, g gender_rate (-1 genderless),\n` +
  `//        L legendary, M mythical, a [[abilityName, hidden], …],\n` +
  `//        lv [level, moveIdx, …], tm/tu/eg [moveIdx, …]  (referencing MOVES)\n` +
  `// TYPE_CHART: { types[18], effectiveness{defType:{weak,resist,immune}} }\n` +
  `export const MOVES = ` + JSON.stringify(moves) + `;\n\n` +
  `export const MONS = ` + JSON.stringify(mons) + `;\n\n` +
  `export const TYPE_CHART = ` + JSON.stringify(typeChart) + `;\n`;

writeFileSync(outPath, header, 'utf8');
const kb = Math.round(statSync(outPath).size / 102.4) / 10;
console.log(`build_dex: ${counts.mons} pokemon, ${counts.moves} moves + ` +
  `${typeChart.types.length} types → tgcloud/lib/dexdata.js (${kb} KB)` +
  `${moveConflicts ? `, ${moveConflicts} move-stat conflicts (first wins)` : ''}` +
  `${learnsetDupes + sourceDupes ? `, ${learnsetDupes + sourceDupes} learnset dupes dropped` : ''}` +
  `${unresolvedStrings ? `, ${unresolvedStrings} string learnset entries unresolved (skipped)` : ''}`);
