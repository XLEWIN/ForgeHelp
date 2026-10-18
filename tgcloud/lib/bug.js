// `/bug` — one-tap bug reports to the developers' group chat.
// Port of help/helpbot/bug.py; the JSON state file is replaced by the
// bugReports / bugReplies / bugSeq tables (state must survive restarts
// and every invocation is stateless).
//
// Flow:
// 1. A player sends `/bug <text>` (or replies to a message with it).
// 2. A card lands in BUG_REPORT_CHAT_ID — reporter link, id, chat type,
//    time, the escaped report in a blockquote — plus Send reply / Dismiss.
// 3. A developer REPLIES to that card (text or media — stored, not
//    forwarded yet) and taps Send reply.
// 4. The stored reply is delivered to the reporting user as a message
//    from "Developers of Forge", replying to their original /bug message.
//    Dismiss closes the card instead.

import { api, db } from 'sdk';
import { eq, asc, sql } from 'sdk/db';
import { bugReports, bugReplies, bugSeq } from '../schema.js';
import * as cfg from './config.js';
import { E } from './emoji.js';
import { DANGER, SUCCESS, coloredKbDict, editMessageHtml, sendText, htmlEscape } from './rich.js';

/** Keep at most this many reports (oldest dropped first). */
const MAX_REPORTS = 200;

/** Wall-clock in the bot's fixed UTC+5:30 offset (port of _fmt_ts). */
function fmtTs(ts) {
  const when = new Date((ts + 5.5 * 3600) * 1000);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const p2 = (n) => String(n).padStart(2, '0');
  return `${p2(when.getUTCDate())} ${months[when.getUTCMonth()]} ${when.getUTCFullYear()}, ` +
    `${p2(when.getUTCHours())}:${p2(when.getUTCMinutes())} UTC+5:30`;
}

function cardHtml(seq, name, uid, chatKind, ts, body) {
  const text = htmlEscape(body);
  return (
    `${E.CROSS} <b>Bug report #${seq}</b>\n` +
    `${'━━━━━━━━━━━━'}\n` +
    `${E.USER} <b>${htmlEscape(name || 'Unknown trainer')}</b> · ` +
    `id <code>${uid}</code> · ${htmlEscape(chatKind)}\n` +
    `${E.CHAT} ${fmtTs(ts)}\n\n` +
    `<blockquote>${text}</blockquote>\n\n` +
    '<i>Reply to this message with your answer, then tap ' +
    '<b>💬 Send reply</b>. Tap <b>✖ Dismiss</b> to close it.</i>'
  );
}

function rows(uid, origMid) {
  return [[
    ['💬 Send reply', `bug|send|${uid}|${origMid}`, SUCCESS],
    ['✖ Dismiss', `bug|drop|${uid}|${origMid}`, DANGER],
  ]];
}

function doneHtml(report, baseHtml, footer) {
  return `${report?.html || baseHtml}\n\n${footer}`;
}

/** Next report number (replaces bug.py's module-level _seq). */
async function nextSeq() {
  const [row] = await db.insert(bugSeq).values({ id: 1, seq: 1 })
    .onConflictDoUpdate({
      target: bugSeq.id,
      set: { seq: sql`${bugSeq.seq} + 1` },
    })
    .returning()
    .run();
  return row?.seq ?? 1;
}

/** Prune the oldest reports beyond MAX_REPORTS. */
async function prune() {
  const count = await db.$count(bugReports);
  if (count <= MAX_REPORTS) return;
  const overflow = count - MAX_REPORTS;
  const old = await db.select({ key: bugReports.key })
    .from(bugReports)
    .orderBy(asc(bugReports.ts))
    .limit(overflow)
    .all();
  for (const row of old) {
    await db.delete(bugReports).where(eq(bugReports.key, row.key)).run();
    await db.delete(bugReplies).where(eq(bugReplies.key, row.key)).run();
  }
}

/** True when *message* replies to one of our bug cards (used to keep the
 *  group AI quiet on those replies). */
export async function isBugCardReply(message) {
  if (!message || !cfg.BUG_REPORT_CHAT_ID) return false;
  const target = message.reply_to_message;
  if (!target) return false;
  const key = `${message.chat.id}:${target.message_id}`;
  const row = await db.select({ key: bugReports.key }).from(bugReports)
    .where(eq(bugReports.key, key)).get();
  return Boolean(row);
}

/** `/bug <text>` (or as a reply) → report card in the dev group. */
export async function cmdBug(message, args) {
  if (!cfg.BUG_REPORT_CHAT_ID) return; // no dev group configured
  const chat = message.chat;
  const user = message.from;
  if (!message || !chat) return;

  let body = (args || []).join(' ').trim();
  if (!body && message.reply_to_message) {
    body = (message.reply_to_message.text || message.reply_to_message.caption || '').trim();
  }
  if (!body) {
    await sendText(chat.id,
      `${E.CHAT} <b>Report a bug to the Developers of Forge</b>\n\n` +
      'Usage: <code>/bug what went wrong</code>\n' +
      '…or reply to a message with <code>/bug</code> to include it.',
      { replyTo: message.message_id });
    return;
  }
  body = body.slice(0, 1500);

  const name = user?.full_name || 'Unknown trainer';
  const uid = user?.id || 0;
  const dm = chat.type === 'private' ? chat.id : uid;
  const kind = chat.type === 'private' ? 'private' : String(chat.type);

  const seq = await nextSeq();
  const card = cardHtml(seq, name, uid, kind, Date.now() / 1000, body);

  const sent = await sendText(cfg.BUG_REPORT_CHAT_ID, card, {
    markup: coloredKbDict(rows(uid, message.message_id)),
  });
  if (!sent || !sent.message_id) {
    await sendText(chat.id,
      `${E.CROSS} I couldn't reach the Developers right now — ` +
      'please try again in a moment.',
      { replyTo: message.message_id });
    console.warn(`bug card delivery failed (seq ${seq})`);
    return;
  }

  const key = `${cfg.BUG_REPORT_CHAT_ID}:${sent.message_id}`;
  await db.insert(bugReports).values({
    key, uid, dm, origMid: message.message_id, name, kind,
    seq, ts: Math.floor(Date.now() / 1000), html: card, done: false,
  }).run();
  await prune();

  await sendText(chat.id,
    `${E.CHECK} <b>Bug report #${seq} delivered.</b>\n` +
    'The Developers of Forge will reply to you here.',
    { replyTo: message.message_id });
}

/** Store a developer's reply to a bug card until Send is tapped.
 *  Returns true when the message targeted one of our cards. */
export async function storeReplyIfCard(message) {
  if (!message || !message.reply_to_message) return false;
  if (message.from?.is_bot) return false;
  const key = `${message.chat.id}:${message.reply_to_message.message_id}`;
  const report = await db.select({ key: bugReports.key }).from(bugReports)
    .where(eq(bugReports.key, key)).get();
  if (!report) return false; // not (or no longer) a bug card

  const text = (message.text || message.caption || '').trim();
  const hasMedia = Boolean(message.photo || message.video || message.document
    || message.audio || message.voice || message.sticker || message.video_note);
  if (!text && !hasMedia) return false;

  await db.insert(bugReplies).values({
    key,
    mid: message.message_id,
    text: text.slice(0, 3500),
    media: !text,
    fromName: message.from?.full_name || '?',
    ts: Math.floor(Date.now() / 1000),
  }).onConflictDoUpdate({
    target: bugReplies.key,
    set: {
      mid: message.message_id,
      text: text.slice(0, 3500),
      media: !text,
      fromName: message.from?.full_name || '?',
      ts: Math.floor(Date.now() / 1000),
    },
  }).run();

  try {
    await sendText(message.chat.id,
      `${E.CHECK} Reply stored — tap <b>💬 Send reply</b> on the report ` +
      'card to deliver it to the trainer.',
      { replyTo: message.message_id });
  } catch (e) {
    console.warn('could not confirm stored reply', e);
  }
  return true;
}

/** Deliver to the reporter, replying to their original /bug message;
 *  falls back to a standalone message when that message is gone. */
async function sendDm(chatId, text, replyTo) {
  try {
    return await api.sendMessage({
      chat_id: chatId,
      text,
      parse_mode: 'HTML',
      reply_parameters: { message_id: replyTo },
    });
  } catch (e) {
    return await api.sendMessage({ chat_id: chatId, text, parse_mode: 'HTML' });
  }
}

/** Send reply / Dismiss on a bug card (port of on_bug_button). */
export async function onBugButton(query) {
  if (!query) return;
  const data = String(query.data || '').split('|');
  const action = data[1] || '';
  let uid = Number(data[2]) || 0;
  let orig = Number(data[3]) || 0;
  if (!Number.isFinite(uid)) uid = 0;
  if (!Number.isFinite(orig)) orig = 0;
  const msg = query.message;
  if (!msg) {
    await answerCb(query);
    return;
  }

  const key = `${msg.chat.id}:${msg.message_id}`;
  const report = await db.select().from(bugReports).where(eq(bugReports.key, key)).get();
  const who = htmlEscape(query.from?.full_name || '?');

  if (action === 'drop') {
    await answerCb(query, 'Dismissed.');
    const footer = `${E.CROSS} Dismissed by ${who} · ${fmtTs(Date.now() / 1000)}`;
    await editMessageHtml(msg.chat.id, msg.message_id,
      doneHtml(report, msg.text || '', footer),
      { markup: { inline_keyboard: [] } });
    if (report) {
      await db.update(bugReports).set({ done: true }).where(eq(bugReports.key, key)).run();
      await db.delete(bugReplies).where(eq(bugReplies.key, key)).run();
    }
    return;
  }

  if (action !== 'send') {
    await answerCb(query);
    return;
  }

  const reply = await db.select().from(bugReplies).where(eq(bugReplies.key, key)).get();
  if (!reply) {
    await answerCb(query, 'Reply to this report first, then tap 💬 Send reply.', true);
    return;
  }
  if (report?.done) {
    await answerCb(query, 'This report was already handled.', true);
    return;
  }

  const dm = report?.dm || uid;
  const origMid = report?.origMid || orig;
  const header = `${E.CHAT} <b>Developers of Forge</b>\n\n`;
  try {
    if (reply.text) {
      await sendDm(dm, header + reply.text, origMid);
    } else {
      const head = await sendDm(dm, header + 'A Developer replied to your bug report:', origMid);
      const kwargs = head?.message_id
        ? { reply_parameters: { message_id: head.message_id } }
        : {};
      await api.copyMessage({
        chat_id: dm,
        from_chat_id: msg.chat.id,
        message_id: reply.mid,
        ...kwargs,
      });
    }
  } catch (e) {
    console.warn(`bug reply delivery failed (dm=${dm})`, e);
    await answerCb(query, `Delivery failed: ${String(e?.description || e?.message || e).slice(0, 90)}`, true);
    return;
  }

  const name = htmlEscape(report?.name || 'the reporter');
  if (report) {
    await db.update(bugReports).set({ done: true }).where(eq(bugReports.key, key)).run();
    await db.delete(bugReplies).where(eq(bugReplies.key, key)).run();
  }
  const footer = `${E.CHECK} Reply delivered to ${name} · ${fmtTs(Date.now() / 1000)}`;
  await editMessageHtml(msg.chat.id, msg.message_id,
    doneHtml(report, msg.text || '', footer),
    { markup: { inline_keyboard: [] } });
  await answerCb(query, 'Delivered to the reporter.');
}

async function answerCb(query, text = '', showAlert = false) {
  try {
    await api.answerCallbackQuery({
      callback_query_id: query.id,
      ...(text ? { text } : {}),
      ...(showAlert ? { show_alert: true } : {}),
    });
  } catch (e) {
    console.warn('answerCallbackQuery failed', e);
  }
}
