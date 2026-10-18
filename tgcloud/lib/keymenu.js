// `/keymenu` — owner-only AI key inventory — port of help/helpbot/keymenu.py.
// Shows every configured key (masked), its health, usage counters and the
// failover order, with Refresh and Test all keys buttons. Only users in
// OWNER_IDS can open it; everyone else is ignored silently.

import { api } from 'sdk';
import * as cfg from './config.js';
import * as keyvault from './keyvault.js';
import { E, uiTag } from './emoji.js';
import { PRIMARY, SUCCESS, coloredKbDict, editMessageHtml, sendText, htmlEscape } from './rich.js';

/** Callback prefix — data looks like `km|refresh` / `km|test`. */
const CB = 'km';

const STATE_TAG = {
  healthy: E.CHECK,
  cooling: E.WARN,
  failing: E.CROSS,
  new: E.SPARKLE,
};
const STATE_WORD = {
  healthy: 'healthy',
  cooling: 'cooling down',
  failing: 'failing',
  new: 'untested',
};

function isOwner(user) {
  return Boolean(user) && cfg.isOwner(user.id);
}

function ago(ts) {
  if (!ts) return 'never';
  const dt = Math.floor(Date.now() / 1000 - ts / 1000);
  if (dt < 5) return 'just now';
  if (dt < 60) return `${dt}s ago`;
  if (dt < 3600) return `${Math.floor(dt / 60)}m ago`;
  if (dt < 86400) return `${Math.floor(dt / 3600)}h ago`;
  return `${Math.floor(dt / 86400)}d ago`;
}

function rows() {
  // Plain labels + premium icons (port of keymenu.py Refresh / Test all keys).
  return [[
    ['Refresh', `${CB}|refresh`, PRIMARY, 'rocket'],
    ['Test all keys', `${CB}|test`, SUCCESS, 'bolt'],
  ]];
}

/** Classic HTML body — one block per key, masked, in failover order. */
export async function render() {
  const snap = await keyvault.snapshot();
  if (!snap.length) {
    return (
      `${uiTag('sparkle')} <b>AI key menu</b>\n` +
      `${'━━━━━━━━━━━━'}\n` +
      `${E.WARN} No keys configured — set ` +
      '<code>OPENROUTER_API_KEYS</code> in tgcloud/lib/config.js.'
    );
  }
  const lines = [
    `${uiTag('sparkle')} <b>AI key menu</b> — ${snap.length} keys`,
    '━━━━━━━━━━━━',
    '',
  ];
  snap.forEach((k, i) => {
    if (k.disabled) {
      // On the temporary disable list — never presented as healthy/failing.
      lines.push(
        `${i + 1}. ${E.CROSS} <b>${htmlEscape(k.label)}</b> ` +
        `<code>${htmlEscape(k.masked)}</code> — disabled ` +
        '(excluded from the chain and tests)',
      );
      lines.push(
        `   <code>${htmlEscape(k.model)}</code> · ${k.uses} uses · ` +
        `${k.ok} ok · ${k.fail} fail · last ${ago(k.lastUsed)}`,
      );
      return;
    }
    const tag = STATE_TAG[k.state] || E.SPARKLE;
    const word = STATE_WORD[k.state] || k.state;
    let detail = '';
    if (k.state === 'cooling') detail = ` · retry in ${Math.floor(k.cooldownLeft)}s`;
    else if (k.state === 'failing' && k.lastError) detail = ` · ${htmlEscape(k.lastError.slice(0, 70))}`;
    lines.push(
      `${i + 1}. ${tag} <b>${htmlEscape(k.label)}</b> ` +
      `<code>${htmlEscape(k.masked)}</code> — ${word}${detail}`,
    );
    lines.push(
      `   <code>${htmlEscape(k.model)}</code> · ${k.uses} uses · ` +
      `${k.ok} ok · ${k.fail} fail · last ${ago(k.lastUsed)}`,
    );
  });
  // Active failover order, calling out skipped positions: "1 → 2 → 3 → 5 (4 disabled)".
  const activeNums = [];
  const disabledNums = [];
  snap.forEach((k, i) => (k.disabled ? disabledNums : activeNums).push(i + 1));
  const order = activeNums.join(' → ')
    + (disabledNums.length ? ` (${disabledNums.join(', ')} disabled)` : '');
  lines.push(
    '',
    `<i>Failover ${order}: on failure the next key takes over — ` +
    '429 pauses a key 60s, auth errors 5 min.</i>',
  );
  return lines.join('\n');
}

/** Owner-only status card. Silent for everyone else. */
export async function cmdKeymenu(message) {
  const user = message.from;
  if (!message || !isOwner(user)) return;
  const sent = await sendText(message.chat.id, await render(), {
    markup: coloredKbDict(rows()),
    replyTo: message.message_id,
  });
  if (!sent) console.warn(`keymenu delivery failed (user ${user?.id ?? '?'})`);
}

/** Refresh the view / ping every key (owner only). */
export async function onKeymenuButton(query) {
  if (!query) return;
  if (!isOwner(query.from)) {
    await answerCb(query, 'Owner only.', true);
    return;
  }
  const msg = query.message;
  if (!msg) {
    await answerCb(query);
    return;
  }

  const action = String(query.data || '').split('|')[1] || '';
  if (action === 'refresh') {
    await answerCb(query, 'Refreshed.');
    await editMessageHtml(msg.chat.id, msg.message_id, await render(), {
      markup: coloredKbDict(rows()),
    });
    return;
  }
  if (action === 'test') {
    await answerCb(query, 'Testing enabled keys…');
    const results = await keyvault.testAll();
    const attempted = results.filter(([k]) => !k.disabled);
    const skipped = results.filter(([k]) => k.disabled);
    const bad = attempted.filter(([, ok]) => ok === false)
      .map(([k, , err]) => [k.label, err]);
    await editMessageHtml(msg.chat.id, msg.message_id, await render(), {
      markup: coloredKbDict(rows()),
    });
    let summary = `${E.CHECK} Tested ${attempted.length} keys — ` +
      `${attempted.length - bad.length} ok, ${bad.length} failing.`;
    if (skipped.length) {
      summary += `\n${E.CROSS} Skipped (disabled): ` +
        skipped.map(([k]) => htmlEscape(k.label)).join(', ');
    }
    if (bad.length) {
      summary += '\n' + bad.slice(0, 5).map(([label, err]) =>
        `${E.CROSS} ${htmlEscape(label)}: <code>${htmlEscape(String(err || '').slice(0, 80))}</code>`,
      ).join('\n');
    }
    try {
      await api.sendMessage({ chat_id: msg.chat.id, text: summary, parse_mode: 'HTML' });
    } catch (e) {
      console.warn('keymenu test summary not delivered', e);
    }
    return;
  }
  await answerCb(query);
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
