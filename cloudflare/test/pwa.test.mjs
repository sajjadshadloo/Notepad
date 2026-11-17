// The installable web app: what the page promises the browser, and what the
// service worker is forbidden to keep.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import worker from '../src/worker.mjs';

const read = name => fs.readFileSync(new URL('../public/' + name, import.meta.url), 'utf8');

test('the app page links the manifest and allows only what the PWA needs', async () => {
  const response = await worker.fetch(new Request('https://example.test/app'), {});
  const html = await response.text();
  assert.match(html, /rel="manifest" href="\/manifest\.webmanifest"/);
  assert.match(html, /rel="apple-touch-icon"/);
  const csp = response.headers.get('Content-Security-Policy');
  assert.match(csp, /manifest-src 'self'/);
  assert.match(csp, /worker-src 'self'/);
  assert.doesNotMatch(csp, /unsafe-inline/);
});

test('the bare address leads to the app', async () => {
  const response = await worker.fetch(new Request('https://example.test/'), {});
  assert.equal(response.status, 302);
  assert.equal(response.headers.get('Location'), 'https://example.test/app');
});

test('every icon the manifest names exists, and the app starts at /app', () => {
  const manifest = JSON.parse(read('manifest.webmanifest'));
  assert.equal(manifest.start_url, '/app');
  assert.equal(manifest.display, 'standalone');
  assert.equal(manifest.dir, 'rtl');
  for (const icon of manifest.icons) {
    assert.ok(fs.existsSync(new URL('../public' + icon.src, import.meta.url)), icon.src);
  }
  assert.ok(manifest.icons.some(i => i.purpose === 'maskable'));
});

test('the service worker never touches notes, the bot or non-GET requests', () => {
  const sw = read('sw.js');
  assert.match(sw, /startsWith\('\/api\/'\)/);
  assert.match(sw, /startsWith\('\/telegram\/'\)/);
  assert.match(sw, /request\.method !== 'GET'/);
});

test('every file the service worker precaches exists', () => {
  const list = /const SHELL = \[([\s\S]*?)\];/.exec(read('sw.js'))[1];
  for (const [, path] of list.matchAll(/'(\/[^']+)'/g)) {
    if (path === '/app') continue;   // served by the worker, not a file
    assert.ok(fs.existsSync(new URL('../public' + path, import.meta.url)), path);
  }
});
