/**
 * serve-dist.mjs — a tiny static file server for the built site.
 *
 * WHY: the UI guards (verify-text-stacking, verify-collapse, verify-columns,
 * verify-interview-panel) open the site in headless Chrome. Relying on a server that
 * a human happened to start made them fail for the wrong reason, which is worse than
 * not having them - a guard that reports "connection refused" trains you to ignore
 * it. audit-layout.mjs already served its own files; this shares that behaviour.
 *
 * MIME types cover exactly what dist/ contains; anything else is served as binary.
 */
import { createServer } from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import { extname, join, normalize, resolve } from 'node:path';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.jsonl': 'application/x-ndjson; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
};

/**
 * Wait until the SPA has actually rendered its view.
 *
 * WHY this matters more than it looks: every UI guard here is a negative assertion
 * ("no stacked text", "nothing clipped"). Against an EMPTY page they all pass
 * trivially. Measured: `verify-text-stacking.mjs` reported "未发现竖排文字" against the
 * published site while the page still said "数据加载中…" - the published payload is
 * ~4 MB over the network, so a fixed wait is not enough. A guard that succeeds because
 * nothing rendered is worse than no guard, because it reports safety it never checked.
 *
 * @param {(expr: string) => Promise<any>} evaluate  CDP Runtime.evaluate wrapper
 *        returning the result value.
 * @param {string} readyExpr  expression that is true once the view has rendered.
 * @param {number} timeoutMs
 */
export async function waitForRender(evaluate, readyExpr, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      if ((await evaluate(readyExpr)) === true) return true;
    } catch { /* page still navigating */ }
    await new Promise((r) => setTimeout(r, 1000));
  }
  return false;
}

/**
 * True when the shell has finished loading and the route has real content.
 * Deliberately checks that the "数据加载中" placeholder is gone AND that the document
 * has substantial text, so it fails loudly rather than silently passing.
 */
export const RENDERED_EXPR =
  "document.body.innerText.indexOf('数据加载中') === -1"
  + " && document.body.innerText.length > 800";

export async function serveDir(rootDir) {
  const root = resolve(rootDir);
  if (!existsSync(root)) throw new Error(`serveDir: ${root} does not exist`);
  const server = createServer((req, res) => {
    try {
      const raw = decodeURIComponent((req.url || '/').split('?')[0]);
      let rel = normalize(raw).replace(/^([/\\])+/, '');
      if (rel.includes('..')) { res.writeHead(403).end('forbidden'); return; }
      let file = join(root, rel);
      if (existsSync(file) && statSync(file).isDirectory()) file = join(file, 'index.html');
      if (!existsSync(file)) { res.writeHead(404).end('not found'); return; }
      res.writeHead(200, {
        'Content-Type': MIME[extname(file).toLowerCase()] || 'application/octet-stream',
        // No caching: a guard must test the files that are on disk right now.
        'Cache-Control': 'no-store',
      });
      createReadStream(file).pipe(res);
    } catch (e) {
      res.writeHead(500).end(String(e && e.message));
    }
  });
  await new Promise((res) => server.listen(0, '127.0.0.1', res));
  const { port } = server.address();
  return {
    url: `http://127.0.0.1:${port}`,
    close: () => new Promise((res) => server.close(res)),
  };
}
