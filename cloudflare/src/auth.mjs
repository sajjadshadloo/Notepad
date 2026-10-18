const encoder = new TextEncoder();

function constantTimeEqual(a, b) {
  if (!a || !b || a.length !== b.length) return false;
  let difference = 0;
  for (let i = 0; i < a.length; i++) difference |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return difference === 0;
}

async function hmac(key, value) {
  const imported = await crypto.subtle.importKey('raw', key, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return new Uint8Array(await crypto.subtle.sign('HMAC', imported, encoder.encode(value)));
}

function hex(bytes) {
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}

export async function verifiedTelegramIdentity(initData, token, now = Date.now()) {
  if (!initData || !token || initData.length > 8192) return null;
  const params = new URLSearchParams(initData);
  if (new Set(params.keys()).size !== [...params.keys()].length) return null;
  const hash = params.get('hash');
  const timestamp = Number(params.get('auth_date'));
  if (!hash || !/^[0-9a-f]{64}$/i.test(hash) || !Number.isSafeInteger(timestamp) ||
      Math.abs(now / 1000 - timestamp) > 86400) return false;
  params.delete('hash');
  const data = Array.from(params.entries()).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([key, value]) => `${key}=${value}`).join('\n');
  const secret = await hmac(encoder.encode('WebAppData'), token);
  if (!constantTimeEqual(hex(await hmac(secret, data)), hash.toLowerCase())) return false;
  try {
    const id = JSON.parse(params.get('user')).id;
    return Number.isSafeInteger(id) && id > 0 ? String(id) : null;
  } catch { return null; }
}

export async function verifiedTelegramUser(initData, token, ownerId, now = Date.now()) {
  const id = await verifiedTelegramIdentity(initData, token, now);
  return Boolean(id && ownerId && id === String(ownerId));
}

export async function sha256(value) {
  return hex(new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(value))));
}

export async function authenticate(request, env) {
  if (!env.DB) return null;
  if (desktopAuthorized(request, env)) {
    const account = await env.DB.prepare("SELECT id FROM accounts WHERE id = 'legacy-owner' AND disabled = 0").first();
    const device = await env.DB.prepare("SELECT id FROM devices WHERE id = 'legacy-desktop' AND revoked = 0").first();
    return account && device ? { userId: account.id, deviceId: device.id, kind: 'desktop' } : null;
  }
  const key = request.headers.get('Authorization')?.replace(/^Bearer /, '');
  if (key && /^[0-9a-f]{64}$/.test(key)) {
    const device = await env.DB.prepare(`SELECT d.id, d.user_id FROM devices d
      JOIN accounts a ON a.id = d.user_id WHERE d.key_hash = ? AND d.revoked = 0 AND a.disabled = 0`)
      .bind(await sha256(key)).first();
    if (device) return { userId: device.user_id, deviceId: device.id, kind: 'desktop' };
  }
  const telegramId = await verifiedTelegramIdentity(request.headers.get('X-Telegram-Init-Data'), env.TELEGRAM_BOT_TOKEN);
  if (!telegramId) return null;
  const { accountForTelegram } = await import('./accounts.mjs');
  const account = await accountForTelegram(env, telegramId);
  return account ? { userId: account.id, telegramId, kind: 'telegram' } : null;
}

export async function authorized(request, env) {
  return Boolean(await authenticate(request, env));
}

export function desktopAuthorized(request, env) {
  const desktopKey = request.headers.get('Authorization')?.replace(/^Bearer /, '');
  return Boolean(env.DESKTOP_SYNC_KEY && constantTimeEqual(desktopKey, env.DESKTOP_SYNC_KEY));
}
