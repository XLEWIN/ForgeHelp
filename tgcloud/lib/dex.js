// Pokédex transport — the sdk-facing half of /poke /mv /build (ports
// cmd_poke/cmd_mv/cmd_build + on_poke_button/on_build_button). Bodies and
// keyboard rows come from the pure modules (pokemon.js / dexui.js); this
// file only talks to the Bot API through the shared rich.js helpers.
//
// Send ladder for photos (parity with Python send_photo_url → fetch →
// text): sendPhoto by URL (Telegram fetches the art) → download once and
// multipart-upload (blocked URLs) → text-only fallback. Every step
// attaches the colored keyboard with the stripped/bare fallback chain.

import { api, BotApiError, fetch as sdkFetch, InputFile } from 'sdk';
import * as dataui from './dataui.js';
import * as dexui from './dexui.js';
import { E, stripCustomEmoji } from './emoji.js';
import * as pokeapi from './pokeapi.js';
import {
  coloredKbDict, htmlEscape as esc, sendRichStep, sendText,
} from './rich.js';
import { getPokemonData, getPokemonByNameFuzzy, ready } from './pokemon.js';

const FETCH_TIMEOUT_MS = 10_000;

function guard(ms) {
  try {
    return AbortSignal.timeout(ms);
  } catch (_) {
    return undefined; // no AbortSignal.timeout on this runtime — send unguarded
  }
}

/** Payload variants with markup: colored → stripped → bare. */
function kbVariants(payload, markup) {
  const variants = [];
  if (markup) {
    variants.push({ ...payload, reply_markup: markup });
    const stripped = {
      inline_keyboard: markup.inline_keyboard.map((row) => row.map((btn) => {
        const clean = { ...btn };
        delete clean.style;
        delete clean.icon_custom_emoji_id;
        return clean;
      })),
    };
    if (JSON.stringify(stripped) !== JSON.stringify(markup)) {
      variants.push({ ...payload, reply_markup: stripped });
    }
  }
  const bare = { ...payload };
  delete bare.reply_markup;
  variants.push(bare);
  return variants;
}

/** Run api[method](payload) across the markup variants. {result, error}. */
async function callWithKb(method, payload, markup) {
  let last = null;
  for (const attempt of kbVariants(payload, markup)) {
    try {
      return { result: await api[method](attempt), error: null };
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

function logRejected(method, chatId, messageId, error) {
  const where = messageId ? ` msg=${messageId}` : '';
  console.info(`${method} rejected chat=${chatId}${where}: ` +
    `${String(error?.description || '').slice(0, 200)}`);
}

// ── In-place edits (captions on photos, text otherwise) ──────────────────

/** Edit a message caption (photos) or text (everything else) in place,
 *  always with the given keyboard rows (colored → stripped → bare). */
async function editInPlace(chatId, messageId, isPhoto, richBody, classicBody, rows) {
  const markup = rows && rows.length ? coloredKbDict(rows) : null;
  if (isPhoto) {
    const payload = {
      chat_id: chatId,
      message_id: messageId,
      caption: classicBody,
      parse_mode: 'HTML',
    };
    const { result, error } = await callWithKb('editMessageCaption', payload, markup);
    if (result !== null) return 'ok';
    if (String(error?.description || '').toLowerCase().includes('not modified')) return 'unchanged';
    logRejected('editMessageCaption', chatId, messageId, error);
    return 'fail';
  }
  // Bot API editMessageText rejects <p>/<hr> — classic body only.
  const payload = {
    chat_id: chatId,
    message_id: messageId,
    text: classicBody || richBody,
    parse_mode: 'HTML',
  };
  const { result, error } = await callWithKb('editMessageText', payload, markup);
  if (result !== null) return 'ok';
  if (String(error?.description || '').toLowerCase().includes('not modified')) return 'unchanged';
  logRejected('editMessageText', chatId, messageId, error);
  return 'fail';
}

// ── Photo ladder ─────────────────────────────────────────────────────────

/** sendPhoto by URL with reply_markup ladder. Returns result or null. */
async function sendPhotoLadder(chatId, photo, caption, rows, replyTo) {
  const payload = { chat_id: chatId, photo, caption, parse_mode: 'HTML' };
  if (replyTo) payload.reply_parameters = { message_id: replyTo };
  const markup = rows && rows.length ? coloredKbDict(rows) : null;
  const { result, error } = await callWithKb('sendPhoto', payload, markup);
  if (result !== null) return result;
  logRejected('sendPhoto(url)', chatId, 0, error);
  return null;
}

/** Download artwork bytes (web fetch + stream accumulation). */
async function fetchImage(url) {
  try {
    const res = await sdkFetch(url, { signal: guard(FETCH_TIMEOUT_MS) });
    if (!res || !res.ok) return null;
    const chunks = [];
    let total = 0;
    for await (const chunk of res.body) {
      const bytes = typeof chunk === 'string' ? new TextEncoder().encode(chunk) : chunk;
      chunks.push(bytes);
      total += bytes.length;
    }
    const out = new Uint8Array(total);
    let off = 0;
    for (const c of chunks) {
      out.set(c, off);
      off += c.length;
    }
    return out;
  } catch (e) {
    console.debug('fetchImage failed', e);
    return null;
  }
}

/** Multipart sendPhoto with an in-memory file. `mime` matches the bytes
 *  (dex artwork is PNG; the /start welcome photo is JPEG). */
export async function sendPhotoBytes(chatId, bytes, filename, caption, rows, replyTo, mime = 'image/png') {
  const payload = {
    chat_id: chatId,
    photo: new InputFile(bytes, filename, { type: mime }),
    caption,
    parse_mode: 'HTML',
  };
  if (replyTo) payload.reply_parameters = { message_id: replyTo };
  const markup = rows && rows.length ? coloredKbDict(rows) : null;
  const { result, error } = await callWithKb('sendPhoto', payload, markup);
  if (result !== null) return result;
  logRejected('sendPhoto(bytes)', chatId, 0, error);
  return null;
}

/** Photo ladder: URL → bytes → rich/classic text (port of cmd_poke path).
 *  The text fallback carries the keyboard on the RICH send too (port of
 *  send_rich_step reply_markup — buttons always show up). */
async function sendDexPhoto(chatId, view, replyTo) {
  const rows = view.rows;
  if (view.photo) {
    const sent = await sendPhotoLadder(chatId, view.photo, view.caption, rows, replyTo);
    if (sent) return;
    const data = await fetchImage(view.photo);
    if (data) {
      const sent2 = await sendPhotoBytes(chatId, data, `${view.pokemon.id}.png`,
        view.caption, rows, replyTo);
      if (sent2) return;
    }
    console.debug('sendPhoto path failed; classic text fallback');
  }
  await sendRichStep(chatId, view.rich, {
    replyTo,
    markup: rows && rows.length ? coloredKbDict(rows) : null,
    classicText: view.caption,
  });
}

// ── Notices ──────────────────────────────────────────────────────────────

/** Text send with body + markup ladders (original /data pattern:
 *  full-HTML body first, custom-emoji-stripped body second; each body
 *  carries the colored → stripped → bare keyboard variants). */
async function sendTextLadder(chatId, bodies, rows, replyTo) {
  const markup = rows && rows.length ? coloredKbDict(rows) : null;
  for (const body of bodies) {
    if (!body) continue;
    const payload = { chat_id: chatId, text: body, parse_mode: 'HTML' };
    if (replyTo) payload.reply_parameters = { message_id: replyTo };
    const { result, error } = await callWithKb('sendMessage', payload, markup);
    if (result !== null) return 'ok';
    const desc = String(error?.description || '').toLowerCase();
    if (desc.includes('parse entities')) continue; // try stripped body
    logRejected('sendMessage', chatId, 0, error);
    return 'fail';
  }
  return 'fail';
}

/** In-place text edit with the same body + markup ladders (editMessageText
 *  rejects the <p>/<hr> rich subset — /data bodies are line HTML, so the
 *  full body is eligible). */
async function editTextLadder(chatId, messageId, bodies, rows) {
  const markup = rows && rows.length ? coloredKbDict(rows) : null;
  let last = null;
  for (const body of bodies) {
    if (!body) continue;
    const payload = {
      chat_id: chatId,
      message_id: messageId,
      text: body,
      parse_mode: 'HTML',
    };
    const { result, error } = await callWithKb('editMessageText', payload, markup);
    if (result !== null) return 'ok';
    last = error;
    const desc = String(error?.description || '').toLowerCase();
    if (desc.includes('not modified')) return 'unchanged';
    if (!desc.includes('parse entities')) {
      logRejected('editMessageText', chatId, messageId, error);
      return 'fail';
    }
    // entity parse failure → retry with the stripped body
  }
  if (last) logRejected('editMessageText', chatId, messageId, last);
  return 'fail';
}

async function sendNotice(message, text, rows = null) {
  await sendText(message.chat.id, text, {
    replyTo: message.message_id,
    markup: rows && rows.length ? coloredKbDict(rows) : null,
  });
}

function dexNotReadyText() {
  return `${E.WARN} The local Pokédex isn't bundled in this build — ` +
    'my notes still know moves and builds: <code>/ask best build for ' +
    'charizard</code>';
}

// One row, one button — coloredKbDict wants rows-of-triples all the way;
// plain label + premium icon (port of the helpbot Help Menu buttons).
const HELP_MENU_ROWS = [[['Help Menu', 'hp|menu', 'primary', 'gift']]];

// ── Commands ─────────────────────────────────────────────────────────────

/** /mv [pokemon|move] — a Pokémon's move list, or a move's detail card. */
export async function cmdMv(message, args) {
  const query = args.join(' ').trim();
  if (!ready()) {
    await sendNotice(message, dexNotReadyText(), HELP_MENU_ROWS);
    return;
  }
  const view = dexui.mvView(query);
  if (view.kind !== 'ok' && view.kind !== 'move') {
    await sendNotice(message, view.text);
    return;
  }
  const markup = view.rows.length ? coloredKbDict(view.rows) : null;
  // Rich page first — Prev/Next rides on BOTH the rich send and the
  // classic fallback (port of pokedex_ui: "attached to BOTH the rich
  // send and the classic fallback so buttons always show up").
  await sendRichStep(message.chat.id, view.rich, {
    replyTo: message.message_id,
    markup,
    classicText: view.classic,
  });
}

/** /poke [pokemon] — photo + types + max level + interactive pages. */
export async function cmdPoke(message, args) {
  const query = args.join(' ').trim();
  if (!ready()) {
    await sendNotice(message, dexNotReadyText(), HELP_MENU_ROWS);
    return;
  }
  const view = dexui.pokeView(query);
  if (view.kind !== 'ok') {
    await sendNotice(message, view.text);
    return;
  }
  await sendDexPhoto(message.chat.id, view, message.message_id);
}

/** /build [pokemon] (alias /set) — competitive build menu. */
export async function cmdBuild(message, args) {
  const query = args.join(' ').trim();
  if (!ready()) {
    await sendNotice(message, dexNotReadyText(), HELP_MENU_ROWS);
    return;
  }
  const view = dexui.buildView(query);
  if (view.kind !== 'ok') {
    await sendNotice(message, view.text);
    return;
  }
  await sendDexPhoto(message.chat.id, view, message.message_id);
}

/** /data [pokemon] — species encyclopedia (port of data.py data_command):
 *  local card first; Evolutions/Locations pull from PokeAPI on demand. */
export async function cmdData(message, args) {
  const query = args.join(' ').trim();
  if (!query) {
    await sendTextLadder(message.chat.id, [dataui.dataUsageText()], null, message.message_id);
    return;
  }
  if (!ready()) {
    await sendNotice(message, dexNotReadyText(), HELP_MENU_ROWS);
    return;
  }
  const p = getPokemonByNameFuzzy(query);
  if (!p) {
    await sendTextLadder(message.chat.id, [dataui.dataNotFoundText()], null, message.message_id);
    return;
  }
  const view = dataui.dataView(p);
  await sendTextLadder(
    message.chat.id,
    [view.rich, stripCustomEmoji(view.rich)],
    view.rows,
    message.message_id,
  );
}

// ── Callbacks ────────────────────────────────────────────────────────────

/** `pk|{id}|{view}|{page}` + `bd|{id}|{cat}|{view}|{page}` — edit-in-place.
 *  If the original message has a photo, only the caption + markup are
 *  edited so the picture stays put (port of on_poke_button/on_build_button). */
export async function onDexButton(query) {
  const data = String(query.data || '').split('|');
  const isPk = data[0] === 'pk';
  let pid;
  let view;
  let page;
  let cat = '';
  try {
    if (isPk) {
      pid = Number(data[1]);
      view = data[2] || '';
      page = Number(data[3] || 0) || 0;
      if (!Number.isFinite(pid) || !view) throw new Error('bad pk data');
    } else {
      pid = Number(data[1]);
      cat = data[2] || '';
      view = data[3] || '';
      page = Number(data[4] || 0) || 0;
      if (!Number.isFinite(pid) || !view) throw new Error('bad bd data');
    }
  } catch (_) {
    await answer(query); // stale/malformed — clear the spinner
    return;
  }
  await answer(query);

  if (view === 'close') {
    try {
      await api.deleteMessage({
        chat_id: query.message?.chat?.id,
        message_id: query.message?.message_id,
      });
    } catch (e) {
      console.debug('dex close/delete failed', e);
    }
    return;
  }

  if (!ready()) {
    try {
      await sendNotice(query.message, dexNotReadyText());
    } catch (e) {
      console.debug('dex not-ready notice failed', e);
    }
    return;
  }

  let p = getPokemonData(pid);
  if (!p) p = getPokemonByNameFuzzy(String(pid));
  if (!p) {
    try {
      await sendNotice(query.message, `${E.CROSS} That Pokémon left the local dex.`);
    } catch (e) {
      console.debug('dex missing notice failed', e);
    }
    return;
  }

  const msg = query.message;
  const chatId = msg.chat.id;
  const msgId = msg.message_id;
  const isPhoto = Boolean(msg.photo) || Boolean(msg.caption);
  const resolved = isPk
    ? dexui.pokeCallbackView(p, view, page)
    : dexui.buildCallbackView(p, cat, view, page);
  await editInPlace(chatId, msgId, isPhoto, resolved.rich, resolved.classic, resolved.rows);
}

async function answer(query, text = '', showAlert = false) {
  try {
    await api.answerCallbackQuery({
      callback_query_id: query.id,
      ...(text ? { text } : {}),
      ...(showAlert ? { show_alert: true } : {}),
    });
  } catch (e) {
    console.debug('answerCallbackQuery failed', e);
  }
}

/** `d:{action}:{id}` (+ loc page / mlist category+page) — port of
 *  data.py handle_data_callback. Local views render synchronously;
 *  Evolutions/Locations fetch PokeAPI first (answer the spinner before
 *  awaiting, exactly like the original). */
export async function onDataButton(query) {
  const parts = String(query.data || '').split(':');
  if (parts.length < 3) {
    await answer(query);
    return;
  }
  const action = parts[1];
  if (action === 'noop') {
    await answer(query);
    return;
  }
  const pid = Number(parts[2]);
  if (!Number.isFinite(pid)) {
    await answer(query);
    return;
  }
  const p = getPokemonData(pid) || getPokemonByNameFuzzy(String(pid));
  if (!p) {
    await answer(query, 'Pokémon data not found.', true);
    return;
  }
  await answer(query);
  const msg = query.message;
  if (!msg) return;
  const chatId = msg.chat.id;
  const msgId = msg.message_id;
  const userLabel = query.from?.first_name || query.from?.username || 'User';

  let view = null;
  try {
    if (action === 'evo') {
      const species = await pokeapi.getSpecies(pid);
      const chain = await pokeapi.getEvolutionChain(pid, species);
      const text = dataui.evoBody(p, species, chain);
      view = { rich: text, classic: text, rows: dataui.evoRows(p) };
    } else if (action === 'loc') {
      const page = Number(parts[3] || 0) || 0;
      const encounters = await pokeapi.getEncounters(pid); // null on failure
      const { text, total } = dataui.locBody(p, encounters, page);
      view = { rich: text, classic: text, rows: dataui.locRows(p, page, total) };
    } else {
      const extra = {
        category: parts[3] || 'levelup',
        page: Number(parts[4] || 0) || 0,
      };
      view = dataui.dataCallbackView(p, action, extra, userLabel);
    }
  } catch (e) {
    console.debug('data callback failed', e);
  }
  if (!view) return; // unknown action — already answered
  await editTextLadder(
    chatId,
    msgId,
    [view.rich, stripCustomEmoji(view.rich)],
    view.rows,
  );
}

// Re-export for handlers that render the notice query text themselves.
export { esc };
