/**
 * check-parts.mjs — validate each authoring part (and the concatenation) with
 * the real parser, reporting line/column so a template-literal mistake is easy
 * to find. Run: node scripts/check-parts.mjs
 */
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';

const here = dirname(fileURLToPath(import.meta.url));
const jsDir = resolve(here, '..', 'web', 'assets', 'js');
const PARTS = ['core.part.js', 'ui.part.js', 'views.part.js', 'views2.part.js'];

function stripExports(code) {
  return code
    .replace(/^export\s+(async\s+function|function|const|let|var|class)\b/gm, '$1')
    .replace(/^export\s*\{[^}]*\}\s*;?\s*$/gm, '')
    .replace(/^export\s+default\s+/gm, 'void ');
}

const tmp = mkdtempSync(join(tmpdir(), 'fut-'));
let failed = 0;

/* eslint-disable no-new-func */
function parseCheck(label, code) {
  const file = join(tmp, 'slice.mjs');
  writeFileSync(file, code, 'utf8');
  try {
    execFileSync(process.execPath, ['--check', file], { stdio: 'pipe' });
    console.log(`[ok]   ${label}`);
    return true;
  } catch (err) {
    failed += 1;
    const out = String(err.stderr || err.message).split('\n').slice(0, 8).join('\n');
    console.log(`[FAIL] ${label}\n${out}`);
    return false;
  }
}

const merged = PARTS.map((p) => stripExports(readFileSync(join(jsDir, p), 'utf8')));

for (let i = 0; i < PARTS.length; i += 1) {
  parseCheck(PARTS[i], merged[i]);
}

parseCheck('concat(core,ui)', merged[0] + '\n' + merged[1]);
parseCheck('concat(core,ui,views)', merged[0] + '\n' + merged[1] + '\n' + merged[2]);
parseCheck('ALL', merged.join('\n'));

process.exit(failed ? 1 : 0);
