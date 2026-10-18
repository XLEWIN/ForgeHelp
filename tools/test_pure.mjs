// Local tests for the SDK-free modules (knowledge, kb, sanitize, emoji).
// Run: node tools/test_pure.mjs  — or: npm run kb && npm run check
// Mirrors the Python gates in help/selftest.py where they overlap.

import { FILES, CHUNKS } from '../tgcloud/lib/knowledge.js';
import * as kb from '../tgcloud/lib/kb.js';
import {
  splitMessage, stripPlainEmoji, markdownToHtml, sanitizeHtml, stripTags,
} from '../tgcloud/lib/sanitize.js';
import { E, uiTag, stripCustomEmoji, uiGlyph } from '../tgcloud/lib/emoji.js';

let failed = 0;
function check(name, ok, detail = '') {
  if (ok) console.log(`ok    ${name}`);
  else {
    failed += 1;
    console.error(`FAIL  ${name}${detail ? ` — ${detail}` : ''}`);
  }
}

// ── bundled knowledge (parity with the Python knowledge base) ────────────
check('knowledge: 16 files', FILES.length === 16, `got ${FILES.length}`);
check('knowledge: 138 chunks', CHUNKS.length === 138, `got ${CHUNKS.length}`);
check('knowledge: no secrets in bundle',
  !JSON.stringify(CHUNKS).match(/api[_-]?key|sk-proj|gsk_/i));
check('knowledge: every chunk has fields',
  CHUNKS.every((c) => c.source && c.text));

const stats = kb.stats();
check('kb.stats: 138 chunks', stats.chunks === 138, `got ${stats.chunks}`);
check('kb.stats: 16 files', stats.files === 16, `got ${stats.files}`);
check('kb.stats: 161 command names', stats.commands === 161, `got ${stats.commands}`);

// ── kb behaviour ──────────────────────────────────────────────────────────
const line = kb.commandLine('hunt');
check('commandLine("hunt")', typeof line === 'string' && line.startsWith('- `/hunt`'),
  JSON.stringify(line));
const hits = kb.search('shiny odds', 3);
check('search("shiny odds") returns hits', hits.length > 0);
check('search hits shaped {chunk,score}',
  hits.every((h) => h.chunk && typeof h.score === 'number' && h.score > 0));
check('search prefers commands for "/hunt"',
  kb.search('/hunt', 1)[0]?.chunk.text.toLowerCase().includes('hunt'),
  kb.search('/hunt', 1)[0]?.chunk.source);
check('guides() non-empty', kb.guides().length >= 10,
  `got ${kb.guides().length}`);
check('guideText("commands")', typeof kb.guideText('commands') === 'string');
check('guideTitle returns title', kb.guideTitle('commands').length > 0);
check('fileForTerm("battle") → 03-battles-and-gyms',
  kb.fileForTerm('battle') === '03-battles-and-gyms',
  String(kb.fileForTerm('battle')));
check('fileForTerm with no match → null (matches Python)',
  kb.fileForTerm('shiny') === null, String(kb.fileForTerm('shiny')));
check('contextFor() returns [text, sources]',
  (() => {
    const [ctx, src] = kb.contextFor('how do shiny odds work', 6000);
    return typeof ctx === 'string' && ctx.length > 0 && Array.isArray(src);
  })());

// ── sanitize pipeline ────────────────────────────────────────────────────
check('markdownToHtml bold', markdownToHtml('a **b** c').includes('<b>b</b>'));
check('sanitizeHtml strips script',
  !sanitizeHtml('<p>ok</p><script>alert(1)</script>').includes('<script>'));
check('stripTags removes tags', stripTags('<b>hi</b> there') === 'hi there');

const long = 'x'.repeat(9000);
const parts = splitMessage(long);
check('splitMessage splits at 3800', parts.length > 1 && parts.every((p) => p.length <= 3800));
check('splitMessage lossless', parts.join('') === long);

const mixed = 'shiny ✨ <tg-emoji emoji-id="5918098311184654030">✨</tg-emoji> pokemon';
const stripped = stripPlainEmoji(mixed);
const outsideTags = stripped.replace(/<tg-emoji[^>]*>[\s\S]*?<\/tg-emoji>/g, '');
check('stripPlainEmoji removes unicode emoji', !/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(outsideTags),
  JSON.stringify(stripped));
check('stripPlainEmoji keeps <tg-emoji>', stripped.includes('<tg-emoji'));

// ── emoji / premium UI rules ─────────────────────────────────────────────
check('E.CROSS non-empty', typeof E.CROSS === 'string' && E.CROSS.length > 0);
check('uiTag("chat") is a <tg-emoji> tag', uiTag('chat').startsWith('<tg-emoji'));
check('stripCustomEmoji unwraps to the fallback glyph',
  stripCustomEmoji('<tg-emoji emoji-id="5918098311184654030">🔥</tg-emoji>') === '🔥');
check('uiGlyph has no empty string for chat', uiGlyph('chat') !== '');

console.log(`\n${failed ? `${failed} FAILED` : 'all passed'}`);
process.exit(failed ? 1 : 0);
