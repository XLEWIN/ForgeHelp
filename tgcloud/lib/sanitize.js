// Telegram HTML safety + premium-emoji guarantee — pure port of the text
// pipeline in help/helpbot/ai.py (no SDK imports; unit-testable locally).
//
// Models emit rich HTML / markdown / plain emoji; Telegram only accepts a
// tiny HTML subset and this bot's UI is premium-emoji-only. Everything
// flows through normalizeHtml → markdownToHtml → sanitizeHtml →
// stripPlainEmoji → ensurePremiumEmoji before it is sent.

import { E } from './emoji.js';

// Telegram allows a small HTML subset. Anything outside it is escaped.
// Order matters: the href variant first, then bare "a", so the closing
// form </a> is allowed too (otherwise links flatten in the balance check).
const ALLOWED_TAG = new RegExp(
  '</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|blockquote|tg-spoiler|' +
  'a\\s+href="[^"]+"|a|tg-emoji[^>]*)>',
  'gi',
);
const ENTITY = /&(amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);/g;

function escapeChar(ch) {
  // Telegram's HTML subset has no &apos; — a lone apostrophe is legal
  // as-is, so never turn ' into an entity Telegram will print raw.
  return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch];
}

function escapeStr(text) {
  return text.replace(/[&<>"]/g, escapeChar);
}

/** Escape <>& except for already-valid entities (port of _escape_range). */
function escapeRange(chunk) {
  let out = '';
  let pos = 0;
  for (const m of chunk.matchAll(ENTITY)) {
    out += escapeStr(chunk.slice(pos, m.index));
    out += m[0];
    pos = (m.index || 0) + m[0].length;
  }
  return out + escapeStr(chunk.slice(pos));
}

/** Map the HTML Telegram does not support onto what it does (port of
 *  _normalize_html): lists become dashes, headings become bold, the rest
 *  inline is unwrapped. */
export function normalizeHtml(text) {
  text = String(text || '').replace(/<br\s*\/?>/gi, '\n');
  text = text.replace(/<\/(p|div|tr|table|blockquote)>/gi, '\n');
  text = text.replace(/<h[1-6][^>]*>(.*?)<\/h[1-6]>/gis, '<b>$1</b>');
  text = text.replace(/<(?:strong|b)\s*>/gi, '<b>').replace(/<\/(?:strong|b)>/gi, '</b>');
  text = text.replace(/<(?:em|i)\s*>/gi, '<i>').replace(/<\/(?:em|i)>/gi, '</i>');
  text = text.replace(/<li[^>]*>/gi, '- ').replace(/<\/li>/gi, '\n');
  // Drop the wrappers themselves (order matters: after <li> → "- ").
  text = text.replace(
    /<\/?(?:html|head|body|meta|ul|ol|p|div|span|section|article|table|thead|tbody|tr|td|th)[^>]*>/gi,
    '',
  );
  // Telegram HTML does not know &apos;/&#39; — print them as '.
  return text.replace(/&apos;/g, "'").replace(/&#39;/g, "'");
}

/** Convert the markdown some models emit anyway into Telegram HTML
 *  (port of _markdown_to_html). Runs before sanitising. */
export function markdownToHtml(text) {
  text = String(text || '').replace(/^#{1,6}\s*(.+)$/gm, '<b>$1</b>');
  text = text.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  text = text.replace(/(?<![\w*])\*([^*\n]+)\*(?![\w*])/g, '<i>$1</i>');
  text = text.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  return text;
}

/** Balance check (port of _balanced) — hyphenated names (tg-emoji,
 *  tg-spoiler) are one token, stray unknown tags fail. */
function balanced(text) {
  const stack = [];
  for (const m of text.matchAll(/<(\/?)([a-z][a-z0-9-]*)([^>]*)>/gi)) {
    const closing = m[1] === '/';
    const name = m[2].toLowerCase();
    const attrs = m[3];
    if (['a', 'blockquote', 'pre', 'code', 'tg-spoiler', 'tg-emoji', 'b', 'i',
      'u', 's', 'strong', 'em', 'ins', 'strike', 'del'].includes(name)) {
      if (closing) {
        if (!stack.length || stack[stack.length - 1] !== name) return false;
        stack.pop();
      } else if (!attrs.trimEnd().endsWith('/')) {
        stack.push(name);
      }
    } else if (!closing) {
      return false; // stray unknown tag
    }
  }
  return !stack.length;
}

/** Keep Telegram-legal tags, escape everything else; flatten when tags are
 *  unbalanced (port of sanitize_html). */
export function sanitizeHtml(text) {
  if (!text) return '';
  // Models sometimes emit &apos; / &#39; themselves; Telegram shows those
  // as raw text, so normalise to a plain apostrophe first.
  text = text.replace(/&apos;/g, "'").replace(/&#39;/g, "'");
  let out = '';
  let pos = 0;
  ALLOWED_TAG.lastIndex = 0;
  for (let m = ALLOWED_TAG.exec(text); m; m = ALLOWED_TAG.exec(text)) {
    out += escapeRange(text.slice(pos, m.index));
    out += m[0];
    pos = m.index + m[0].length;
  }
  out += escapeRange(text.slice(pos));
  return balanced(out) ? out : escapeRange(text);
}

/** Split on paragraph boundaries so long answers still send (port of
 *  split_message, limit 3800). */
export function splitMessage(text, limit = 3800) {
  text = String(text || '').trim();
  if (text.length <= limit) return [text];
  const parts = [];
  let current = '';
  for (const para of text.split(/\n{2,}/)) {
    const candidate = `${current}\n\n${para}`.trim();
    if (candidate.length <= limit) {
      current = candidate;
      continue;
    }
    if (current) {
      parts.push(current);
      current = '';
    }
    if (para.length <= limit) {
      current = para;
      continue;
    }
    let rest = para;
    while (rest.length > limit) { // very long single paragraph
      let cut = rest.lastIndexOf(' ', limit);
      cut = cut > limit / 2 ? cut : limit;
      parts.push(rest.slice(0, cut).trim());
      rest = rest.slice(cut).trim();
    }
    current = rest;
  }
  if (current) parts.push(current);
  return parts.filter(Boolean);
}

// ── premium-emoji guarantee ──────────────────────────────────────────────

/** Heuristic topic → premium emoji used when the model skipped them. */
const TOPICS = [
  [['shin', 'sparkl', 'rare'], E.SPARKLE],
  [['coin', 'price', 'cost', 'f.c', 'econom', 'shop', 'buy', 'sell', 'trade'], E.COIN],
  [['battle', 'fight', 'pvp', 'team', 'move', 'damage', 'type'], E.BATTLE],
  [['region', 'travel', 'route', 'pokedex', 'dex'], E.REGION],
  [['leaderboard', 'rank', 'trophy', 'top', 'win'], E.TROPHY],
  [['gift', 'reward', 'claim', 'bonus', 'daily'], E.GIFT],
  [['catch', 'hunt', 'ball', 'capture'], E.STAR],
  [['help', 'guide', 'command', 'how'], E.ROCKET],
];

function topicTag(text) {
  const low = String(text || '').toLowerCase();
  for (const [words, tag] of TOPICS) {
    if (words.some((w) => low.includes(w))) return tag;
  }
  return E.SPARKLE;
}

/** Premium <tg-emoji>…</tg-emoji> blocks (kept verbatim while stripping). */
const TG_EMOJI_BLOCK = /<tg-emoji\b[^>]*>.*?<\/tg-emoji>/gis;

/** Everything Telegram would render as a *normal* unicode emoji —
 *  variation selectors / ZWJ included so sequences collapse cleanly. */
const PLAIN_EMOJI = new RegExp(
  '[' +
  '\\u{1F000}-\\u{1FAFF}' + // pictographs, emoticons, transport
  '\\u{1FB00}-\\u{1FBFF}' + // symbols and pictographs extended-A
  '\\u2600-\\u27BF' + // misc symbols + dingbats (✨✅⚔️…)
  '\\u2B00-\\u2BFF' + // arrows, stars (⭐)
  '\\uFE00-\\uFE0F' + // variation selectors
  '\\u200D' + // zero-width joiner
  '\\u20E3' + // combining keycap
  ']+',
  'gu',
);

/** Remove every normal unicode emoji, keeping premium <tg-emoji> tags
 *  (port of strip_plain_emoji). */
export function stripPlainEmoji(text) {
  if (!text) return text;
  const tags = [];
  text = text.replace(TG_EMOJI_BLOCK, (m) => {
    tags.push(m);
    return `\x00${tags.length - 1}\x00`;
  });
  text = text.replace(PLAIN_EMOJI, '');
  return text.replace(/\x00(\d+)\x00/g, (_m, i) => tags[Number(i)]);
}

/** Guarantee the HTML carries at least one premium <tg-emoji> (port of
 *  ensure_premium_emoji — called after sanitizeHtml so tags survive). */
export function ensurePremiumEmoji(text) {
  if (!text) return text;
  if (text.includes('tg-emoji')) return text;
  const tag = topicTag(text);
  // Insert after any leading Oak/catchphrase line if present, else at top.
  const lines = text.split('\n');
  const first = lines[0];
  const rest = lines.length > 1 ? '\n' + lines.slice(1).join('\n') : '';
  if (first.trimStart().startsWith('<b>')) return `${first}\n${tag}${rest}`;
  return `${tag} ${text}`;
}

/** Strip all tags for plain-text fallback / history (bot.py _strip_tags). */
export function stripTags(text) {
  return String(text || '').replace(/<[^>]+>/g, '');
}
