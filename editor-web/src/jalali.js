// Jalali (Persian) calendar, ported from core/jalali.py so the editor shows
// the same date pills the desktop app always did.

const MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
  'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];
const STARTS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
const leapG = (y) => (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
const div = (a, b) => Math.floor(a / b);

export const toAscii = (s) => s
  .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
  .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660));
export const toPersian = (s) => String(s).replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[Number(d)]);

export function fromGregorian(gy, gm, gd) {
  let jy;
  if (gy > 1600) { jy = 979; gy -= 1600; } else { jy = 0; gy -= 621; }
  const adjusted = gm > 2 ? gy + 1 : gy;
  let days = 365 * gy + div(adjusted + 3, 4) - div(adjusted + 99, 100)
    + div(adjusted + 399, 400) - 80 + gd + STARTS[gm - 1];
  jy += 33 * div(days, 12053); days %= 12053;
  jy += 4 * div(days, 1461); days %= 1461;
  if (days > 365) { jy += div(days - 1, 365); days = (days - 1) % 365; }
  if (days < 186) return [jy, 1 + div(days, 31), 1 + (days % 31)];
  return [jy, 7 + div(days - 186, 30), 1 + ((days - 186) % 30)];
}

export function toGregorian(jy, jm, jd) {
  let gy;
  if (jy > 979) { gy = 1600; jy -= 979; } else { gy = 621; }
  let days = 365 * jy + div(jy, 33) * 8 + div((jy % 33) + 3, 4) + 78 + jd
    + (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186);
  gy += 400 * div(days, 146097); days %= 146097;
  if (days > 36524) {
    days -= 1; gy += 100 * div(days, 36524); days %= 36524;
    if (days >= 365) days += 1;
  }
  gy += 4 * div(days, 1461); days %= 1461;
  if (days > 365) { gy += div(days - 1, 365); days = (days - 1) % 365; }
  const lengths = [31, leapG(gy) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  let gd = days + 1; let gm = 0;
  while (gm < 12 && gd > lengths[gm]) { gd -= lengths[gm]; gm += 1; }
  return [gy, gm + 1, gd];
}

const dayNumber = (y, m, d) => Math.round(Date.UTC(y, m - 1, d) / 86400000);

/** "امروز", "فردا", "دیروز" or "۵ شهریور" (+ year when not this year). */
export function pill(jy, jm, jd, now = new Date()) {
  if (jm < 1 || jm > 12 || jd < 1 || jd > 31) return null;
  const [gy, gm, gd] = toGregorian(jy, jm, jd);
  const delta = dayNumber(gy, gm, gd) - dayNumber(now.getFullYear(), now.getMonth() + 1, now.getDate());
  if (delta === 0) return { label: 'امروز', delta };
  if (delta === 1) return { label: 'فردا', delta };
  if (delta === -1) return { label: 'دیروز', delta };
  const [thisYear] = fromGregorian(now.getFullYear(), now.getMonth() + 1, now.getDate());
  let text = `${jd} ${MONTHS[jm - 1]}`;
  if (jy !== thisYear) text += ` ${jy}`;
  return { label: toPersian(text), delta };
}

export function stampFor(date = new Date()) {
  const [y, m, d] = fromGregorian(date.getFullYear(), date.getMonth() + 1, date.getDate());
  return toPersian(`@${String(y).padStart(4, '0')}/${String(m).padStart(2, '0')}/${String(d).padStart(2, '0')}`);
}
