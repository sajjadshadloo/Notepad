import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { DatabaseSync } from 'node:sqlite';

import { D1Notes } from '../src/repository.mjs';
import worker from '../src/worker.mjs';
import { verifiedTelegramUser } from '../src/auth.mjs';

function database() {
  const sqlite = new DatabaseSync(':memory:');
  sqlite.exec(readFileSync(new URL('../schema.sql', import.meta.url), 'utf8'));
  const db = {
    prepare(sql) {
      return {
        async first() { return sqlite.prepare(sql).get() ?? null; },
        async all() { return { results: sqlite.prepare(sql).all() }; },
        bind(...params) {
          return {
            async first() { return sqlite.prepare(sql).get(...params) ?? null; },
            async all() { return { results: sqlite.prepare(sql).all(...params) }; },
            async run() { return { meta: { changes: sqlite.prepare(sql).run(...params).changes } }; },
          };
        },
      };
    },
    async batch(statements) {
      sqlite.exec('BEGIN');
      try {
        for (const statement of statements) await statement.run();
        sqlite.exec('COMMIT');
      } catch (error) {
        sqlite.exec('ROLLBACK');
        throw error;
      }
    },
  };
  return { db, sqlite };
}

function update(text, edited = false) {
  const message = {
    message_id: 42,
    chat: { id: 123, type: 'private' },
    from: { id: 123 },
    text,
  };
  return edited ? { edited_message: message } : { message };
}

test('Telegram webhook creates one note, edits it, and ignores retry', async () => {
  const { db, sqlite } = database();
  const env = {
    DB: db, TELEGRAM_BOT_TOKEN: 'test-only',
    TELEGRAM_WEBHOOK_SECRET: 'webhook-test-secret', TELEGRAM_OWNER_ID: '123',
  };
  const originalFetch = globalThis.fetch;
  const replies = [];
  globalThis.fetch = async (_url, options) => {
    replies.push(JSON.parse(options.body).text);
    return new Response('{}', { status: 200 });
  };
  const request = (body, secret = 'webhook-test-secret') => new Request(
    'https://example.com/telegram/webhook', {
      method: 'POST', headers: { 'X-Telegram-Bot-Api-Secret-Token': secret },
      body: JSON.stringify(body),
    }
  );
  try {
    assert.equal((await worker.fetch(request(update('خرید دارو'), 'wrong'), env)).status, 403);
    assert.equal((await worker.fetch(request(update('خرید دارو')), env)).status, 200);
    assert.equal((await worker.fetch(request(update('خرید دارو')), env)).status, 200);
    assert.equal((await worker.fetch(request(update('خرید دارو و نان', true)), env)).status, 200);
    const rows = sqlite.prepare('SELECT text, version FROM notes').all().map(row => ({ ...row }));
    assert.deepEqual(rows, [{ text: 'خرید دارو و نان', version: 2 }]);
    assert.equal(replies.length, 2);
  } finally {
    globalThis.fetch = originalFetch;
    sqlite.close();
  }
});

test('stale Telegram edit preserves both texts as a conflict', async () => {
  const { db, sqlite } = database();
  try {
    const notes = new D1Notes(db);
    const created = await notes.createFromMessage(123, 42, 'متن اول');
    sqlite.prepare('UPDATE notes SET text = ?, version = 2 WHERE id = ?')
      .run('ویرایش ویندوز', created.noteId);
    const result = await notes.editFromMessage(123, 42, 'ویرایش تلگرام');
    assert.equal(result.kind, 'conflict');
    assert.deepEqual(sqlite.prepare('SELECT text, version FROM notes').all().map(row => ({ ...row })),
      [{ text: 'ویرایش ویندوز', version: 2 }]);
    assert.deepEqual(sqlite.prepare('SELECT current_text, proposed_text FROM conflicts').all().map(row => ({ ...row })),
      [{ current_text: 'ویرایش ویندوز', proposed_text: 'ویرایش تلگرام' }]);
  } finally {
    sqlite.close();
  }
});

test('only the configured owner in a private chat can create notes', async () => {
  const { processTelegramUpdate } = await import('../src/handler.mjs');
  let called = false;
  const notes = { async createFromMessage() { called = true; return { kind: 'created' }; } };
  const foreign = update('private text');
  foreign.message.from.id = 456;
  assert.equal(await processTelegramUpdate(foreign, '123', notes), null);
  const group = update('group text');
  group.message.chat.type = 'group';
  assert.equal(await processTelegramUpdate(group, '123', notes), null);
  assert.equal(called, false);
});

test('desktop API supports list, create, edit, delete and stale version rejection', async () => {
  const { db, sqlite } = database();
  const env = { DB: db, DESKTOP_SYNC_KEY: 'only-for-test' };
  const call = (path, method = 'GET', body, key = 'only-for-test') => worker.fetch(
    new Request('https://example.com/api' + path, {
      method, headers: { Authorization: 'Bearer ' + key },
      body: body && JSON.stringify(body),
    }), env);
  try {
    assert.equal((await call('/notes', 'GET', null, 'wrong')).status, 401);
    const created = await call('/notes', 'POST', { path: 'Tasks/Inbox.md', text: '- [ ] خرید' });
    assert.equal(created.status, 201);
    const note = (await created.json()).note;
    assert.equal((await (await call('/notes')).json()).notes.length, 1);
    assert.equal((await call('/notes/' + note.id, 'PUT', { version: 1, text: 'بعدی' })).status, 200);
    assert.equal((await call('/notes/' + note.id, 'PUT', { version: 1, text: 'قدیمی' })).status, 409);
    assert.equal((await call('/notes/' + note.id, 'DELETE', { version: 2 })).status, 200);
    assert.equal((await (await call('/notes')).json()).notes[0].deleted, 1);
    const restored = await call('/notes', 'POST', { path: 'Tasks/Inbox.md', text: 'دوباره' });
    assert.equal(restored.status, 201);
    assert.equal((await restored.json()).note.id, note.id);
  } finally { sqlite.close(); }
});

test('Mini App signature accepts only the owner and rejects edits', async () => {
  const token = '123:test-only';
  const now = 1800000000000;
  const input = new URLSearchParams({ auth_date: String(now / 1000),
    user: JSON.stringify({ id: 123, first_name: 'Test' }) });
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode('WebAppData'),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const secret = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(token));
  const finalKey = await crypto.subtle.importKey('raw', secret,
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const data = Array.from(input.entries()).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([k, v]) => `${k}=${v}`).join('\n');
  const hash = Array.from(new Uint8Array(await crypto.subtle.sign('HMAC', finalKey,
    new TextEncoder().encode(data))), b => b.toString(16).padStart(2, '0')).join('');
  input.set('hash', hash);
  assert.equal(await verifiedTelegramUser(input.toString(), token, '123', now), true);
  assert.equal(await verifiedTelegramUser(input.toString(), token, '456', now), false);
  input.set('user', JSON.stringify({ id: 456 }));
  assert.equal(await verifiedTelegramUser(input.toString(), token, '456', now), false);
});

test('desktop sync status is owner-readable and desktop-writable', async () => {
  const { db, sqlite } = database();
  const env = { DB: db, DESKTOP_SYNC_KEY: 'only-for-test' };
  const call = (method, body, key = 'only-for-test') => worker.fetch(new Request(
    'https://example.com/api/sync-status', {
      method, headers: { Authorization: 'Bearer ' + key },
      body: body === undefined ? undefined : JSON.stringify(body),
    }), env);
  const status = { state: 'ok', downloaded: 1, uploaded: 0, deleted: 0,
    conflicts: 0, skipped: 0, error: '' };
  try {
    assert.equal((await call('GET', undefined, 'wrong')).status, 401);
    assert.equal((await (await call('GET')).json()).status, null);
    assert.equal((await call('POST', status, 'wrong')).status, 401);
    assert.equal((await call('POST', { ...status, skipped: -1 })).status, 400);
    assert.equal((await call('POST', status)).status, 200);
    const first = (await (await call('GET')).json()).status;
    assert.equal(first.state, 'ok');
    assert.equal(first.downloaded, 1);
    assert.ok(first.completed_at);
    assert.equal((await call('POST', { ...status, state: 'error', error: 'offline' })).status, 200);
    const second = (await (await call('GET')).json()).status;
    assert.equal(second.state, 'error');
    assert.equal(second.completed_at, first.completed_at);
  } finally { sqlite.close(); }
});
