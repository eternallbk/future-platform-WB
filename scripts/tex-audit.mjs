/**
 * tex-audit.mjs — render EVERY stored formula with the real tex() and report leaks.
 *
 * WHY: `check-formulas.mjs` proves the renderer does not THROW. That is not the same
 * as proving it renders. tex() degrades an unrecognised command into a visible
 * `<span class="tex-unknown">\foo</span>` so typos cannot hide - which means a
 * formula can "pass the gate" while still showing raw LaTeX to the reader. That is
 * exactly what happened: a formula rendered as literal text ending in `\tilde{a}`
 * even though no exception was raised.
 *
 * This audit extracts tex() from the built bundle, renders every formula, and
 * counts leaked backslash commands per formula, so unsupported commands surface as
 * a number instead of a screenshot someone has to eyeball.
 *
 * Usage: node scripts/tex-audit.mjs [--verbose]
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';

const ROOT = process.cwd();
const bundle = readFileSync(join(ROOT, 'web/assets/js/app.js'), 'utf-8');

// Isolate the renderer: from the GREEK table through the end of tex().
const start = bundle.indexOf('const GREEK = {');
const endMarker = '/** Inline math with the accents removed';
const end = bundle.indexOf(endMarker);
if (start < 0 || end < 0 || end <= start) {
  console.error('[tex-audit] could not locate tex() in the bundle');
  process.exit(2);
}
const src = bundle.slice(start, end);
const tmp = mkdtempSync(join(tmpdir(), 'texaudit-'));
const file = join(tmp, 'tex.mjs');
// `esc` is defined earlier in the bundle; re-provide it so the slice stands alone.
writeFileSync(file, `
const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ESC[c]); }
${src}
export { tex };
`);

const { tex } = await import(pathToFileURL(file).href);

const formulas = JSON.parse(readFileSync(join(ROOT, 'web/data/formulas.json'), 'utf-8')).formulas;
const verbose = process.argv.includes('--verbose');

let leaked = 0;
let clean = 0;
const offenders = [];

for (const f of formulas) {
  const html = tex(f.latex || '');
  const unknown = [...html.matchAll(/tex-unknown">\\([^<]*)</g)].map((m) => m[1]);
  if (unknown.length) {
    leaked++;
    offenders.push({ id: f.id, name: f.name, unknown: [...new Set(unknown)] });
  } else {
    clean++;
  }
}

console.log('');
console.log('='.repeat(74));
console.log(`tex-audit: ${formulas.length} formula(s) | ${clean} render clean | ${leaked} leak a raw command`);
console.log('='.repeat(74));
for (const o of offenders.slice(0, verbose ? 100 : 18)) {
  console.log(`  ${o.id.padEnd(38)} ${o.unknown.join(', ')}`);
  if (verbose) console.log(`      ${o.name}`);
}
if (leaked > offenders.length) console.log(`  ... and ${leaked - 18} more`);
const all = [...new Set(offenders.flatMap((o) => o.unknown))].sort();
console.log('');
console.log('  distinct unsupported commands:', all.length ? all.join(' ') : '(none)');
console.log('='.repeat(74));
console.log('');
process.exit(leaked ? 1 : 0);
