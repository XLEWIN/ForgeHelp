// Update handler — `message` updates (port of help/helpbot/bot.py).
//
// Routing mirrors build_app()'s PTB handler order:
//   1. commands             (start/help/about/ask/ai/commands/guide/search/
//                            reset/new/bug/keymenu + dex: mv/poke/build)
//   2. dev-group replies    (bug card replies — stored, never answered)
//   3. private non-command  → question (rate-limited, AI answer)
//   4. group non-command    → reply-to-bot / @mention only (GROUP_MODE='mention')
// Unknown commands are ignored silently; only text messages are considered.
//
// The platform invokes `export default(message, ctx)` with the Message
// payload; the full Update (update_id etc.) is on ctx.update.

import * as cfg from '../lib/config.js';
import * as kb from '../lib/kb.js';
import * as ai from '../lib/ai.js';
import * as bug from '../lib/bug.js';
import * as dex from '../lib/dex.js';
import * as keymenu from '../lib/keymenu.js';
import * as pages from '../lib/pages.js';
import * as state from '../lib/state.js';
import { E } from '../lib/emoji.js';
import { classicHtml, htmlEscape as esc, coloredKbDict, sendText } from '../lib/rich.js';
import { sendAnswer, sendRichPage, botMe, typing } from '../lib/flows.js';

// ── update routing ───────────────────────────────────────────────────────

export default async function onMessage(message) {
  try {
    await route(message);
  } catch (e) {
    console.error('unhandled error in message handler', e);
    try {
      await state.bumpStat('errors');
    } catch (_) { /* best effort */ }
    try {
      if (message?.chat?.id) {
        await sendText(message.chat.id,
          'Something went wrong on my side — try again in a moment.',
          { replyTo: message.message_id });
      }
    } catch (_) { /* best effort */ }
  }
}

async function route(message) {
  if (!message || !message.chat) return;
  const chat = message.chat;
  const text = message.text || '';

  // 1. Commands — `/name[@otherbot] [args]` at the start of the text.
  if (text.startsWith('/')) {
    const m = text.match(/^\/([A-Za-z0-9_]{1,32})(?:@([A-Za-z0-9_]{1,64}))?(?:\s+([\s\S]*))?$/);
    if (m) {
      const [, rawCmd, atBot, rest] = m;
      const me = await botMe();
      // Addressed to a different bot → not ours (PTB behaves the same).
      if (atBot && atBot.toLowerCase() !== String(me.username || '').toLowerCase()) return;
      const args = rest ? rest.trim().split(/\s+/) : [];
      await dispatch(rawCmd.toLowerCase(), message, args);
      return;
    }
    // Leading slash but not a plain command (e.g. "/こんにちは") → ignore,
    // like PTB's entity-based command filter would.
    return;
  }

  // 2. Developers' group: store a reply to a bug card (text or media).
  //    A stored reply swallows the update; otherwise fall through like the
  //    Python build does (all PTB handlers share group 0).
  const isDevChat = Boolean(cfg.BUG_REPORT_CHAT_ID) && chat.id === cfg.BUG_REPORT_CHAT_ID;
  if (isDevChat && (await bug.storeReplyIfCard(message))) return;

  // 3. Private chat → any non-command text is a question.
  if (chat.type === 'private') {
    await onPrivateQuestion(message);
    return;
  }

  // 4. Groups/supergroups → reply-to-bot or @mention only.
  if (chat.type === 'group' || chat.type === 'supergroup') {
    if (!isDevChat && (await bug.isBugCardReply(message))) return;
    await onGroupMessage(message);
  }
  // Channels and anything else: ignored (Python filters cover PRIVATE/GROUPS).
}

async function dispatch(cmd, message, args) {
  switch (cmd) {
    case 'start': return cmdStart(message);
    case 'help': return cmdHelp(message);
    case 'about': return cmdAbout(message);
    case 'ask':
    case 'ai': return cmdAsk(message, args);
    case 'commands': return cmdCommands(message, args);
    case 'guide': return cmdGuide(message, args);
    case 'search': return cmdSearch(message, args);
    case 'reset':
    case 'new': return cmdReset(message);
    case 'mv':
    case 'moves': return dex.cmdMv(message, args);
    case 'poke':
    case 'pokedex':
    case 'dex': return dex.cmdPoke(message, args);
    case 'build':
    case 'set': return dex.cmdBuild(message, args);
    case 'data': return dex.cmdData(message, args);
    case 'bug': return bug.cmdBug(message, args);
    case 'keymenu': return keymenu.cmdKeymenu(message);
    default: return undefined; // unknown command → silently ignored
  }
}

// ── questions ────────────────────────────────────────────────────────────

async function onPrivateQuestion(message) {
  const text = (message.text || '').trim();
  if (!text || text.startsWith('/') || text.length < 3) return;
  await answerFor(message, text);
}

async function onGroupMessage(message) {
  const text = (message.text || '').trim();
  if (!text || text.startsWith('/')) return;

  const me = await botMe();
  const username = String(me.username || 'Professor_OakBot').toLowerCase();
  const rt = message.reply_to_message;
  const replied = Boolean(rt && rt.from && rt.from.id === me.id && me.id);
  const mentioned = mentionsBot(message, username);

  if (replied || mentioned) {
    const question = questionFromReply(message, username);
    if (question && question.trim().length >= 2) {
      await answerFor(message, question.trim());
      return;
    }
    // Tag with nothing usable — a short nudge.
    if (mentioned || replied) {
      const own = stripMention(message.text || '', username);
      await answerFor(message, own || 'What can you help with?');
      return;
    }
  }

  if (cfg.GROUP_MODE === 'all') {
    await onPrivateQuestion(message);
  }
}

/** The one answer path: rate-limit → typing → history → AI → send. */
async function answerFor(message, question) {
  const user = message.from;
  if (!(await state.allowed(user && user.id))) {
    await sendAnswer({
      chatId: message.chat.id,
      replyTo: message.message_id,
      text: `${E.WARN} One moment, trainer — please wait ` +
        `${cfg.RATE_GAP_SECONDS}s between questions ` +
        `(up to ${cfg.RATE_MAX_PER_WINDOW} per ` +
        `${Math.floor(cfg.RATE_WINDOW_SECONDS / 60)} minutes).`,
    });
    return;
  }

  await state.bumpStat('questions');
  await typing(message.chat.id);

  const history = await state.getHistory(message.chat.id);
  const result = await ai.answer(question, { history });
  await state.bumpStat(result.mode);
  if (result.mode === 'ai') {
    await state.remember(message.chat.id, question, result.text);
  }

  await sendAnswer({
    chatId: message.chat.id,
    replyTo: message.message_id,
    text: result.text,
    markup: answerKb(),
  });
}

function answerKb() {
  return coloredKbDict([[
    ['📖 Help Menu', 'hp|menu', 'primary'],
    ['📋 Commands', 'hp|commands', 'primary'],
    ['🔄 Reset chat', 'hp|reset', 'danger'],
  ]]);
}

// ── mention helpers (port of bot.py _mentions_bot / _strip_mention) ──────

function mentionsBot(message, username) {
  const text = (message.text || message.caption || '').toLowerCase();
  if (text.includes(`@${username}`)) return true;
  const entities = message.entities || message.caption_entities || [];
  for (const entity of entities) {
    if ((entity.type === 'mention' || entity.type === 'text_mention')
        && entity.offset < text.length
        && text.slice(entity.offset, entity.offset + entity.length) === `@${username}`) {
      return true;
    }
  }
  return false;
}

function escapeRe(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function stripMention(text, username) {
  return (text || '')
    .replace(new RegExp(`@${escapeRe(username)}\\b`, 'gi'), '')
    .replace(/^[ \s?!,.:\-]+/, '')
    .replace(/[ \s?!,.:\-]+$/, '');
}

/** When the bot is tagged in a reply, prefer the ORIGINAL message text
 *  (someone replies "@Professor_OakBot" to a question → answer the question). */
function questionFromReply(message, username) {
  const rt = message.reply_to_message;
  const original = ((rt && (rt.text || rt.caption)) || '').trim();
  const rf = rt && rt.from;
  if (rf && rf.is_bot) return null; // never re-answer the bot's own messages
  const own = stripMention(message.text || message.caption || '', username);
  if (original && (!own || own.length < 3)) return original;
  if (own && original) return own; // tag + extra text → answer the extra text
  return own || original || null;
}

// ── commands ─────────────────────────────────────────────────────────────

async function cmdStart(message) {
  const name = (message.from && message.from.first_name) || 'Trainer';
  const me = await botMe();
  const rich = pages.richStart(name, me.username);
  await sendRichPage({
    chatId: message.chat.id,
    rich,
    classicMarkup: pages.startKb(),
    classicText: classicHtml(rich),
    replyTo: message.message_id,
  });
}

async function cmdHelp(message) {
  const rich = pages.richHelp();
  await sendRichPage({
    chatId: message.chat.id,
    rich,
    classicMarkup: pages.guideKb(),
    classicText: classicHtml(rich),
    replyTo: message.message_id,
  });
}

async function cmdAbout(message) {
  const stats = await state.getStats();
  const rich = pages.richAbout(stats);
  await sendRichPage({
    chatId: message.chat.id,
    rich,
    classicMarkup: coloredKbDict([[
      [`🛟 Support ${cfg.SUPPORT_LABEL}`, cfg.SUPPORT_URL, 'link'],
      ['📖 Help Menu', 'hp|menu', 'primary'],
    ]]),
    classicText: classicHtml(rich),
    replyTo: message.message_id,
  });
}

async function cmdAsk(message, args) {
  const question = args.join(' ').trim();
  if (!question) {
    const rich = pages.richAskUsage();
    await sendRichPage({
      chatId: message.chat.id,
      rich,
      classicMarkup: pages.askUsageKb(),
      classicText: classicHtml(rich),
      replyTo: message.message_id,
    });
    return;
  }
  await answerFor(message, question);
}

async function cmdCommands(message, args) {
  const chatId = message.chat.id;
  const replyTo = message.message_id;
  const name = (args[0] || '').trim().toLowerCase();

  if (name) {
    const line = kb.commandLine(name);
    if (line) {
      await sendAnswer({
        chatId, replyTo,
        text: `${esc(line)}\n\n<i>Full context: /guide commands · ` +
          `/search ${esc(name)}</i>`,
      });
      return;
    }
    const hits = kb.search(`/${name}`, 3);
    if (hits.length) {
      await sendAnswer({
        chatId, replyTo,
        text: hits.map((h) =>
          `<blockquote><b>${esc(h.chunk.title)}</b>\n` +
          `${esc(h.chunk.text.slice(0, 500))}</blockquote>`).join('\n'),
      });
      return;
    }
    await sendAnswer({
      chatId, replyTo,
      text: `${E.CROSS} I have no index entry for /${esc(name)}. ` +
        'Try /commands or /search.',
    });
    return;
  }

  await sendAnswer({
    chatId, replyTo,
    text: `${E.STAR} <b>Command index</b> — send /commands &lt;name&gt; for ` +
      'one entry.\n\n' +
      'Most asked: /start /help /hunt /myteam /pc /breed /trade ' +
      '/daily /weekly /quest /battle /gymbattle /pvp /regions /travel ' +
      '/shop /mycoins /mystats /leaderboard /guess',
    markup: coloredKbDict([[['📋 Full index', 'hp|commands', 'primary']]]),
  });
}

async function cmdGuide(message, args) {
  const chatId = message.chat.id;
  const replyTo = message.message_id;
  if (!args.length) {
    await sendRichPage({
      chatId,
      rich: pages.richGuidePicker(),
      classicMarkup: pages.guideKb(),
      replyTo,
    });
    return;
  }
  const stem = kb.fileForTerm(args.join(' ').toLowerCase());
  const text = stem ? kb.guideText(stem) : null;
  if (!text) {
    await sendAnswer({
      chatId, replyTo,
      text: `${E.CROSS} No guide with that name. Tap /guide with no ` +
        'arguments to browse.',
    });
    return;
  }
  const title = kb.guideTitle(stem);
  const rich = pages.guideRichBody(stem, title, text);
  await sendRichPage({ chatId, rich, classicMarkup: pages.guideKb(), replyTo });
}

async function cmdSearch(message, args) {
  const chatId = message.chat.id;
  const replyTo = message.message_id;
  const query = args.join(' ').trim();
  if (!query) {
    await sendAnswer({ chatId, replyTo, text: 'Usage: /search shiny odds' });
    return;
  }
  const hits = kb.search(query, 5);
  if (!hits.length) {
    await sendAnswer({
      chatId, replyTo,
      text: `${E.CROSS} Nothing in the knowledge base matched that.`,
    });
    return;
  }
  const parts = [`${E.STAR} <b>Top matches for</b> <code>${esc(query)}</code>\n`];
  for (const hit of hits) {
    const snippet = hit.chunk.text.slice(0, 220).replace(/\n/g, ' ');
    parts.push(
      `<blockquote><b>${esc(hit.chunk.title)}</b> ` +
      `(${esc(hit.chunk.source)}, score ${hit.score.toFixed(1)})\n` +
      `${esc(snippet)} …</blockquote>`,
    );
  }
  await sendAnswer({ chatId, replyTo, text: parts.join('\n') });
}

async function cmdReset(message) {
  const had = await state.clearHistory(message.chat.id);
  await sendAnswer({
    chatId: message.chat.id,
    replyTo: message.message_id,
    text: had
      ? `${E.CHECK} Conversation cleared — ask me anything fresh, trainer!`
      : `${E.CHAT} Nothing to clear yet — just ask me anything.`,
  });
}
