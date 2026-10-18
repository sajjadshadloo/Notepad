const taskLine = /^\s*-\s+\[([ xX])\]\s+(.+)$/;
const dateStamp = /\s*@(\d{3,4})[/-](\d{1,2})[/-](\d{1,2})(?:\s+\d{1,2}:\d{2})?(\s*↻)?\s*$/;
const tehranClock = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', hourCycle: 'h23',
});
const persianDate = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
  timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit',
});

const ascii = value => String(value).replace(/[۰-۹]/g, digit => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(digit)))
  .replace(/[٠-٩]/g, digit => String('٠١٢٣٤٥٦٧٨٩'.indexOf(digit)));
const pad = value => String(value).padStart(2, '0');
const parts = (formatter, date) => Object.fromEntries(formatter.formatToParts(date)
  .filter(part => ['year', 'month', 'day', 'hour'].includes(part.type))
  .map(part => [part.type, Number(ascii(part.value))]));
const dayKey = (year, month, day) => `${year}/${pad(month)}/${pad(day)}`;
const persianKey = date => {
  const value = parts(persianDate, date);
  return dayKey(value.year, value.month, value.day);
};

function jalaliToGregorian(year, month, day) {
  let jy = year;
  let gy = jy > 979 ? 1600 : 621;
  if (jy > 979) jy -= 979;
  let days = 365 * jy + Math.floor(jy / 33) * 8
    + Math.floor((jy % 33 + 3) / 4) + 78 + day
    + (month < 7 ? (month - 1) * 31 : (month - 7) * 30 + 186);
  gy += 400 * Math.floor(days / 146097);
  days %= 146097;
  if (days > 36524) {
    days -= 1;
    gy += 100 * Math.floor(days / 36524);
    days %= 36524;
    if (days >= 365) days += 1;
  }
  gy += 4 * Math.floor(days / 1461);
  days %= 1461;
  if (days > 365) {
    gy += Math.floor((days - 1) / 365);
    days = (days - 1) % 365;
  }
  return new Date(Date.UTC(gy, 0, days + 1, 12));
}

function dueDate(year, month, day) {
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  const date = year >= 1600
    ? new Date(Date.UTC(year, month - 1, day, 12))
    : jalaliToGregorian(year, month, day);
  const valid = year >= 1600
    ? date.getUTCFullYear() === year && date.getUTCMonth() + 1 === month
      && date.getUTCDate() === day
    : persianKey(date) === dayKey(year, month, day);
  return valid ? date : null;
}

export function dailyDigestClock(now) {
  const local = parts(tehranClock, now);
  return { hour: local.hour, day: dayKey(local.year, local.month, local.day),
    persianDay: persianKey(now),
    date: new Date(Date.UTC(local.year, local.month - 1, local.day, 12)) };
}

export function collectDailyTasks(notes, now) {
  const clock = dailyDigestClock(now);
  const overdue = [];
  const today = [];
  for (const note of notes) {
    if (note.deleted) continue;
    for (const line of note.text.split('\n')) {
      const task = taskLine.exec(line);
      if (!task || task[1] !== ' ') continue;
      const normalized = ascii(task[2]);
      const stamp = dateStamp.exec(normalized);
      if (!stamp) continue;
      const date = dueDate(Number(stamp[1]), Number(stamp[2]), Number(stamp[3]));
      if (!date) continue;
      const title = task[2].slice(0, stamp.index).trim();
      if (!title) continue;
      const due = persianKey(date);
      if (stamp[4]) {
        const days = Math.round((clock.date - date) / 86400000);
        if (days >= 0 && days % 7 === 0) today.push({ title, due });
      } else if (due < clock.persianDay) overdue.push({ title, due });
      else if (due === clock.persianDay) today.push({ title, due });
    }
  }
  overdue.sort((a, b) => a.due.localeCompare(b.due));
  return { overdue, today, day: clock.persianDay };
}

export function dailyDigestText(summary) {
  if (!summary.overdue.length && !summary.today.length) return null;
  const lines = [`☀️ کارهای مانده — ${summary.day}`, ''];
  for (const [label, tasks] of [['🔴 عقب‌افتاده', summary.overdue], ['📅 امروز', summary.today]]) {
    if (!tasks.length) continue;
    lines.push(`${label} (${tasks.length})`);
    for (const task of tasks.slice(0, 12)) {
      const title = task.title.length > 110 ? task.title.slice(0, 107) + '…' : task.title;
      lines.push(`• ${title}${label.startsWith('🔴') ? ` (${task.due})` : ''}`);
    }
    if (tasks.length > 12) lines.push(`• و ${tasks.length - 12} کار دیگر`);
    lines.push('');
  }
  lines.push('کارهای انجام‌شده را در Mini App تیک بزن.');
  return lines.join('\n');
}

export async function runDailyDigest(env, now = new Date(), send = fetch, userId = 'legacy-owner', chatId = env.TELEGRAM_OWNER_ID, suppliedNotes = null) {
  const clock = dailyDigestClock(now);
  if (clock.hour !== 9) return { kind: 'outside-hour' };
  if (!env.DB || !env.TELEGRAM_BOT_TOKEN || !chatId) {
    throw new Error('Daily digest is not configured');
  }
  const notes = suppliedNotes || (await env.DB.prepare('SELECT text, deleted FROM notes WHERE user_id = ?').bind(userId).all()).results;
  const message = dailyDigestText(collectDailyTasks(notes, now));
  if (!message) return { kind: 'empty' };
  const claimed = await env.DB.prepare(`INSERT INTO daily_digest (user_id, day, state, claimed_at)
    VALUES (?, ?, 'pending', ?) ON CONFLICT(user_id, day) DO UPDATE SET
    state = 'pending', claimed_at = excluded.claimed_at, error = ''
    WHERE daily_digest.state = 'failed'`).bind(userId, clock.day, now.getTime()).run();
  if (claimed.meta.changes !== 1) return { kind: 'already-claimed' };

  let response;
  try {
    response = await send(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: Number(chatId), text: message }),
    });
  } catch (error) {
    // A timeout may follow successful delivery. Keep the claim to prevent duplicates.
    await env.DB.prepare('UPDATE daily_digest SET error = ? WHERE user_id = ? AND day = ?')
      .bind('Telegram response unknown', userId, clock.day).run();
    throw error;
  }
  let result;
  try { result = await response.json(); } catch {
    await env.DB.prepare('UPDATE daily_digest SET error = ? WHERE user_id = ? AND day = ?')
      .bind('Telegram response unreadable', userId, clock.day).run();
    throw new Error('Telegram daily digest response is unreadable');
  }
  if (!response.ok || result.ok === false) {
    await env.DB.prepare("UPDATE daily_digest SET state = 'failed', error = ? WHERE user_id = ? AND day = ?")
      .bind(`Telegram rejected request (${response.status})`, userId, clock.day).run();
    throw new Error(`Telegram rejected daily digest (${response.status})`);
  }
  if (result.ok !== true || !result.result?.message_id) {
    await env.DB.prepare('UPDATE daily_digest SET error = ? WHERE user_id = ? AND day = ?')
      .bind('Telegram response incomplete', userId, clock.day).run();
    throw new Error('Telegram daily digest response is incomplete');
  }
  await env.DB.prepare("UPDATE daily_digest SET state = 'sent', sent_at = ?, message_id = ? WHERE user_id = ? AND day = ?")
    .bind(Date.now(), result.result.message_id, userId, clock.day).run();
  return { kind: 'sent', day: clock.day };
}

// Bound each invocation; later quarter-hours pick up remaining unsent accounts.
// Grouping happens inside the Worker, never in a user's API response.
export async function runAllDailyDigests(env, now = new Date(), send = fetch) {
  const clock = dailyDigestClock(now);
  if (clock.hour !== 9) return { kind: 'outside-hour' };
  if (env.TELEGRAM_OWNER_ID) {
    const { accountForTelegram } = await import('./accounts.mjs');
    await accountForTelegram(env, String(env.TELEGRAM_OWNER_ID));
  }
  const accounts = (await env.DB.prepare(`SELECT a.id, a.telegram_id
    FROM accounts a LEFT JOIN daily_digest d ON d.user_id = a.id AND d.day = ?
    WHERE a.disabled = 0 AND a.telegram_id IS NOT NULL
      AND (d.state IS NULL OR d.state = 'failed')
    ORDER BY (d.state IS NOT NULL), a.id LIMIT 20`)
    .bind(clock.day).all()).results;
  const results = [];
  for (const account of accounts) {
    const notes = (await env.DB.prepare('SELECT text, deleted FROM notes WHERE user_id = ? AND deleted = 0')
      .bind(account.id).all()).results;
    if (!dailyDigestText(collectDailyTasks(notes, now))) continue;
    try { results.push(await runDailyDigest(env, now, send, account.id, account.telegram_id, notes)); }
    catch { results.push({ kind: 'delivery-error' }); }
    if (results.length >= 6) break;
  }
  return { kind: 'processed', results };
}
