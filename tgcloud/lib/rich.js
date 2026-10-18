// Rich Message helpers (sendRichMessage) + classic HTML fallback — port of
// help/helpbot/rich.py, using the platform SDK (`api.*`) instead of raw
// api.telegram.org HTTP (the platform owns the token here).
// Row serialization (keyboards + pills) lives in keyboard.js (pure) and is
// re-exported here so existing call sites keep importing from rich.js.
//
// Rich HTML dialect (core.telegram.org/bots/api#rich-html-style):
// - larger text: <h1>..<h6>
// - structure:   <p> <hr/> <ul>/<ol>/<li> <table> <footer> <blockquote>
// - inline:       <b> <i> <u> <s> <code> <mark> <tg-spoiler> <tg-emoji>
// - buttons:      <tg-button-row> / <tg-button type="callback_data|url">
//
// Every send degrades: colored keyboard → stripped keyboard → bare, and
// rich pages fall back to classic HTML + inline keyboard.

import { api, BotApiError } from 'sdk';
import { withKbFallback } from './keyboard.js';
import { DANGER, LINK, PRIMARY, SUCCESS, htmlEscape } from './style.js';

// Style constants + escaping live in style.js (pure); the row builders
// live in keyboard.js (pure) — all re-exported here so existing call
// sites keep importing them from rich.js.
export { DANGER, LINK, PRIMARY, SUCCESS, htmlEscape };
export {
  coloredKbDict, classicKbDict, rowsToPills, rowsToKb, pillLabel, glyphLabel,
} from './keyboard.js';

const SEP = '━━━━━━━━━━━━';

function esc(text) {
  return htmlEscape(text);
}

// ── Transport ────────────────────────────────────────────────────────────

/** Try each payload variant with `call`; returns {result, error}.
 *  BotApiError variants are consumed; anything else rethrows. */
async function tryVariants(call, variants) {
  let last = null;
  for (const attempt of variants) {
    try {
      return { result: await call(attempt), error: null };
    } catch (e) {
      if (e instanceof BotApiError) {
        last = e;
        continue;
      }
      throw e;
    }
  }
  return { result: null, error: last };
}

/** sendRichMessage(html=…). `markup` is attached to the rich send
 *  (port of send_rich's reply_markup — colored → stripped → bare).
 *  Returns result / true, or null on failure. */
export async function sendRich(chatId, richHtml, { replyTo = null, markup = null } = {}) {
  const payload = { chat_id: chatId, rich_message: { html: richHtml } };
  if (replyTo) payload.reply_parameters = { message_id: replyTo };
  const { result, error } = await tryVariants(
    (attempt) => api.sendRichMessage(attempt),
    withKbFallback(payload, markup),
  );
  if (result !== null) return result;
  console.info(`sendRichMessage rejected chat=${chatId}: ${String(error?.description || '').slice(0, 200)}`);
  return null;
}

/** Send rich HTML; fall back to classic HTML + keyboard. Returns true
 *  when the rich message went out (port of send_rich_step):
 *  `markup` attaches to BOTH the rich send and the classic fallback;
 *  `classicMarkup` overrides it for the fallback when provided. */
export async function sendRichStep(chatId, richHtml, {
  replyTo = null, markup = null, classicMarkup = null, classicText = null,
} = {}) {
  if (await sendRich(chatId, richHtml, { replyTo, markup })) return true;
  const kb = classicMarkup !== null ? classicMarkup : markup;
  const text = classicText !== null ? classicText : classicHtml(richHtml);
  const payload = { chat_id: chatId, text, parse_mode: 'HTML' };
  if (replyTo) payload.reply_parameters = { message_id: replyTo };
  const { result } = await tryVariants(
    (attempt) => api.sendMessage(attempt),
    withKbFallback(payload, kb),
  );
  if (result !== null) return false;
  // Last resort: plain text.
  const plain = { chat_id: chatId, text: text.replace(/<[^>]+>/g, '') };
  if (replyTo) plain.reply_parameters = { message_id: replyTo };
  try {
    await api.sendMessage(plain);
  } catch (e) {
    console.error(`classic sendMessage all variants failed chat=${chatId}`, e);
  }
  return false;
}

/** sendMessage with classic HTML + colored keyboard. Returns the sent
 *  Message or null (port of send_text). */
export async function sendText(chatId, text, { markup = null, replyTo = null } = {}) {
  const payload = { chat_id: chatId, text, parse_mode: 'HTML' };
  if (replyTo) payload.reply_parameters = { message_id: replyTo };
  const { result, error } = await tryVariants(
    (attempt) => api.sendMessage(attempt),
    withKbFallback(payload, markup),
  );
  if (result !== null && typeof result === 'object') return result;
  console.info(`send_text all variants failed chat=${chatId}: ${String(error?.description || '').slice(0, 200)}`);
  return null;
}

/** editMessageText with HTML — 'ok' | 'unchanged' | 'fail'. */
export async function editMessageHtml(chatId, messageId, text, { markup = null } = {}) {
  const payload = { chat_id: chatId, message_id: messageId, text, parse_mode: 'HTML' };
  const { result, error } = await tryVariants(
    (attempt) => api.editMessageText(attempt),
    withKbFallback(payload, markup),
  );
  if (result !== null) return 'ok';
  if (String(error?.description || '').toLowerCase().includes('not modified')) return 'unchanged';
  console.info(`editMessageText rejected chat=${chatId} msg=${messageId}: ${String(error?.description || '').slice(0, 200)}`);
  return 'fail';
}

/** editMessageReplyMarkup only (caption untouched). 'ok' | 'fail'. */
export async function editMarkup(chatId, messageId, markup) {
  const payload = { chat_id: chatId, message_id: messageId };
  const { result } = await tryVariants(
    (attempt) => api.editMessageReplyMarkup(attempt),
    withKbFallback(payload, markup),
  );
  return result !== null ? 'ok' : 'fail';
}

// ── Downgrades ───────────────────────────────────────────────────────────

/** Downgrade Rich HTML to the classic Bot API HTML subset (port of
 *  classic_html in rich.py). */
export function classicHtml(rich) {
  let s = rich;
  s = s.replace(/<hr\s*\/?>/g, SEP);
  s = s.replace(/<h([1-6])[^>]*>(.*?)<\/h\1>/gis, '<b>$2</b>');
  s = s.replace(/<p>(.*?)<\/p>/gis, '$1\n');
  s = s.replace(/<li>(.*?)<\/li>/gis, '• $1\n');
  for (const tag of ['ul', 'ol']) s = s.split(`<${tag}>`).join('').split(`</${tag}>`).join('');
  // Drop pill rows: the classic keyboard carries the same buttons.
  s = s.replace(/<tg-button-row[^>]*>.*?<\/tg-button-row>/gis, '');
  s = s.replace(/<tg-button[^>]*>(.*?)<\/tg-button>/gis, '$1');
  s = s.replace(/<footer>(.*?)<\/footer>/gis, '$1\n');
  s = s.replace(/<mark>(.*?)<\/mark>/gis, '<b>$1</b>');
  s = s.replace(/<br\s*\/?>/g, '\n');
  s = s.replace(/<\/?(?:figure|figcaption|img|video|audio)\b[^>]*>/g, '');
  // Tables: rich <table> → classic plain-text rows.
  s = s.replace(/<table>.*?<\/table>/gis, (block) => {
    const rows = [];
    for (const tr of block.matchAll(/<tr>(.*?)<\/tr>/gis)) {
      const cells = [...tr[1].matchAll(/<t[hd][^>]*>(.*?)<\/t[hd]>/gis)]
        .map((c) => c[1].replace(/<[^>]+>/g, '').trim());
      rows.push(cells.join(' | '));
    }
    return rows.length ? `${rows.join('\n')}\n` : '';
  });
  for (const [richEnt, classicRep] of [
    ['&nbsp;', ' '], ['&hellip;', '…'], ['&mdash;', '—'],
    ['&ndash;', '–'], ['&apos;', "'"], ['&#39;', "'"],
  ]) {
    s = s.split(richEnt).join(classicRep);
  }
  s = s.replace(/\n{3,}/g, '\n\n');
  return s.trim();
}

const MD_TABLE_SEP = /^\s*\|?[\s:|-]+\|?\s*$/;
const MD_TABLE_ROW = /^\s*\|(.+)\|\s*$/;

/** Convert markdown pipe tables to Rich <table> HTML (port of
 *  markdown_tables_to_html — only the table block is replaced). */
export function markdownTablesToHtml(md) {
  const lines = String(md || '').split('\n');
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (MD_TABLE_ROW.test(line) && i + 1 < lines.length && MD_TABLE_SEP.test(lines[i + 1])) {
      const headerCells = line.slice(line.indexOf('|') + 1, line.lastIndexOf('|'))
        .split('|').map((c) => c.trim());
      i += 2; // skip separator
      const bodyRows = [];
      while (i < lines.length) {
        const m = lines[i].match(MD_TABLE_ROW);
        if (!m) break;
        bodyRows.push(m[1].split('|').map((c) => c.trim()));
        i += 1;
      }
      const parts = ['<table>'];
      if (headerCells.length) {
        parts.push('<tr>', ...headerCells.map((c) => `<th>${esc(c)}</th>`), '</tr>');
      }
      for (const row of bodyRows) {
        parts.push('<tr>', ...row.map((c) => `<td>${esc(c)}</td>`), '</tr>');
      }
      parts.push('</table>');
      out.push(parts.join(''));
    } else {
      out.push(line);
      i += 1;
    }
  }
  return out.join('\n');
}
