import { accountForTelegram } from './accounts.mjs';
import { D1Notes } from './repository.mjs';
import { approvePairing, presentPairing, rateLimit } from './pairing.mjs';

export async function routeTelegramUpdate(update, env, origin) {
  const callback = update?.callback_query;
  const message = callback?.message || update?.edited_message || update?.message;
  const sender = callback?.from || message?.from;
  if (message?.chat?.type !== 'private' || !Number.isSafeInteger(sender?.id) ||
      sender.id <= 0 || sender.id !== message.chat.id) return null;
  const telegramId = String(sender.id);
  if (!(await rateLimit(env, `telegram:${telegramId}`, 60))) return null;
  const text = message.text?.trim() || '';
  const start = /^\/start(?:\s+(.+))?$/.exec(text);
  const account = await accountForTelegram(env, telegramId, Boolean(start && !callback));
  if (!account) return start ? { chatId: sender.id, text: 'ثبت‌نام فعلاً در دسترس نیست. بعداً دوباره امتحان کن.' } : null;
  if (callback) {
    if (callback.data?.startsWith('pair:approve:')) {
      const ok = await approvePairing(env, callback.data.slice(13), account, telegramId);
      return { chatId: sender.id, callbackId: callback.id,
        text: ok ? 'رایانه متصل شد. به برنامه برگرد و پوشهٔ یادداشت‌های قابل همگام‌سازی را تأیید کن.'
          : 'این درخواست منقضی یا قبلاً استفاده شده است؛ از برنامه دوباره اتصال را شروع کن.' };
    }
    const revoke = /^revoke:([0-9a-f-]{36}|legacy-desktop)$/.exec(callback.data || '');
    if (revoke) {
      const changed = await env.DB.prepare('UPDATE devices SET revoked = 1 WHERE id = ? AND user_id = ? AND revoked = 0')
        .bind(revoke[1], account.id).run();
      return { chatId: sender.id, callbackId: callback.id,
        text: changed.meta.changes ? 'دسترسی این رایانه قطع شد. فایل‌های محلی آن حذف نمی‌شوند.' : 'این دستگاه پیدا نشد یا قبلاً قطع شده است.' };
    }
    return null;
  }
  if (start?.[1]?.startsWith('pair_')) {
    const token = start[1].slice(5);
    const pairing = await presentPairing(env, token, telegramId);
    return pairing ? { chatId: sender.id,
      text: `اتصال رایانهٔ «${pairing.name}»\nکد تطبیق: ${pairing.confirm_code}\nاگر این کد در برنامهٔ خودت دیده می‌شود، اتصال را تأیید کن.`,
      replyMarkup: { inline_keyboard: [[{ text: 'تأیید اتصال این رایانه', callback_data: 'pair:approve:' + token }]] } }
      : { chatId: sender.id, text: 'لینک اتصال معتبر نیست یا منقضی شده است. از برنامه دوباره شروع کن.' };
  }
  if (start || text === '/help') return { chatId: sender.id,
    text: 'دفترچهٔ شخصی تو آماده است. پیام متنی بفرست تا یادداشت شود؛ برای اتصال ویندوز دکمهٔ «اتصال به تلگرام» را در برنامه بزن.\n/devices — مدیریت رایانه‌های متصل',
    replyMarkup: { inline_keyboard: [[{ text: 'بازکردن دفترچه', web_app: { url: origin + '/app' } }]] } };
  if (text === '/devices') {
    const rows = (await env.DB.prepare('SELECT id, name FROM devices WHERE user_id = ? AND revoked = 0 ORDER BY created_at')
      .bind(account.id).all()).results;
    return { chatId: sender.id, text: rows.length ? 'برای قطع دسترسی، رایانه را انتخاب کن:' : 'رایانه‌ای متصل نیست.',
      ...(rows.length ? { replyMarkup: { inline_keyboard: rows.map(row => [{ text: 'قطع اتصال: ' + row.name, callback_data: 'revoke:' + row.id }]) } } : {}) };
  }
  try { return await processTelegramUpdate(update, telegramId, new D1Notes(env.DB, account.id)); }
  catch (error) {
    if (String(error).includes('account_quota')) return { chatId: sender.id,
      text: 'ظرفیت آزمایشی دفترچه پر شده است. این تغییر ذخیره نشد؛ متن پیام را نگه دار و با پشتیبانی تماس بگیر.' };
    throw error;
  }
}

export async function processTelegramUpdate(update, ownerId, notes) {
  const edited = Boolean(update?.edited_message);
  const message = update?.edited_message ?? update?.message;
  if (!message || message.chat?.type !== 'private' ||
      String(message.from?.id) !== String(ownerId) ||
      message.from?.id !== message.chat?.id) {
    return null;
  }
  const text = message.text?.trim();
  if (!text || text.startsWith('/')) return null;
  if (text.length > 20000) return { chatId: message.chat.id, text: 'متن یادداشت بیش از حد بلند است.' };

  const result = edited
    ? await notes.editFromMessage(message.chat.id, message.message_id, text)
    : await notes.createFromMessage(message.chat.id, message.message_id, text);
  const replies = {
    created: 'یادداشت ذخیره شد. ویرایش همین پیام، همین یادداشت را به‌روز می‌کند.',
    edited: 'ویرایش یادداشت ذخیره شد.',
    conflict: 'تعارض ثبت شد؛ هر دو نسخه محفوظ‌اند و بعداً می‌توانی آن‌ها را ادغام کنی.',
    unknown: 'پیام اصلی را پیدا نکردم؛ یادداشت جدیدی ساخته نشد.',
  };
  return replies[result.kind] ? { chatId: message.chat.id, text: replies[result.kind] } : null;
}
