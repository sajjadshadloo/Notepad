// The page's own API, driven the way the desktop host drives it.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makeEditor } from './dom.mjs';
import { createApp } from '../src/app.js';

globalThis.requestAnimationFrame ??= (fn) => setTimeout(fn, 0);

function page(text, host = {}) {
  makeEditor(); // sets up the DOM globals
  const root = document.createElement('div');
  document.body.appendChild(root);
  const app = createApp(root, host);
  app.open(text);
  return app;
}

test('selectMatch picks the n-th match, so the host replaces what it shows', () => {
  const app = page('سیب موز سیب\n');
  assert.equal(app.selectMatch('سیب', 1, true), true);
  assert.equal(app.selectedText(), 'سیب');
  assert.equal(app.selectMatch('هلو', 0, true), false);
});

test('a selection over two lines reports where it ends', () => {
  const seen = [];
  const app = page('اول\nدوم\nسوم\n', { cursor: (c) => seen.push(c) });
  app.cmd('selectAll');
  const last = seen[seen.length - 1];
  assert.equal(last.line, 1);
  assert.equal(last.endLine, 3);
});
