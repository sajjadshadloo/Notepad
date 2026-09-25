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

export async function verifiedTelegramUser(initData, token, ownerId, now = Date.now()) {
  if (!initData || !token || !ownerId || initData.length > 8192) return false;
  const params = new URLSearchParams(initData);
  const hash = params.get('hash');
  const timestamp = Number(params.get('auth_date'));
  if (!hash || !/^[0-9a-f]{64}$/i.test(hash) || !Number.isSafeInteger(timestamp) ||
      Math.abs(now / 1000 - timestamp) > 86400) return false;
  params.delete('hash');
  const data = Array.from(params.entries()).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([key, value]) => `${key}=${value}`).join('\n');
  const secret = await hmac(encoder.encode('WebAppData'), token);
  if (!constantTimeEqual(hex(await hmac(secret, data)), hash.toLowerCase())) return false;
  try { return String(JSON.parse(params.get('user')).id) === String(ownerId); }
  catch { return false; }
}

export async function authorized(request, env) {
  if (desktopAuthorized(request, env)) return true;
  return verifiedTelegramUser(request.headers.get('X-Telegram-Init-Data'),
    env.TELEGRAM_BOT_TOKEN, env.TELEGRAM_OWNER_ID);
}

export function desktopAuthorized(request, env) {
  const desktopKey = request.headers.get('Authorization')?.replace(/^Bearer /, '');
  return Boolean(env.DESKTOP_SYNC_KEY && constantTimeEqual(desktopKey, env.DESKTOP_SYNC_KEY));
}
