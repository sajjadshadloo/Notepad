import { processTelegramUpdate } from './handler.mjs';
import { D1Notes } from './repository.mjs';
import { handleApi } from './api.mjs';
import { miniAppHtml } from './miniapp.mjs';
import { runDailyDigest } from './daily-digest.mjs';

function sameSecret(received, expected) {
  if (!received || !expected || received.length !== expected.length) return false;
  let difference = 0;
  for (let i = 0; i < received.length; i++) difference |= received.charCodeAt(i) ^ expected.charCodeAt(i);
  return difference === 0;
}

export default {
  async scheduled(controller, env) {
    await runDailyDigest(env, new Date(controller.scheduledTime));
  },
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/health' && request.method === 'GET') return new Response('ok');
    if (url.pathname === '/app' && request.method === 'GET') return new Response(miniAppHtml, {
      headers: { 'Content-Type': 'text/html; charset=utf-8',
        'Content-Security-Policy': "default-src 'none'; script-src 'self' https://telegram.org; style-src 'self'; font-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors https://web.telegram.org https://*.telegram.org" },
    });
    if (url.pathname === '/app.js' && request.method === 'GET') return new Response((await import('./miniapp-client.mjs')).miniAppScript, {
      headers: { 'Content-Type': 'application/javascript; charset=utf-8' },
    });
    if (url.pathname === '/telegram/menu' && ['GET', 'POST'].includes(request.method)) {
      if (!env.DESKTOP_SYNC_KEY || !sameSecret(request.headers.get('Authorization'),
          `Bearer ${env.DESKTOP_SYNC_KEY}`)) return new Response('Forbidden', { status: 403 });
      const endpoint = request.method === 'POST' ? 'setChatMenuButton' : 'getChatMenuButton';
      const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${endpoint}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: Number(env.TELEGRAM_OWNER_ID),
          ...(request.method === 'POST' ? { menu_button: { type: 'web_app', text: 'نوت پلاس',
            web_app: { url: `${url.origin}/app` } } } : {}) }),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) return new Response('Telegram menu request failed', { status: 502 });
      return new Response(JSON.stringify(request.method === 'POST' ? { ok: true } : result.result), {
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
      });
    }
    if (url.pathname.startsWith('/api/')) return handleApi(request, env, new D1Notes(env.DB));
    if (url.pathname !== '/telegram/webhook' || request.method !== 'POST') {
      return new Response('Not found', { status: 404 });
    }
    if (!sameSecret(request.headers.get('X-Telegram-Bot-Api-Secret-Token'), env.TELEGRAM_WEBHOOK_SECRET)) {
      return new Response('Forbidden', { status: 403 });
    }
    if (!env.DB || !env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_OWNER_ID) {
      return new Response('Service not configured', { status: 503 });
    }
    const raw = await request.text();
    if (raw.length > 65536) return new Response('Too large', { status: 413 });
    let update;
    try { update = JSON.parse(raw); } catch { return new Response('Bad JSON', { status: 400 }); }

    const reply = await processTelegramUpdate(update, env.TELEGRAM_OWNER_ID, new D1Notes(env.DB));
    if (reply) {
      const sent = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: reply.chatId, text: reply.text }),
      });
      if (!sent.ok) return new Response('Telegram reply failed', { status: 502 });
    }
    return new Response('ok');
  },
};
