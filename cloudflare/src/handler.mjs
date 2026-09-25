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
