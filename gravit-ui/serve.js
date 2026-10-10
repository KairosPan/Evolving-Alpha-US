// gravit-ui/serve.js — a zero-dependency static server: `npm start` → http://127.0.0.1:4830/
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, join, normalize, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('.', import.meta.url));
export const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.md': 'text/markdown; charset=utf-8',
};

export function contentType(path) {
  return TYPES[extname(path).toLowerCase()] ?? 'application/octet-stream';
}

export function createApp(root = ROOT) {
  return createServer(async (req, res) => {
    const url = new URL(req.url, 'http://localhost');
    let path = normalize(decodeURIComponent(url.pathname));
    if (path.endsWith(sep) || path.endsWith('/')) path += 'index.html';
    const file = join(root, path);
    if (!file.startsWith(root)) { res.writeHead(403); return res.end(); }
    try {
      const s = await stat(file);
      if (s.isDirectory()) { res.writeHead(302, { location: url.pathname + '/' }); return res.end(); }
      res.writeHead(200, { 'content-type': contentType(file), 'cache-control': 'no-store' });
      res.end(await readFile(file));
    } catch {
      res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
      res.end('not found');
    }
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PORT || 4830);
  createApp().listen(port, '127.0.0.1', () => console.log(`gravit-ui at http://127.0.0.1:${port}/`));
}
