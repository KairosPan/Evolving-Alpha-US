// gravit-ui/tests/serve.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createApp, contentType } from '../serve.js';

function listen(app) {
  return new Promise(resolve => app.listen(0, '127.0.0.1', () => resolve(app.address().port)));
}

test('contentType maps the files the shell serves', () => {
  assert.equal(contentType('index.html'), 'text/html; charset=utf-8');
  assert.equal(contentType('js/app.js'), 'text/javascript; charset=utf-8');
  assert.equal(contentType('css/app.css'), 'text/css; charset=utf-8');
  assert.equal(contentType('x.bin'), 'application/octet-stream');
});

test('the server serves index.html at / and 404s a missing file', async () => {
  const app = createApp();
  const port = await listen(app);
  try {
    const home = await fetch(`http://127.0.0.1:${port}/`);
    assert.equal(home.status, 200);
    assert.equal(home.headers.get('content-type'), 'text/html; charset=utf-8');
    const body = await home.text();
    assert.match(body, /<title>Gravit<\/title>/);
    assert.match(body, /css\/tokens\.css/);
    const missing = await fetch(`http://127.0.0.1:${port}/nope.js`);
    assert.equal(missing.status, 404);
  } finally {
    app.close();
  }
});
