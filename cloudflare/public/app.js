// Notepad Plus Mini App — the v4 design, on the real notes.
//
// The notes live in D1 and on the desktop as plain files; this page is a view
// of them. A task is a checkbox line anywhere, with an optional trailing
// stamp exactly as the desktop writes it:  - [ ] متن @۱۴۰۵/۰۷/۰۳ ۱۰:۰۰ ↻
// New tasks go to tasks.md, quick notes to Inbox/, like the desktop app.
(() => {
  'use strict';
  const tg = window.Telegram && window.Telegram.WebApp;
  const $ = id => document.getElementById(id);

  // ---------------------------------------------------------------- digits
  const FA = '۰۱۲۳۴۵۶۷۸۹';
  const fa = v => String(v).replace(/\d/g, d => FA[+d]);
  const ascii = v => String(v == null ? '' : v)
    .replace(/[۰-۹]/g, d => FA.indexOf(d))
    .replace(/[٠-٩]/g, d => '٠١٢٣٤٥٦٧٨٩'.indexOf(d));
  const pad = n => String(n).padStart(2, '0');

  // ------------------------------------------------------- Jalali calendar
  // Day numbers are Julian day numbers, so "tomorrow" is just +1.
  const div = (a, b) => ~~(a / b);
  const mod = (a, b) => a - ~~(a / b) * b;
  const BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097,
    2192, 2262, 2324, 2394, 2456, 3178];
  function jalCal(jy) {
    const gy = jy + 621;
    let leapJ = -14, jp = BREAKS[0], jump = 0;
    for (let i = 1; i < BREAKS.length; i++) {
      const jm = BREAKS[i];
      jump = jm - jp;
      if (jy < jm) break;
      leapJ += div(jump, 33) * 8 + div(mod(jump, 33), 4);
      jp = jm;
    }
    let n = jy - jp;
    leapJ += div(n, 33) * 8 + div(mod(n, 33) + 3, 4);
    if (mod(jump, 33) === 4 && jump - n === 4) leapJ += 1;
    const leapG = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150;
    const march = 20 + leapJ - leapG;
    if (jump - n < 6) n = n - jump + div(jump + 4, 33) * 33;
    let leap = mod(mod(n + 1, 33) - 1, 4);
    if (leap === -1) leap = 4;
    return { leap, gy, march };
  }
  function g2d(gy, gm, gd) {
    const d = div((gy + div(gm - 8, 6) + 100100) * 1461, 4) + div(153 * mod(gm + 9, 12) + 2, 5) + gd - 34840408;
    return d - div(div(gy + 100100 + div(gm - 8, 6), 100) * 3, 4) + 752;
  }
  function d2g(jdn) {
    let j = 4 * jdn + 139361631;
    j = j + div(div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908;
    const i = div(mod(j, 1461), 4) * 5 + 308;
    const gm = mod(div(i, 153), 12) + 1;
    return [div(j, 1461) - 100100 + div(8 - gm, 6), gm, div(mod(i, 153), 5) + 1];
  }
  function j2d(jy, jm, jd) {
    const r = jalCal(jy);
    return g2d(r.gy, 3, r.march) + (jm - 1) * 31 - div(jm, 7) * (jm - 7) + jd - 1;
  }
  function d2j(jdn) {
    const gy = d2g(jdn)[0];
    let jy = gy - 621;
    const r = jalCal(jy);
    let k = jdn - g2d(gy, 3, r.march);
    if (k >= 0) {
      if (k <= 185) return [jy, 1 + div(k, 31), mod(k, 31) + 1];
      k -= 186;
    } else {
      jy -= 1;
      k += 179;
      if (r.leap === 1) k += 1;
    }
    return [jy, 7 + div(k, 30), mod(k, 30) + 1];
  }
  const monthStart = (jy, jm) => j2d(jy, jm, 1);
  const nextMonth = (jy, jm) => jm === 12 ? [jy + 1, 1] : [jy, jm + 1];
  const prevMonth = (jy, jm) => jm === 1 ? [jy - 1, 12] : [jy, jm - 1];
  const monthLength = (jy, jm) => monthStart(...nextMonth(jy, jm)) - monthStart(jy, jm);

  const WD = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه'];
  const WDS = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'];
  const MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر',
    'دی', 'بهمن', 'اسفند'];
  const weekIndex = d => (d + 2) % 7; // Saturday is 0
  const wdOf = d => WD[weekIndex(d)];

  // "Now" is always Tehran's, whatever the phone thinks.
  const clockFmt = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Tehran', year: 'numeric', month: 'numeric', day: 'numeric',
    hour: 'numeric', minute: 'numeric', hourCycle: 'h23',
  });
  let T = 0, NOW = 0;
  function tick() {
    const p = {};
    for (const part of clockFmt.formatToParts(new Date())) p[part.type] = +part.value;
    T = g2d(p.year, p.month, p.day);
    NOW = (p.hour % 24) * 60 + p.minute;
  }
  tick();
  const dayOfTime = ms => {
    const p = {};
    for (const part of clockFmt.formatToParts(new Date(ms))) p[part.type] = +part.value;
    return g2d(p.year, p.month, p.day);
  };

  function dname(d) {
    const [jy, jm, jd] = d2j(d);
    return fa(jd) + ' ' + MONTHS[jm - 1] + (jy !== d2j(T)[0] ? ' ' + fa(jy) : '');
  }
  const whenLabel = d => d == null ? 'بدون تاریخ' : d === T ? 'امروز' : d === T + 1 ? 'فردا'
    : d === T - 1 ? 'دیروز' : dname(d);
  const hm = m => fa(Math.floor(m / 60)) + ':' + fa(pad(m % 60));
  function stampOf(day, time) {
    const [y, m, d] = d2j(day);
    return fa('@' + y + '/' + pad(m) + '/' + pad(d)
      + (time != null ? ' ' + pad(Math.floor(time / 60)) + ':' + pad(time % 60) : ''));
  }
  function ago(ms) {
    if (!ms) return '';
    const minutes = Math.floor((Date.now() - ms) / 60000);
    if (minutes < 1) return 'همین حالا';
    if (minutes < 60) return fa(minutes) + ' دقیقه پیش';
    const days = T - dayOfTime(ms);
    if (days <= 0) return fa(Math.floor(minutes / 60)) + ' ساعت پیش';
    if (days === 1) return 'دیروز';
    if (days < 7) return fa(days) + ' روز پیش';
    if (days < 14) return 'هفته‌ی پیش';
    if (days < 30) return fa(Math.floor(days / 7)) + ' هفته پیش';
    return dname(dayOfTime(ms));
  }

  // ------------------------------------------------------------------ DOM
  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    if (props) {
      for (const key in props) {
        const value = props[key];
        if (value == null || value === false) continue;
        if (key === 'class') el.className = value;
        else if (key.startsWith('on')) el.addEventListener(key.slice(2), value);
        else if (key === 'style') Object.assign(el.style, value);
        else if (key in el) el[key] = value;
        else el.setAttribute(key, value);
      }
    }
    for (const kid of kids.flat(9)) {
      if (kid == null || kid === false) continue;
      el.append(kid instanceof Node ? kid : String(kid));
    }
    if (tag === 'button' && !el.getAttribute('type')) el.type = 'button';
    return el;
  }
  const holder = document.createElement('div');
  function svg(size, body, stroke = 1.6, fill = false) {
    holder.innerHTML = '<svg width="' + size + '" height="' + size + '" viewBox="0 0 16 16" '
      + (fill ? 'fill="currentColor"' : 'fill="none" stroke="currentColor" stroke-width="' + stroke
        + '" stroke-linecap="round" stroke-linejoin="round"') + ' aria-hidden="true">' + body + '</svg>';
    return holder.firstChild;
  }
  const ICON = {
    tick: s => svg(s, '<polyline points="3,8.5 6.5,12 13,4.5"></polyline>', 2.4),
    chevron: s => svg(s, '<path d="M10 4 6 8l4 4"></path>', 1.6),
    back: () => svg(20, '<path d="M6 4l4 4-4 4"></path>', 1.6),
    plus: (s, w) => svg(s, '<path d="M8 3v10M3 8h10"></path>', w),
    sort: () => svg(14, '<path d="M4.5 2.5v11M2 11l2.5 2.5L7 11M9 4h5M9 8h4M9 12h3"></path>', 1.6),
    search: () => svg(17, '<circle cx="7" cy="7" r="4.5"></circle><line x1="10.5" y1="10.5" x2="14" y2="14"></line>', 1.5),
    dots: () => svg(18, '<circle cx="8" cy="3.5" r="1.3"></circle><circle cx="8" cy="8" r="1.3"></circle><circle cx="8" cy="12.5" r="1.3"></circle>', 0, true),
    calendar: () => svg(13, '<rect x="2" y="3" width="12" height="11" rx="2.2"></rect><path d="M2 6.5h12"></path>', 1.6),
    clock: () => svg(13, '<circle cx="8" cy="8" r="6"></circle><path d="M8 4.8V8l2.2 1.4"></path>', 1.6),
    pen: () => svg(18, '<path d="M11.5 2.5l2 2L6 12l-3 1 1-3z"></path>', 1.4),
    pin: () => svg(18, '<path d="M10 1.8 14.2 6l-1.8.7-2.6 2.6.2 2.9-1.1 1.1-5.2-5.2 1.1-1.1 2.9.2 2.6-2.6z"></path><path d="M5.3 10.7 1.8 14.2"></path>', 1.4),
    bell: () => svg(18, '<path d="M4 6.5a4 4 0 0 1 8 0c0 3 1.5 4 1.5 4h-11S4 9.5 4 6.5z"></path><path d="M6.8 13a1.4 1.4 0 0 0 2.4 0"></path>', 1.4),
  };

  // ---------------------------------------------------------------- data
  const TASKS_FILE = 'tasks.md';
  const INBOX = 'Inbox';
  const FOLDER_LABELS = {
    projects: 'پروژه‌ها', ideas: 'ایده‌ها', inbox: 'ورودی‌ها', me: 'من', private: 'خصوصی',
    archive: 'بایگانی', daily: 'روزانه', sites: 'سایت‌ها', personal: 'شخصی',
  };
  const ROOT_LABEL = 'عمومی';
  let notes = [];
  let conflicts = [];
  let desktop = null;
  let pins = new Set();
  let loaded = false;
  let loadError = '';

  const live = () => notes.filter(n => !n.deleted);
  const fileOf = path => path.split('/').pop();
  const stemOf = path => fileOf(path).replace(/\.(md|txt|markdown)$/i, '');
  const folderOf = path => path.includes('/') ? path.split('/')[0] : '';
  const folderLabel = key => key ? FOLDER_LABELS[key.toLowerCase()] || key : ROOT_LABEL;
  const srcOf = note => note.path === TASKS_FILE ? TASKS_FILE : stemOf(note.path);
  const isLive = note => note && !note.deleted && notes.includes(note);
  // A reload swaps every note object; anything held across one looks it up again.
  const fresh = note => notes.find(n => n.id === note.id) || note;
  function folders() {
    const keys = new Set(live().map(n => folderOf(n.path)));
    const order = Object.keys(FOLDER_LABELS);
    const rank = k => { const i = order.indexOf(k.toLowerCase()); return k === '' ? 99 : i < 0 ? 50 : i; };
    return [...keys].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
  }

  const TASK_RE = /^(\s*)- \[([ xX])\]\s+(.+)$/;
  const STAMP_RE = /\s*@(\d{3,4})[/-](\d{1,2})[/-](\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?(\s*↻)?\s*$/;
  function allTasks() {
    const found = [];
    for (const note of live()) {
      note.text.split('\n').forEach((whole, index) => {
        const line = whole.replace(/\r$/, '');
        const m = TASK_RE.exec(line);
        if (!m) return;
        const body = m[3];
        const s = STAMP_RE.exec(ascii(body));
        let stampDay = null, time = null;
        if (s) {
          const y = +s[1], mo = +s[2], d = +s[3];
          stampDay = y >= 1600 ? g2d(y, mo, d) : j2d(y, mo, d);
          if (s[4] != null) time = +s[4] * 60 + +s[5];
        }
        const done = m[2] !== ' ';
        const repeats = Boolean(s && s[6]);
        let day = stampDay;
        // A weekly task is due on its next occurrence, as on the desktop.
        if (repeats && !done && day != null && day < T) day += Math.ceil((T - day) / 7) * 7;
        found.push({
          id: note.id + ':' + index, note, line: index, indent: m[1], raw: line,
          text: (s ? body.slice(0, s.index) : body).trim(), done, day, time, repeats,
          src: srcOf(note),
        });
      });
    }
    return found;
  }
  function lineFor(task, change = {}) {
    const t = Object.assign({}, task, change);
    let line = t.indent + '- [' + (t.done ? 'x' : ' ') + '] ' + t.text;
    if (t.day != null) line += ' ' + stampOf(t.day, t.time) + (t.repeats ? ' ↻' : '');
    return line;
  }
  const plain = s => s.replace(/^#+\s*/, '').replace(/^\s*- \[[ xX]\]\s*/, '').replace(/^\s*[*-]\s+/, '')
    .replace(/\[\[|\]\]/g, '').replace(/@[۰-۹0-9/-]+(\s[۰-۹0-9:]+)?(\s*↻)?/g, '').replace(/\*\*/g, '').trim();

  // ----------------------------------------------------------------- API
  async function api(path, method = 'GET', body) {
    let response;
    try {
      response = await fetch('/api' + path, {
        method,
        headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': (tg && tg.initData) || '' },
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw Error('ارتباط برقرار نیست. دوباره امتحان کن.');
    }
    let data = {};
    try { data = await response.json(); } catch { /* an empty body */ }
    if (!response.ok) {
      const error = Error(response.status === 401 ? 'در بات /start بزن و دفترچه را از همان‌جا باز کن.'
        : response.status === 409 ? (data.error === 'path_exists' ? 'فایلی با این نام هست.'
          : 'این مورد جای دیگری هم تغییر کرده؛ نسخه‌ی تازه آمد.')
          : response.status === 413 ? 'ظرفیت آزمایشی دفترچه یا اندازهٔ متن بیش از حد است. تغییر ذخیره نشد.'
          : response.status === 429 ? 'درخواست زیاد است. کمی بعد دوباره امتحان کن.'
          : 'خطا در ارتباط با سرویس');
      error.status = response.status;
      error.code = data.error;
      throw error;
    }
    return data;
  }

  let writing = 0;
  let reloadAfterWrites = false;
  async function load() {
    if (writing) { reloadAfterWrites = true; return; }
    try {
      const [list, open] = await Promise.all([api('/notes'), api('/conflicts').catch(() => ({ conflicts: [] }))]);
      if (writing) { reloadAfterWrites = true; return; }
      notes = list.notes;
      conflicts = open.conflicts || [];
      loaded = true;
      loadError = '';
    } catch (error) {
      if (!loaded) loadError = error.message;
      else flash(error.message);
    }
    loadDesktop();
    render();
  }
  async function loadDesktop() {
    try { desktop = (await api('/sync-status')).status; } catch { desktop = undefined; }
    renderChrome();
    if (S.sheet === 'sync') renderSheet();
  }
  function remember(note) {
    const i = notes.findIndex(n => n.id === note.id);
    if (i >= 0) notes[i] = Object.assign(notes[i], note);
    else notes.push(note);
    return notes[i >= 0 ? i : notes.length - 1];
  }

  // A note's text changes here first; the server catches up in order. A
  // second change made while the first is on its way is sent after it.
  function write(note, text) {
    note.text = text;
    note.updated_at = Date.now();
    render();
    if (note.busy) { note.again = true; return note.busy; }
    writing++;
    note.busy = (async () => {
      try {
        do {
          note.again = false;
          const sent = note.text;
          const result = await api('/notes/' + note.id, 'PUT', { version: note.version, text: sent });
          note.version = result.note.version;
          note.updated_at = result.note.updated_at;
          if (note.text !== sent) note.again = true;
        } while (note.again);
      } catch (error) {
        flash(error.message);
        reloadAfterWrites = true;
      } finally {
        note.busy = null;
        writing--;
        if (!writing && reloadAfterWrites) { reloadAfterWrites = false; load(); }
      }
    })();
    return note.busy;
  }
  async function create(path, text) {
    writing++;
    try {
      const dot = path.lastIndexOf('.');
      for (let n = 1; n < 30; n++) {
        const candidate = n === 1 ? path : path.slice(0, dot) + ' (' + n + ')' + path.slice(dot);
        const taken = live().some(note => note.path.toLowerCase() === candidate.toLowerCase());
        if (taken) continue;
        try { return remember((await api('/notes', 'POST', { path: candidate, text })).note); }
        catch (error) { if (error.code !== 'path_exists') throw error; }
      }
      throw Error('فایلی با این نام هست.');
    } finally {
      writing--;
      if (!writing && reloadAfterWrites) { reloadAfterWrites = false; load(); }
    }
  }
  async function remove(note) {
    if (note.busy) await note.busy;
    writing++;
    try {
      const result = await api('/notes/' + note.id, 'DELETE', { version: note.version });
      remember(result.note);
    } finally {
      writing--;
      if (!writing && reloadAfterWrites) { reloadAfterWrites = false; load(); }
    }
  }
  const safeName = text => text.replace(/[\\/:*?"<>|\u0000-\u001f]/g, '-').replace(/\s+/g, ' ')
    .trim().replace(/^\.+/, '').slice(0, 40).trim() || 'یادداشت';

  // Changes to a task are changes to one line of its file.
  function editLines(task, change) {
    const note = fresh(task.note);
    const lines = note.text.split('\n');
    const current = (lines[task.line] || '').replace(/\r$/, '');
    if (current !== task.raw) { flash('این کار جای دیگری تغییر کرده؛ دوباره نگاه کن.'); load(); return false; }
    const cr = /\r$/.test(lines[task.line]) ? '\r' : '';
    const next = change(current);
    if (next === null) lines.splice(task.line, 1);
    else lines[task.line] = next + cr;
    write(note, lines.join('\n'));
    return true;
  }
  const setTask = (task, change) => editLines(task, () => lineFor(task, change));
  function toggle(task) {
    const done = !task.done;
    if (!editLines(task, line => line.replace(/\[([ xX])\]/, done ? '[x]' : '[ ]'))) return;
    if (done) flash('«' + task.text + '» انجام شد', () => {
      const again = findTask(fresh(task.note), task.line);
      if (again) editLines(again, line => line.replace(/\[([ xX])\]/, '[ ]'));
    });
  }
  function findTask(note, line) {
    return allTasks().find(t => t.note.id === note.id && t.line === line) || null;
  }
  async function appendTask(text, day, time) {
    const line = lineFor({ indent: '', done: false, text, day, time, repeats: false });
    const note = live().find(n => n.path === TASKS_FILE);
    if (note) {
      const body = note.text.replace(/\s+$/, '');
      const newline = note.text.includes('\r\n') ? '\r\n' : '\n';
      write(note, (body ? body + newline + line : line) + newline);
    } else {
      await create(TASKS_FILE, line + '\n');
      render();
    }
  }

  // Pins follow the owner across devices through Telegram's cloud storage.
  const cloud = tg && tg.CloudStorage && tg.isVersionAtLeast && tg.isVersionAtLeast('6.9');
  function loadPins() {
    const apply = value => {
      try { pins = new Set(JSON.parse(value || '[]')); } catch { pins = new Set(); }
      render();
    };
    let local = null;
    try { local = localStorage.getItem('np-pins'); } catch { /* private mode */ }
    if (cloud) tg.CloudStorage.getItem('pins', (error, value) => apply(error || !value ? local : value));
    else apply(local);
  }
  function savePins() {
    const value = JSON.stringify([...pins]);
    try { localStorage.setItem('np-pins', value); } catch { /* private mode */ }
    if (cloud) tg.CloudStorage.setItem('pins', value);
  }
  function prefs(key, fallback) {
    try { return localStorage.getItem('np-' + key) || fallback; } catch { return fallback; }
  }
  function setPref(key, value) {
    try { localStorage.setItem('np-' + key, value); } catch { /* private mode */ }
  }

  // --------------------------------------------------------------- state
  const S = {
    tab: 'today', editor: null, sheet: null,
    nFolder: 'all', nQuery: '', sort: prefs('sort', 'recent'), tFilter: 'all',
    calMode: prefs('cal', 'month'), selDay: T,
    cap: '', capDest: 'task', capDay: null, capTime: null,
    selTask: null, selNote: null, conflictId: null, pick: 'current',
  };
  function set(change) { Object.assign(S, change); render(); }
  function go(tab) {
    S.tab = tab; S.editor = null; S.sheet = null;
    $('scroll').scrollTop = 0;
    render();
  }

  let toastTimer = null, undoAction = null;
  function flash(message, undo) {
    clearTimeout(toastTimer);
    undoAction = undo || null;
    $('toastText').textContent = message;
    $('toastUndo').classList.toggle('hidden', !undo);
    $('toast').classList.remove('hidden');
    toastTimer = setTimeout(() => { $('toast').classList.add('hidden'); undoAction = null; }, 3200);
  }
  $('toastUndo').onclick = () => {
    const action = undoAction;
    clearTimeout(toastTimer);
    $('toast').classList.add('hidden');
    undoAction = null;
    if (action) action();
  };

  // ------------------------------------------------------------- pieces
  function checkbox(task, big) {
    const cls = (big ? 'task-check' : 'check') + (task.done ? ' done' : task.late ? ' late' : '');
    return h('button', {
      class: cls,
      'aria-label': task.done ? 'باز کردن دوباره' : 'انجام شد',
      onclick: event => { event.stopPropagation(); toggle(task); },
    }, h('i', null, task.done ? ICON.tick(big ? 14 : 13) : null));
  }
  function describe(t) {
    t.late = !t.done && t.day != null && t.day < T;
    t.isToday = t.day === T;
    return t;
  }
  function metaOf(t) {
    return [t.time != null && t.day !== T ? hm(t.time) : '', t.repeats ? '↻ هر هفته' : '', t.src]
      .filter(Boolean).join(' · ');
  }
  const openTask = t => () => set({ sheet: 'task', selTask: t.id });
  function rowText(t) {
    return h('span', { class: 'row-text' + (t.done ? ' done' : t.late ? ' late' : '') }, t.text);
  }
  function plainRow(t) {
    return h('div', { class: 'list-row', onclick: openTask(t) }, checkbox(t),
      h('div', { class: 'row-body' }, rowText(t), h('span', { class: 'row-meta' }, metaOf(t))));
  }
  function badgedRow(t) {
    const when = whenLabel(t.day) + (t.time != null ? ' · ' + hm(t.time) : '') + (t.repeats ? ' ↻' : '');
    return h('div', { class: 'list-row', onclick: openTask(t) }, checkbox(t),
      h('div', { class: 'row-body badged' }, rowText(t),
        h('div', { class: 'row-tags' },
          t.day != null || t.time != null
            ? h('span', { class: 'badge' + (t.late ? ' late' : t.isToday ? ' today' : '') }, when) : null,
          h('span', { class: 'row-src' }, t.src))));
  }
  const chip = (label, on, onclick, extra = '') =>
    h('button', { class: 'chip ' + extra + (on ? ' on' : ''), onclick }, label);
  function head(sub, title, ...tools) {
    return h('div', { class: 'head' },
      h('div', { class: 'head-text' }, h('span', { class: 'head-sub' }, sub),
        h('span', { class: 'head-title' }, title)), tools);
  }

  // ---------------------------------------------------------------- Today
  function viewToday(tasks) {
    const late = tasks.filter(t => t.late);
    const todayT = tasks.filter(t => t.day === T);
    const timed = todayT.filter(t => t.time != null).sort((a, b) => a.time - b.time);
    const loose = todayT.filter(t => t.time == null).sort((a, b) => a.done - b.done);
    const next = timed.find(t => !t.done && t.time >= NOW);
    const tomorrow = tasks.filter(t => t.day === T + 1 && !t.done)
      .sort((a, b) => (a.time == null ? 9999 : a.time) - (b.time == null ? 9999 : b.time));
    const doneCount = todayT.filter(t => t.done).length;
    const [jy, jm, jd] = d2j(T);

    const fill = h('div', { class: 'progress-fill' });
    fill.style.width = (todayT.length ? Math.round(doneCount / todayT.length * 100) : 0) + '%';
    const page = h('div', { class: 'page today' },
      h('div', { class: 'head today' },
        h('div', { class: 'head-text' },
          h('span', { class: 'head-sub' }, wdOf(T) + '، ' + fa(jd) + ' ' + MONTHS[jm - 1] + ' ' + fa(jy)),
          h('span', { class: 'head-title' }, 'امروز')),
        h('div', { class: 'progress' },
          h('span', null, fa(doneCount) + ' از ' + fa(todayT.length) + ' انجام شده'),
          h('div', { class: 'progress-track' }, fill))));

    if (late.length) {
      page.append(h('div', { class: 'review' },
        h('div', { class: 'review-head' },
          h('span', { class: 'review-title' }, 'از روزهای قبل مانده · ' + fa(late.length)),
          h('button', { class: 'review-all', onclick: () => moveAll(late, T) }, 'همه برای امروز')),
        late.map(t => h('div', { class: 'review-row' },
          h('div', { class: 'review-line' }, h('span', { class: 'review-text' }, t.text),
            h('span', { class: 'review-when' }, whenLabel(t.day))),
          h('div', { class: 'review-actions' },
            h('button', { onclick: () => { if (setTask(t, { day: T })) flash('به امروز آمد'); } }, 'امروز'),
            h('button', { onclick: () => { if (setTask(t, { day: T + 1 })) flash('برای فردا ماند'); } }, 'فردا'),
            h('button', { onclick: () => toggle(t) }, 'انجام شد'))))));
    }

    if (next) {
      const minutes = next.time - NOW;
      page.append(h('div', { class: 'next', onclick: openTask(next) },
        h('div', { class: 'next-time' }, hm(next.time)),
        h('div', { class: 'next-body' },
          h('span', { class: 'next-eta' }, 'بعدی · ' + (minutes < 60 ? fa(minutes) + ' دقیقه دیگر'
            : 'حدود ' + fa(Math.round(minutes / 60)) + ' ساعت دیگر')),
          h('span', { class: 'next-text' }, next.text),
          h('span', { class: 'next-src' }, next.src))));
    }

    page.append(h('div', { class: 'section' },
      h('div', { class: 'section-head' }, h('b', null, 'برنامه‌ی ساعت‌دار'), h('span', null, fa(timed.length))),
      timed.map(t => h('div', { class: 'timed' },
        h('span', { class: 'timed-at' + (t.done || t.time < NOW ? ' past' : '') }, hm(t.time)),
        h('div', { class: 'card-row', onclick: openTask(t) }, checkbox(t),
          h('div', { class: 'row-body' }, rowText(t), h('span', { class: 'row-meta' }, metaOf(t))))))));

    page.append(h('div', { class: 'section' },
      h('div', { class: 'section-head' }, h('b', null, 'هر وقت شد'), h('span', null, fa(loose.length))),
      h('div', { class: 'box-list' }, loose.map(plainRow),
        loose.length ? null : h('div', { class: 'list-empty' }, 'کار بی‌ساعتی برای امروز نیست'))));

    if (tomorrow.length) {
      page.append(h('div', { class: 'tomorrow', onclick: () => { S.tab = 'cal'; S.selDay = T + 1; $('scroll').scrollTop = 0; render(); } },
        h('b', null, 'فردا'),
        h('span', null, tomorrow.map(t => (t.time != null ? hm(t.time) + ' ' : '') + t.text).join('، ')),
        ICON.chevron(14)));
    }
    return page;
  }
  function moveAll(list, day) {
    const byNote = new Map();
    for (const t of list) {
      if (!byNote.has(t.note)) byNote.set(t.note, []);
      byNote.get(t.note).push(t);
    }
    for (const [held, items] of byNote) {
      const note = fresh(held);
      const lines = note.text.split('\n');
      for (const t of items) {
        if ((lines[t.line] || '').replace(/\r$/, '') !== t.raw) continue;
        const cr = /\r$/.test(lines[t.line]) ? '\r' : '';
        lines[t.line] = lineFor(t, { day }) + cr;
      }
      write(note, lines.join('\n'));
    }
    flash('همه به امروز آمدند');
  }

  // ---------------------------------------------------------------- Notes
  function noteCard(note) {
    const title = stemOf(note.path);
    const open = (note.text.match(/^\s*- \[ \]/gm) || []).length;
    const preview = note.text.split('\n').map(plain).filter(Boolean).filter(l => l !== title)[0] || 'خالی';
    return h('div', { class: 'note' },
      h('div', { class: 'note-main', onclick: () => openNote(note) },
        h('span', { class: 'note-title' }, title),
        h('span', { class: 'note-preview' }, preview),
        h('div', { class: 'note-meta' },
          h('span', { class: 'note-folder' }, folderLabel(folderOf(note.path))),
          h('span', null, ago(note.updated_at)),
          open ? h('span', { class: 'note-open' }, fa(open) + ' کار باز') : null)),
      h('button', { class: 'note-menu', title: 'گزینه‌ها', onclick: () => set({ sheet: 'note', selNote: note.id }) },
        ICON.dots()));
  }
  function noteSections() {
    const q = S.nQuery.trim().toLowerCase();
    let list = live().filter(n => (S.nFolder === 'all' || folderOf(n.path) === S.nFolder)
      && (!q || n.path.toLowerCase().includes(q) || n.text.toLowerCase().includes(q)));
    list = list.sort(S.sort === 'name'
      ? (a, b) => stemOf(a.path).localeCompare(stemOf(b.path), 'fa')
      : (a, b) => (b.updated_at || 0) - (a.updated_at || 0) || a.path.localeCompare(b.path));
    const pinned = list.filter(n => pins.has(n.path)), rest = list.filter(n => !pins.has(n.path));
    const box = h('div', { class: 'col' });
    if (pinned.length) box.append(h('div', { class: 'note-group' },
      h('span', { class: 'note-group-label' }, 'سنجاق‌شده'), pinned.map(noteCard)));
    if (rest.length) box.append(h('div', { class: 'note-group' },
      h('span', { class: 'note-group-label' },
        pinned.length ? 'بقیه' : S.sort === 'name' ? 'به ترتیب نام' : 'آخرین تغییرها'),
      rest.map(noteCard)));
    if (!list.length) box.append(h('div', { class: 'empty' }, 'یادداشتی پیدا نشد'));
    return box;
  }
  function viewNotes() {
    const all = live();
    const input = h('input', {
      value: S.nQuery, placeholder: 'جست‌وجو در عنوان و متن…', id: 'noteSearch', enterKeyHint: 'search',
      oninput: event => { S.nQuery = event.target.value; $('noteSections').replaceChildren(noteSections()); },
    });
    const sections = h('div', { id: 'noteSections' }, noteSections());
    return h('div', { class: 'page' },
      head(fa(all.length) + ' یادداشت', 'یادداشت‌ها',
        h('button', { class: 'tool-btn', onclick: () => { S.sort = S.sort === 'name' ? 'recent' : 'name'; setPref('sort', S.sort); render(); } },
          ICON.sort(), S.sort === 'name' ? 'نام' : 'تازه‌ترین'),
        h('button', { class: 'new-btn', title: 'یادداشت جدید', onclick: newNote }, ICON.plus(16, 1.9))),
      h('div', { class: 'search' }, ICON.search(), input),
      h('div', { class: 'chips' },
        [['all', 'همه']].concat(folders().map(k => [k, folderLabel(k)])).map(([key, name]) =>
          h('button', { class: 'chip' + (S.nFolder === key ? ' on' : ''), onclick: () => set({ nFolder: key }) },
            name, h('small', null, fa(key === 'all' ? all.length : all.filter(n => folderOf(n.path) === key).length))))),
      sections);
  }

  // ---------------------------------------------------------------- Tasks
  const FILTERS = {
    all: () => true,
    today: t => t.day === T || t.late,
    late: t => t.late,
    week: t => t.day != null && t.day >= T && t.day <= T + 6,
    later: t => t.day != null && t.day > T + 6,
    none: t => t.day == null,
    done: t => t.done,
  };
  const CHIPS = [['all', 'همه'], ['today', 'امروز'], ['late', 'عقب‌افتاده'], ['week', 'این هفته'],
    ['later', 'بعداً'], ['none', 'بدون تاریخ'], ['done', 'انجام‌شده']];
  const byTime = (a, b) => a.done - b.done || (a.day == null ? 1e9 : a.day) - (b.day == null ? 1e9 : b.day)
    || (a.time == null ? 9999 : a.time) - (b.time == null ? 9999 : b.time);
  function viewTasks(tasks) {
    const late = tasks.filter(t => t.late);
    const pool = key => key === 'done' ? tasks : tasks.filter(t => key === 'all' || key === 'today' || !t.done);
    const filtered = pool(S.tFilter).filter(FILTERS[S.tFilter]);
    let groups;
    if (S.tFilter === 'all') {
      groups = [
        ['عقب‌افتاده', FILTERS.late, 'late'], ['امروز', t => t.day === T, ''], ['فردا', t => t.day === T + 1, ''],
        ['این هفته', t => t.day != null && t.day > T + 1 && t.day <= T + 6 && !t.done, ''],
        ['بعداً', t => t.day != null && t.day > T + 6 && !t.done, ''], ['بدون تاریخ', t => t.day == null && !t.done, 'dim'],
      ].map(([label, f, tone]) => ({ label, tone, items: filtered.filter(f).sort(byTime) })).filter(g => g.items.length);
    } else {
      const items = filtered.sort(byTime);
      groups = items.length ? [{ label: Object.fromEntries(CHIPS)[S.tFilter], tone: '', items }] : [];
    }
    return h('div', { class: 'page' },
      h('div', { class: 'head-text' },
        h('span', { class: 'head-sub' }, fa(tasks.filter(t => !t.done).length) + ' کار باز'
          + (late.length ? ' · ' + fa(late.length) + ' عقب‌افتاده' : '')),
        h('span', { class: 'head-title' }, 'کارها')),
      h('div', { class: 'chips' }, CHIPS.map(([key, name]) =>
        h('button', { class: 'chip' + (S.tFilter === key ? ' on' : ''), onclick: () => set({ tFilter: key }) },
          name, h('small', null, fa(pool(key).filter(FILTERS[key]).length))))),
      groups.map(g => h('div', { class: 'section' },
        h('div', { class: 'group-head' }, h('b', { class: g.tone }, g.label), h('span', null, fa(g.items.length))),
        h('div', { class: 'box-list' }, g.items.map(badgedRow)))),
      groups.length ? null : h('div', { class: 'empty' }, 'این‌جا کاری نیست'));
  }

  // ------------------------------------------------------------- Calendar
  function viewCal(tasks) {
    const sel = S.selDay;
    const [jy, jm] = d2j(sel);
    const dayTasks = d => tasks.filter(t => t.day === d);
    const seg = h('div', { class: 'seg' },
      h('button', { class: S.calMode === 'month' ? 'on' : '', onclick: () => { setPref('cal', 'month'); set({ calMode: 'month' }); } }, 'ماه'),
      h('button', { class: S.calMode === 'week' ? 'on' : '', onclick: () => { setPref('cal', 'week'); set({ calMode: 'week' }); } }, 'هفته'));
    const page = h('div', { class: 'page' },
      head(fa(jy), MONTHS[jm - 1], seg,
        sel !== T ? h('button', { class: 'today-btn', onclick: () => set({ selDay: T }) }, 'امروز') : null));

    let surface;
    if (S.calMode === 'month') {
      const first = monthStart(jy, jm), len = monthLength(jy, jm), offset = weekIndex(first);
      const cells = Math.ceil((offset + len) / 7) * 7;
      const grid = h('div', { class: 'month-grid' }, WDS.map(w => h('span', { class: 'month-wd' }, w)));
      for (let i = 0; i < cells; i++) {
        const d = first + i - offset, inMonth = i >= offset && i < offset + len;
        const open = inMonth ? dayTasks(d).filter(t => !t.done) : [];
        const cls = 'mday' + (!inMonth ? ' out' : '') + (i % 7 === 6 ? ' fri' : '')
          + (d === T ? ' now' : '') + (d === sel ? ' sel' : '');
        grid.append(h('button', { class: cls, onclick: () => inMonth && set({ selDay: d }) },
          h('b', null, inMonth ? fa(d2j(d)[2]) : ''),
          h('span', { class: 'dots' }, open.slice(0, 3).map(t => h('i', { class: t.day < T ? 'late' : '' })))));
      }
      surface = h('div', { class: 'month' }, grid);
      swipe(surface, dir => {
        const [ny, nm] = dir > 0 ? nextMonth(jy, jm) : prevMonth(jy, jm);
        const start = monthStart(ny, nm);
        set({ selDay: T >= start && T < start + monthLength(ny, nm) ? T : start });
      });
    } else {
      const wstart = sel - weekIndex(sel);
      surface = h('div', { class: 'week' }, WDS.map((w, k) => {
        const d = wstart + k, n = dayTasks(d).filter(t => !t.done).length;
        const cls = 'wday' + (k === 6 ? ' fri' : '') + (d === T ? ' now' : '') + (d === sel ? ' sel' : '');
        return h('button', { class: cls, onclick: () => set({ selDay: d }) },
          h('small', null, w), h('b', null, fa(d2j(d)[2])), h('span', null, n ? fa(n) + ' کار' : '—'));
      }));
      swipe(surface, dir => set({ selDay: sel + dir * 7 }));
    }
    page.append(surface);

    const selT = dayTasks(sel);
    page.append(h('div', { class: 'agenda' },
      h('div', { class: 'agenda-text' },
        h('b', null, (sel === T ? 'امروز، ' : sel === T + 1 ? 'فردا، ' : wdOf(sel) + '، ') + dname(sel)),
        h('span', null, selT.length ? fa(selT.filter(t => !t.done).length) + ' کار باز · '
          + fa(selT.filter(t => t.time != null).length) + ' ساعت‌دار' : 'کاری ثبت نشده')),
      h('button', { class: 'tool-btn', onclick: () => openCapture(sel, null) }, ICON.plus(13, 1.9), 'کار برای این روز')));

    const allDay = selT.filter(t => t.time == null).sort((a, b) => a.done - b.done);
    if (allDay.length) {
      page.append(h('div', { class: 'allday' },
        h('span', { class: 'allday-label' }, 'بدون ساعت'),
        h('div', { class: 'col g6' }, allDay.map(t =>
          h('div', { class: 'allday-row' + (t.done ? ' done' : t.late ? ' late' : ''), onclick: openTask(t) },
            h('i'), h('span', null, t.text), t.repeats ? h('em', null, '↻') : null)))));
    }

    const hours = h('div', { class: 'hours' });
    for (let hour = 8; hour <= 21; hour++) {
      const items = selT.filter(t => t.time != null && (Math.floor(t.time / 60) === hour
        || (hour === 8 && t.time < 480) || (hour === 21 && t.time >= 1320))).sort((a, b) => a.time - b.time);
      const isNow = sel === T && Math.floor(NOW / 60) === hour;
      const row = h('div', { class: 'hour' },
        h('span', { class: 'hour-label' + (isNow ? ' now' : '') }, fa(hour) + ':۰۰'),
        h('div', { class: 'hour-slot', onclick: () => openCapture(sel, hour * 60) },
          items.map(t => h('div', {
            class: 'slot-item' + (t.done ? ' done' : ''),
            onclick: event => { event.stopPropagation(); set({ sheet: 'task', selTask: t.id }); },
          }, h('b', null, hm(t.time)), h('span', null, t.text)))));
      if (isNow) {
        const line = h('div', { class: 'now-line' }, h('i'));
        line.style.top = Math.round((NOW % 60) / 60 * 100) + '%';
        row.append(line);
      }
      hours.append(row);
    }
    page.append(hours, h('span', { class: 'hint' }, 'روی هر ساعت خالی بزن تا کاری برای همان ساعت ثبت شود'));
    return page;
  }
  function swipe(el, move) {
    let x0 = null, y0 = null;
    el.addEventListener('touchstart', e => { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; }, { passive: true });
    el.addEventListener('touchend', e => {
      if (x0 == null) return;
      const dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
      x0 = null;
      // Right-to-left: what comes next is on the left, pulled in by a rightward swipe.
      if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) move(dx > 0 ? 1 : -1);
    }, { passive: true });
  }

  // --------------------------------------------------------------- Editor
  function openNote(note) {
    // A textarea only ever hands back \n; a Windows file keeps its \r\n on save.
    const text = note.text.replace(/\r\n/g, '\n');
    S.editor = { id: note.id, folder: folderOf(note.path), title: stemOf(note.path), base: text, draft: text,
      crlf: note.text.includes('\r\n') };
    S.sheet = null;
    $('scroll').scrollTop = 0;
    render();
  }
  function newNote() {
    const folder = S.nFolder === 'all' ? INBOX : S.nFolder;
    S.editor = { id: null, folder, title: 'یادداشت بی‌نام', base: '', draft: '' };
    S.sheet = null;
    $('scroll').scrollTop = 0;
    render();
    const title = document.querySelector('.ed-title');
    if (title) { title.focus(); title.select(); }
  }
  const edNote = () => S.editor && S.editor.id ? notes.find(n => n.id === S.editor.id) : null;
  const dirty = () => Boolean(S.editor) && (S.editor.id ? S.editor.draft !== S.editor.base : S.editor.draft.trim() !== '');
  async function saveNote() {
    const ed = S.editor;
    if (!ed || !dirty()) return true;
    try {
      if (ed.id) {
        const note = edNote();
        if (!isLive(note)) throw Error('این یادداشت دیگر نیست.');
        write(note, ed.crlf ? ed.draft.replace(/\n/g, '\r\n') : ed.draft);
      } else {
        const note = await create((ed.folder ? ed.folder + '/' : '') + safeName(ed.title) + '.md', ed.draft);
        ed.id = note.id;
        ed.title = stemOf(note.path);
      }
      ed.base = ed.draft;
      flash('ذخیره شد · روی رایانه هم به‌روز می‌شود');
      updateEditor();
      return true;
    } catch (error) {
      flash(error.message);
      return false;
    }
  }
  function leaveEditor() { S.editor = null; S.sheet = null; render(); }
  function edBack() { if (dirty()) set({ sheet: 'unsaved' }); else leaveEditor(); }
  function viewEditor() {
    const ed = S.editor;
    const note = edNote();
    const title = h('input', {
      class: 'ed-title', value: ed.title, readOnly: Boolean(ed.id), 'aria-label': 'عنوان',
      oninput: event => { ed.title = event.target.value; },
    });
    const area = h('textarea', {
      class: 'ed-text', id: 'edText', value: ed.draft, spellcheck: false, placeholder: 'بنویس…',
      oninput: event => { ed.draft = event.target.value; updateEditor(); },
    });
    return h('div', { class: 'editor', 'data-key': 'editor:' + (ed.id || 'new') },
      h('div', { class: 'ed-head' },
        h('button', { class: 'ed-back', title: 'برگشت', onclick: edBack }, ICON.back()),
        h('div', { class: 'ed-titles' }, title, h('span', { class: 'ed-state', id: 'edState' })),
        h('button', { class: 'ed-save', id: 'edSave', onclick: () => saveNote() }, 'ذخیره')),
      h('div', { class: 'ed-meta' }, h('b', null, folderLabel(ed.folder)), h('span', { id: 'edMeta' },
        [note ? ago(note.updated_at) : 'تازه', fa(ed.draft.split('\n').length) + ' خط'].filter(Boolean).join(' · '))),
      area);
  }
  function updateEditor() {
    const ed = S.editor;
    if (!ed) return;
    const isDirty = dirty();
    const state = $('edState'), save = $('edSave'), meta = $('edMeta');
    if (state) { state.textContent = isDirty ? 'ذخیره نشده' : 'ذخیره شد'; state.classList.toggle('dirty', isDirty); }
    if (save) save.classList.toggle('dirty', isDirty);
    const note = edNote();
    if (meta) meta.textContent = [note ? ago(note.updated_at) : 'تازه', fa(ed.draft.split('\n').length) + ' خط']
      .filter(Boolean).join(' · ');
  }
  function insert(snippet, back) {
    const area = $('edText');
    if (!area || !S.editor) return;
    const at = area.selectionStart == null ? area.value.length : area.selectionStart;
    const end = area.selectionEnd == null ? at : area.selectionEnd;
    area.value = area.value.slice(0, at) + snippet + area.value.slice(end);
    S.editor.draft = area.value;
    const caret = at + snippet.length - back;
    area.focus();
    area.setSelectionRange(caret, caret);
    updateEditor();
  }
  function renderEdbar() {
    const bar = $('edbar');
    const [y, m, d] = d2j(T);
    const tools = [['☐', 'کار', '\n- [ ] ', 0], ['@', 'تاریخ', ' @' + fa(y + '/' + pad(m) + '/' + pad(d)), 0],
      ['[[', 'پیوند', '[[]]', 2], ['#', 'عنوان', '\n## ', 0], ['B', 'پررنگ', '****', 2]];
    bar.replaceChildren(...tools.map(([glyph, title, snippet, back]) => h('button', {
      title,
      // Keep the textarea's caret: a tap on a button would otherwise blur it first.
      onmousedown: event => event.preventDefault(),
      onclick: () => insert(snippet, back),
    }, h('b', null, glyph), h('span', null, title))));
  }

  // --------------------------------------------------------------- Sheets
  function openCapture(day = null, time = null) {
    set({ sheet: 'capture', cap: '', capDest: 'task', capDay: day, capTime: time });
  }
  const WD_ALT = ['یکشنبه', 'دوشنبه', 'سه‌شنبه', 'سه شنبه', 'چهارشنبه', 'پنجشنبه', 'پنج‌شنبه', 'پنج شنبه', 'جمعه', 'شنبه'];
  function cut(raw, t, re) {
    const m = t.match(re);
    if (!m) return null;
    const s = m.index + m[1].length, e = s + m[2].length;
    return { m, raw: raw.slice(0, s) + raw.slice(e), t: t.slice(0, s) + t.slice(e) };
  }
  // «جلسه با حمید فردا ساعت ۱۱», «قبض اینترنت ۱۰ مهر»: the when, read out of the words.
  function parseWhen(input) {
    let raw = input, t = ascii(input), time = null, day = null, r;
    const B = '(^|\\s)', E = '(?=\\s|$)';
    if ((r = cut(raw, t, new RegExp(B + '(ساعت\\s*(\\d{1,2})(?::(\\d{2}))?)' + E)))
        || (r = cut(raw, t, new RegExp(B + '((\\d{1,2}):(\\d{2}))' + E)))) {
      let hour = parseInt(r.m[3], 10);
      const minute = parseInt(r.m[4] || '0', 10);
      if (hour < 7) hour += 12;
      if (hour <= 23 && minute < 60) { time = hour * 60 + minute; raw = r.raw; t = r.t; }
    }
    const [cy] = d2j(T);
    const rules = [
      ['(پس[‌ ]?فردا)', () => T + 2], ['(فردا)', () => T + 1], ['(امروز)', () => T],
      ['(هفته(?:‌ی|ی)?\\s*بعد)', () => T + 7],
      ['(\\d{1,2}\\s*(?:' + MONTHS.join('|') + '))', m => {
        const n = parseInt(m[2], 10), month = MONTHS.findIndex(name => m[2].endsWith(name)) + 1;
        if (n < 1 || n > monthLength(cy, month)) return null;
        const d = j2d(cy, month, n);
        return d < T ? j2d(cy + 1, month, Math.min(n, monthLength(cy + 1, month))) : d;
      }],
      ['(' + WD_ALT.join('|') + ')', m => {
        let name = m[2].replace(/ /g, '‌');
        if (name === 'پنج‌شنبه') name = 'پنجشنبه';
        return T + (((WD.indexOf(name) - weekIndex(T)) + 7) % 7 || 7);
      }],
    ];
    for (const [src, fn] of rules) {
      r = cut(raw, t, new RegExp(B + src + E));
      if (r) { const d = fn(r.m); if (d != null) { day = d; raw = r.raw; } break; }
    }
    if (day == null && time == null) return null;
    return { day, time, text: raw.replace(/\s+/g, ' ').trim() };
  }
  function captureNow() {
    const pv = S.cap.trim() ? parseWhen(S.cap) : null;
    return {
      pv,
      day: pv && pv.day != null ? pv.day : (S.capDay == null ? T : S.capDay),
      time: pv && pv.time != null ? pv.time : S.capTime,
    };
  }
  function captureParts() {
    const { pv, day, time } = captureNow();
    const box = h('div', { class: 'col g14', id: 'capParts' });
    if (S.capDest === 'task') {
      const defs = [['امروز', { day: T }], ['فردا', { day: T + 1 }], ['پس‌فردا', { day: T + 2 }],
        ['هفته‌ی بعد', { day: T + 7 }], ['بدون ساعت', { time: null }], ['۹:۰۰', { time: 540 }],
        ['۱۲:۰۰', { time: 720 }], ['۱۷:۰۰', { time: 1020 }], ['۲۰:۰۰', { time: 1200 }]];
      box.append(h('div', { class: 'col g10' },
        h('div', { class: 'pills' },
          h('span', { class: 'pill' }, ICON.calendar(), whenLabel(day)
            + (day !== T && day !== T + 1 ? '' : ' · ' + wdOf(day) + ' ' + dname(day))),
          time != null ? h('span', { class: 'pill' }, ICON.clock(), 'ساعت ' + hm(time)) : null,
          h('small', null, pv ? 'از متن تشخیص داده شد' : '')),
        h('div', { class: 'chips' }, defs.map(([label, v]) => {
          const on = 'day' in v ? day === v.day : time === v.time;
          return chip(label, on, () => {
            // Once a chip decides, the words that said when leave the text —
            // but what they said stays, unless this chip overrides it.
            if (pv) {
              S.capDay = day; S.capTime = time; S.cap = pv.text;
              const area = $('capText');
              if (area) area.value = S.cap;
            }
            if ('day' in v) S.capDay = v.day; else S.capTime = v.time;
            refreshCapture();
          }, 'sm');
        }))));
    } else {
      box.append(h('span', { class: 'cap-note' }, 'یک یادداشت تازه در پوشه‌ی «ورودی‌ها» ساخته می‌شود و روی رایانه هم می‌آید.'));
    }
    const ready = Boolean(S.cap.trim());
    box.append(h('button', { class: 'big-btn' + (ready ? ' go' : ''), onclick: saveCapture },
      S.capDest === 'task' ? 'افزودن کار' : 'ذخیره در ورودی‌ها'));
    return box;
  }
  function refreshCapture() {
    const parts = $('capParts');
    if (parts) parts.replaceWith(captureParts());
  }
  let capturing = false;
  async function saveCapture() {
    const raw = S.cap.trim();
    if (!raw || capturing) return;
    capturing = true;
    try {
      if (S.capDest === 'task') {
        const { pv, day, time } = captureNow();
        const text = pv ? pv.text || raw : raw;
        S.sheet = null;
        await appendTask(text, day, time);
        flash('به کارهای ' + whenLabel(day) + (time != null ? ' ساعت ' + hm(time) : '') + ' اضافه شد');
      } else {
        await create(INBOX + '/' + safeName(raw.split('\n')[0]) + '.md', raw + '\n');
        S.sheet = null;
        flash('در «ورودی‌ها» ذخیره شد');
      }
      S.cap = '';
      render();
    } catch (error) {
      flash(error.message);
    } finally {
      capturing = false;
    }
  }
  function sheetCapture() {
    const area = h('textarea', {
      class: 'cap-text', id: 'capText', value: S.cap,
      placeholder: S.capDest === 'task' ? 'مثلاً «جلسه با حمید فردا ساعت ۱۱»' : 'فکر، ایده یا هر چیزی که نباید یادت برود…',
      oninput: event => { S.cap = event.target.value; refreshCapture(); },
    });
    setTimeout(() => area.focus(), 60);
    const dest = (key, label) => h('button', {
      class: S.capDest === key ? 'on' : '',
      onclick: () => { S.capDest = key; renderSheet(true); },
    }, label);
    return h('div', { class: 'col' },
      h('div', { class: 'sheet-head' }, h('span', { class: 'sheet-title' }, 'ضبط سریع'),
        h('div', { class: 'seg soft' }, dest('task', 'کار'), dest('inbox', 'یادداشت'))),
      area, captureParts());
  }
  function sheetTask(tasks) {
    const tk = tasks.find(t => t.id === S.selTask);
    if (!tk) return null;
    const summary = tk.day == null ? 'بدون تاریخ'
      : wdOf(tk.day) + '، ' + dname(tk.day) + (tk.time != null ? ' · ساعت ' + hm(tk.time) : ' · بدون ساعت');
    const days = Array.from({ length: 7 }, (_, k) => {
      const d = T + k;
      return h('button', { class: 'd7' + (tk.day === d ? ' on' : ''), onclick: () => setTask(tk, { day: d }) },
        h('small', null, k === 0 ? 'امروز' : WDS[weekIndex(d)]), h('b', null, fa(d2j(d)[2])));
    });
    const times = [['بدون ساعت', null], ['۹:۰۰', 540], ['۱۰:۰۰', 600], ['۱۲:۰۰', 720], ['۱۴:۰۰', 840],
      ['۱۶:۰۰', 960], ['۱۸:۰۰', 1080], ['۲۰:۰۰', 1200]];
    const raw = lineFor(tk).trim();
    return h('div', { class: 'col g16' },
      h('div', { class: 'task-top' }, checkbox(tk, true),
        h('div', { class: 'col g2 flex1' },
          h('span', { class: 'task-name' + (tk.done ? ' done' : '') }, tk.text),
          h('span', { class: 'sheet-sub' }, summary))),
      h('div', { class: 'col g8' }, h('span', { class: 'label' }, 'روز'),
        h('div', { class: 'days7' }, days),
        h('div', { class: 'row-flat' },
          chip('هفته‌ی بعد', tk.day === T + 7, () => setTask(tk, { day: T + 7 }), 'sm wide'),
          chip('بدون تاریخ', tk.day == null, () => setTask(tk, { day: null, time: null, repeats: false }), 'sm wide'))),
      h('div', { class: 'col g8' }, h('span', { class: 'label' }, 'ساعت'),
        h('div', { class: 'row-wrap' }, times.map(([label, v]) =>
          chip(label, tk.time === v, () => setTask(tk, { time: v, day: tk.day == null && v != null ? T : tk.day }), 'sm')))),
      h('div', { class: 'switch-row' },
        h('div', { class: 'switch-text' }, h('span', null, 'تکرار هر هفته'),
          h('small', null, tk.repeats ? 'بعد از انجام، هفته‌ی بعد دوباره می‌آید' : 'فقط یک بار')),
        h('button', {
          class: 'switch' + (tk.repeats ? ' on' : ''), 'aria-label': 'تکرار هر هفته',
          onclick: () => setTask(tk, { repeats: !tk.repeats, day: tk.day == null ? T : tk.day }),
        }, h('i'))),
      h('div', { class: 'col g6' },
        h('span', { class: 'src-note' }, 'در فایل «' + fileOf(tk.note.path) + '» این‌طور ذخیره می‌شود'),
        h('div', { class: 'raw' }, raw)),
      h('div', { class: 'row-flat' },
        h('button', { class: 'btn-soft', onclick: () => openNote(tk.note) }, 'باز کردن یادداشت'),
        h('button', {
          class: 'btn-danger', onclick: () => {
            if (!editLines(tk, () => null)) return;
            S.sheet = null;
            render();
            flash('کار حذف شد', () => {
              const note = fresh(tk.note);
              const lines = note.text.split('\n');
              lines.splice(tk.line, 0, tk.raw);
              write(note, lines.join('\n'));
            });
          },
        }, 'حذف')));
  }
  function sheetNote() {
    const nt = live().find(n => n.id === S.selNote);
    if (!nt) return null;
    const here = folderOf(nt.path);
    const targets = [...new Set(folders().concat([INBOX]))].filter(k => k !== '');
    return h('div', { class: 'col' },
      h('div', { class: 'col g2' }, h('span', { class: 'sheet-title' }, stemOf(nt.path)),
        h('span', { class: 'sheet-sub' }, [folderLabel(here), ago(nt.updated_at)].filter(Boolean).join(' · '))),
      h('div', { class: 'menu' },
        h('button', { onclick: () => openNote(nt) }, ICON.pen(), 'ویرایش'),
        h('button', {
          onclick: () => {
            const had = pins.has(nt.path);
            if (had) pins.delete(nt.path); else pins.add(nt.path);
            savePins();
            set({ sheet: null });
            flash(had ? 'سنجاق برداشته شد' : 'سنجاق شد');
          },
        }, ICON.pin(), pins.has(nt.path) ? 'برداشتن سنجاق' : 'سنجاق کردن بالای فهرست')),
      h('div', { class: 'col g8' }, h('span', { class: 'label' }, 'انتقال به پوشه'),
        h('div', { class: 'row-wrap' }, targets.map(key =>
          chip(folderLabel(key), key === here, () => moveNote(nt, key), 'md')))),
      h('button', { class: 'btn-danger h48', onclick: () => trashNote(nt) }, 'انتقال به سطل بازیافت'));
  }
  // A file's path is its identity to the desktop sync, so a move is a copy
  // at the new path and the old one sent to the Recycle Bin.
  async function moveNote(held, folder) {
    const note = fresh(held);
    if (folderOf(note.path) === folder) return;
    set({ sheet: null });
    try {
      if (note.busy) await note.busy;
      const moved = await create(folder + '/' + fileOf(note.path), note.text);
      await remove(note);
      if (pins.delete(note.path)) { pins.add(moved.path); savePins(); }
      render();
      flash('به «' + folderLabel(folder) + '» منتقل شد');
    } catch (error) { flash(error.message); load(); }
  }
  async function trashNote(held) {
    const note = fresh(held);
    set({ sheet: null });
    try {
      await remove(note);
      render();
      flash('به سطل بازیافت رفت', async () => {
        try { await create(note.path, note.text); render(); } catch (error) { flash(error.message); }
      });
    } catch (error) { flash(error.message); load(); }
  }
  function syncSummary() {
    if (conflicts.length) return { tone: 'bad', title: conflicts.length === 1 ? 'یک مورد نیاز به تصمیم دارد' : fa(conflicts.length) + ' مورد نیاز به تصمیم دارند' };
    if (desktop === undefined) return { tone: 'idle', title: 'وضعیت رایانه در دسترس نیست' };
    if (!desktop) return { tone: 'idle', title: 'هنوز گزارشی از رایانه نیامده' };
    if (Date.now() - desktop.checked_at > 3 * 60 * 1000) return { tone: 'idle', title: 'رایانه فعلاً وصل نیست' };
    if (desktop.state === 'error') return { tone: 'bad', title: 'همگام‌سازی رایانه خطا دارد' };
    if (desktop.state === 'attention') return { tone: 'bad', title: desktop.conflicts ? fa(desktop.conflicts) + ' تعارض روی رایانه' : 'همگام‌سازی نیاز به بررسی دارد' };
    return { tone: '', title: 'همه‌چیز همگام است' };
  }
  function sheetSync() {
    const sum = syncSummary();
    const d = desktop || {};
    return h('div', { class: 'col' },
      h('span', { class: 'sheet-title' }, 'همگام‌سازی'),
      h('div', { class: 'sync-card' },
        h('div', { class: 'sync-line' }, h('span', { class: 'sync-dot ' + sum.tone }),
          h('div', null, h('b', null, sum.title), h('small', null, 'رایانه · بررسی هر دقیقه'))),
        h('div', { class: 'sync-grid' },
          h('div', null, h('small', null, 'آخرین بررسی'), h('span', null, d.checked_at ? ago(d.checked_at) : '—')),
          h('div', null, h('small', null, 'ارسال / دریافت'), h('span', null, fa(d.uploaded || 0) + ' / ' + fa(d.downloaded || 0))),
          h('div', null, h('small', null, 'ردشده'), h('span', null, fa(d.skipped || 0))))),
      conflicts.length ? h('div', { class: 'col g8' },
        h('span', { class: 'label danger' }, 'نیاز به تصمیم · ' + fa(conflicts.length)),
        conflicts.map(c => h('button', { class: 'conflict-row', onclick: () => set({ sheet: 'conflict', conflictId: c.id, pick: 'current' }) },
          h('div', null, h('b', null, stemOf(c.path)), h('small', null, 'هم روی رایانه و هم در تلگرام تغییر کرده')),
          ICON.chevron(16)))) : null,
      h('div', { class: 'info-row' }, ICON.bell(),
        h('span', null, 'پیام روزانه ساعت ۹ صبح در تلگرام، حتی وقتی رایانه خاموش است.')),
      h('button', {
        class: 'btn-primary solo', onclick: async () => {
          set({ sheet: null });
          await load();
          flash('تازه شد · آخرین نسخه‌ها آمد');
        },
      }, 'بررسی الان'));
  }
  function sheetConflict() {
    const c = conflicts.find(x => x.id === S.conflictId);
    if (!c) return null;
    const note = live().find(n => n.id === c.note_id);
    const mine = (note ? note.text : c.current_text).split('\n');
    const theirs = c.proposed_text.split('\n');
    const lines = (a, b) => {
      const shown = a.slice(0, 14).map((t, i) => h('span', { class: t !== b[i] ? 'diff' : '' }, t || ' '));
      if (a.length > 14) shown.push(h('span', null, '…'));
      return shown;
    };
    const version = (key, label, time, a, b) => h('button', {
      class: 'version' + (S.pick === key ? ' on' : ''), onclick: () => set({ pick: key }),
    }, h('div', { class: 'version-head' }, h('b', null, label), h('small', null, time)),
    h('div', { class: 'version-lines' }, lines(a, b)));
    const settle = async keep => {
      try {
        const result = await api('/conflicts/' + c.id, 'POST', { keep });
        set({ sheet: null });
        await load();
        flash(keep === 'both' && result.note ? 'نسخه‌ی تلگرام با نام «' + fa(stemOf(result.note.path)) + '» ذخیره شد' : 'تعارض حل شد');
      } catch (error) { flash(error.message); load(); }
    };
    return h('div', { class: 'col' },
      h('div', { class: 'col g2' }, h('span', { class: 'sheet-title' }, 'کدام نسخه بماند؟'),
        h('span', { class: 'sheet-sub' }, '«' + stemOf(c.path) + '» در هر دو جا تغییر کرده. خط‌های متفاوت رنگی‌اند.')),
      version('current', 'نسخه‌ی رایانه', note ? ago(note.updated_at) : '', mine, theirs),
      version('proposed', 'نسخه‌ی تلگرام', ago(c.created_at), theirs, mine),
      h('div', { class: 'row-flat' },
        h('button', { class: 'btn-primary', onclick: () => settle(S.pick) },
          S.pick === 'current' ? 'نگه داشتن نسخه‌ی رایانه' : 'نگه داشتن نسخه‌ی تلگرام'),
        h('button', { class: 'btn-soft h48', onclick: () => settle('both') }, 'هر دو را نگه دار')));
  }
  function sheetUnsaved() {
    return h('div', { class: 'col' },
      h('span', { class: 'sheet-title' }, 'تغییرات ذخیره نشده'),
      h('span', { class: 'body-text' }, 'اگر بدون ذخیره برگردی، چیزهایی که نوشتی از دست می‌روند.'),
      h('div', { class: 'row-flat' },
        h('button', { class: 'btn-primary', onclick: async () => { if (await saveNote()) leaveEditor(); } }, 'ذخیره و برگشت'),
        h('button', { class: 'btn-danger h48', onclick: leaveEditor }, 'دور بریز')));
  }
  let sheetKey = '';
  function renderSheet(force) {
    const backdrop = $('sheet'), body = $('sheetBody');
    if (!S.sheet) { backdrop.classList.add('hidden'); sheetKey = ''; return; }
    const key = S.sheet + ':' + (S.sheet === 'capture' ? S.capDest : '');
    // The capture sheet holds a half-typed text; it is rebuilt only when it opens.
    if (S.sheet === 'capture' && key === sheetKey && !force) return;
    const build = { capture: sheetCapture, task: sheetTask, note: sheetNote, sync: sheetSync,
      conflict: sheetConflict, unsaved: sheetUnsaved }[S.sheet];
    const content = build(currentTasks);
    if (!content) { S.sheet = null; backdrop.classList.add('hidden'); sheetKey = ''; return; }
    if (key !== sheetKey) body.scrollTop = 0;
    sheetKey = key;
    body.replaceChildren(h('div', { class: 'grip' }, h('i')), content);
    backdrop.classList.remove('hidden');
  }
  $('sheet').onclick = event => { if (event.target === $('sheet')) set({ sheet: null }); };

  // --------------------------------------------------------------- render
  let currentTasks = [];
  let screenKey = '';
  function renderChrome() {
    const late = currentTasks.filter(t => t.late).length;
    const badge = $('navBadge');
    badge.textContent = fa(late);
    badge.classList.toggle('hidden', !late);
    document.querySelectorAll('.nav-item').forEach(b => b.classList.toggle('on', b.dataset.tab === S.tab));
    $('nav').classList.toggle('hidden', Boolean(S.editor));
    $('edbar').classList.toggle('hidden', !S.editor);
    $('scroll').classList.toggle('editing', Boolean(S.editor));
    $('syncDot').className = 'sync-dot ' + syncSummary().tone;
    if (tg && tg.BackButton && tg.isVersionAtLeast && tg.isVersionAtLeast('6.1')) {
      if (S.editor || S.sheet) tg.BackButton.show(); else tg.BackButton.hide();
    }
  }
  function render() {
    tick();
    currentTasks = allTasks().map(describe);
    renderChrome();
    const screen = $('screen');
    if (!loaded) {
      screenKey = 'state';
      screen.replaceChildren(h('div', { class: 'state' }, loadError
        ? [h('b', null, 'باز نشد'), loadError] : 'در حال آوردن یادداشت‌ها…'));
      renderSheet();
      return;
    }
    if (S.editor) {
      const key = 'editor:' + (S.editor.id || 'new');
      if (screenKey === key || (screenKey === 'editor:new' && key.startsWith('editor:'))) {
        screenKey = key;
        updateEditor();
      } else {
        screenKey = key;
        screen.replaceChildren(viewEditor());
        renderEdbar();
        updateEditor();
      }
    } else {
      // Typing in the notes search rebuilds only the list; nothing else here holds focus.
      const focused = document.activeElement && document.activeElement.id === 'noteSearch';
      if (S.tab === 'notes' && focused && screenKey === 'notes') $('noteSections').replaceChildren(noteSections());
      else screen.replaceChildren({ today: viewToday, notes: viewNotes, tasks: viewTasks, cal: viewCal }[S.tab](currentTasks));
      screenKey = S.tab;
    }
    renderSheet();
  }

  // ----------------------------------------------------------- wiring
  document.querySelectorAll('.nav-item').forEach(b => { b.onclick = () => go(b.dataset.tab); });
  $('fab').onclick = () => openCapture();
  $('syncButton').onclick = () => { set({ sheet: 'sync' }); loadDesktop(); };
  $('closeApp').onclick = () => { if (tg && tg.close) tg.close(); else window.history.back(); };

  const THEMES = { dark: { bg: '#191a1f', chrome: '#16171b' }, light: { bg: '#f1f3f7', chrome: '#ffffff' } };
  function applyTheme() {
    const scheme = (tg && tg.colorScheme) || (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
    document.documentElement.dataset.theme = scheme;
    const colours = THEMES[scheme] || THEMES.dark;
    document.querySelector('meta[name="theme-color"]').content = colours.chrome;
    if (tg && tg.isVersionAtLeast && tg.isVersionAtLeast('6.9')) {
      try { tg.setHeaderColor(colours.chrome); tg.setBackgroundColor(colours.bg); } catch { /* older clients */ }
    }
    if (tg && tg.isVersionAtLeast && tg.isVersionAtLeast('7.10')) {
      try { tg.setBottomBarColor(colours.chrome); } catch { /* older clients */ }
    }
  }
  applyTheme();
  // WebViews may resize only their visual viewport when the keyboard opens.
  // Keep the editor and its toolbar inside the actually visible height.
  function fitViewport() {
    const visible = (window.visualViewport && window.visualViewport.height) || window.innerHeight;
    const telegram = tg && tg.viewportHeight;
    const height = telegram > 0 ? Math.min(telegram, visible) : visible;
    if (height > 0) document.documentElement.style.setProperty('--app-height', height + 'px');
  }
  fitViewport();
  window.addEventListener('resize', fitViewport);
  if (window.visualViewport) window.visualViewport.addEventListener('resize', fitViewport);
  if (tg) {
    tg.ready();
    tg.expand();
    if (tg.isVersionAtLeast && tg.isVersionAtLeast('7.7') && tg.disableVerticalSwipes) tg.disableVerticalSwipes();
    if (tg.onEvent) tg.onEvent('themeChanged', applyTheme);
    if (tg.onEvent) tg.onEvent('viewportChanged', fitViewport);
    if (tg.BackButton) tg.BackButton.onClick(() => {
      if (S.sheet) set({ sheet: null });
      else if (S.editor) edBack();
    });
  }
  // Leaving with unsaved text is the one thing the page asks about.
  if (tg && tg.isVersionAtLeast && tg.isVersionAtLeast('6.2')) {
    setInterval(() => {
      if (dirty()) tg.enableClosingConfirmation(); else tg.disableClosingConfirmation();
    }, 1500);
  }

  render();
  loadPins();
  load();
  setInterval(() => {
    // The clock moves the "now" line and the next task; the files may have
    // changed on the desktop. Neither may disturb something being typed.
    if (S.editor || S.sheet === 'capture' || (document.activeElement && document.activeElement.id === 'noteSearch')) return;
    load();
  }, 60000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && !S.editor && S.sheet !== 'capture') load();
  });
})();
