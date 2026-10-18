import { sha256 } from './auth.mjs';

const json = (body, status = 200) => Response.json(body, {
  status, headers: { 'Cache-Control': 'no-store' },
});
const hex64 = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
const randomHex = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2, '0')).join('');
const botNames = new Map();

async function botUsername(env) {
  if (env.TELEGRAM_BOT_USERNAME) return env.TELEGRAM_BOT_USERNAME;
  if (!env.TELEGRAM_BOT_TOKEN) return '';
  const botId = env.TELEGRAM_BOT_TOKEN.split(':')[0];
  if (botNames.has(botId)) return botNames.get(botId);
  try {
    const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/getMe`, {
      signal: AbortSignal.timeout(5000),
    });
    const data = await response.json();
    if (response.ok && data.ok && /^[A-Za-z0-9_]{5,32}$/.test(data.result?.username || '')) {
      botNames.set(botId, data.result.username);
      return data.result.username;
    }
  } catch { /* report an unavailable service without exposing the bot token */ }
  return '';
}

export async function rateLimit(env, bucket, maximum, windowMs = 60000) {
  const now = Date.now();
  const key = await sha256(bucket);
  const result = await env.DB.prepare(`INSERT INTO request_limits (bucket, count, expires_at) VALUES (?, 1, ?)
    ON CONFLICT(bucket) DO UPDATE SET count = CASE WHEN expires_at <= ? THEN 1 ELSE count + 1 END,
    expires_at = CASE WHEN expires_at <= ? THEN excluded.expires_at ELSE expires_at END RETURNING count`)
    .bind(key, now + windowMs, now, now).first();
  return result.count <= maximum;
}

export async function pairingApi(request, env) {
  if (!env.DB) return json({ error: 'not_configured' }, 503);
  const path = new URL(request.url).pathname;
  const match = /^\/api\/pairings\/([0-9a-f-]{36})$/.exec(path);
  if (request.method !== 'POST' || (path !== '/api/pairings' && !match)) return json({ error: 'not_found' }, 404);
  const ip = request.headers.get('CF-Connecting-IP') || 'local';
  if (!(await rateLimit(env, `pair:${match ? 'poll' : 'start'}:${ip}`, match ? 120 : 6))) {
    return json({ error: 'rate_limited' }, 429);
  }
  let body;
  try {
    const raw = await request.text();
    if (raw.length > 2048) return json({ error: 'too_large' }, 413);
    body = JSON.parse(raw);
  } catch { return json({ error: 'bad_json' }, 400); }
  if (!hex64(body?.poll_key)) return json({ error: 'invalid_pairing' }, 400);
  const pollHash = await sha256(body.poll_key);
  if (match) {
    const pairing = await env.DB.prepare(`SELECT p.user_id, p.device_id, p.expires_at, d.revoked, a.disabled
      FROM pairings p LEFT JOIN devices d ON d.id = p.device_id LEFT JOIN accounts a ON a.id = p.user_id
      WHERE p.id = ? AND p.poll_hash = ?`).bind(match[1], pollHash).first();
    if (!pairing) return json({ error: 'not_found' }, 404);
    if (pairing.expires_at <= Date.now()) return json({ error: 'expired' }, 410);
    if (pairing.revoked || pairing.disabled) return json({ error: 'revoked' }, 403);
    return json({ status: pairing.user_id ? 'approved' : 'pending',
      ...(pairing.user_id ? { user_id: pairing.user_id, device_id: pairing.device_id } : {}) });
  }
  const username = await botUsername(env);
  if (!/^[A-Za-z0-9_]{5,32}$/.test(username)) return json({ error: 'not_configured' }, 503);
  if (!hex64(body.key_hash) || typeof body.name !== 'string' || !body.name.trim() || body.name.length > 80) {
    return json({ error: 'invalid_pairing' }, 400);
  }
  const now = Date.now();
  await env.DB.batch([
    env.DB.prepare('DELETE FROM pairings WHERE expires_at <= ?').bind(now),
    env.DB.prepare('DELETE FROM request_limits WHERE expires_at <= ?').bind(now - 3600000),
  ]);
  const id = crypto.randomUUID(), link = randomHex(), deviceId = crypto.randomUUID();
  const code = String(crypto.getRandomValues(new Uint32Array(1))[0] % 1000000).padStart(6, '0');
  const expires = now + 600000;
  const result = await env.DB.prepare(`INSERT INTO pairings
    (id, link_hash, poll_hash, key_hash, device_id, name, confirm_code, expires_at, created_at)
    SELECT ?, ?, ?, ?, ?, ?, ?, ?, ? WHERE (SELECT COUNT(*) FROM pairings) < 500`)
    .bind(id, await sha256(link), pollHash, body.key_hash, deviceId, body.name.trim(), code, expires, now).run();
  if (!result.meta.changes) return json({ error: 'busy' }, 503);
  return json({ id, confirm_code: code, expires_at: expires,
    telegram_url: `https://t.me/${username}?start=pair_${link}` }, 201);
}

export async function presentPairing(env, token, telegramId) {
  if (!/^[0-9a-f]{32}$/.test(token)) return null;
  const hash = await sha256(token);
  await env.DB.prepare(`UPDATE pairings SET presented_to = ? WHERE link_hash = ? AND presented_to IS NULL
    AND user_id IS NULL AND expires_at > ?`).bind(String(telegramId), hash, Date.now()).run();
  return env.DB.prepare(`SELECT name, confirm_code FROM pairings WHERE link_hash = ?
    AND presented_to = ? AND user_id IS NULL AND expires_at > ?`)
    .bind(hash, String(telegramId), Date.now()).first();
}

export async function approvePairing(env, token, account, telegramId) {
  if (!/^[0-9a-f]{32}$/.test(token)) return false;
  const hash = await sha256(token), now = Date.now();
  // The insert and claim run in one D1 transaction. A retry inserts no second
  // device, and an expired/forwarded approval cannot claim somebody's session.
  const result = await env.DB.batch([
    env.DB.prepare(`INSERT OR IGNORE INTO devices (id, user_id, key_hash, name, created_at)
      SELECT device_id, ?, key_hash, name, ? FROM pairings
      WHERE link_hash = ? AND presented_to = ? AND user_id IS NULL AND expires_at > ?
      AND (SELECT COUNT(*) FROM devices WHERE user_id = ? AND revoked = 0) < 10`)
      .bind(account.id, now, hash, String(telegramId), now, account.id),
    env.DB.prepare(`UPDATE pairings SET user_id = ? WHERE link_hash = ? AND presented_to = ?
      AND user_id IS NULL AND expires_at > ? AND EXISTS
      (SELECT 1 FROM devices d WHERE d.id = pairings.device_id AND d.user_id = ? AND d.revoked = 0)`)
      .bind(account.id, hash, String(telegramId), now, account.id),
  ]);
  return result[1].meta.changes === 1;
}
