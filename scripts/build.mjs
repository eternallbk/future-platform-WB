/**
 * build.mjs — concatenate the authoring parts into one classic script.
 *
 * Why not ship native ES modules? The workbench must also work when opened
 * straight from disk (`file://index.html`), and browsers block module scripts
 * over file:// because of CORS. A single classic script has no such problem,
 * so the source of truth stays split into readable parts and this build step
 * emits `assets/js/app.js`.
 *
 * Run:  node scripts/build.mjs        (also invoked by run-daily.ps1)
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const jsDir = join(root, 'web', 'assets', 'js');

const PARTS = ['core.part.js', 'ui.part.js', 'views.part.js', 'views2.part.js'];
const OUT = join(jsDir, 'app.js');

/**
 * Guard: app.js is emitted as a CLASSIC script so that `file://index.html`
 * works with no server. Module-only syntax would throw a SyntaxError at parse
 * time in that context, so fail the build instead of shipping a blank page.
 */
const FORBIDDEN = [
  [/\bimport\.meta\b/, 'import.meta is only valid inside a module'],
  [/^\s*import\s+[\w{*]/m, 'static import is only valid inside a module'],
  [/^\s*export\s/m, 'a leftover export statement (stripExports should have removed it)'],
];

/** Lines that are pure comments cannot break the parser, so ignore them. */
function significantLines(code) {
  return code
    .split('\n')
    .filter((l) => {
      const t = l.trim();
      return t && !t.startsWith('//') && !t.startsWith('*') && !t.startsWith('/*');
    })
    .join('\n');
}

/** Strip ESM export syntax so the parts fuse into one program scope. */
function stripExports(code) {
  return code
    .replace(/^export\s+(async\s+function|function|const|let|var|class)\b/gm, '$1')
    .replace(/^export\s*\{[^}]*\}\s*;?\s*$/gm, '')
    .replace(/^export\s+default\s+/gm, 'void ');
}

/**
 * Find duplicate top-level declarations in the fused program.
 *
 * Why this check exists: the parts share ONE program scope, so two parts
 * declaring the same top-level `const` is a fatal SyntaxError at load time and
 * the whole page goes blank. That happened for real (`ACCENTS`, the theme
 * accent palette, vs a LaTeX accent table added later). Each part parsed fine on
 * its own, so per-part validation could not see it - only the concatenation can.
 */
function findDuplicateDeclarations(code) {
  const seen = new Map();
  const dupes = [];
  const re = /^(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)/gm;
  let m;
  while ((m = re.exec(code)) !== null) {
    const name = m[1];
    const line = code.slice(0, m.index).split('\n').length;
    if (seen.has(name)) dupes.push({ name, first: seen.get(name), again: line });
    else seen.set(name, line);
  }
  return dupes;
}

const banner = (() => {
  const parts = PARTS.filter((p) => existsSync(join(jsDir, p)));
  return `/* ============================================================================
 * Future · 求职学习工作台 — app.js
 * GENERATED FILE — do not edit by hand.
 * Sources: ${parts.join(', ')}
 * Rebuild: node scripts/build.mjs
 * ========================================================================= */
'use strict';
`;
})();

let out = banner;
let totalLines = 0;

for (const part of PARTS) {
  const p = join(jsDir, part);
  if (!existsSync(p)) {
    console.error(`[build] missing part: ${part}`);
    process.exitCode = 1;
    continue;
  }
  const code = stripExports(readFileSync(p, 'utf8'));
  const sig = significantLines(code);
  for (const [re, why] of FORBIDDEN) {
    const m = sig.match(re);
    if (m) {
      console.error(`[build] ${part}: forbidden module syntax "${m[0]}" — ${why}`);
      process.exitCode = 1;
    }
  }
  const lines = code.split('\n').length;
  totalLines += lines;
  out += `\n/* ===== ${part} — ${lines} lines ===== */\n\n${code.trimEnd()}\n`;
}

// Fatal-at-runtime check: duplicate top-level declarations blank the whole page.
const dupes = findDuplicateDeclarations(out);
if (dupes.length) {
  console.error('[build] DUPLICATE top-level declarations in the fused program:');
  for (const d of dupes) {
    console.error(`  ${d.name}  first at line ${d.first}, again at line ${d.again}`);
  }
  console.error('[build] These are a SyntaxError in the browser and the page will be blank.');
  process.exitCode = 1;
}

out += `
/* ===== entry point ===== */
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => boot());
} else {
  boot();
}
`;

mkdirSync(jsDir, { recursive: true });
writeFileSync(OUT, out, 'utf8');

const bytes = Buffer.byteLength(out, 'utf8');
console.log(`[build] wrote ${OUT}`);
console.log(`[build] ${totalLines} source lines -> ${(bytes / 1024).toFixed(1)} KiB`);
