// Shared send/answer plumbing used by both handlers (port of bot.py's
// send_answer / _bot_username / typing action helpers).

import { api } from 'sdk';
import { sendRichStep } from './rich.js';
import { splitMessage, stripTags } from './sanitize.js';

let ME = null;

/** Our bot identity (cached per isolate — module state does not need to
 *  survive across invocations, only within one). */
export async function botMe() {
  if (!ME) {
    try {
      ME = await api.getMe();
    } catch (e) {
      console.warn('getMe failed; assuming Professor_OakBot', e);
      ME = { id: 0, username: 'Professor_OakBot' };
    }
  }
  return ME;
}

/** Send possibly-long HTML, falling back to plain text if unparseable
 *  (port of bot.py send_answer). Markup attaches to the LAST part. */
export async function sendAnswer({ chatId, text, replyTo = null, markup = null }) {
  const parts = splitMessage(text);
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    const markupPart = i === parts.length - 1 ? markup : null;
    try {
      const payload = { chat_id: chatId, text: part, parse_mode: 'HTML' };
      if (replyTo) payload.reply_parameters = { message_id: replyTo };
      if (markupPart) payload.reply_markup = markupPart;
      await api.sendMessage(payload);
    } catch (e) {
      console.debug(`HTML rejected (${e?.description || e}); retrying as plain text`);
      try {
        const plain = { chat_id: chatId, text: stripTags(part) };
        if (replyTo) plain.reply_parameters = { message_id: replyTo };
        if (markupPart) plain.reply_markup = markupPart;
        await api.sendMessage(plain);
      } catch (e2) {
        console.error('Failed to send fallback message', e2);
      }
    }
  }
}

/** Send a rich page with its classic fallback (port of _send_rich_page /
 *  send_rich_step call sites). Returns true when the rich send won. */
export async function sendRichPage({ chatId, rich, classicText, classicMarkup, replyTo = null }) {
  return sendRichStep(chatId, rich, { replyTo, classicMarkup, classicText });
}

/** Best-effort typing indicator (port of send_action(ChatAction.TYPING)). */
export async function typing(chatId) {
  try {
    await api.sendChatAction({ chat_id: chatId, action: 'typing' });
  } catch (_) {
    /* best effort */
  }
}
