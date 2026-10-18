// Rich page builders — port of the page functions in help/helpbot/bot.py
// (rich_start / rich_help / rich_about / rich_ask_usage + guide rows).
// Bodies are Rich HTML (pills embedded); classic downgrades come from
// rich.js classicHtml() and the matching classic keyboards.

import * as cfg from './config.js';
import * as kb from './kb.js';
import { E, uiTag } from './emoji.js';
import {
  DANGER, LINK, PRIMARY, SUCCESS, coloredKbDict, rowsToPills,
  markdownTablesToHtml,
} from './rich.js';
import { stripPlainEmoji } from './sanitize.js';

export const SEP = '━━━━━━━━━━━━';

/** Start/home buttons — Unicode emoji labels + colored styles (no
 *  premium-icon prerequisite; same rows feed pills and classic kb). */
function homeRows() {
  return [
    [
      ['💬 Ask Oak', 'hp|ask', SUCCESS],
      ['📖 Help Menu', 'hp|menu', PRIMARY],
    ],
    [['📋 Commands', 'hp|commands', PRIMARY]],
    [[`🛟 Support ${cfg.SUPPORT_LABEL}`, cfg.SUPPORT_URL, LINK]],
  ];
}

/** Classic fallback — same labels + styles as the rich pills. */
export function homeKb() {
  return coloredKbDict(homeRows());
}

/** Guide rows — Unicode labels, PRIMARY nav style. */
export function guideRows() {
  const rows = [];
  for (const [stem, title] of kb.guides()) {
    const label = stem.replace(/^\d+-/, '').replace(/-/g, ' ');
    rows.push([[
      `📖 ${title || label.replace(/\b\w/g, (c) => c.toUpperCase())}`,
      `hp|${stem}`,
      PRIMARY,
    ]]);
  }
  rows.push([['📋 All commands', 'hp|commands', PRIMARY]]);
  rows.push([
    ['💬 Ask Oak', 'hp|ask', SUCCESS],
    ['✖ Close', 'hp|close', DANGER],
  ]);
  return rows;
}

/** Classic guide keyboard — same labels + styles as the pills. */
export function guideKb() {
  return coloredKbDict(guideRows());
}

/** Rich /start — premium title, short blurb, action pills (no photo). */
export function richStart(_name, username = 'Professor_OakBot') {
  const who = esc(username || 'Professor_OakBot');
  return (
    `<p>${uiTag('fire')} <b>@${who}</b></p>` +
    '<p>I\'m the AI study guide for <b>Forge</b> (@PokeForgebot) — ' +
    'a Pokémon catching, battling and trading game here on Telegram. ' +
    'Ask me anything about commands, shiny odds, regions, breeding ' +
    'and more!</p>' +
    '<p>Type your question, or use ' +
    '<code>/ask &lt;your question&gt;</code>. ' +
    '/help for the full command list.</p>' +
    rowsToPills(homeRows())
  );
}

/** Classic /start keyboard + body fallback. */
export function startKb() {
  return homeKb();
}

/** Rich /help body — Oak field guide + guide pills. The offline dex
 *  commands (/mv /poke /build) are listed — the compact Pokédex ships
 *  in this build (tgcloud/lib/dexdata.js). */
export function richHelp() {
  return (
    `<h2>${uiTag('sparkle')} Professor Oak's Forge Field Guide</h2>` +
    `<p>${uiTag('chat')} Ah, a curious trainer! Ask me anything about ` +
    'the <b>Forge</b> Pokémon game — catching, battling, breeding, ' +
    'trading, regions, quests, every command — and I\'ll share what my ' +
    'research notes say.</p>' +
    `<h3>${uiTag('star')} Commands</h3>` +
    '<ul>' +
    '<li><code>/ask &lt;question&gt;</code> — ask me anything ' +
    '(alias: /ai)</li>' +
    '<li><code>/reset</code> — forget this conversation, start fresh</li>' +
    '<li><code>/commands [name]</code> — command index</li>' +
    '<li><code>/guide [topic]</code> — full guides</li>' +
    '<li><code>/search &lt;question&gt;</code> — raw documentation ' +
    'matches</li>' +
    '<li><code>/mv &lt;pokemon&gt;</code> — every learnable move with ' +
    'power, accuracy and source</li>' +
    '<li><code>/poke &lt;pokemon&gt;</code> — Pokédex card with IVs, ' +
    'natures and move lists</li>' +
    '<li><code>/build &lt;pokemon&gt;</code> — competitive build ideas ' +
    '(alias: /set)</li>' +
    '<li><code>/bug &lt;text&gt;</code> — report a bug to the ' +
    'Developers</li>' +
    '<li><code>/about</code> — bot status</li>' +
    '<li><code>/help</code> — this message</li>' +
    '</ul>' +
    `<blockquote>${uiTag('chat')} I remember our last few exchanges, so ` +
    'follow-ups like "and what about Johto?" work just fine. Tap a ' +
    'guide below!</blockquote>' +
    `<h3>${uiTag('gift')} Guides</h3>` +
    rowsToPills(guideRows())
  );
}

/** Rich /about body — provider chain + knowledge stats + live counters. */
export function richAbout(stats) {
  const chain = keyChain();
  const mode = chain.length ? formatChain(chain) : 'no API key — short fallback replies';
  const kbStats = kb.stats();
  return (
    `<h2>${uiTag('sparkle')} Professor Oak's Forge Help Bot</h2>` +
    `<p>${uiTag('chat')} AI: ${esc(mode)}</p>` +
    `<p>${uiTag('star')} Knowledge: ${kbStats.files} files · ` +
    `${kbStats.chunks} chunks · ${kbStats.commands} command names</p>` +
    `<p>${uiTag('fire')} Answered so far: ${stats.questions} ` +
    `(AI ${stats.ai || 0}, fallback ${stats.fallback || 0}, ` +
    `off-topic ${stats.offtopic || 0})</p>` +
    `<footer>Support: ${cfg.SUPPORT_LABEL} · Updates: @ForgeUpdates</footer>` +
    rowsToPills([
      [[`🛟 Support ${cfg.SUPPORT_LABEL}`, cfg.SUPPORT_URL, LINK]],
      [['📖 Help Menu', 'hp|menu', PRIMARY]],
    ])
  );
}

/** Rich /ask with no arguments — usage card. */
export function richAskUsage() {
  return (
    `<h3>${uiTag('chat')} How to ask me</h3>` +
    '<p>Usage: <code>/ask how do I breed eggs?</code></p>' +
    '<blockquote>Or just send your question here in DM — I\'m always ' +
    'listening!</blockquote>' +
    rowsToPills([[
      ['💬 Example question', 'hp|example', SUCCESS],
    ]])
  );
}

/** Classic /ask usage keyboard. */
export function askUsageKb() {
  return coloredKbDict([[['💬 Example question', 'hp|example', SUCCESS]]]);
}

/** Guide picker body (used by /guide and hp|menu). */
export function richGuidePicker() {
  return `<h3>${uiTag('gift')} Pick a guide, trainer</h3>` + rowsToPills(guideRows());
}

// ── guide rendering ──────────────────────────────────────────────────────

function stripTags(text) {
  return String(text || '').replace(/<[^>]+>/g, '');
}

/** Build a Rich HTML body for a guide, converting markdown tables
 *  (port of bot.py _guide_rich_body). */
export function guideRichBody(stem, title, text) {
  void stem;
  const titleEsc = esc(title);
  let body = markdownTablesToHtml(stripPlainEmoji(text));
  // Turn markdown headings into Rich headings.
  body = body.replace(/^#### (.+)$/gm, '<h6>$1</h6>');
  body = body.replace(/^### (.+)$/gm, '<h5>$1</h5>');
  body = body.replace(/^## (.+)$/gm, '<h4>$1</h4>');
  body = body.replace(/^# (.+)$/gm, '<h3>$1</h3>');
  // Bold markdown → <b>; inline code → <code>.
  body = body.replace(/\*\*(.+?)\*\*/gs, '<b>$1</b>');
  body = body.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bullet lists → <ul><li> (consecutive groups only).
  const out = [];
  let inList = false;
  for (const line of body.split('\n')) {
    const m = line.match(/^[-*] (.+)$/);
    if (m) {
      if (!inList) {
        out.push('<ul>');
        inList = true;
      }
      out.push(`<li>${m[1]}</li>`);
    } else {
      if (inList) {
        out.push('</ul>');
        inList = false;
      }
      out.push(line);
    }
  }
  if (inList) out.push('</ul>');
  body = out.join('\n');
  return `<h3>${uiTag('gift')} <b>${titleEsc}</b></h3>\n${body}`;
}

// ── local provider view (for /about) ─────────────────────────────────────

import { chainSpec as keyChain, formatChain } from './keyvault.js';

function esc(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Keep E referenced (used by classic fallbacks at call sites).
export { E, stripTags };
