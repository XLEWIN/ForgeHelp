// /data encyclopedia UI builders — port of forge/modules/pokedex/data.py
// (message bodies + keyboard rows). SDK-free and pure: API-backed inputs
// (species record, evolution chain, encounters) are passed in by the
// transport (dex.js), which fetches them through pokeapi.js.
//
// Callback data: ``d:{action}:{id}`` (original colon format)
//   actions: back | moves | evo | loc | weak | mlist | noop
//   loc adds :{page}; mlist adds :{category}:{page}.
// Every view hides its own button and carries Back to home (edit-in-place).

import { typeLabel, typeLine, uiTag } from './emoji.js';
import {
  STAT_ORDER, bestNatures, calculateStatRange, evYieldDisplay, movesFor,
  statAbbr, typeEffectiveness, artworkUrl,
} from './pokemon.js';
import { PRIMARY, SUCCESS, htmlEscape as esc } from './style.js';

export const CB_D = 'd';

/** Moves per page on /data move lists (original _MOVES_PER_PAGE). */
export const DATA_MOVES_PER_PAGE = 10;
/** Locations per page (original _LOCATIONS_PER_PAGE). */
export const LOCATIONS_PER_PAGE = 8;

const CAT_ICONS = {
  Physical: () => uiTag('comet'),
  Special: () => uiTag('sparkle'),
  Status: () => uiTag('status'),
};

const CAT_LABELS = {
  levelup: 'Level Up',
  tm: 'TMs',
  tutor: 'Tutor',
  egg: 'Egg',
};

function ceilDiv(n, d) {
  return Math.max(1, Math.ceil(n / d));
}

function clampPage(page, totalPages) {
  return Math.max(0, Math.min(page, totalPages - 1));
}

// ── Command texts ────────────────────────────────────────────────────────

export function dataUsageText() {
  return `${uiTag('aim')} Please specify a Pokémon.\n\nExample:\n<code>/data froakie</code>`;
}

export function dataNotFoundText() {
  return `${uiTag('cross')} Pokémon not found.\n\n` +
    'Please check the name or Poké ID and try again.';
}

// ── Main card ────────────────────────────────────────────────────────────

function mainBody(p) {
  const name = esc(p.name || 'Unknown');
  const lines = [
    `<b>${name}'s Data</b>`,
    '',
    `• <b>Species ID:</b> ${p.id}`,
    `• <b>Type:</b> ${typeLine(p.types || [])}`,
    `• <b>Catch Rate:</b> ${esc(p.catch_rate ?? 'Unknown')}`,
    `• <b>EV Yield:</b> ${esc(evYieldDisplay(p.ev_yields || {}))}`,
    `• <b>Best Natures:</b> ${esc(bestNatures(p.base_stats || {}).join(', '))}`,
    '',
    `${uiTag('star')} <b>Base Stats:</b>`,
  ];
  for (const stat of STAT_ORDER) {
    const base = Number(p.base_stats?.[stat] || 0);
    const [lo, hi] = calculateStatRange(base, stat);
    lines.push(`<b>${statAbbr(stat)}:</b> ${base} (${lo} - ${hi})`);
  }
  // Invisible artwork link (parity with the original card — tap to open).
  const image = artworkUrl(p);
  if (image) lines.push('', `<a href="${esc(image)}">\u200c</a>`);
  return lines.join('\n');
}

/** Menu rows: Moves / Evolutions / Locations / Weakness (current hidden). */
export function mainRows(p, hide = '') {
  const id = p.id;
  const rows = [
    [
      ['🎁 Moves', `${CB_D}:moves:${id}`, SUCCESS],
      ['🔥 Evolutions', `${CB_D}:evo:${id}`, SUCCESS],
    ],
    [
      ['📍 Locations', `${CB_D}:loc:${id}:0`, SUCCESS],
      ['⚠️ Weakness', `${CB_D}:weak:${id}`, SUCCESS],
    ],
  ];
  if (!hide) return rows;
  return rows
    .map((row) => row.filter((b) => b[1].split(':')[1] !== hide))
    .filter((row) => row.length);
}

function backRow(p) {
  return [[['◀ Back', `${CB_D}:back:${p.id}`, PRIMARY]]];
}

/** Sub-page keyboard: menu minus the current view + Back. */
function pageRows(p, hide) {
  return [...mainRows(p, hide), ...backRow(p)];
}

/** Main card as a view: single body (rich === classic), menu keyboard. */
export function dataView(p) {
  return {
    kind: 'ok',
    pokemon: p,
    rich: mainBody(p),
    classic: mainBody(p),
    rows: mainRows(p),
  };
}

// ── Moves category menu ──────────────────────────────────────────────────

function movesMenuBody(p) {
  return `${uiTag('chat')} How would you like to browse ${esc(p.name || 'Unknown')}'s moves?`;
}

/** Category rows (Tutor only when data exists) + menu + Back. */
export function movesRows(p, hideCategory = '') {
  const id = p.id;
  const catRows = [
    [
      ['🔥 Level Up', `${CB_D}:mlist:${id}:levelup:0`, SUCCESS],
      ['⭐ TMs', `${CB_D}:mlist:${id}:tm:0`, SUCCESS],
    ],
  ];
  const tutorBtn = ['👑 Tutor', `${CB_D}:mlist:${id}:tutor:0`, SUCCESS];
  const eggBtn = ['💙 Egg', `${CB_D}:mlist:${id}:egg:0`, SUCCESS];
  // tutor_moves is empty for most species — only show Tutor with data.
  catRows.push((p._raw && p._raw.tu && p._raw.tu.length) ? [tutorBtn, eggBtn] : [eggBtn]);
  let rows = catRows;
  if (hideCategory) {
    rows = catRows
      .map((row) => row.filter((b) => b[1].split(':')[3] !== hideCategory))
      .filter((row) => row.length);
  }
  return [...rows, ...mainRows(p, 'moves'), ...backRow(p)];
}

export function movesMenuView(p) {
  return {
    rich: movesMenuBody(p),
    classic: movesMenuBody(p),
    rows: movesRows(p),
  };
}

// ── Paginated move list ──────────────────────────────────────────────────

function moveEntry(mv, category) {
  const name = esc(mv.name || 'Unknown');
  const type = typeLabel(mv.type || 'Normal');
  const method = category === 'levelup' && mv.level ? ` - Lv.${mv.level}` : '';
  const power = mv.power !== null && mv.power !== undefined ? mv.power : 'None';
  const acc = mv.accuracy !== null && mv.accuracy !== undefined ? mv.accuracy : 'None';
  const catIcon = (CAT_ICONS[mv.category] || CAT_ICONS.Special)();
  const line1 = `• <b>${name}</b> [ ${type} ]${method}`;
  const line2 = `${uiTag('bolt')} Power: ${power}  |  ` +
    `${uiTag('aim')} Accuracy: ${acc}  |  ${catIcon} ${esc(mv.category || 'Status')}`;
  return `${line1}\n${line2}`;
}

function moveListBody(p, category, page, userLabel) {
  const name = esc(p.name || 'Unknown');
  const moves = movesFor(p, category);
  const totalPages = ceilDiv(moves.length, DATA_MOVES_PER_PAGE);
  page = clampPage(page, totalPages);
  const chunk = moves.slice(page * DATA_MOVES_PER_PAGE, (page + 1) * DATA_MOVES_PER_PAGE);
  const label = CAT_LABELS[category] || category;
  const lines = [
    `<b>${esc(userLabel || 'User')}</b>`,
    `│ /data ${esc(p.name || '')}`,
    '',
    `<b><i>${name} — ${esc(label)} Moves</i></b>`,
    '',
  ];
  if (!chunk.length) {
    lines.push('No moves found for this method.');
  } else {
    for (const mv of chunk) {
      lines.push(moveEntry(mv, category));
      lines.push('');
    }
  }
  lines.push(`Page: ${page + 1}/${totalPages}`);
  return lines.join('\n');
}

/** Nav row (Prev / counter / Next) — counter only when paginated. */
function moveListNav(p, category, page, totalPages) {
  const id = p.id;
  const rows = [];
  if (totalPages > 1) {
    const nav = [];
    if (page > 0) {
      nav.push(['◀ Prev', `${CB_D}:mlist:${id}:${category}:${page - 1}`, PRIMARY]);
    }
    nav.push([`${page + 1}/${totalPages}`, `${CB_D}:noop:0`, PRIMARY]);
    if (page < totalPages - 1) {
      nav.push(['Next ▶', `${CB_D}:mlist:${id}:${category}:${page + 1}`, SUCCESS]);
    }
    rows.push(nav);
  }
  return rows;
}

export function moveListView(p, category, page, userLabel) {
  const moves = movesFor(p, category);
  const totalPages = ceilDiv(moves.length, DATA_MOVES_PER_PAGE);
  page = clampPage(page, totalPages);
  return {
    rich: moveListBody(p, category, page, userLabel),
    classic: moveListBody(p, category, page, userLabel),
    rows: [
      ...moveListNav(p, category, page, totalPages),
      ...movesRows(p, category),
    ],
  };
}

// ── Evolutions (API input: species record + evolution chain) ─────────────

/** Port of data.py _parse_evolution_chain — flat [{from,to,method}]. */
export function parseEvolutionChain(chain) {
  const results = [];
  if (!chain) return results;
  const fromName = chain.species?.name || '';
  for (const evo of chain.evolves_to || []) {
    const toName = evo.species?.name || '';
    const details = evo.evolution_details || [];
    // details[0] is the oldest version group; prefer the canonical
    // is_default entry (Leafeon's DP entry differs from the default).
    const detail = details.find((d) => d && d.is_default) || details[0] || {};
    results.push({
      from: titleize(fromName),
      to: titleize(toName),
      method: evolutionMethod(detail),
    });
    results.push(...parseEvolutionChain(evo));
  }
  return results;
}

/** Port of data.py's method-string builder (level-up variants, items,
 *  trade, shed + time-of-day / known-move / location / gender suffixes). */
function evolutionMethod(detail) {
  const trigger = detail.trigger?.name || '';
  const parts = [];
  if (trigger === 'level-up') {
    // PokeAPI encodes the level-up variant in the detail fields.
    if (detail.min_level) parts.push(`Level ${detail.min_level}`);
    else if (detail.known_move_type) {
      parts.push(`Level up knowing a ${titleize(detail.known_move_type.name || '?')}-type move`);
    } else if (detail.min_steps) parts.push(`Level up after ${detail.min_steps} steps`);
    else if (detail.used_move) {
      parts.push(`Level up after using ${titleize(detail.used_move.name || '?')}`);
    } else if (detail.min_move_count) {
      parts.push(`Level up knowing ${detail.min_move_count} moves`);
    } else if (detail.party_species) {
      parts.push(`Level up with ${titleize(detail.party_species.name || '?')} in party`);
    } else if (detail.party_type) {
      parts.push(`Level up with a ${titleize(detail.party_type.name || '?')}-type Pokémon in party`);
    } else if (detail.min_happiness) parts.push('Level up (high friendship)');
    else if (detail.min_affection) parts.push('Level up (high affection)');
    else if (detail.min_beauty) parts.push('Level up (high beauty)');
    else if (detail.relative_physical_stats === 1) parts.push('Level up (Atk > Def)');
    else if (detail.relative_physical_stats === -1) parts.push('Level up (Atk < Def)');
    else if (detail.relative_physical_stats === 0) parts.push('Level up (Atk = Def)');
    else if (detail.needs_overworld_rain) parts.push('Level up (while raining)');
    else if (detail.turn_upside_down) parts.push('Level up (turn console upside-down)');
    else parts.push('Level up');
  } else if (trigger === 'use-item') {
    parts.push(`Use ${titleize(detail.item?.name || '')}`);
  } else if (trigger === 'trade') {
    // held_item is JSON null (not absent) for plain trades.
    const held = detail.held_item?.name;
    if (held) parts.push(`Trade holding ${titleize(held)}`);
    else if (detail.trade_species) {
      parts.push(`Trade with ${titleize(detail.trade_species.name || '?')} in party`);
    } else parts.push('Trade');
  } else if (trigger === 'shed') {
    parts.push('Level up (Nincada)');
  } else {
    parts.push(trigger ? titleize(trigger) : 'Unknown');
  }

  if (detail.time_of_day) parts.push(`(${titleize(detail.time_of_day)})`);
  if (detail.known_move) parts.push(`knowing ${titleize(detail.known_move.name || '')}`);
  if (detail.location) parts.push(`at ${titleize(detail.location.name || '')}`);
  if (typeof detail.gender === 'number') {
    const g = { 1: 'female-only', 2: 'male-only' }[detail.gender];
    if (g) parts.push(`(${g})`);
  } else if (detail.gender && typeof detail.gender === 'object' && detail.gender.name) {
    const g = { 1: 'female-only', 2: 'male-only' }[detail.gender.name] || '';
    if (g) parts.push(`(${g})`);
  }
  return parts.join(' ') || 'Unknown';
}

/** Port of data.py _get_all_evolutions — every species in the chain. */
export function allEvolutions(chain) {
  const out = [];
  if (!chain) return out;
  out.push(titleize(chain.species?.name || ''));
  for (const evo of chain.evolves_to || []) out.push(...allEvolutions(evo));
  return out;
}

function titleize(slug) {
  return String(slug || '').replace(/-/g, ' ')
    .split(' ').filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

/** Evolutions & Forms body — species/chain come from the API cache (both
 *  may be null on failure; the original renders the same fallbacks). */
export function evoBody(p, species, chain) {
  const name = esc(p.name || 'Unknown');
  const forms = [];
  for (const v of (species && species.varieties) || []) {
    if (v.is_default) continue;
    const n = titleize(v.pokemon?.name || '');
    if (n) forms.push(n);
  }
  const formsBlock = forms.length
    ? `\n\n<b>Forms:</b>\n${forms.map((f) => `• <b>${esc(f)}</b>`).join('\n')}`
    : '';

  const header = `${uiTag('rocket')} <b>${name} — Evolutions &amp; Forms</b>\n`;
  const chainData = chain && chain.chain ? chain.chain : null;
  if (!chainData) {
    return `${header}\nNo evolution data available.${formsBlock}`;
  }
  const evolutions = parseEvolutionChain(chainData);
  const lines = [header];
  if (evolutions.length) {
    lines.push('', '<b>Evolutions:</b>', '');
    for (const evo of evolutions) {
      lines.push(`• <b>${esc(evo.from)}</b> → <b>${esc(evo.to)}</b>`);
      lines.push(`  ↳ ${esc(evo.method)}`);
    }
  } else {
    const all = allEvolutions(chainData);
    if (all.length <= 1) {
      lines.push('', `<b>${esc(all[0] || name)}</b> does not evolve.`);
    } else {
      lines.push('', '<b>Evolutions:</b>', '');
      for (let i = 0; i < all.length - 1; i += 1) {
        lines.push(`• <b>${esc(all[i])}</b> → <b>${esc(all[i + 1])}</b>`);
      }
    }
  }
  if (formsBlock) lines.push('', formsBlock.replace(/^\n/, ''));
  return lines.join('\n');
}

// ── Locations (API input: /pokemon/{id}/encounters) ──────────────────────

/** Group encounters by area with unique versions (original logic). */
export function groupEncounters(encounters) {
  const groups = new Map();
  for (const enc of encounters || []) {
    const areaName = titleize(enc.location_area?.name || 'Unknown');
    if (!groups.has(areaName)) groups.set(areaName, []);
    for (const ver of enc.version_details || []) {
      const detail = (ver.encounter_details && ver.encounter_details[0]) || {};
      groups.get(areaName).push({
        version: titleize(ver.version?.name || ''),
        rate: detail.chance || 0,
      });
    }
  }
  return [...groups.entries()];
}

export function locBody(p, encounters, page = 0) {
  const name = esc(p.name || 'Unknown');
  const header = `${uiTag('region')} <b>${name} — Locations</b>\n`;
  const all = groupEncounters(encounters);
  if (!all.length) {
    return { text: `${header}\nNo location data available.`, total: 0 };
  }
  const totalPages = ceilDiv(all.length, LOCATIONS_PER_PAGE);
  page = clampPage(page, totalPages);
  const lines = [header];
  for (const [areaName, details] of all.slice(
    page * LOCATIONS_PER_PAGE, (page + 1) * LOCATIONS_PER_PAGE,
  )) {
    lines.push(`• <b>${esc(areaName)}</b>`);
    const versions = [...new Set(details.map((d) => d.version).filter(Boolean))].sort();
    if (versions.length) lines.push(`  ↳ ${esc(versions.slice(0, 3).join(', '))}`);
  }
  lines.push(`\nPage ${page + 1}/${totalPages}`);
  return { text: lines.join('\n'), total: all.length };
}

export function locRows(p, page, total) {
  const id = p.id;
  const totalPages = ceilDiv(total, LOCATIONS_PER_PAGE);
  page = clampPage(page, totalPages);
  const rows = [];
  const nav = [];
  if (page > 0) nav.push(['◀ Prev', `${CB_D}:loc:${id}:${page - 1}`, PRIMARY]);
  if (total && page < totalPages - 1) {
    nav.push(['Next ▶', `${CB_D}:loc:${id}:${page + 1}`, SUCCESS]);
  }
  if (nav.length) rows.push(nav);
  return [...rows, ...mainRows(p, 'loc'), ...backRow(p)];
}

// ── Weakness (bundled type chart) ────────────────────────────────────────

export function weakBody(p) {
  const name = esc(p.name || 'Unknown');
  const types = p.types || [];
  const eff = typeEffectiveness(types);
  const lines = [`${uiTag('warn')} <b>${name} Type Weaknesses:</b>`, ''];
  lines.push(`<b>Types:</b> ${typeLine(types)}`, '');

  const bucket = (value) => Object.keys(eff.multipliers)
    .filter((t) => Math.round(eff.multipliers[t] * 100) / 100 === value)
    .sort();

  const x4 = bucket(4.0);
  const x2 = bucket(2.0);
  const half = bucket(0.5);
  const quarter = bucket(0.25);
  const immune = bucket(0.0);

  if (x4.length) lines.push(`<b>4× Weak to:</b> ${typeLine(x4)}`);
  if (x2.length) lines.push(`<b>2× Weak to:</b> ${typeLine(x2)}`);
  if (immune.length) lines.push(`<b>Immune (0×):</b> ${typeLine(immune)}`);
  if (half.length) lines.push(`<b>Resists (0.5×):</b> ${typeLine(half)}`);
  if (quarter.length) lines.push(`<b>Resists (0.25×):</b> ${typeLine(quarter)}`);
  if (!(x4.length || x2.length || immune.length || half.length || quarter.length)) {
    lines.push('No weaknesses or resistances.');
  }
  return lines.join('\n');
}

// ── Callback dispatcher (local actions only) ─────────────────────────────
// evo/loc need the API first — dex.js handles those two actions itself.

/** Sync views for: back | moves | mlist | weak. Returns null for others
 *  (evo/loc/noop) so the transport knows it must take over. */
export function dataCallbackView(p, action, extra, userLabel) {
  if (action === 'back') {
    return { rich: mainBody(p), classic: mainBody(p), rows: mainRows(p) };
  }
  if (action === 'moves') {
    return { rich: movesMenuBody(p), classic: movesMenuBody(p), rows: movesRows(p) };
  }
  if (action === 'weak') {
    const text = weakBody(p);
    return { rich: text, classic: text, rows: pageRows(p, 'weak') };
  }
  if (action === 'mlist') {
    const category = (extra && extra.category) || 'levelup';
    const page = (extra && extra.page) || 0;
    const view = moveListView(p, category, page, userLabel);
    return view;
  }
  return null;
}

/** Keyboard for the Evolutions view (API already fetched by then). */
export function evoRows(p) {
  return pageRows(p, 'evo');
}

export { backRow as backRowFor, pageRows as pageRowsFor };
