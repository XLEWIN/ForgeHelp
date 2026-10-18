// Resolve every relative import in tgcloud/** against the filesystem —
// catches path typos ('../lib/x.js' vs './lib/x.js') without the runtime.
import { readdirSync, statSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..', 'tgcloud');
const files = [];

function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full);
    else if (entry.endsWith('.js')) files.push(full);
  }
}
walk(root);

const IMPORT_RE = /(?:^|\n)\s*import\s[^'"]*?from\s*['"]([^'"]+)['"]|(?:^|\n)\s*import\s*['"]([^'"]+)['"]/g;
let failed = 0;
let checked = 0;

for (const file of files) {
  const src = await import('node:fs').then((fs) => fs.readFileSync(file, 'utf8'));
  for (const m of src.matchAll(IMPORT_RE)) {
    const spec = m[1] || m[2];
    if (!spec) continue;
    if (spec === 'sdk' || spec.startsWith('sdk/')) continue; // platform module
    checked += 1;
    if (!spec.startsWith('.')) {
      failed += 1;
      console.error(`FAIL  ${file}: non-relative, non-sdk import '${spec}'`);
      continue;
    }
    const target = resolve(dirname(file), spec);
    if (!existsSync(target)) {
      failed += 1;
      console.error(`FAIL  ${file}: '${spec}' -> missing ${target}`);
    }
  }
}
console.log(`${checked} relative imports checked in ${files.length} modules` +
  `${failed ? ` — ${failed} FAILED` : ' — all resolve'}`);
process.exit(failed ? 1 : 0);
