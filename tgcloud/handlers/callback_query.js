// Update handler — `callback_query` updates (port of bot.py's
// CallbackQueryHandler registrations: `hp|` guide pages, `bug|` bug cards,
// `km|` key menu, `pk|`/`bd|` dex pages (offline Pokédex bundled as
// tgcloud/lib/dexdata.js), `d:` /data encyclopedia pages).

import { api } from 'sdk';
import * as kb from '../lib/kb.js';
import * as bug from '../lib/bug.js';
import * as dex from '../lib/dex.js';
import * as keymenu from '../lib/keymenu.js';
import * as pages from '../lib/pages.js';
import * as state from '../lib/state.js';
import { E } from '../lib/emoji.js';
import { coloredKbDict, sendText } from '../lib/rich.js';
import { sendRichPage } from '../lib/flows.js';

export default async function onCallback(query) {
  try {
    const data = String(query?.data || '');
    if (data.startsWith('hp|')) return await onGuideButton(query);
    if (data.startsWith('bug|')) return await bug.onBugButton(query);
    if (data.startsWith('km|')) return await keymenu.onKeymenuButton(query);
    if (data.startsWith('d:')) return await dex.onDataButton(query);
    if (data.startsWith('pk|') || data.startsWith('bd|')) {
      return await dex.onDexButton(query);
    }
    await answerCb(query); // stale/unknown data — clear the spinner
  } catch (e) {
    console.error('unhandled error in callback_query handler', e);
    try {
      await state.bumpStat('errors');
    } catch (_) { /* best effort */ }
    try {
      if (query?.message?.chat?.id) {
        await sendText(query.message.chat.id,
          'Something went wrong on my side — try again in a moment.',
          { replyTo: query.message.message_id });
      }
    } catch (_) { /* best effort */
    }
  }
}

// ── `hp|…` guide / help pages (port of bot.py on_guide_button) ──────────

async function onGuideButton(query) {
  const data = String(query.data || '');
  const pipe = data.indexOf('|');
  const stem = pipe >= 0 ? data.slice(pipe + 1) : '';
  await answerCb(query);

  const msg = query.message;
  if (!msg) return;
  const chatId = msg.chat.id;
  const msgId = msg.message_id;

  if (stem === 'close') {
    try {
      await api.deleteMessage({ chat_id: chatId, message_id: msgId });
    } catch (e) {
      console.debug('close/delete failed', e);
    }
    return;
  }

  if (stem === 'reset') {
    try {
      const had = await state.clearHistory(chatId);
      await sendText(chatId,
        had
          ? `${E.CHECK} Conversation cleared — ask me anything fresh!`
          : `${E.CHAT} Nothing to clear yet.`,
        { replyTo: msgId });
    } catch (e) {
      console.debug('hp|reset failed', e);
    }
    return;
  }

  if (stem === 'menu') {
    try {
      await sendRichPage({
        chatId,
        rich: pages.richGuidePicker(),
        classicMarkup: pages.guideKb(),
        replyTo: msgId,
      });
    } catch (e) {
      console.debug('hp|menu failed', e);
    }
    return;
  }

  if (stem === 'commands') {
    try {
      await sendText(chatId,
        `${E.STAR} <b>Command index</b>\n\n` +
        'Most asked: /start /help /hunt /myteam /pc /breed /trade ' +
        '/daily /weekly /quest /battle /gymbattle /pvp /regions ' +
        '/travel /shop /mycoins /mystats /leaderboard /guess',
        {
          replyTo: msgId,
          markup: coloredKbDict([[['📖 Help Menu', 'hp|menu', 'primary']]]),
        });
    } catch (e) {
      console.debug('hp|commands failed', e);
    }
    return;
  }

  if (stem === 'ask') {
    try {
      await sendText(chatId,
        `${E.CHAT} Just type your question, or use ` +
        '<code>/ask &lt;question&gt;</code>.\n' +
        'Example: <code>/ask how do shiny odds work?</code>',
        { replyTo: msgId });
    } catch (e) {
      console.debug('hp|ask failed', e);
    }
    return;
  }

  if (stem === 'example') {
    try {
      await sendText(chatId, '/ask how do shiny odds work?', { replyTo: msgId });
    } catch (e) {
      console.debug('hp|example failed', e);
    }
    return;
  }

  // A guide stem — send the rich guide page (as a NEW message, no reply,
  // matching Python's send_rich_step call without reply_to).
  const text = kb.guideText(stem);
  if (!text) {
    try {
      await sendText(chatId, `${E.CROSS} That guide is gone — try /guide.`,
        { replyTo: msgId });
    } catch (e) {
      console.debug('missing guide notice failed', e);
    }
    return;
  }
  const title = kb.guideTitle(stem);
  const rich = pages.guideRichBody(stem, title, text);
  await sendRichPage({ chatId, rich, classicMarkup: pages.guideKb() });
}

async function answerCb(query, text = '', showAlert = false) {
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
