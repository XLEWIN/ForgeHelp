// Pokédex UI builders — port of help/helpbot/pokedex_ui.py + build_ui.py
// (rendering + keyboard rows). SDK-free: returns HTML strings and
// [label, callbackData, style] row triples; the transport layer (dex.js)
// turns rows into reply markup. Unicode button labels + Bot API styles
// (no premium icon prerequisite on buttons).

import { E, typeLine, typeTag, uiTag } from './emoji.js';
import {
  CATEGORY_TITLES, MAX_LEVEL, NATURE_TABLE, STAT_ORDER, allMoveRows,
  abilitiesDisplay, artworkUrl, bestNatures, calculateStatRange, dexNumber,
  evYieldDisplay, genderDisplay, getMoveByNameFuzzy, getPokemonByNameFuzzy,
  getPokemonData, moveLearners, movesFor, natureFor, heldItemsFor,
  recommendedEvs, statAbbr, statAt100,
} from './pokemon.js';
import { DANGER, PRIMARY, SUCCESS, htmlEscape as esc } from './style.js';

export const CB_PK = 'pk';
export const CB_BD = 'bd';

/** Moves per page on /poke sub-lists. */
export const MOVES_PER_PAGE = 10;
/** Moves per page on /mv (flat list). */
export const MV_PER_PAGE = 12;
/** Moves listed per page on the build Moves view. */
export const BUILD_MOVES_PER_PAGE = 8;

function ceilDiv(n, d) {
  return Math.max(1, Math.ceil(n / d));
}

function clampPage(page, totalPages) {
  return Math.max(0, Math.min(page, totalPages - 1));
}

// ── /mv — all moves, flat, paginated, prev/next only ─────────────────────

function mvPageHtml(p, page) {
  const name = esc(p.name || 'Unknown');
  const rows = allMoveRows(p);
  const totalPages = ceilDiv(rows.length, MV_PER_PAGE);
  page = clampPage(page, totalPages);
  const chunk = rows.slice(page * MV_PER_PAGE, (page + 1) * MV_PER_PAGE);
  const parts = [
    `<p>${uiTag('battle')} <b>${name}</b> · ${typeLine(p.types || [])}</p>`,
    '<hr/>',
  ];
  for (const m of chunk) {
    const power = m.power !== null && m.power !== undefined ? m.power : '—';
    const acc = m.accuracy !== null && m.accuracy !== undefined ? `${m.accuracy}%` : '—';
    parts.push(
      `<p>${typeTag(m.type)} <b>${esc(m.name)}</b> · ${esc(power)} · ` +
      `${esc(acc)} · ${esc(m.source)}</p>`,
    );
  }
  if (!chunk.length) {
    parts.push(`<p>${uiTag('cross')} No moves in the local dex.</p>`);
  }
  if (totalPages > 1) {
    parts.push(`<footer>Page ${page + 1}/${totalPages} · ${rows.length} moves</footer>`);
  }
  return parts.join('');
}

function mvRows(p, page, totalPages) {
  // Only Prev (blue) / Next (green) buttons — data carries the dex id;
  // plain labels + premium aim/rocket icons (port of pokedex_ui _mv_rows).
  const pid = p.id;
  const rows = [];
  const nav = [];
  if (page > 0) {
    nav.push(['◀ Prev', `${CB_PK}|${pid}|mvpage|${page - 1}`, PRIMARY, 'aim']);
  }
  if (page < totalPages - 1) {
    nav.push(['Next ▶', `${CB_PK}|${pid}|mvpage|${page + 1}`, SUCCESS, 'rocket']);
  }
  if (nav.length) rows.push(nav);
  return rows;
}

function mvClassicText(p, page) {
  const name = esc(p.name || 'Unknown');
  const rows = allMoveRows(p);
  const totalPages = ceilDiv(rows.length, MV_PER_PAGE);
  page = clampPage(page, totalPages);
  const chunk = rows.slice(page * MV_PER_PAGE, (page + 1) * MV_PER_PAGE);
  const lines = [`${name} · ${typeLine(p.types || [])}`, ''];
  for (const m of chunk) {
    const power = m.power !== null && m.power !== undefined ? m.power : '—';
    const acc = m.accuracy !== null && m.accuracy !== undefined ? `${m.accuracy}%` : '—';
    lines.push(
      `${typeTag(m.type)} <b>${esc(m.name)}</b> · ${power} · ${acc} · ${esc(m.source)}`,
    );
  }
  if (totalPages > 1) lines.push(`\n<i>Page ${page + 1}/${totalPages}</i>`);
  return lines.join('\n');
}

/** Move detail card for /mv <move-name> — name, type, category, power,
 *  accuracy, PP, effect and learnset info (fields present in the source
 *  dumps; priority is not, so it is never shown). Rich and classic share
 *  the premium type/PP tags; the classic body only drops <p>/<hr>. */
function moveCardBits(m) {
  const bits = [];
  const power = m.power !== null && m.power !== undefined ? m.power : '—';
  const acc = m.accuracy !== null && m.accuracy !== undefined ? `${m.accuracy}%` : '—';
  const pp = m.pp !== null && m.pp !== undefined ? m.pp : '—';
  const learner = moveLearners(m.idx);
  const sources = [];
  if (learner.levelUpCount) sources.push(`Lv ${learner.levelUpCount}`);
  if (learner.tmCount) sources.push(`TM ${learner.tmCount}`);
  if (learner.tutorCount) sources.push(`Tutor ${learner.tutorCount}`);
  if (learner.eggCount) sources.push(`Egg ${learner.eggCount}`);
  bits.push({
    key: 'header',
    html: `<p>${uiTag('battle')} <b>${esc(m.name)}</b> · ${typeTag(m.type)} ` +
      `${esc(m.type)} · ${esc(m.category)}</p>`,
    text: `${typeTag(m.type)} <b>${esc(m.name)}</b> · ${esc(m.type)} · ${esc(m.category)}`,
  });
  bits.push({
    key: 'stats',
    html: `<p>${uiTag('bolt')} Power: ${esc(power)} · ${uiTag('aim')} ` +
      `Accuracy: ${esc(acc)} · ${uiTag('pp')} PP: ${esc(pp)}</p>`,
    text: `${uiTag('bolt')} Power: ${esc(power)} · ${uiTag('aim')} ` +
      `Accuracy: ${esc(acc)} · ${uiTag('pp')} PP: ${esc(pp)}`,
  });
  if (m.description) {
    bits.push({
      key: 'effect',
      html: `<p>${uiTag('info')} Effect: ${esc(m.description)}</p>`,
      text: `${uiTag('info')} Effect: ${esc(m.description)}`,
    });
  }
  bits.push({
    key: 'learners',
    html: `<p>${uiTag('user')} Learned by ${learner.total} Pokémon` +
      (sources.length ? ` · ${esc(sources.join(' · '))}` : '') + '</p>',
    text: `${uiTag('user')} Learned by ${learner.total} Pokémon` +
      (sources.length ? ` · ${esc(sources.join(' · '))}` : ''),
  });
  if (learner.levelUp.length) {
    const examples = learner.levelUp
      .map((x) => `${esc(x.name)} Lv.${x.level}`).join(' · ');
    bits.push({
      key: 'examples',
      html: `<p>${uiTag('sparkle')} Level-up: ${examples}</p>`,
      text: `${uiTag('sparkle')} Level-up: ${examples}`,
    });
  }
  return bits;
}

function moveCardHtml(m) {
  const bits = moveCardBits(m);
  return bits[0].html + '<hr/>' + bits.slice(1).map((b) => b.html).join('');
}

function moveCardClassic(m) {
  return moveCardBits(m).map((b) => b.text).join('\n');
}

/** Shared entry for /mv: resolves the query (Pokémon first — the original
 *  behaviour — then the move dataset), returns send parts or an error. */
export function mvView(query) {
  if (!query) {
    return { kind: 'usage', text: `${E.CHAT} Usage: <code>/mv Garchomp</code>` };
  }
  const p = getPokemonByNameFuzzy(query);
  if (p) {
    const total = allMoveRows(p).length;
    const totalPages = ceilDiv(total, MV_PER_PAGE);
    return {
      kind: 'ok',
      pokemon: p,
      rich: mvPageHtml(p, 0),
      classic: mvClassicText(p, 0),
      rows: totalPages > 1 ? mvRows(p, 0, totalPages) : [],
    };
  }
  // Not a Pokémon — fall back to the move dataset ("/mv flamethrower").
  const m = getMoveByNameFuzzy(query);
  if (m) {
    return {
      kind: 'move',
      move: m,
      rich: moveCardHtml(m),
      classic: moveCardClassic(m),
      rows: [],
    };
  }
  return {
    kind: 'notfound',
    text: `${E.CROSS} I don't know a Pokémon or a move called ` +
      `<code>${esc(query)}</code>. Try /mv Pikachu or /mv Flamethrower.`,
  };
}

/** /mv pagination for callbacks. */
export function mvPageView(p, page) {
  const total = allMoveRows(p).length;
  const totalPages = ceilDiv(total, MV_PER_PAGE);
  page = clampPage(page, totalPages);
  return {
    rich: mvPageHtml(p, page),
    classic: mvClassicText(p, page),
    rows: totalPages > 1 ? mvRows(p, page, totalPages) : [],
  };
}

// ── /poke — photo + name/types/max level + sub-pages ─────────────────────

function pokeMainHtml(p) {
  const name = esc(p.name || 'Unknown');
  const dex = dexNumber(p.id);
  const tagBits = [];
  if (p.is_legendary) tagBits.push(`${uiTag('crown')} Legendary`);
  if (p.is_mythical) tagBits.push(`${uiTag('sparkle')} Mythical`);
  const tags = tagBits.length ? ` · ${tagBits.join(' · ')}` : '';
  return (
    `<p>${uiTag('star')} <b>${name}</b> ${dex}${tags}</p>` +
    `<p>${typeLine(p.types || [])}</p>` +
    `<p>${uiTag('level')} Max Level: ${MAX_LEVEL}</p>` +
    `<p>${uiTag('info')} Tap a button below — IVs, moves, and more.</p>`
  );
}

function pokeIvsHtml(p) {
  const name = esc(p.name || 'Unknown');
  const bs = p.base_stats || {};
  const parts = [
    `<p>${uiTag('gem')} <b>${name}</b> · Max IVs (Lv.${MAX_LEVEL})</p>`,
    '<hr/>',
  ];
  for (const stat of STAT_ORDER) {
    const base = Number(bs[stat] || 0);
    const maxv = base * 2 + 31 + 63 + MAX_LEVEL;
    parts.push(`<p><b>${statAbbr(stat)}</b> · base ${base} · max ${maxv}</p>`);
  }
  parts.push(`<p>${uiTag('bolt')} Stat range at Lv.50:</p>`);
  for (const stat of STAT_ORDER) {
    const base = Number(bs[stat] || 0);
    const [lo, hi] = calculateStatRange(base, stat);
    parts.push(`<p><b>${statAbbr(stat)}</b> · ${lo} – ${hi}</p>`);
  }
  const natures = bestNatures(bs).join(', ');
  const evs = evYieldDisplay(p.ev_yields || {});
  const catchRate = p.catch_rate ?? '—';
  const gender = genderDisplay(p.gender_rate);
  parts.push(`<p>${uiTag('heart')} Best natures: ${natures}</p>`);
  parts.push(`<p>${uiTag('bolt')} EV yield: ${evs}</p>`);
  parts.push(`<p>${uiTag('circle')} Catch rate: ${esc(catchRate)}</p>`);
  parts.push(`<p>${uiTag('user')} Gender: ${esc(gender)}</p>`);
  parts.push(
    `<p>${uiTag('status')} Abilities: ${esc(abilitiesDisplay(p))}</p>`,
  );
  return parts.join('');
}

function moveListBits(m, category) {
  const bits = [typeTag(m.type || 'Normal'), `<b>${esc(m.name || '?')}</b>`];
  if (m.power !== null && m.power !== undefined) bits.push(`${m.power} power`);
  if (m.accuracy !== null && m.accuracy !== undefined) bits.push(`${m.accuracy}%`);
  if (category === 'levelup' && m.level) bits.push(`Lv.${m.level}`);
  return bits;
}

function moveListHtml(p, category, page) {
  const name = esc(p.name || 'Unknown');
  const moves = movesFor(p, category);
  const title = CATEGORY_TITLES[category] || category;
  const totalPages = ceilDiv(moves.length, MOVES_PER_PAGE);
  page = clampPage(page, totalPages);
  const chunk = moves.slice(page * MOVES_PER_PAGE, (page + 1) * MOVES_PER_PAGE);
  const parts = [
    `<p>${uiTag('battle')} <b>${name}</b> · ${title}</p>`,
    '<hr/>',
  ];
  if (!chunk.length) {
    parts.push(`<p>${uiTag('cross')} No ${title.toLowerCase()} in the local dex.</p>`);
  }
  for (const m of chunk) parts.push(`<p>${moveListBits(m, category).join(' · ')}</p>`);
  if (totalPages > 1) {
    parts.push(`<footer>Page ${page + 1}/${totalPages} · ${moves.length} moves</footer>`);
  }
  return parts.join('');
}

function moveListClassic(p, category, page) {
  const name = esc(p.name || 'Unknown');
  const moves = movesFor(p, category);
  const title = CATEGORY_TITLES[category] || category;
  const totalPages = ceilDiv(moves.length, MOVES_PER_PAGE);
  page = clampPage(page, totalPages);
  const chunk = moves.slice(page * MOVES_PER_PAGE, (page + 1) * MOVES_PER_PAGE);
  const lines = [`${name} · ${title}`, ''];
  for (const m of chunk) lines.push(moveListBits(m, category).join(' · '));
  if (totalPages > 1) lines.push(`\n<i>Page ${page + 1}/${totalPages}</i>`);
  return lines.join('\n');
}

function cbView(data) {
  const parts = String(data || '').split('|');
  return parts.length > 2 ? parts[2] : '';
}

function pokeRows(p, hide = '') {
  // Main buttons minus the current view. Plain labels + premium icons +
  // blue/green/red (port of pokedex_ui _poke_rows).
  const pid = p.id;
  const hasTutor = Boolean(p._raw.tu.length);
  const hasEgg = Boolean(p._raw.eg.length);
  let rows = [
    [
      ['IVs', `${CB_PK}|${pid}|ivs|0`, PRIMARY, 'gem'],
      ['Moves', `${CB_PK}|${pid}|mvmenu|0`, SUCCESS, 'gift'],
    ],
    [
      ['Level-Up', `${CB_PK}|${pid}|levelup|0`, PRIMARY, 'fire'],
      ['TMs', `${CB_PK}|${pid}|tms|0`, SUCCESS, 'star'],
    ],
  ];
  if (hasTutor || hasEgg) {
    const row = [];
    if (hasTutor) row.push(['Tutor', `${CB_PK}|${pid}|tutor|0`, PRIMARY, 'crown']);
    if (hasEgg) row.push(['Egg', `${CB_PK}|${pid}|egg|0`, SUCCESS, 'heart']);
    rows.push(row);
  }
  rows.push([['Close', `${CB_PK}|${pid}|close|0`, DANGER, 'cross']]);
  if (hide) {
    rows = rows
      .map((row) => row.filter((b) => cbView(b[1]) !== hide))
      .filter((row) => row.length);
  }
  return rows;
}

function backRow(p) {
  return [['Back', `${CB_PK}|${p.id}|main|0`, PRIMARY, 'globe']];
}

function subRows(p, hide, page = 0, category = '') {
  // Sub-page: main buttons (minus current) + optional nav + Back.
  let rows = pokeRows(p, hide);
  if (category) {
    const moves = movesFor(p, category);
    const totalPages = ceilDiv(moves.length, MOVES_PER_PAGE);
    const nav = [];
    if (page > 0) {
      nav.push(['◀ Prev', `${CB_PK}|${p.id}|${category}|${page - 1}`, PRIMARY, 'aim']);
    }
    if (page < totalPages - 1) {
      nav.push(['Next ▶', `${CB_PK}|${p.id}|${category}|${page + 1}`, SUCCESS, 'rocket']);
    }
    if (nav.length) rows = [nav, ...rows];
  }
  rows = [...rows, backRow(p)];
  return rows;
}

function pokeCaption(p, view = 'main', page = 0) {
  if (view === 'main') return pokeMainHtml(p);
  if (view === 'ivs') return pokeIvsHtml(p);
  if (view === 'mvmenu') {
    return `<p>${uiTag('chat')} <b>${esc(p.name)}</b> — pick a move list:</p>`;
  }
  if (['levelup', 'tutor', 'tms', 'egg'].includes(view)) {
    return moveListHtml(p, view, page);
  }
  return pokeMainHtml(p);
}

function pokeClassicCaption(p, view = 'main', page = 0) {
  if (view === 'main') {
    const name = esc(p.name || 'Unknown');
    const tags = [];
    if (p.is_legendary) tags.push('Legendary');
    if (p.is_mythical) tags.push('Mythical');
    const tagStr = tags.length ? ` · ${tags.join(' · ')}` : '';
    return (
      `<b>${name}</b> ${dexNumber(p.id)}${tagStr}\n` +
      `${typeLine(p.types || [])}\n` +
      `Max Level: ${MAX_LEVEL}\n\n` +
      'Tap a button below — IVs, moves, and more.'
    );
  }
  if (view === 'ivs') {
    const name = esc(p.name || 'Unknown');
    const bs = p.base_stats || {};
    const lines = [`<b>${name}</b> · Max IVs (Lv.${MAX_LEVEL})`, ''];
    for (const stat of STAT_ORDER) {
      const base = Number(bs[stat] || 0);
      const maxv = base * 2 + 31 + 63 + MAX_LEVEL;
      lines.push(`<b>${statAbbr(stat)}</b> · base ${base} · max ${maxv}`);
    }
    lines.push('');
    lines.push('Stat range at Lv.50:');
    for (const stat of STAT_ORDER) {
      const base = Number(bs[stat] || 0);
      const [lo, hi] = calculateStatRange(base, stat);
      lines.push(`<b>${statAbbr(stat)}</b> · ${lo} – ${hi}`);
    }
    lines.push('');
    lines.push(`Best natures: ${bestNatures(bs).join(', ')}`);
    lines.push(`EV yield: ${evYieldDisplay(p.ev_yields || {})}`);
    lines.push(`Catch rate: ${p.catch_rate ?? '—'}`);
    lines.push(`Gender: ${genderDisplay(p.gender_rate)}`);
    lines.push(`Abilities: ${abilitiesDisplay(p)}`);
    return lines.join('\n');
  }
  if (view === 'mvmenu') {
    return `${E.CHAT} <b>${esc(p.name)}</b> — pick a move list: Level-Up, TMs, Tutor, Egg.`;
  }
  if (['levelup', 'tutor', 'tms', 'egg'].includes(view)) {
    return moveListClassic(p, view, page);
  }
  return pokeClassicCaption(p, 'main', page);
}

/** Shared entry for /poke: resolves the query, returns send parts or an
 *  error text. Photo captions only accept the classic HTML subset. */
export function pokeView(query) {
  if (!query) {
    return { kind: 'usage', text: `${E.CHAT} Usage: <code>/poke Garchomp</code>` };
  }
  const p = getPokemonByNameFuzzy(query);
  if (!p) {
    return {
      kind: 'notfound',
      text: `${E.CROSS} I don't know a Pokémon called <code>${esc(query)}</code>. Try /poke Pikachu.`,
    };
  }
  return {
    kind: 'ok',
    pokemon: p,
    photo: artworkUrl(p),
    caption: pokeClassicCaption(p, 'main'),
    rich: pokeMainHtml(p),
    rows: pokeRows(p),
  };
}

// ── /build — category menu + paged build cards ───────────────────────────

/** (key, label, style, iconKey) category menu — 4 options, blue/green,
 *  plain labels + premium icons (port of build_ui CATEGORIES). */
export const CATEGORIES = [
  ['atk', 'Best ATK', PRIMARY, 'battle'],
  ['spatk', 'Best SP.ATK', SUCCESS, 'bolt'],
  ['def', 'Best DEF', PRIMARY, 'gem'],
  ['spdef', 'Best SP.DEF', SUCCESS, 'heart'],
];

/** Friendly titles shown on build cards. */
export const CAT_TITLES = {
  atk: 'Physical Sweep (ATK)',
  spatk: 'Special Sweep (SP.ATK)',
  def: 'Physical Wall (DEF)',
  spdef: 'Special Wall (SP.DEF)',
};

/** Stats prioritised per category (for ranking base stats / EV notes). */
export const CAT_FOCUS = {
  atk: ['attack', 'speed'],
  spatk: ['sp_atk', 'speed'],
  def: ['defense', 'hp'],
  spdef: ['sp_def', 'hp'],
};

/** Damage category filter for the Moves page. */
export const CAT_MOVE_FILTER = {
  atk: 'Physical',
  spatk: 'Special',
  def: 'Status', // walls want utility; fall back to damaging if empty
  spdef: 'Status',
};

// ── Recommendation engine ────────────────────────────────────────────────

function bestMoves(p, cat) {
  // Top moves for a category: STAB + high power first, then utility.
  const types = new Set((p.types || []).map((t) => String(t).toLowerCase()));
  const want = CAT_MOVE_FILTER[cat] || 'Physical';
  const rows = allMoveRows(p);
  const score = (m) => {
    const power = m.power || 0;
    const mtype = String(m.type || '').toLowerCase();
    const category = String(m.category || '');
    const stab = types.has(mtype) ? 1 : 0;
    const catMatch = category === want ? 1 : 0;
    if (cat === 'def' || cat === 'spdef') {
      // Walls: utility/status first, then reliable damaging STAB.
      const isStatus = category === 'Status' ? 1 : 0;
      return [isStatus, stab, power];
    }
    return [catMatch, stab, power];
  };
  // Python: sorted(key=score, reverse=True) — stable sort on tuples.
  const ranked = [...rows]
    .map((m, i) => [score(m), i, m])
    .sort((a, b) => {
      for (let k = 0; k < a[0].length; k++) {
        if (a[0][k] !== b[0][k]) return b[0][k] - a[0][k];
      }
      return a[1] - b[1];
    })
    .map((x) => x[2]);

  if (cat === 'atk' || cat === 'spatk') {
    const damaging = ranked.filter(
      (m) => (m.power || 0) > 0 && String(m.category) === want,
    );
    if (damaging.length < 4) {
      const extra = ranked.filter(
        (m) => (m.power || 0) > 0 && !damaging.includes(m),
      );
      damaging.push(...extra);
    }
    return damaging.slice(0, 6);
  }
  // Walls: status moves first, then strongest STAB / coverage.
  const status = ranked.filter((m) => String(m.category) === 'Status');
  const damaging = ranked.filter((m) => (m.power || 0) > 0);
  return [...status.slice(0, 3), ...damaging.slice(0, 4)].slice(0, 6);
}

/** Full recommendation bundle for one category (port of recommend_build). */
export function recommendBuild(p, cat) {
  const bs = p.base_stats || {};
  const nature = natureFor(cat, bs);
  const [plus, minus] = NATURE_TABLE[nature] || [null, null];
  const evs = recommendedEvs(cat);
  const items = heldItemsFor(cat);
  const moves = bestMoves(p, cat);
  const [focus1, focus2] = CAT_FOCUS[cat] || ['attack', 'speed'];

  const statLines = [];
  for (const stat of STAT_ORDER) {
    const base = Number(bs[stat] || 0);
    const ev = Number(evs[stat] || 0);
    const val = statAt100(base, stat, 31, ev,
      stat === plus, stat === minus);
    statLines.push({
      label: statAbbr(stat),
      base,
      ev,
      value: val,
      mark: stat === plus ? ' +' : (stat === minus ? ' −' : ''),
    });
  }

  return {
    cat,
    title: CAT_TITLES[cat] || cat,
    nature,
    plus: plus ? statAbbr(plus) : '—',
    minus: minus ? statAbbr(minus) : '—',
    evs,
    ivs: '31/31/31/31/31/31',
    items,
    moves,
    stats: statLines,
    focus: [statAbbr(focus1), statAbbr(focus2)],
  };
}

// ── HTML builders (build cards) ──────────────────────────────────────────

function evText(evs) {
  const parts = [];
  for (const s of STAT_ORDER) {
    const v = Number(evs[s] || 0);
    if (v) parts.push(`${v} ${statAbbr(s)}`);
  }
  return parts.length ? parts.join(' / ') : '0';
}

function summaryHtml(p, rec) {
  const name = esc(p.name || 'Unknown');
  const dex = dexNumber(p.id);
  const parts = [
    `<p>${uiTag('star')} <b>${name}</b> ${dex} · ${esc(rec.title)}</p>`,
    `<p>${typeLine(p.types || [])}</p>`,
    '<hr/>',
    `<p>${uiTag('heart')} <b>Nature:</b> ${esc(rec.nature)} (+${esc(rec.plus)} / −${esc(rec.minus)})</p>`,
    `<p>${uiTag('bolt')} <b>EVs:</b> ${esc(evText(rec.evs))}</p>`,
    `<p>${uiTag('gem')} <b>IVs:</b> ${esc(rec.ivs)}</p>`,
    `<p>${uiTag('gift')} <b>Items:</b> ${esc(rec.items.slice(0, 3).join(', '))}</p>`,
    '<hr/>',
    `<p>${uiTag('battle')} Stats at Lv.${MAX_LEVEL}:</p>`,
  ];
  for (const line of rec.stats) {
    parts.push(
      `<p><b>${esc(line.label)}</b>${esc(line.mark)} · base ${line.base} · ` +
      `EV ${line.ev} → ${line.value}</p>`,
    );
  }
  return parts.join('');
}

function buildMovesHtml(p, rec, page) {
  const name = esc(p.name || 'Unknown');
  const moves = rec.moves;
  const totalPages = ceilDiv(moves.length, BUILD_MOVES_PER_PAGE);
  page = clampPage(page, totalPages);
  const chunk = moves.slice(page * BUILD_MOVES_PER_PAGE, (page + 1) * BUILD_MOVES_PER_PAGE);
  const parts = [
    `<p>${uiTag('battle')} <b>${name}</b> · ${esc(rec.title)} moves</p>`,
    '<hr/>',
  ];
  if (!chunk.length) parts.push(`<p>${uiTag('cross')} No moves in the local dex.</p>`);
  for (const m of chunk) {
    const bits = [typeTag(m.type || 'Normal'), `<b>${esc(m.name || '?')}</b>`,
      String(m.category || '?')];
    if (m.power !== null && m.power !== undefined) bits.push(`${m.power} power`);
    if (m.accuracy !== null && m.accuracy !== undefined) bits.push(`${m.accuracy}%`);
    if (m.source) bits.push(esc(m.source));
    parts.push(`<p>${bits.join(' · ')}</p>`);
  }
  if (totalPages > 1) {
    parts.push(`<footer>Page ${page + 1}/${totalPages} · ${moves.length} moves</footer>`);
  }
  return parts.join('');
}

function menuHtml(p) {
  // Rich HTML for the menu view (sendRichMessage only — has <p>).
  const name = esc(p.name || 'Unknown');
  const dex = dexNumber(p.id);
  return (
    `<p>${uiTag('sparkle')} <b>${name}</b> ${dex} — pick a build category:</p>` +
    `<p>${uiTag('info')} Each card shows nature, EVs, IVs, items and the best moves for that role.</p>`
  );
}

function menuClassic(p) {
  // Classic HTML caption for the menu view (sendPhoto / editCaption safe).
  const name = esc(p.name || 'Unknown');
  const dex = dexNumber(p.id);
  return (
    `${E.SPARKLE} <b>${name}</b> ${dex} — pick a build category:\n\n` +
    'Each card shows nature, EVs, IVs, items and the best moves for that role.'
  );
}

function summaryClassic(p, rec) {
  const name = esc(p.name || 'Unknown');
  const lines = [
    `<b>${name}</b> · ${esc(rec.title)}`,
    `Nature: ${esc(rec.nature)} (+${esc(rec.plus)}/−${esc(rec.minus)})`,
    `EVs: ${esc(evText(rec.evs))}`,
    `IVs: ${esc(rec.ivs)}`,
    `Items: ${esc(rec.items.slice(0, 3).join(', '))}`,
    '',
    'Stats at Lv.100:',
  ];
  for (const line of rec.stats) {
    lines.push(
      `<b>${esc(line.label)}</b>${esc(line.mark)} · base ${line.base} · ` +
      `EV ${line.ev} · → ${line.value}`,
    );
  }
  return lines.join('\n');
}

function buildMovesClassic(p, rec, page) {
  const name = esc(p.name || 'Unknown');
  const moves = rec.moves;
  const totalPages = ceilDiv(moves.length, BUILD_MOVES_PER_PAGE);
  page = clampPage(page, totalPages);
  const chunk = moves.slice(page * BUILD_MOVES_PER_PAGE, (page + 1) * BUILD_MOVES_PER_PAGE);
  const lines = [`${name} · ${esc(rec.title)} moves`, ''];
  for (const m of chunk) {
    const bits = [typeTag(m.type || 'Normal'), `<b>${esc(m.name || '?')}</b>`,
      String(m.category || '?')];
    if (m.power !== null && m.power !== undefined) bits.push(`${m.power} power`);
    if (m.accuracy !== null && m.accuracy !== undefined) bits.push(`${m.accuracy}%`);
    lines.push(bits.join(' · '));
  }
  if (totalPages > 1) lines.push(`\n<i>Page ${page + 1}/${totalPages}</i>`);
  return lines.join('\n');
}

// ── Keyboards ────────────────────────────────────────────────────────────

function menuRows(p) {
  const pid = p.id;
  const rows = [];
  for (const [key, label, style, icon] of CATEGORIES) {
    rows.push([[label, `${CB_BD}|${pid}|${key}|sum|0`, style, icon]]);
  }
  rows.push([['Close', `${CB_BD}|${pid}|menu|close|0`, DANGER, 'cross']]);
  return rows;
}

function buildRows(p, cat, view, page, totalPages) {
  // Summary/moves keyboard: Moves|Back-style nav + Close — plain labels
  // + premium icons (port of build_ui _build_rows).
  const pid = p.id;
  const rows = [];
  if (view === 'sum') {
    rows.push([
      ['Moves', `${CB_BD}|${pid}|${cat}|mv|0`, SUCCESS, 'gift'],
      ['Back', `${CB_BD}|${pid}|menu|menu|0`, PRIMARY, 'globe'],
    ]);
  } else if (view === 'mv') {
    const nav = [];
    if (page > 0) {
      nav.push(['◀ Prev', `${CB_BD}|${pid}|${cat}|mv|${page - 1}`, PRIMARY, 'aim']);
    }
    if (page < totalPages - 1) {
      nav.push(['Next ▶', `${CB_BD}|${pid}|${cat}|mv|${page + 1}`, SUCCESS, 'rocket']);
    }
    if (nav.length) rows.push(nav);
    rows.push([
      ['Summary', `${CB_BD}|${pid}|${cat}|sum|0`, PRIMARY, 'star'],
      ['Back', `${CB_BD}|${pid}|menu|menu|0`, SUCCESS, 'globe'],
    ]);
  }
  rows.push([['Close', `${CB_BD}|${pid}|${cat}|close|0`, DANGER, 'cross']]);
  return rows;
}

// ── Commands ─────────────────────────────────────────────────────────────

/** Shared entry for /build (and /set alias). */
export function buildView(query) {
  if (!query) {
    return { kind: 'usage', text: `${E.CHAT} Usage: <code>/build Garchomp</code>` };
  }
  const p = getPokemonByNameFuzzy(query);
  if (!p) {
    return {
      kind: 'notfound',
      text: `${E.CROSS} I don't know a Pokémon called <code>${esc(query)}</code>. Try /build Garchomp.`,
    };
  }
  return {
    kind: 'ok',
    pokemon: p,
    photo: artworkUrl(p),
    caption: menuClassic(p),
    rich: menuHtml(p),
    rows: menuRows(p),
  };
}

/** Full view resolution for `bd|` callbacks — pure (transport edits). */
export function buildCallbackView(p, cat, view, page) {
  if (cat === 'menu' || view === 'menu') {
    return { rich: menuHtml(p), classic: menuClassic(p), rows: menuRows(p) };
  }
  if (!CAT_TITLES[cat]) {
    return {
      rich: menuHtml(p),
      classic: `${E.CROSS} Unknown category.`,
      rows: menuRows(p),
    };
  }
  const rec = recommendBuild(p, cat);
  if (view === 'mv') {
    const totalPages = ceilDiv(rec.moves.length, BUILD_MOVES_PER_PAGE);
    page = clampPage(page, totalPages);
    return {
      rich: buildMovesHtml(p, rec, page),
      classic: buildMovesClassic(p, rec, page),
      rows: buildRows(p, cat, 'mv', page, totalPages),
    };
  }
  // Default / "sum" — the main build card.
  return {
    rich: summaryHtml(p, rec),
    classic: summaryClassic(p, rec),
    rows: buildRows(p, cat, 'sum', 0, 1),
  };
}

// ── `pk|` callback resolution — pure ─────────────────────────────────────

/** Resolve a `pk|{id}|{view}|{page}` callback to body + rows.
 *  view: main | ivs | mvmenu | levelup | tutor | tms | egg | mvpage */
export function pokeCallbackView(p, view, page) {
  if (view === 'mvpage') {
    const v = mvPageView(p, page);
    return { ...v, classic: v.classic };
  }
  if (view === 'main') {
    return {
      rich: pokeCaption(p, 'main'),
      classic: pokeClassicCaption(p, 'main'),
      rows: pokeRows(p),
    };
  }
  if (view === 'ivs') {
    return {
      rich: pokeCaption(p, 'ivs'),
      classic: pokeClassicCaption(p, 'ivs'),
      rows: subRows(p, 'ivs'),
    };
  }
  if (view === 'mvmenu') {
    const pid = p.id;
    const rows = [
      [
        ['Level-Up', `${CB_PK}|${pid}|levelup|0`, PRIMARY, 'fire'],
        ['TMs', `${CB_PK}|${pid}|tms|0`, SUCCESS, 'star'],
      ],
      [
        ['Tutor', `${CB_PK}|${pid}|tutor|0`, PRIMARY, 'crown'],
        ['Egg', `${CB_PK}|${pid}|egg|0`, SUCCESS, 'heart'],
      ],
      backRow(p),
    ];
    return {
      rich: pokeCaption(p, 'mvmenu'),
      classic: pokeClassicCaption(p, 'mvmenu'),
      rows,
    };
  }
  if (['levelup', 'tutor', 'tms', 'egg'].includes(view)) {
    return {
      rich: moveListHtml(p, view, page),
      classic: moveListClassic(p, view, page),
      rows: subRows(p, view, page, view),
    };
  }
  return {
    rich: pokeMainHtml(p),
    classic: pokeClassicCaption(p, 'main'),
    rows: pokeRows(p),
  };
}

export { getPokemonData, getPokemonByNameFuzzy };
