import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { DatabaseSync } from 'node:sqlite';

import { collectDailyTasks, dailyDigestClock, dailyDigestText, runDailyDigest } from '../src/daily-digest.mjs';
import worker from '../src/worker.mjs';

function database() {
  const sqlite = new DatabaseSync(':memory:');
  sqlite.exec(readFileSync(new URL('../schema.sql', import.meta.url), 'utf8'));
  const db = {
    prepare(sql) {
      return {
        async all() { return { results: sqlite.prepare(sql).all() }; },
        bind(...values) {
          return {
            async run() { return { meta: { changes: sqlite.prepare(sql).run(...values).changes } }; },
          };
        },
      };
    },
  };
  return { db, sqlite };
}

const morning = new Date('2026-09-24T05:30:00Z'); // 09:00 in Tehran, 1405/07/02
const envFor = db => ({ DB: db, TELEGRAM_BOT_TOKEN: 'test-only', TELEGRAM_OWNER_ID: '123' });
const insertNote = (sqlite, text) => sqlite.prepare(
  'INSERT INTO notes (id, path, text, version) VALUES (?, ?, ?, 1)'
).run(crypto.randomUUID(), `${crypto.randomUUID()}.md`, text);

test('daily summary reads open Jalali and Gregorian tasks, not completed or undated tasks', () => {
  assert.deepEqual(dailyDigestClock(morning), {
    hour: 9, day: '2026/09/24', persianDay: '1405/07/02',
    date: new Date('2026-09-24T12:00:00Z'),
  });
  const summary = collectDailyTasks([{ deleted: 0, text: [
    '- [ ] کار عقب‌افتاده @۱۴۰۵/۰۷/۰۱',
    '- [ ] کار امروز @1405/07/02 18:00',
    '- [ ] تاریخ میلادی @2026-09-24',
    '- [x] انجام‌شده @1405/07/02',
    '- [ ] بدون تاریخ',
    '- [ ] تاریخ غلط @1405/13/45',
    '- [ ] کار تکراری @1405/06/26 10:00 ↻',
  ].join('\n') }, { deleted: 1, text: '- [ ] حذف‌شده @1405/07/02' }], morning);
  assert.deepEqual(summary.overdue.map(task => task.title), ['کار عقب‌افتاده']);
  assert.deepEqual(summary.today.map(task => task.title),
    ['کار امروز', 'تاریخ میلادی', 'کار تکراری']);
  const message = dailyDigestText(summary);
  assert.match(message, /عقب‌افتاده \(1\)/);
  assert.match(message, /امروز \(3\)/);
  assert.doesNotMatch(message, /• انجام‌شده|• حذف‌شده|• بدون تاریخ/);
});

test('scheduled digest sends once, only during Tehran morning', async () => {
  const { db, sqlite } = database();
  insertNote(sqlite, '- [ ] خرید دارو @1405/07/02 18:00');
  const env = envFor(db);
  const previousFetch = globalThis.fetch;
  const sent = [];
  globalThis.fetch = async (_url, options) => {
    sent.push(JSON.parse(options.body));
    return Response.json({ ok: true, result: { message_id: 777 } });
  };
  try {
    assert.deepEqual(await runDailyDigest(env, new Date('2026-09-24T05:29:00Z')),
      { kind: 'outside-hour' });
    await worker.scheduled({ scheduledTime: morning.getTime() }, env);
    assert.deepEqual(await runDailyDigest(env, new Date('2026-09-24T05:45:00Z')),
      { kind: 'already-claimed' });
    assert.equal(sent.length, 1);
    assert.equal(sent[0].chat_id, 123);
    assert.match(sent[0].text, /خرید دارو/);
    assert.deepEqual({ ...sqlite.prepare('SELECT day, state, message_id FROM daily_digest').get() },
      { day: '2026/09/24', state: 'sent', message_id: 777 });
  } finally { globalThis.fetch = previousFetch; sqlite.close(); }
});

test('empty day does not send; definite Telegram failure can retry', async () => {
  const { db, sqlite } = database();
  const env = envFor(db);
  let attempts = 0;
  const send = async () => {
    attempts += 1;
    return attempts === 1
      ? Response.json({ ok: false, description: 'Unavailable' }, { status: 503 })
      : Response.json({ ok: true, result: { message_id: 1 } });
  };
  try {
    assert.deepEqual(await runDailyDigest(env, morning, send), { kind: 'empty' });
    insertNote(sqlite, '- [ ] تماس @1405/07/02');
    await assert.rejects(runDailyDigest(env, morning, send), /Telegram rejected/);
    assert.equal(sqlite.prepare('SELECT state FROM daily_digest').get().state, 'failed');
    assert.deepEqual(await runDailyDigest(env, morning, send),
      { kind: 'sent', day: '2026/09/24' });
    assert.equal(attempts, 2);
  } finally { sqlite.close(); }
});

test('unknown Telegram delivery result keeps claim to avoid duplicate messages', async () => {
  const { db, sqlite } = database();
  insertNote(sqlite, '- [ ] تماس @1405/07/02');
  const env = envFor(db);
  let attempts = 0;
  const send = async () => { attempts += 1; throw new Error('Connection lost'); };
  try {
    await assert.rejects(runDailyDigest(env, morning, send), /Connection lost/);
    assert.deepEqual(await runDailyDigest(env, morning, send), { kind: 'already-claimed' });
    assert.equal(attempts, 1);
    assert.equal(sqlite.prepare('SELECT state FROM daily_digest').get().state, 'pending');
  } finally { sqlite.close(); }
});
