import { routeTelegramUpdate } from './handler.mjs';
import { handleApi } from './api.mjs';
import { miniAppHtml } from './miniapp.mjs';
import { runAllDailyDigests } from './daily-digest.mjs';
import { pairingApi } from './pairing.mjs';

function sameSecret(received, expected) {
  if (!received || !expected || received.length !== expected.length) return false;
  let difference = 0;
  for (let i = 0; i < received.length; i++) difference |= received.charCodeAt(i) ^ expected.charCodeAt(i);
  return difference === 0;
}

export default {
  async scheduled(controller, env) {
    if (env.MAINTENANCE === 'true') return;
    await runAllDailyDigests(env, new Date(controller.scheduledTime));
  },
  async fetch(request, env) {
    const url = new URL(request.url);
    if (env.MAINTENANCE === 'true' && (url.pathname.startsWith('/api/') || url.pathname === '/telegram/webhook')) {
      return new Response('Sync is being upgraded. Please retry shortly.', {
        status: 503, headers: { 'Retry-After': '30', 'Cache-Control': 'no-store' },
      });
    }
    if (url.pathname === '/health' && request.method === 'GET') return new Response('ok');
    if (url.pathname === '/app' && request.method === 'GET') return new Response(miniAppHtml, {
      headers: { 'Content-Type': 'text/html; charset=utf-8',
        'Content-Security-Policy': "default-src 'none'; script-src 'self' https://telegram.org; style-src 'self'; font-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors https://web.telegram.org https://*.telegram.org" },
    });
    if (url.pathname === '/telegram/webhook-settings' && ['GET', 'POST'].includes(request.method)) {
      if (!env.DESKTOP_SYNC_KEY || !sameSecret(request.headers.get('Authorization'),
          `Bearer ${env.DESKTOP_SYNC_KEY}`)) return new Response('Forbidden', { status: 403 });
      if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_WEBHOOK_SECRET) return new Response('Service not configured', { status: 503 });
      const required = ['message', 'edited_message', 'callback_query'];
      const telegram = async (method, body) => {
        const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body || {}), signal: AbortSignal.timeout(10000),
        });
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error('Telegram configuration unavailable');
        return result.result;
      };
      const info = await telegram('getWebhookInfo');
      const expected = url.origin + '/telegram/webhook';
      const current = info.allowed_updates || [];
      const acceptsCallbacks = !current.length || current.includes('callback_query');
      if (request.method === 'POST') {
        if (info.url !== expected) return new Response('Webhook URL mismatch', { status: 409 });
        await telegram('setWebhook', { url: expected, secret_token: env.TELEGRAM_WEBHOOK_SECRET,
          allowed_updates: [...new Set([...current, ...required])] });
        // Never drop queued updates; new callback events use the repaired filter.
        return Response.json({ ok: true }, { headers: { 'Cache-Control': 'no-store' } });
      }
      return Response.json({ configured_for_this_worker: info.url === expected,
        allowed_updates: current, callback_queries_enabled: acceptsCallbacks,
        pending_update_count: info.pending_update_count || 0,
        last_error_date: info.last_error_date || null }, { headers: { 'Cache-Control': 'no-store' } });
    }
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
    if (url.pathname === '/api/pairings' || url.pathname.startsWith('/api/pairings/')) return pairingApi(request, env);
    if (url.pathname.startsWith('/api/')) return handleApi(request, env);
    if (url.pathname !== '/telegram/webhook' || request.method !== 'POST') {
      return new Response('Not found', { status: 404 });
    }
    if (!sameSecret(request.headers.get('X-Telegram-Bot-Api-Secret-Token'), env.TELEGRAM_WEBHOOK_SECRET)) {
      return new Response('Forbidden', { status: 403 });
    }
    if (!env.DB || !env.TELEGRAM_BOT_TOKEN) {
      return new Response('Service not configured', { status: 503 });
    }
    const raw = await request.text();
    if (raw.length > 65536) return new Response('Too large', { status: 413 });
    let update;
    try { update = JSON.parse(raw); } catch { return new Response('Bad JSON', { status: 400 }); }

    const reply = await routeTelegramUpdate(update, env, url.origin);
    if (reply) {
      if (reply.callbackId) await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/answerCallbackQuery`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ callback_query_id: reply.callbackId }),
      });
      const sent = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: reply.chatId, text: reply.text,
          ...(reply.replyMarkup ? { reply_markup: reply.replyMarkup } : {}) }),
      });
      if (!sent.ok) return new Response('Telegram reply failed', { status: 502 });
    }
    return new Response('ok');
  },
};
