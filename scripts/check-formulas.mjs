#!/usr/bin/env node
/**
 * check-formulas.mjs — render every stored formula's LaTeX and fail on exceptions.
 *
 * WHY THIS EXISTS (a real outage):
 *   The 公式剖析 page went completely blank with
 *     "Cannot read properties of null (reading '0')"
 *   thrown from inside tex(). One malformed LaTeX string was enough, because the
 *   whole view is produced by a single template literal: any exception during the
 *   render replaced the entire page with an error card. The daily agent writes new
 *   formulas unattended, so a new bad string can appear overnight with no human in
 *   the loop - this check is the guard that catches it before it reaches the site.
 *
 * It evaluates the REAL tex() implementation lifted out of the built bundle, so it
 * cannot drift from what the browser runs.
 *
 * Usage: node scripts/check-formulas.mjs
 */
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const BUNDLE = join(ROOT, 'web', 'assets', 'js', 'app.js');
const FORMULAS = join(ROOT, 'web', 'data', 'formulas.json');

const src = readFileSync(BUNDLE, 'utf8');

// The tex machinery spans one contiguous region: the earliest constant table it
// closes over (GREEK) through tex() itself (which ends where texInline begins).
// The bundle has ESM `export` keywords stripped, hence the bare declarations.
const start = src.indexOf('const GREEK =');
const end = src.indexOf('function texInline(');
if (start < 0 || end < 0) {
  console.error('[formulas] could not locate the tex() machinery in the bundle.');
  console.error('[formulas] Did the bundle layout change? Update this extraction.');
  process.exit(2);
}
const chunk = src.slice(start, end);

// tex() calls esc(), which lives elsewhere in the bundle; supply the same
// behaviour so the extracted code runs standalone.
const prelude = `
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
  return ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[c]; }); }
`;

let tex;
try {
  // eslint-disable-next-line no-new-func
  tex = new Function(`${prelude}\n${chunk}\nreturn tex;`)();
} catch (e) {
  console.error(`[formulas] failed to evaluate the tex machinery: ${e.message}`);
  process.exit(2);
}

let data;
try {
  data = JSON.parse(readFileSync(FORMULAS, 'utf8'));
} catch (e) {
  console.error(`[formulas] cannot read formulas.json: ${e.message}`);
  process.exit(2);
}

const list = data.formulas || [];
if (!list.length) {
  console.error('[formulas] formulas.json contains no formulas');
  process.exit(2);
}

let failures = 0;
let rendered = 0;
for (const f of list) {
  for (const field of ['latex', 'formula']) {
    const value = f[field];
    if (!value) continue;
    rendered++;
    try {
      const html = tex(value);
      if (typeof html !== 'string' || !html.length) {
        failures++;
        console.error(`[FAIL] ${f.id} (${field}): produced empty output`);
      }
    } catch (e) {
      failures++;
      console.error(`[FAIL] ${f.id} (${field}): ${e.message}`);
      console.error(`       ${JSON.stringify(String(value).slice(0, 160))}`);
    }
  }
}

console.log(`[formulas] ${list.length} formula(s), ${rendered} LaTeX string(s) rendered, ${failures} failure(s)`);
if (failures) {
  console.error('[formulas] A formula that throws will blank the whole 公式剖析 page');
  console.error('[formulas] (the view is one template literal). Fix the LaTeX or the renderer.');
  process.exit(1);
}
console.log('[formulas] OK');
