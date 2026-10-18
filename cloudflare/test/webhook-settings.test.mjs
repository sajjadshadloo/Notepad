import assert from 'node:assert/strict';
import { test } from 'node:test';
import worker from '../src/worker.mjs';

test('webhook diagnostics are owner-only and repair includes callbacks without dropping updates or exposing secrets', async () => {
  const env = { DESKTOP_SYNC_KEY: 'admin-only', TELEGRAM_BOT_TOKEN: 'token-test', TELEGRAM_WEBHOOK_SECRET: 'secret-test' };
  const old = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return Response.json({ ok: true, result: url.endsWith('getWebhookInfo')
      ? { url: 'https://example.test/telegram/webhook', allowed_updates: ['message', 'edited_message'], pending_update_count: 2 }
      : true });
  };
  const request = (method, key = 'admin-only') => new Request('https://example.test/telegram/webhook-settings', {
    method, headers: { Authorization: 'Bearer ' + key },
  });
  try {
    assert.equal((await worker.fetch(request('GET', 'wrong'), env)).status, 403);
    assert.equal(calls.length, 0);
    const status = await (await worker.fetch(request('GET'), env)).json();
    assert.equal(status.callback_queries_enabled, false);
    assert.equal(status.configured_for_this_worker, true);
    assert.equal(status.pending_update_count, 2);
    assert.equal((await worker.fetch(request('POST'), env)).status, 200);
    const repair = calls.at(-1).body;
    assert.deepEqual(repair.allowed_updates, ['message', 'edited_message', 'callback_query']);
    assert.equal(repair.secret_token, env.TELEGRAM_WEBHOOK_SECRET);
    assert.equal(repair.url, 'https://example.test/telegram/webhook');
    assert.equal(repair.drop_pending_updates, undefined);
    assert.ok(!JSON.stringify(status).includes(env.TELEGRAM_BOT_TOKEN));
    assert.ok(!JSON.stringify(status).includes(env.TELEGRAM_WEBHOOK_SECRET));
  } finally { globalThis.fetch = old; }
});

test('default Telegram update filter already accepts callback queries', async () => {
  const old = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ ok: true, result: { url: 'https://example.test/telegram/webhook' } });
  try {
    const request = new Request('https://example.test/telegram/webhook-settings', { headers: { Authorization: 'Bearer key' } });
    const response = await worker.fetch(request, { DESKTOP_SYNC_KEY: 'key', TELEGRAM_BOT_TOKEN: 'token', TELEGRAM_WEBHOOK_SECRET: 'secret' });
    assert.equal((await response.json()).callback_queries_enabled, true);
  } finally { globalThis.fetch = old; }
});
