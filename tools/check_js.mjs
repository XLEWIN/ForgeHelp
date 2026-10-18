// Syntax-check every .js / .mjs file that ships or builds the bot.
// (package.json has "type": "module", so `node --check` parses .js as ESM.)
import { execFileSync } from 'node:child_process';
import { readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const roots = ['tgcloud', 'tools'];
const files = [];

function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full);
    else if (entry.endsWith('.js') || entry.endsWith('.mjs')) files.push(full);
  }
}
for (const r of roots) walk(r);

let failed = 0;
for (const file of files) {
  try {
    execFileSync(process.execPath, ['--check', file], { stdio: 'pipe' });
    console.log(`ok    ${file}`);
  } catch (e) {
    failed += 1;
    console.error(`FAIL  ${file}\n${String(e.stderr || e.message)}`);
  }
}
console.log(`\n${files.length - failed}/${files.length} files parse`);
process.exit(failed ? 1 : 0);
