// Local tests for the SDK-free modules (knowledge, kb, sanitize, emoji,
// style, pokemon, dexui, dataui, pokecache) + dexdata integrity against the
// forge-main generation dumps (when the sibling checkout exists). Importing
// dexui/dataui also proves that stack is sdk-free — a stray `from 'sdk'`
// would fail to resolve under plain Node.
// Run: node tools/test_pure.mjs  — or: npm run kb && npm run dex && npm run check
// Mirrors the Python gates in help/selftest.py where they overlap.

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { FILES, CHUNKS } from '../tgcloud/lib/knowledge.js';
import * as kb from '../tgcloud/lib/kb.js';
import {
  splitMessage, stripPlainEmoji, markdownToHtml, sanitizeHtml, stripTags,
} from '../tgcloud/lib/sanitize.js';
import { E, uiTag, stripCustomEmoji, uiGlyph } from '../tgcloud/lib/emoji.js';
import { PRIMARY, SUCCESS, DANGER, htmlEscape } from '../tgcloud/lib/style.js';
import * as pokemon from '../tgcloud/lib/pokemon.js';
import * as dexui from '../tgcloud/lib/dexui.js';
import * as dataui from '../tgcloud/lib/dataui.js';
import * as pokecache from '../tgcloud/lib/pokecache.js';
import { MOVES, MONS, TYPE_CHART } from '../tgcloud/lib/dexdata.js';

let failed = 0;
function check(name, ok, detail = '') {
  if (ok) console.log(`ok    ${name}`);
  else {
    failed += 1;
    console.error(`FAIL  ${name}${detail ? ` — ${detail}` : ''}`);
  }
}

// ── bundled knowledge (parity with the Python knowledge base) ────────────
check('knowledge: 16 files', FILES.length === 16, `got ${FILES.length}`);
check('knowledge: 138 chunks', CHUNKS.length === 138, `got ${CHUNKS.length}`);
check('knowledge: no secrets in bundle',
  !JSON.stringify(CHUNKS).match(/api[_-]?key|sk-proj|gsk_/i));
check('knowledge: every chunk has fields',
  CHUNKS.every((c) => c.source && c.text));

const stats = kb.stats();
check('kb.stats: 138 chunks', stats.chunks === 138, `got ${stats.chunks}`);
check('kb.stats: 16 files', stats.files === 16, `got ${stats.files}`);
check('kb.stats: 161 command names', stats.commands === 161, `got ${stats.commands}`);

// ── kb behaviour ──────────────────────────────────────────────────────────
const line = kb.commandLine('hunt');
check('commandLine("hunt")', typeof line === 'string' && line.startsWith('- `/hunt`'),
  JSON.stringify(line));
const hits = kb.search('shiny odds', 3);
check('search("shiny odds") returns hits', hits.length > 0);
check('search hits shaped {chunk,score}',
  hits.every((h) => h.chunk && typeof h.score === 'number' && h.score > 0));
check('search prefers commands for "/hunt"',
  kb.search('/hunt', 1)[0]?.chunk.text.toLowerCase().includes('hunt'),
  kb.search('/hunt', 1)[0]?.chunk.source);
check('guides() non-empty', kb.guides().length >= 10,
  `got ${kb.guides().length}`);
check('guideText("commands")', typeof kb.guideText('commands') === 'string');
check('guideTitle returns title', kb.guideTitle('commands').length > 0);
check('fileForTerm("battle") → 03-battles-and-gyms',
  kb.fileForTerm('battle') === '03-battles-and-gyms',
  String(kb.fileForTerm('battle')));
check('fileForTerm with no match → null (matches Python)',
  kb.fileForTerm('shiny') === null, String(kb.fileForTerm('shiny')));
check('contextFor() returns [text, sources]',
  (() => {
    const [ctx, src] = kb.contextFor('how do shiny odds work', 6000);
    return typeof ctx === 'string' && ctx.length > 0 && Array.isArray(src);
  })());

// ── sanitize pipeline ────────────────────────────────────────────────────
check('markdownToHtml bold', markdownToHtml('a **b** c').includes('<b>b</b>'));
check('sanitizeHtml strips script',
  !sanitizeHtml('<p>ok</p><script>alert(1)</script>').includes('<script>'));
check('stripTags removes tags', stripTags('<b>hi</b> there') === 'hi there');

const long = 'x'.repeat(9000);
const parts = splitMessage(long);
check('splitMessage splits at 3800', parts.length > 1 && parts.every((p) => p.length <= 3800));
check('splitMessage lossless', parts.join('') === long);

const mixed = 'shiny ✨ <tg-emoji emoji-id="5918098311184654030">✨</tg-emoji> pokemon';
const stripped = stripPlainEmoji(mixed);
const outsideTags = stripped.replace(/<tg-emoji[^>]*>[\s\S]*?<\/tg-emoji>/g, '');
check('stripPlainEmoji removes unicode emoji', !/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(outsideTags),
  JSON.stringify(stripped));
check('stripPlainEmoji keeps <tg-emoji>', stripped.includes('<tg-emoji'));

// ── emoji / premium UI rules ─────────────────────────────────────────────
check('E.CROSS non-empty', typeof E.CROSS === 'string' && E.CROSS.length > 0);
check('uiTag("chat") is a <tg-emoji> tag', uiTag('chat').startsWith('<tg-emoji'));
check('stripCustomEmoji unwraps to the fallback glyph',
  stripCustomEmoji('<tg-emoji emoji-id="5918098311184654030">🔥</tg-emoji>') === '🔥');
check('uiGlyph has no empty string for chat', uiGlyph('chat') !== '');

// ── style constants (Bot API 10.1 button styles) ────────────────────────
check('style: primary/success/danger',
  PRIMARY === 'primary' && SUCCESS === 'success' && DANGER === 'danger');
check('style: htmlEscape parity with Python html.escape',
  htmlEscape('a<b>&"c"') === 'a&lt;b&gt;&amp;&quot;c&quot;');

// ── offline Pokédex (dexdata + pokemon + dexui) ─────────────────────────
check('dex: ready + 1025 pokemon', pokemon.ready() && pokemon.count() === 1025,
  `got ${pokemon.count()}`);

const charizard = pokemon.getPokemonByName('charizard');
check('dex: charizard id 6 Fire/Flying',
  Boolean(charizard) && charizard.id === 6 && charizard.types.join('/') === 'Fire/Flying',
  JSON.stringify(charizard && { id: charizard.id, types: charizard.types }));
check('dex: fuzzy prefix "char" → Charmander',
  pokemon.getPokemonByNameFuzzy('char')?.id === 4,
  String(pokemon.getPokemonByNameFuzzy('char')?.id));
check('dex: fuzzy digits "445" → Garchomp',
  pokemon.getPokemonByNameFuzzy('445')?.id === 445);
check('dex: fuzzy "#0006" → Charizard',
  pokemon.getPokemonByNameFuzzy('#0006')?.id === 6);
check('dex: fuzzy "mr mime" → Mr. Mime',
  pokemon.getPokemonByNameFuzzy('mr mime')?.id === 122,
  String(pokemon.getPokemonByNameFuzzy('mr mime')?.id));
check('dex: artwork url constructed from id',
  pokemon.artworkUrl(charizard) ===
  'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/6.png');
check('dex: arceus-fire form synthesized', (() => {
  const f = pokemon.getPokemonByName('arceus-fire');
  return Boolean(f) && f.id === 493 && f.types.join('/') === 'Fire'
    && f.art.includes('493-fire.png');
})());
check('dex: genderDisplay(-1) → Genderless',
  pokemon.genderDisplay(-1) === 'Genderless');
check('dex: dexNumber(6) → #0006', pokemon.dexNumber(6) === '#0006');
check('dex: ev yield display',
  pokemon.evYieldDisplay({ hp: 0, attack: 0, defense: 0, sp_atk: 1, sp_def: 0, speed: 0 })
  === '1 SP.ATK');
check('dex: stat range hp sanity (base 45 → 105–152)', (() => {
  const [lo, hi] = pokemon.calculateStatRange(45, 'hp');
  return lo === 105 && hi === 152;
})(), JSON.stringify(pokemon.calculateStatRange(45, 'hp')));

const chRows = pokemon.allMoveRows(charizard);
check('dex: charizard has move rows', chRows.length > 0, `got ${chRows.length}`);
check('dex: move rows have source labels',
  chRows.every((r) => /^(Lv\.\d+|TM|Tutor|Egg)$/.test(r.source)),
  JSON.stringify(chRows[0] || null));
check('dex: bulbasaur level-up starts with Tackle',
  pokemon.allMoveRows(pokemon.getPokemonByName('bulbasaur'))[0]?.name === 'Tackle');
check('dex: movesFor(levelup) carries levels',
  pokemon.movesFor(pokemon.getPokemonByName('bulbasaur'), 'levelup')[0]?.level === 1);

// ── /mv command view ────────────────────────────────────────────────────
check('/mv: usage without args', dexui.mvView('').kind === 'usage');
check('/mv: unknown → notfound', dexui.mvView('notarealmon99999').kind === 'notfound');
const mv = dexui.mvView('garchomp');
check('/mv: garchomp ok + prev/next row',
  mv.kind === 'ok' && mv.rows.length === 1 && mv.rows[0].length >= 1,
  JSON.stringify({ kind: mv.kind, rows: mv.rows }));
check('/mv: rich page carries premium type tags', mv.rich.includes('<tg-emoji'));
check('/mv: classic shows page footer', mv.classic.includes('Page 1/'));
check('/mv: nav buttons styled blue/green',
  mv.rows[0].some((b) => b[0] === 'Next ▶' && b[2] === SUCCESS));
const mvClamped = dexui.mvPageView(charizard, 999);
check('/mv: page clamped to last', (() => {
  const m = mvClamped.classic.match(/Page (\d+)\/(\d+)/);
  return Boolean(m) && m[1] === m[2];
})(), mvClamped.classic.slice(-40));

// ── /poke command view + pk| callbacks ──────────────────────────────────
check('/poke: usage without args', dexui.pokeView('').kind === 'usage');
const poke = dexui.pokeView('charizard');
check('/poke: ok + photo + classic caption',
  poke.kind === 'ok' && poke.photo.endsWith('/6.png')
  && poke.caption.includes('Max Level: 100'),
  JSON.stringify({ kind: poke.kind, photo: poke.photo }));
check('/poke: unicode labels + styles on buttons',
  poke.rows.flat().some((b) => b[0] === '💎 IVs' && b[2] === PRIMARY)
  && poke.rows.flat().some((b) => b[0] === '🎁 Moves' && b[2] === SUCCESS)
  && poke.rows.flat().some((b) => b[0] === '✖ Close' && b[2] === DANGER));
check('/poke: callback format pk|6|ivs|0',
  poke.rows.flat().some((b) => b[1] === 'pk|6|ivs|0'));
const ivs = dexui.pokeCallbackView(charizard, 'ivs', 0);
check('/poke ivs: natures + Lv.50 ranges',
  ivs.classic.includes('Best natures:') && ivs.classic.includes('Stat range at Lv.50'));
check('/poke ivs: hides own button, has Back',
  ivs.rows.flat().every((b) => !b[1].endsWith('|ivs|0'))
  && ivs.rows.flat().some((b) => b[1] === 'pk|6|main|0'));
const lvl = dexui.pokeCallbackView(charizard, 'levelup', 0);
check('/poke levelup: list + Back',
  lvl.rich.includes('Level-up moves')
  && lvl.rows.flat().some((b) => b[1] === 'pk|6|main|0'));
const mvmenu = dexui.pokeCallbackView(charizard, 'mvmenu', 0);
check('/poke mvmenu: four lists + Back',
  mvmenu.rows.flat().length >= 5,
  JSON.stringify(mvmenu.rows));

// ── /build (alias /set) + bd| callbacks ─────────────────────────────────
check('/build: usage without args', dexui.buildView('').kind === 'usage');
check('/build: unknown → notfound', dexui.buildView('zzzznomon').kind === 'notfound');
const build = dexui.buildView('charizard');
check('/build: ok + menu (4 categories + Close)',
  build.kind === 'ok' && build.rows.length === 5,
  JSON.stringify(build.rows));
check('/build: category callback format bd|6|atk|sum|0',
  build.rows.flat().some((b) => b[1] === 'bd|6|atk|sum|0' && b[2] === PRIMARY));
const rec = dexui.recommendBuild(charizard, 'atk');
check('/build atk: Jolly for base Speed 100', rec.nature === 'Jolly', rec.nature);
check('/build atk: EVs + Life Orb + ≤6 moves',
  rec.evs.attack === 252 && rec.items.includes('Life Orb')
  && rec.moves.length > 0 && rec.moves.length <= 6,
  JSON.stringify({ evs: rec.evs, moves: rec.moves.length }));
check('/build atk: six stat lines with values',
  rec.stats.length === 6 && rec.stats.every((s) => typeof s.value === 'number' && s.value > 0));
const sum = dexui.buildCallbackView(charizard, 'atk', 'sum', 0);
check('/build sum: nature + EV lines',
  sum.classic.includes('Nature:') && sum.classic.includes('EVs:'));
check('/build sum: Moves + Back buttons',
  sum.rows.flat().some((b) => b[1] === 'bd|6|atk|mv|0')
  && sum.rows.flat().some((b) => b[1] === 'bd|6|menu|menu|0'));
const bmv = dexui.buildCallbackView(charizard, 'atk', 'mv', 0);
check('/build mv: Summary + Close buttons',
  bmv.rows.flat().some((b) => b[1] === 'bd|6|atk|sum|0')
  && bmv.rows.flat().some((b) => b[1].includes('|close|')));
check('/build menu round-trip',
  dexui.buildCallbackView(charizard, 'menu', 'menu', 0).rows.length === 5);
check('/build unknown category → menu + notice',
  dexui.buildCallbackView(charizard, 'nope', 'sum', 0).classic.includes('Unknown category'));

// ── move dataset — /mv move lookup (Pokémon first, then move card) ───────
const flame = pokemon.getMoveByName('flamethrower');
check('/mv move: exact "flamethrower" → Fire 90 / PP 15 + effect',
  Boolean(flame) && flame.name === 'Flamethrower' && flame.type === 'Fire'
  && flame.power === 90 && flame.pp === 15 && flame.description.length > 0,
  JSON.stringify(flame));
check('/mv move: fuzzy across spacing "flame thrower"',
  pokemon.getMoveByNameFuzzy('flame thrower')?.name === 'Flamethrower',
  String(pokemon.getMoveByNameFuzzy('flame thrower')?.name));
check('/mv move: unknown move → null (both lookups)',
  pokemon.getMoveByName('notarealmove99999') === null
  && pokemon.getMoveByNameFuzzy('notarealmove99999') === null);
const mvMove = dexui.mvView('flamethrower');
check('/mv move: mvView kind "move" + card fields',
  mvMove.kind === 'move' && mvMove.rich.includes('Power: 90')
  && mvMove.classic.includes('Accuracy: 100%') && mvMove.classic.includes('PP: 15')
  && mvMove.classic.includes('Effect:'),
  JSON.stringify({ kind: mvMove.kind }));
check('/mv move: learners line non-zero (idx attached)',
  /Learned by [1-9]\d* Pokémon/.test(mvMove.classic),
  (mvMove.classic.split('\n').find((l) => l.includes('Learned by ')) || 'missing'));
check('/mv move: single card → no rows',
  Array.isArray(mvMove.rows) && mvMove.rows.length === 0,
  JSON.stringify(mvMove.rows));
check('/mv move: unknown query → notfound mentioning both',
  dexui.mvView('notarealmon99999').text.includes('Pokémon or a move'));

const flameLearners = pokemon.moveLearners(flame.idx);
check('moveLearners(flamethrower): totals + counts + examples',
  flameLearners.total > 20 && flameLearners.levelUpCount > 0
  && flameLearners.tmCount > 0 && flameLearners.levelUp.length > 0
  && flameLearners.levelUp.every((x) => x.name && Number.isFinite(x.level)),
  JSON.stringify(flameLearners));

// ── abilities (/poke IVs — new requirement, hidden flagged) ──────────────
check('abilities: charizard display + hidden flag',
  pokemon.abilitiesDisplay(charizard) === 'Blaze / Solar Power (hidden)',
  pokemon.abilitiesDisplay(charizard));
check('abilities: IVs classic + rich carry the line',
  ivs.classic.includes('Blaze') && ivs.classic.includes('Solar Power (hidden)')
  && ivs.rich.includes('Solar Power (hidden)'),
  ivs.classic.split('\n').filter((l) => l.includes('Solar')).join(' | ') || 'missing');

// ── dexdata integrity (pure — always runs) ───────────────────────────────
check('dexdata: 1025 mons / 783 moves / 18 types',
  MONS.length === 1025 && MOVES.length === 783 && TYPE_CHART.types.length === 18,
  JSON.stringify({ mons: MONS.length, moves: MOVES.length, types: TYPE_CHART.types.length }));
check('dexdata: unique ids 1..1025 in order',
  MONS.length === 1025 && new Set(MONS.map((m) => m.i)).size === 1025
  && MONS.every((m, k) => m.i === k + 1),
  JSON.stringify({ unique: new Set(MONS.map((m) => m.i)).size }));
check('dexdata: move rows shaped + typed + names unique',
  MOVES.every((m) => m.length === 7 && typeof m[0] === 'string' && m[0]
    && TYPE_CHART.types.includes(m[1])
    && ['Physical', 'Special', 'Status'].includes(m[4])
    && (m[5] === null || typeof m[5] === 'number'))
  && new Set(MOVES.map((m) => m[0])).size === MOVES.length,
  `unique names ${new Set(MOVES.map((m) => m[0])).size}`);
check('dexdata: mons shaped + every learnset index in range', MONS.every((m) => {
  if (!(typeof m.n === 'string' && m.n)) return false;
  if (!(m.t.length === 1 || m.t.length === 2)) return false;
  if (m.s.length !== 6 || m.v.length !== 6) return false;
  if (!Array.isArray(m.a)
    || !m.a.every((a) => typeof a[0] === 'string' && a[0] && typeof a[1] === 'boolean')) {
    return false;
  }
  if (m.lv.length % 2 !== 0) return false;
  for (let k = 0; k + 1 < m.lv.length; k += 2) {
    if (!Number.isInteger(m.lv[k + 1]) || m.lv[k + 1] < 0 || m.lv[k + 1] >= MOVES.length) return false;
    if (typeof m.lv[k] !== 'number') return false;
  }
  return [...m.tm, ...m.tu, ...m.eg]
    .every((i) => Number.isInteger(i) && i >= 0 && i < MOVES.length);
}));

// ── type effectiveness (powers /data Weakness view) ──────────────────────
const bulbaEff = pokemon.typeEffectiveness(['Grass', 'Poison']);
check('weakness: bulbasaur 2× Fire/Flying/Ice/Psychic, Ground neutral, Grass 0.25×',
  ['Fire', 'Flying', 'Ice', 'Psychic'].every((t) => bulbaEff.weak.includes(t))
  && bulbaEff.multipliers.Ground === 1
  && bulbaEff.multipliers.Grass === 0.25,
  JSON.stringify(bulbaEff));
const chEff = pokemon.typeEffectiveness(['Fire', 'Flying']);
check('weakness: charizard Rock 4× / Ground immune / Ice neutral (Fire 0.5 × Flying 2)',
  chEff.multipliers.Rock === 4 && chEff.multipliers.Ground === 0
  && chEff.immune.includes('Ground') && chEff.multipliers.Ice === 1,
  JSON.stringify(chEff.multipliers));
const bulbaWeak = dataui.weakBody(pokemon.getPokemonByName('bulbasaur'));
check('/data weak: sections render',
  bulbaWeak.includes('Bulbasaur Type Weaknesses') && bulbaWeak.includes('2× Weak to:')
  && bulbaWeak.includes('Resists (0.25×):'),
  bulbaWeak.slice(0, 160));

// ── /data views + d: callbacks (pure builders) ───────────────────────────
check('/data: usage + notfound texts',
  dataui.dataUsageText().includes('/data froakie')
  && dataui.dataNotFoundText().includes('Pokémon not found.'));

const dataV = dataui.dataView(charizard);
check('/data: main card body + artwork link',
  dataV.rich.includes("Charizard's Data") && dataV.rich.includes('Base Stats:')
  && dataV.rich.includes('<a href="https://raw.githubusercontent.com/'),
  dataV.rich.slice(0, 120));
check('/data: main rows are triples with d: callbacks',
  dataV.rows.length === 2
  && dataV.rows.every((row) => row.every((b) => Array.isArray(b) && b.length === 3
    && b[1].startsWith('d:')))
  && dataV.rows.flat().some((b) => b[1] === 'd:moves:6' && b[2] === SUCCESS)
  && dataV.rows.flat().some((b) => b[1] === 'd:loc:6:0' && b[2] === SUCCESS)
  && dataV.rows.flat().some((b) => b[1] === 'd:weak:6'),
  JSON.stringify(dataV.rows));

const back = dataui.backRowFor(charizard);
check('/data: Back row shape [[triple]]',
  back.length === 1 && back[0].length === 1 && back[0][0][0] === '◀ Back'
  && back[0][0][1] === 'd:back:6' && back[0][0][2] === PRIMARY,
  JSON.stringify(back));

const dataList = dataui.moveListView(charizard, 'levelup', 0, 'Tester');
check('/data mlist: header + user label',
  dataList.rich.includes('Tester') && dataList.rich.includes('Charizard — Level Up Moves'),
  dataList.rich.split('\n')[0]);
check('/data mlist: hides current category, shows the others',
  !dataList.rows.flat().some((b) => b[1] === 'd:mlist:6:levelup:0')
  && dataList.rows.flat().some((b) => b[1] === 'd:mlist:6:tm:0')
  && dataList.rows.flat().some((b) => b[1] === 'd:mlist:6:egg:0'),
  JSON.stringify(dataList.rows));
check('/data mlist: nav counter + back',
  dataList.rows.flat().some((b) => b[1] === 'd:noop:0' && b[2] === PRIMARY)
  && dataList.rows.flat().some((b) => b[1] === 'd:back:6'));
check('/data mlist: every row is rows-of-triples (coloredKbDict shape)',
  dataList.rows.every((row) => Array.isArray(row)
    && row.every((b) => Array.isArray(b) && b.length === 3)),
  JSON.stringify(dataList.rows));
const bulbaRows = dataui.movesRows(pokemon.getPokemonByName('bulbasaur'));
check('/data: empty Tutor category hidden for bulbasaur',
  !bulbaRows.flat().some((b) => b[1] === 'd:mlist:1:tutor:0')
  && bulbaRows.flat().some((b) => b[1] === 'd:mlist:1:egg:0'),
  JSON.stringify(bulbaRows));

const evoChain = {
  chain: {
    species: { name: 'charmander' },
    evolves_to: [{
      species: { name: 'charmeleon' },
      evolution_details: [{ trigger: { name: 'level-up' }, min_level: 16, is_default: true }],
      evolves_to: [{
        species: { name: 'charizard' },
        evolution_details: [{ trigger: { name: 'level-up' }, min_level: 36, is_default: true }],
        evolves_to: [],
      }],
    }],
  },
};
const evoSpecies = {
  varieties: [
    { is_default: true, pokemon: { name: 'charizard' } },
    { is_default: false, pokemon: { name: 'charizard-mega-y' } },
  ],
};
const evoText = dataui.evoBody(charizard, evoSpecies, evoChain);
check('/data evo: steps + methods + forms',
  evoText.includes('Evolutions:') && evoText.includes('Charmander')
  && evoText.includes('↳ Level 16') && evoText.includes('Charmeleon')
  && evoText.includes('↳ Level 36') && evoText.includes('Charizard Mega Y'),
  evoText.slice(0, 300));
check('/data evo: null payload → fallback',
  dataui.evoBody(charizard, null, null).includes('No evolution data available.'));

const encFixture = [
  {
    location_area: { name: 'mt-coronet-1f' },
    version_details: [
      { version: { name: 'platinum' }, encounter_details: [{ chance: 20 }] },
      { version: { name: 'diamond' }, encounter_details: [{ chance: 10 }] },
    ],
  },
  {
    location_area: { name: 'solaceon-road' },
    version_details: [{ version: { name: 'platinum' }, encounter_details: [{ chance: 5 }] }],
  },
];
const loc = dataui.locBody(charizard, encFixture, 0);
check('/data loc: grouped areas + versions + paging',
  loc.text.includes('Mt Coronet 1f') && loc.text.includes('Diamond, Platinum')
  && loc.text.includes('Solaceon Road') && loc.text.includes('Page 1/1')
  && loc.total === 2,
  JSON.stringify({ total: loc.total, head: loc.text.slice(0, 160) }));
check('/data loc: empty payload → fallback',
  dataui.locBody(charizard, null, 0).text.includes('No location data available.'));
const locRows = dataui.locRows(charizard, 0, 2);
check('/data loc: rows hide own button, carry Back',
  !locRows.flat().some((b) => b[1] === 'd:loc:6:0')
  && locRows.flat().some((b) => b[1] === 'd:back:6'),
  JSON.stringify(locRows));
check('/data: callback views (back/moves/weak/mlist sync; evo/loc → transport)',
  ['back', 'moves', 'weak'].every((a) => {
    const v = dataui.dataCallbackView(charizard, a, {}, 'T');
    return v && typeof v.rich === 'string' && v.rich.length > 0 && Array.isArray(v.rows);
  })
  && Boolean(dataui.dataCallbackView(charizard, 'mlist', { category: 'tm', page: 0 }, 'T'))
  && dataui.dataCallbackView(charizard, 'evo', {}, 'T') === null
  && dataui.dataCallbackView(charizard, 'loc', {}, 'T') === null);

// ── pokecache policy (pure — keys, TTL, URL allowlist) ───────────────────
check('pokecache: TTL 7d / prune ceiling 30d',
  pokecache.CACHE_TTL_MS === 7 * 24 * 60 * 60 * 1000
  && pokecache.CACHE_MAX_AGE_MS === 30 * 24 * 60 * 60 * 1000);
check('pokecache: keys normalise',
  pokecache.speciesKey('  Charizard ') === 'species:charizard'
  && pokecache.evoKey(6) === 'evo:6'
  && pokecache.encounterKey(445) === 'enc:445');
check('pokecache: isFresh boundary + junk',
  pokecache.isFresh(1000, 2000, 5000)
  && !pokecache.isFresh(1000, 7000, 5000)
  && !pokecache.isFresh('junk', 2000, 5000)
  && !pokecache.isFresh(9000, 2000, 5000),
  JSON.stringify({
    inside: pokecache.isFresh(1000, 2000, 5000),
    outside: pokecache.isFresh(1000, 7000, 5000),
    junk: pokecache.isFresh('junk', 2000, 5000),
    future: pokecache.isFresh(9000, 2000, 5000),
  }));
check('pokecache: URL allowlist is pokeapi.co-only',
  pokecache.allowedUrl('https://pokeapi.co/api/v2/pokemon-species/6')
  && pokecache.allowedUrl('https://pokeapi.co/api/v2/pokemon/6')
  && pokecache.allowedUrl('https://pokeapi.co/api/v2/evolution-chain/1')
  && !pokecache.allowedUrl('https://evilpokeapi.co/api/v2/pokemon/6')
  && !pokecache.allowedUrl('http://pokeapi.co/api/v2/pokemon/6')
  && !pokecache.allowedUrl('https://example.com/api/v2/pokemon/6'));

// ── secret scan over the new/changed modules ─────────────────────────────
{
  const scanFiles = ['tgcloud/lib/dataui.js', 'tgcloud/lib/pokeapi.js',
    'tgcloud/lib/pokecache.js', 'tgcloud/lib/dex.js', 'tgcloud/schema.js'];
  const secretRe = /(sk-[A-Za-z0-9]{20,}|gsk_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30}|-----BEGIN|bot\d+:[A-Za-z0-9_-]{30,})/;
  const leaks = scanFiles.filter((f) => {
    const src = readFileSync(join(resolve(import.meta.dirname, '..'), f), 'utf8');
    // No literal secrets, and the new pure modules must not import the
    // sdk-backed keyvault (a comment mentioning it is fine).
    return secretRe.test(src) || /import\s.*keyvault/.test(src);
  });
  check('secrets: new modules carry no keys / keyvault imports',
    leaks.length === 0, leaks.join(', '));
}

// ── dexdata parity vs forge-main generation dumps (sibling checkout) ─────
{
  const genDir = resolve(import.meta.dirname, '..', '..', 'forge-main',
    'forge', 'data', 'generations');
  if (!existsSync(genDir)) {
    console.log('skip  dex source parity (no forge-main sibling)');
  } else {
    const typeCase = (t) => {
      const s = String(t || 'Normal').toLowerCase();
      return s.charAt(0).toUpperCase() + s.slice(1);
    };
    const files = readdirSync(genDir).filter((f) => /^gen_\d+\.json$/.test(f)).sort();
    const dumpMons = new Map(); // id (string) → first-seen dump mon (same order as build)
    const rawMoveNames = new Set();
    for (const file of files) {
      const raw = JSON.parse(readFileSync(join(genDir, file), 'utf8'));
      for (const [id, p] of Object.entries(raw.by_id || {})) {
        if (dumpMons.has(id)) continue;
        dumpMons.set(id, p);
        for (const list of [p.moves, p.tm_moves, p.tutor_moves, p.egg_moves]) {
          for (const m of list || []) {
            rawMoveNames.add(typeof m === 'string' ? m : m.name);
          }
        }
      }
    }
    check('parity: dump ids === dex ids (1025)',
      dumpMons.size === 1025 && MONS.every((m) => dumpMons.has(String(m.i))),
      JSON.stringify({ dumps: dumpMons.size }));
    check('parity: names + abilities + stats match the dumps',
      MONS.every((m) => {
        const d = dumpMons.get(String(m.i));
        if (!d || d.name !== m.n) return false;
        const abilities = (d.abilities || []).filter((x) => x && x.name)
          .map((x) => [x.name, Boolean(x.hidden)]);
        if (JSON.stringify(abilities) !== JSON.stringify(m.a)) return false;
        const stats = ['hp', 'attack', 'defense', 'sp_atk', 'sp_def', 'speed']
          .map((k) => Number(d.base_stats?.[k]) || 0);
        return JSON.stringify(stats) === JSON.stringify(m.s)
          && (d.catch_rate ?? null) === m.c
          && (d.gender_rate ?? -1) === m.g
          && Boolean(d.is_legendary) === m.L && Boolean(d.is_mythical) === m.M
          && JSON.stringify((d.types || []).filter(Boolean).map(typeCase))
            === JSON.stringify(m.t);
      }));
    check('parity: move table === unique dump move names (783)',
      rawMoveNames.size === MOVES.length
      && MOVES.every((mv) => rawMoveNames.has(mv[0])),
      JSON.stringify({ raw: rawMoveNames.size, dex: MOVES.length }));
    // Rebuild every learnset exactly like build_dex (dedupe first-wins,
    // string entries resolved by exact name) and deep-compare.
    const nameToIdx = new Map(MOVES.map((mv, i) => [mv[0], i]));
    const resolveIdx = (m) => (typeof m === 'string'
      ? (nameToIdx.get(m) ?? -1)
      : (nameToIdx.get(m.name || '') ?? -1));
    const dedup = (list) => {
      const seen = new Set();
      const out = [];
      for (const m of list || []) {
        const idx = resolveIdx(m);
        if (idx < 0 || seen.has(idx)) continue;
        seen.add(idx);
        out.push(idx);
      }
      return out;
    };
    check('parity: learnsets (lv/tm/tu/eg) match the dumps', MONS.every((m) => {
      const d = dumpMons.get(String(m.i));
      if (!d) return false;
      const seen = new Set();
      const lv = [];
      for (const mv of d.moves || []) {
        const idx = resolveIdx(mv);
        if (idx < 0 || seen.has(idx)) continue;
        seen.add(idx);
        lv.push(Number(mv.level) || 0, idx);
      }
      return JSON.stringify(lv) === JSON.stringify(m.lv)
        && JSON.stringify(dedup(d.tm_moves)) === JSON.stringify(m.tm)
        && JSON.stringify(dedup(d.tutor_moves)) === JSON.stringify(m.tu)
        && JSON.stringify(dedup(d.egg_moves)) === JSON.stringify(m.eg);
    }));
    const chartPath = resolve(genDir, '..', 'type_chart.json');
    const chart = JSON.parse(readFileSync(chartPath, 'utf8'));
    check('parity: TYPE_CHART === forge type_chart.json',
      JSON.stringify({ types: chart.types, effectiveness: chart.effectiveness })
        === JSON.stringify(TYPE_CHART));
  }
}

console.log(`\n${failed ? `${failed} FAILED` : 'all passed'}`);
process.exit(failed ? 1 : 0);
