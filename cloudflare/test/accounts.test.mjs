import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import worker from '../src/worker.mjs';
import { accountForTelegram } from '../src/accounts.mjs';
import { sha256 } from '../src/auth.mjs';
import { D1Notes } from '../src/repository.mjs';
import { routeTelegramUpdate } from '../src/handler.mjs';
import { presentPairing, approvePairing } from '../src/pairing.mjs';
import { runAllDailyDigests } from '../src/daily-digest.mjs';
import { database, schema, initData } from './helpers.mjs';

function service() {
  const { db, sqlite } = database();
  const env = { DB: db, TELEGRAM_OWNER_ID: '123', TELEGRAM_BOT_TOKEN: 'test-token',
    DESKTOP_SYNC_KEY: 'legacy-test-key', TELEGRAM_BOT_USERNAME: 'TestNotepadBot', PUBLIC_REGISTRATION: 'true' };
  const call = (path, method = 'GET', body, headers = {}) => worker.fetch(new Request('https://example.test/api' + path,
    { method, headers: { 'Content-Type': 'application/json', ...headers },
      body: body === undefined ? undefined : JSON.stringify(body) }), env);
  return { db, sqlite, env, call };
}
const bearer = key => ({ Authorization: 'Bearer ' + key });
const textMessage = (id, text) => ({ message: { from: { id }, chat: { id, type: 'private' }, message_id: 12, text } });

async function pair(s, telegramId) {
  const account = await accountForTelegram(s.env, String(telegramId), true);
  const key = crypto.randomUUID().replaceAll('-', '') + crypto.randomUUID().replaceAll('-', '');
  const poll = 'b'.repeat(64);
  const response = await s.call('/pairings', 'POST', { name: 'رایانه آزمایشی', poll_key: poll, key_hash: await sha256(key) });
  assert.equal(response.status, 201);
  const pending = await response.json();
  const token = new URL(pending.telegram_url).searchParams.get('start').slice(5);
  assert.ok(await presentPairing(s.env, token, String(telegramId)));
  assert.ok(await approvePairing(s.env, token, account, String(telegramId)));
  return { account, key, poll, pending, token };
}

test('migration keeps IDs, versions, deleted notes, messages, conflicts, status and digest claims', () => {
  const { sqlite } = database(schema.split('-- Multi-user schema')[0]);
  try {
    sqlite.exec(`INSERT INTO notes VALUES ('note-a', 'tasks.md', 'before', 7, 0, 1234);
      INSERT INTO notes VALUES ('note-b', 'deleted.md', 'kept', 3, 1, 123);
      INSERT INTO telegram_messages VALUES (123, 1, 'note-a', 6, 'old');
      INSERT INTO conflicts VALUES ('c', 'note-a', 123, 1, 6, 7, 'before', 'proposed', 'open', 123);
      INSERT INTO desktop_sync_status (id, checked_at, state) VALUES (1, 42, 'ok');
      INSERT INTO daily_digest (day, state, claimed_at) VALUES ('2026/10/17', 'sent', 32);`);
    const sql = readFileSync(new URL('../migrations/0004_accounts.sql', import.meta.url), 'utf8');
    sqlite.exec('BEGIN;\n' + sql + '\nCOMMIT;');
    assert.equal(sqlite.prepare('SELECT version FROM notes WHERE id = ?').get('note-a').version, 7);
    assert.equal(sqlite.prepare('SELECT deleted FROM notes WHERE id = ?').get('note-b').deleted, 1);
    assert.equal(sqlite.prepare('SELECT user_id FROM telegram_messages').get().user_id, 'legacy-owner');
    assert.equal(sqlite.prepare('SELECT user_id FROM conflicts').get().user_id, 'legacy-owner');
    assert.equal(sqlite.prepare('SELECT checked_at FROM desktop_sync_status').get().checked_at, 42);
    assert.equal(sqlite.prepare('SELECT state FROM daily_digest').get().state, 'sent');
    assert.deepEqual(sqlite.prepare('PRAGMA foreign_key_check').all(), []);
  } finally { sqlite.close(); }
});

test('two users can use the same paths but cannot read, overwrite, delete or resolve each other notes', async () => {
  const s = service();
  try {
    const a = await pair(s, 456), b = await pair(s, 789);
    const create = async (who, text) => (await (await s.call('/notes', 'POST', { path: 'tasks.md', text }, bearer(who.key))).json()).note;
    const noteA = await create(a, 'علی'), noteB = await create(b, 'مریم');
    assert.notEqual(noteA.id, noteB.id);
    const listed = await (await s.call('/notes', 'GET', undefined, bearer(a.key))).json();
    assert.deepEqual(listed.notes.map(n => n.text), ['علی']);
    for (const method of ['PUT', 'DELETE']) {
      assert.equal((await s.call('/notes/' + noteB.id, method, { version: 1, text: 'stolen' }, bearer(a.key))).status, 404);
    }
    const repo = new D1Notes(s.db, b.account.id);
    const mapped = await repo.createFromMessage(789, 1, 'اول');
    await repo.change(mapped.noteId, 1, 'رایانه');
    await repo.editFromMessage(789, 1, 'تلگرام');
    const conflict = (await repo.openConflicts())[0];
    assert.deepEqual((await (await s.call('/conflicts', 'GET', undefined, bearer(a.key))).json()).conflicts, []);
    assert.equal((await s.call('/conflicts/' + conflict.id, 'POST', { keep: 'proposed' }, bearer(a.key))).status, 404);
    assert.equal((await new D1Notes(s.db, b.account.id).list()).find(n => n.id === noteB.id).text, 'مریم');
    assert.equal((await s.call('/notes', 'GET', undefined, bearer('legacy-test-key'))).status, 200);
    assert.deepEqual((await (await s.call('/notes', 'GET', undefined, bearer('legacy-test-key'))).json()).notes, []);
  } finally { s.sqlite.close(); }
});

test('pairing keeps device keys private, requires poll proof and matching Telegram confirmation', async () => {
  const s = service();
  try {
    const a = await pair(s, 456);
    assert.equal((await s.call('/pairings/' + a.pending.id, 'POST', { poll_key: 'c'.repeat(64) })).status, 404);
    const status = await s.call('/pairings/' + a.pending.id, 'POST', { poll_key: a.poll });
    const body = await status.text();
    assert.equal(JSON.parse(body).status, 'approved');
    assert.ok(!body.includes(a.key));
    assert.equal(s.sqlite.prepare('SELECT key_hash FROM devices WHERE user_id = ?').get(a.account.id).key_hash, await sha256(a.key));
    assert.equal(await approvePairing(s.env, a.token, a.account, '456'), false);
    assert.equal(await approvePairing(s.env, a.token, a.account, '789'), false);
    s.sqlite.prepare('UPDATE pairings SET expires_at = 1').run();
    assert.equal((await s.call('/pairings/' + a.pending.id, 'POST', { poll_key: a.poll })).status, 410);
  } finally { s.sqlite.close(); }
});

test('a forwarded pairing link cannot be approved by a different Telegram user', async () => {
  const s = service();
  try {
    const account = await accountForTelegram(s.env, '456', true);
    const response = await s.call('/pairings', 'POST', { name: 'Test', poll_key: 'd'.repeat(64), key_hash: 'e'.repeat(64) });
    const body = await response.json(), token = new URL(body.telegram_url).searchParams.get('start').slice(5);
    assert.ok(await presentPairing(s.env, token, '456'));
    assert.equal(await presentPairing(s.env, token, '789'), null);
    assert.equal(await approvePairing(s.env, token, account, '789'), false);
    assert.equal(s.sqlite.prepare('SELECT COUNT(*) AS n FROM devices WHERE user_id = ?').get(account.id).n, 0);
  } finally { s.sqlite.close(); }
});

test('device revocation is scoped and immediately rejects its credential', async () => {
  const s = service();
  try {
    const a = await pair(s, 456), b = await pair(s, 789);
    const devices = await (await s.call('/devices', 'GET', undefined, bearer(a.key))).json();
    assert.equal(devices.devices.length, 1);
    assert.ok(!JSON.stringify(devices).includes('key_hash'));
    const id = devices.devices[0].id;
    assert.equal((await s.call('/devices/' + id, 'DELETE', undefined, bearer(b.key))).status, 404);
    assert.equal((await s.call('/devices/' + id, 'DELETE', undefined, bearer(a.key))).status, 200);
    assert.equal((await s.call('/notes', 'GET', undefined, bearer(a.key))).status, 401);
    assert.equal((await s.call('/notes', 'GET', undefined, bearer(b.key))).status, 200);
  } finally { s.sqlite.close(); }
});

test('signed Mini App identity uses its own account; unsigned/unknown/disabled identities fail', async () => {
  const s = service();
  try {
    const a = await pair(s, 456);
    await new D1Notes(s.db, a.account.id).create('a.md', 'private');
    const signed = await initData(456);
    const headers = { 'X-Telegram-Init-Data': signed };
    assert.equal((await s.call('/notes', 'GET', undefined, headers)).status, 200);
    assert.equal((await s.call('/notes', 'GET', undefined, { 'X-Telegram-Init-Data': signed.replace('456', '789') })).status, 401);
    assert.equal((await s.call('/notes', 'GET', undefined, { 'X-Telegram-Init-Data': await initData(999) })).status, 401);
    s.sqlite.prepare('UPDATE accounts SET disabled = 1 WHERE id = ?').run(a.account.id);
    assert.equal((await s.call('/notes', 'GET', undefined, headers)).status, 401);
    assert.equal((await s.call('/notes', 'GET', undefined, bearer(a.key))).status, 401);
  } finally { s.sqlite.close(); }
});

test('bot registers separate users; group messages cannot register or pair', async () => {
  const s = service();
  try {
    await routeTelegramUpdate(textMessage(456, '/start'), s.env, 'https://example.test');
    await routeTelegramUpdate(textMessage(789, '/start'), s.env, 'https://example.test');
    await routeTelegramUpdate(textMessage(456, 'یادداشت علی'), s.env, 'https://example.test');
    await routeTelegramUpdate(textMessage(789, 'یادداشت مریم'), s.env, 'https://example.test');
    const rows = s.sqlite.prepare('SELECT user_id, text FROM notes').all();
    assert.equal(rows.length, 2);
    assert.notEqual(rows[0].user_id, rows[1].user_id);
    const group = textMessage(999, '/start'); group.message.chat.type = 'group';
    assert.equal(await routeTelegramUpdate(group, s.env, 'https://example.test'), null);
    assert.equal(s.sqlite.prepare('SELECT COUNT(*) AS n FROM accounts WHERE telegram_id = ?').get('999').n, 0);
  } finally { s.sqlite.close(); }
});

test('registration and pairing have bounded capacity and request throttling', async () => {
  const s = service();
  try {
    s.env.PUBLIC_REGISTRATION = 'false';
    assert.equal(await accountForTelegram(s.env, '456', true), null);
    s.env.PUBLIC_REGISTRATION = 'true'; s.env.MAX_USERS = '2';
    assert.ok(await accountForTelegram(s.env, '456', true));
    assert.equal(await accountForTelegram(s.env, '789', true), null);
    for (let i = 0; i < 6; i++) {
      assert.equal((await s.call('/pairings', 'POST', { name: '', poll_key: 'f'.repeat(64), key_hash: 'e'.repeat(64) })).status, 400);
    }
    assert.equal((await s.call('/pairings', 'POST', { poll_key: 'f'.repeat(64) })).status, 429);
  } finally { s.sqlite.close(); }
});

test('sync heartbeat and daily digest are isolated by account and device', async () => {
  const s = service();
  try {
    const a = await pair(s, 456), b = await pair(s, 789);
    const report = { state: 'ok', downloaded: 1, uploaded: 2, deleted: 0, conflicts: 0, skipped: 0, error: '' };
    assert.equal((await s.call('/sync-status', 'POST', report, bearer(a.key))).status, 200);
    assert.equal((await (await s.call('/sync-status', 'GET', undefined, bearer(b.key))).json()).status, null);
    await new D1Notes(s.db, a.account.id).create('tasks.md', '- [ ] علی @1405/07/02');
    await new D1Notes(s.db, b.account.id).create('tasks.md', '- [ ] مریم @1405/07/02');
    const sent = [];
    const send = async (_url, options) => {
      sent.push(JSON.parse(options.body)); return Response.json({ ok: true, result: { message_id: sent.length } });
    };
    const morning = new Date('2026-09-24T05:30:00Z');
    await runAllDailyDigests(s.env, morning, send);
    await runAllDailyDigests(s.env, morning, send);
    assert.equal(sent.length, 2);
    assert.ok(sent.find(m => m.chat_id === 456).text.includes('علی'));
    assert.ok(!sent.find(m => m.chat_id === 456).text.includes('مریم'));
    assert.ok(sent.find(m => m.chat_id === 789).text.includes('مریم'));
  } finally { s.sqlite.close(); }
});

test('complete webhook pairing flow approves once and can revoke the paired device', async () => {
  const s = service();
  s.env.TELEGRAM_WEBHOOK_SECRET = 'test-webhook-only';
  const sent = [];
  const previous = globalThis.fetch;
  globalThis.fetch = async (_url, options) => {
    sent.push(JSON.parse(options.body));
    return Response.json({ ok: true, result: { message_id: sent.length } });
  };
  try {
    const key = 'a'.repeat(64), pollKey = 'b'.repeat(64);
    const response = await s.call('/pairings', 'POST', { name: 'Alice PC', poll_key: pollKey, key_hash: await sha256(key) });
    const body = await response.json();
    const start = new URL(body.telegram_url).searchParams.get('start');
    const webhook = update => worker.fetch(new Request('https://example.test/telegram/webhook', {
      method: 'POST', headers: { 'X-Telegram-Bot-Api-Secret-Token': 'test-webhook-only' }, body: JSON.stringify(update),
    }), s.env);
    assert.equal((await webhook(textMessage(456, '/start ' + start))).status, 200);
    const button = sent[0].reply_markup.inline_keyboard[0][0];
    assert.equal(button.text, 'تأیید اتصال این رایانه');
    assert.ok(sent[0].text.includes(body.confirm_code));
    const callback = { callback_query: { id: 'callback-1', from: { id: 456 }, data: button.callback_data,
      message: { chat: { id: 456, type: 'private' } } } };
    assert.equal((await webhook(callback)).status, 200);
    const status = await (await s.call('/pairings/' + body.id, 'POST', { poll_key: pollKey })).json();
    assert.equal(status.status, 'approved');
    assert.equal((await s.call('/account', 'GET', undefined, bearer(key))).status, 200);
    await webhook(textMessage(456, '/devices'));
    const revoke = sent.at(-1).reply_markup.inline_keyboard[0][0].callback_data;
    callback.callback_query.data = revoke;
    await webhook(callback);
    assert.equal((await s.call('/notes', 'GET', undefined, bearer(key))).status, 401);
  } finally { globalThis.fetch = previous; s.sqlite.close(); }
});

test('account quota rejection preserves the previous note and other users remain usable', async () => {
  const s = service();
  try {
    const a = await pair(s, 456), b = await pair(s, 789);
    const repo = new D1Notes(s.db, a.account.id);
    const note = await repo.create('n.md', 'keep');
    // Unicode byte size can exceed quota even when request character size is small.
    const response = await s.call('/notes/' + note.id, 'PUT', { version: 1, text: 'م'.repeat(160000) }, bearer(a.key));
    assert.equal(response.status, 413);
    assert.equal((await repo.list())[0].text, 'keep');
    assert.equal((await s.call('/notes', 'POST', { path: 'n.md', text: 'fine' }, bearer(b.key))).status, 201);
  } finally { s.sqlite.close(); }
});

test('maintenance freezes API, webhook and scheduled writes without touching the database', async () => {
  const env = { MAINTENANCE: 'true', DB: { prepare() { throw new Error('must not access DB'); } } };
  for (const path of ['/api/notes', '/api/pairings', '/telegram/webhook']) {
    const response = await worker.fetch(new Request('https://example.test' + path), env);
    assert.equal(response.status, 503);
  }
  await worker.scheduled({ scheduledTime: Date.now() }, env);
  assert.equal((await worker.fetch(new Request('https://example.test/health'), env)).status, 200);
});
