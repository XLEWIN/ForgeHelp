// Row → keyboard / pill serialization (PURE — no sdk). Port of the
// row helpers in help/helpbot/rich.py:
//   colored_kb_dict / classic_kb_dict / rows_to_pills / rows_to_kb /
//   pill_label / glyph_label / _with_kb_fallback / _strip_kb_markup
//
// Rows are shared between the two renderings:
//   item = (label, data) or (label, data, style[, iconKey])
//   - rich pills: label inserted RAW when it already contains tags
//     (pill_label output — `<tg-emoji…>` must survive; port of
//     rows_to_pills "Labels may contain <tg-emoji> (not escaped)"),
//     otherwise HTML-escaped.
//   - classic buttons: tags stripped from the label, the premium
//     emoji arrives via `icon_custom_emoji_id` (Bot API 10.1), the
//     colour via `style`.
// This module is sdk-free so tools/test_pure.mjs can assert the
// serialization directly.

import { uiGlyph, uiIconId, uiTag } from './emoji.js';
import { DANGER, LINK, PRIMARY, SUCCESS, htmlEscape } from './style.js';

function isUrl(data) {
  return String(data || '').startsWith('http://') || String(data || '').startsWith('https://');
}

function esc(text) {
  return htmlEscape(text);
}

// ── Colored classic inline keyboards (Bot API 10.1 style + icon) ────────

/** Raw reply_markup dict with per-button `style` + premium icon. */
export function coloredKbDict(rows, { stripIcons = false } = {}) {
  const board = [];
  for (const row of rows) {
    const line = [];
    for (const item of row) {
      // Pill labels carry <tg-emoji…>fallback</tg-emoji>: drop the WHOLE
      // element (fallback included) — the icon column below renders the
      // premium emoji, and keeping the glyph would double it up.
      const label = String(item[0] ?? '')
        .replace(/<tg-emoji[^>]*>[\s\S]*?<\/tg-emoji>/g, ' ')
        .replace(/<[^>]+>/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
      const data = String(item[1] ?? '');
      const style = item.length > 2 ? String(item[2] ?? '') : '';
      const iconKey = item.length > 3 ? String(item[3] ?? '') : '';
      const btn = { text: label };
      if (isUrl(data)) btn.url = data;
      else btn.callback_data = data;
      if ([PRIMARY, SUCCESS, DANGER, LINK].includes(style) && !stripIcons) btn.style = style;
      if (iconKey && !stripIcons) {
        const icon = uiIconId(iconKey);
        if (icon) btn.icon_custom_emoji_id = icon;
      }
      line.push(btn);
    }
    if (line.length) board.push(line);
  }
  return { inline_keyboard: board };
}

/** Plain keyboard dict (no style / icon) — safe fallback. */
export function classicKbDict(rows) {
  return coloredKbDict(rows, { stripIcons: true });
}

/** Drop style / icon_custom_emoji_id from a raw keyboard dict. */
export function stripKbMarkup(markup) {
  if (!markup || !markup.inline_keyboard) return markup;
  return {
    inline_keyboard: markup.inline_keyboard.map((row) => row.map((btn) => {
      const clean = { ...btn };
      delete clean.style;
      delete clean.icon_custom_emoji_id;
      return clean;
    })),
  };
}

/** Payloads to try: colored kb first, then stripped, then bare. */
export function withKbFallback(payload, markup) {
  const variants = [];
  if (markup) {
    variants.push({ ...payload, reply_markup: markup });
    const stripped = stripKbMarkup(markup);
    if (JSON.stringify(stripped) !== JSON.stringify(markup)) {
      variants.push({ ...payload, reply_markup: stripped });
    }
  }
  const bare = { ...payload };
  delete bare.reply_markup;
  variants.push(bare);
  return variants;
}

// ── Rich pills + classic keyboard from the same rows ─────────────────────

/** `<tg-button-row>` HTML. Labels may contain `<tg-emoji>` (pill_label
 *  output) and are inserted raw; plain labels are HTML-escaped — port of
 *  rows_to_pills. */
export function rowsToPills(rows) {
  const parts = [];
  for (const row of rows) {
    const pills = [];
    for (const item of row) {
      const [label, data] = item;
      const style = item.length > 2 && item[2] ? ` style="${item[2]}"` : '';
      const raw = String(label ?? '');
      const text = raw.includes('<') ? raw : esc(raw);
      if (isUrl(data)) {
        pills.push(`<tg-button type="url" url="${esc(data)}"${style}>${text}</tg-button>`);
      } else {
        pills.push(`<tg-button type="callback_data" data="${esc(data)}"${style}>${text}</tg-button>`);
      }
    }
    parts.push(`<tg-button-row>${pills.join('')}</tg-button-row>`);
  }
  return parts.join('');
}

/** Classic fallback keyboard from the same rows (plain labels). */
export function rowsToKb(rows) {
  return classicKbDict(rows);
}

/** `<tg-emoji…>🎁</tg-emoji> Guides` — premium icon + escaped text. */
export function pillLabel(iconKey, text) {
  const tag = uiTag(iconKey);
  return tag ? `${tag} ${esc(text)}` : esc(text);
}

/** `🎁 Guides` — plain glyph for classic buttons. */
export function glyphLabel(iconKey, text) {
  const g = uiGlyph(iconKey);
  return g ? `${g} ${text}` : text;
}
