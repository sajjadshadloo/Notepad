export const miniAppScript = String.raw`(() => {
  const tg = window.Telegram?.WebApp;
  tg?.ready();
  tg?.expand();
  const $ = id => document.getElementById(id);
  const views = ['today', 'notes', 'tasks', 'calendar', 'editor', 'taskEditor'];
  const taskRe = /^(\s*)- \[([ xX])\]\s+(.+)$/;
  const TASKS_FILE = 'tasks.md';
  const persianDigits = '۰۱۲۳۴۵۶۷۸۹';
  const digits = value => String(value ?? '')
    .replace(/[۰-۹]/g, char => String(persianDigits.indexOf(char)))
    .replace(/[٠-٩]/g, char => String('٠١٢٣٤٥٦٧٨٩'.indexOf(char)));
  const faNumber = value => Number(value).toLocaleString('fa-IR');
  const faDate = value => String(value).replace(/\d/g, digit => persianDigits[Number(digit)]);
  const fmt = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
    year: 'numeric', month: 'numeric', day: 'numeric', timeZone: 'Asia/Tehran',
  });
  const monthFmt = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
    year: 'numeric', month: 'long', timeZone: 'Asia/Tehran',
  });
  let notes = [];
  let current = null;
  let taskCurrent = null;
  let view = 'today';
  let taskFilter = 'open';
  let taskOrigin = 'tasks';
  let noteSnapshot = '';
  let taskSnapshot = '';
  let monthStart = null;
  let selectedDay = null;
  let noticeTimer = null;
  let captureKind = 'task';
  let captureDays = 0;

  function element(tag, className = '', value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = value;
    return node;
  }

  function notice(message, kind = 'error') {
    clearTimeout(noticeTimer);
    const box = $('notice');
    box.textContent = message || '';
    box.dataset.kind = kind;
    box.classList.toggle('hidden', !message);
    if (message && kind === 'success') {
      noticeTimer = setTimeout(() => notice(''), 4500);
    }
  }

  function status(state, label) {
    $('syncStatus').dataset.state = state;
    $('syncStatus').textContent = label;
  }

  function show(name) {
    view = name;
    for (const id of views) $(id + 'View').classList.toggle('hidden', id !== name);
    $('bottomNav').classList.toggle('hidden', name === 'editor' || name === 'taskEditor');
    $('quickCapture').classList.toggle('hidden', name === 'editor' || name === 'taskEditor');
    document.querySelectorAll('.nav-button').forEach(button => {
      const active = button.dataset.view === name;
      button.classList.toggle('active', active);
      if (active) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
    if (name === 'notes') renderNotes();
    if (name === 'today') renderToday();
    if (name === 'tasks') renderTasks();
    if (name === 'calendar') renderCalendar();
    const captions = { today: 'برنامهٔ امروز', notes: 'یادداشت‌های شما', tasks: 'همهٔ کارها', calendar: 'تقویم فارسی' };
    if ($('headerCaption') && captions[name]) $('headerCaption').textContent = captions[name];
    window.scrollTo({ top: 0, behavior: 'instant' });
  }

  async function api(path, method = 'GET', body) {
    let response;
    try {
      response = await fetch('/api' + path, {
        method,
        headers: {
          'Content-Type': 'application/json',
          'X-Telegram-Init-Data': tg?.initData || '',
        },
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      if (path !== '/sync-status') status('error', 'بدون اتصال');
      throw Error('ارتباط با اینترنت برقرار نیست. دوباره تلاش کن.');
    }
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 409) {
        if (data.error === 'path_exists') throw Error('فایلی با این نام از قبل وجود دارد.');
        await load();
        throw Error('این مورد در جای دیگری تغییر کرده است. متن خود را نگه دار و نسخهٔ تازه را بررسی کن.');
      }
      throw Error(response.status === 401
        ? 'برای ورود، این صفحه را از منوی بات تلگرام باز کن.'
        : data.error || 'خطای ارتباط با سرویس');
    }
    return data;
  }

  async function load() {
    status('busy', 'در حال اتصال');
    try {
      notes = (await api('/notes')).notes;
      renderStats();
      renderToday();
      renderNotes();
      renderTasks();
      renderCalendar();
      status('ready', 'آنلاین');
      notice('');
      loadSyncStatus();
    } catch (error) {
      status('error', 'نیاز به بررسی');
      throw error;
    }
  }

  function ago(timestamp) {
    if (!timestamp) return 'نامشخص';
    const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
    if (minutes < 2) return 'همین حالا';
    if (minutes < 60) return faNumber(minutes) + ' دقیقه پیش';
    if (minutes < 1440) return faNumber(Math.floor(minutes / 60)) + ' ساعت پیش';
    return faNumber(Math.floor(minutes / 1440)) + ' روز پیش';
  }

  async function loadSyncStatus() {
    const panel = $('desktopSync');
    try {
      const { status: desktop } = await api('/sync-status');
      if (!desktop) {
        panel.dataset.state = 'unknown';
        $('desktopSyncTitle').textContent = 'هنوز گزارشی از ویندوز نداریم';
        $('desktopSyncDetail').textContent = 'بعد از نخستین همگام‌سازی، وضعیت اینجا نمایش داده می‌شود.';
        return;
      }
      const stale = Date.now() - desktop.checked_at > 3 * 60 * 1000;
      panel.dataset.state = stale ? 'stale' : desktop.state;
      if (stale) $('desktopSyncTitle').textContent = 'ویندوز فعلاً متصل نیست';
      else if (desktop.state === 'error') $('desktopSyncTitle').textContent = 'همگام‌سازی ویندوز خطا دارد';
      else if (desktop.state === 'attention') $('desktopSyncTitle').textContent = 'همگام‌سازی نیاز به بررسی دارد';
      else $('desktopSyncTitle').textContent = 'ارتباط ویندوز برقرار است';
      const issues = [];
      if (desktop.conflicts) issues.push(faNumber(desktop.conflicts) + ' تعارض');
      if (desktop.skipped) issues.push(faNumber(desktop.skipped) + ' فایل در انتظار');
      $('desktopSyncDetail').textContent = 'آخرین بررسی: ' + ago(desktop.checked_at)
        + (desktop.completed_at ? ' · آخرین همگام‌سازی: ' + ago(desktop.completed_at) : '')
        + (issues.length ? ' · ' + issues.join('، ') : '');
    } catch {
      panel.dataset.state = 'unknown';
      $('desktopSyncTitle').textContent = 'وضعیت ویندوز در دسترس نیست';
      $('desktopSyncDetail').textContent = 'بعداً دوباره تازه‌سازی کن.';
    }
  }

  function active() {
    return notes.filter(note => !note.deleted);
  }

  function renderStats() {
    const allTasks = tasks();
    const today = key(new Date());
    $('statNotes').textContent = faNumber(active().length);
    $('statOpen').textContent = faNumber(allTasks.filter(task => !task.done).length);
    $('statToday').textContent = faNumber(allTasks.filter(task => !task.done && task.date === today).length);
  }

  function tomorrowKey() {
    const value = new Date();
    value.setDate(value.getDate() + 1);
    return key(value);
  }

  function captureDate() {
    const value = new Date();
    value.setDate(value.getDate() + captureDays);
    return key(value);
  }

  function closeSheets() {
    $('sheetBackdrop').classList.add('hidden');
    $('quickSheet').classList.add('hidden');
    $('syncSheet').classList.add('hidden');
  }

  function openCapture() {
    captureKind = 'task';
    captureDays = 0;
    $('captureText').value = '';
    $('captureTask').classList.add('active');
    $('captureNote').classList.remove('active');
    $('captureDates').classList.remove('hidden');
    $('captureDates').querySelectorAll('button').forEach(button => button.classList.toggle('active', button.dataset.days === '0'));
    $('saveCapture').textContent = 'افزودن کار';
    $('captureSummary').textContent = 'برای امروز · بدون ساعت';
    $('sheetBackdrop').classList.remove('hidden');
    $('quickSheet').classList.remove('hidden');
    $('syncSheet').classList.add('hidden');
    setTimeout(() => $('captureText').focus(), 0);
  }

  function setCaptureKind(kind) {
    captureKind = kind;
    $('captureTask').classList.toggle('active', kind === 'task');
    $('captureNote').classList.toggle('active', kind === 'note');
    $('captureDates').classList.toggle('hidden', kind === 'note');
    $('saveCapture').textContent = kind === 'task' ? 'افزودن کار' : 'ذخیره در ورودی‌ها';
    $('captureSummary').textContent = kind === 'task' ? 'برای ' + faDate(captureDate()) + ' · بدون ساعت' : 'یک یادداشت تازه در پوشهٔ «ورودی‌ها» ساخته می‌شود';
  }

  async function saveCapture() {
    const text = $('captureText').value.trim();
    if (!text) { $('captureText').focus(); return; }
    $('saveCapture').disabled = true;
    try {
      if (captureKind === 'task') {
        await changeTask(null, taskLine(text, captureDate(), ''));
        closeSheets();
        show('today');
        notice('کار اضافه شد.', 'success');
      } else {
        const title = text.split('\n')[0].replace(/^#+\s*/, '').slice(0, 38) || 'یادداشت سریع';
        const safe = title.replace(/[\\/:*?"<>|]/g, '-');
        await api('/notes', 'POST', { path: 'ورودی‌ها/' + safe + '-' + Date.now() + '.md', text: text.startsWith('#') ? text : '# ' + title + '\n\n' + text });
        await load();
        closeSheets();
        show('notes');
        notice('در ورودی‌ها ذخیره شد.', 'success');
      }
    } catch (error) { notice(error.message); }
    finally { $('saveCapture').disabled = false; }
  }

  function openSyncSheet() {
    $('syncSheetState').textContent = $('desktopSyncTitle').textContent;
    $('syncSheetDetail').textContent = $('desktopSyncDetail').textContent;
    $('sheetBackdrop').classList.remove('hidden');
    $('quickSheet').classList.add('hidden');
    $('syncSheet').classList.remove('hidden');
  }

  function todayTaskRow(task, options = {}) {
    const row = element('div', 'task-card today-task row');
    const box = element('input', 'task-check');
    box.type = 'checkbox';
    box.checked = task.done;
    box.setAttribute('aria-label', 'انجام کار: ' + task.text);
    box.onchange = () => toggleTask(task, box);
    const main = element('button', 'task-main');
    main.type = 'button';
    main.append(element('span', 'task-title' + (task.done ? ' done' : ''), task.text));
    const meta = element('span', 'task-meta');
    if (task.time) meta.append(element('span', 'due today', faDate(task.time)));
    meta.append(element('span', 'task-source', task.note.path.split('/').pop()));
    main.append(meta);
    main.onclick = () => openTask(task, 'today');
    row.append(box, main);
    if (options.review) {
      const actions = element('span', 'review-actions');
      const todayButton = element('button', '', 'امروز');
      todayButton.type = 'button';
      todayButton.onclick = () => rescheduleTask(task, key(new Date()));
      const tomorrowButton = element('button', '', 'فردا');
      tomorrowButton.type = 'button';
      tomorrowButton.onclick = () => rescheduleTask(task, tomorrowKey());
      actions.append(todayButton, tomorrowButton);
      row.append(actions);
    }
    return row;
  }

  async function rescheduleTask(task, date) {
    try {
      await changeTask(task, taskLine(task.text, date, task.time, task.done, task.repeats, task.indent));
      show('today');
      notice('زمان کار تغییر کرد.', 'success');
    } catch (error) { notice(error.message); }
  }

  async function moveAllToToday(overdue) {
    const target = key(new Date());
    const grouped = new Map();
    for (const task of overdue) {
      if (!grouped.has(task.note.id)) grouped.set(task.note.id, { note: task.note, tasks: [] });
      grouped.get(task.note.id).tasks.push(task);
    }
    try {
      for (const { note, tasks: noteTasks } of grouped.values()) {
        const lines = note.text.split('\n');
        for (const task of noteTasks) {
          lines[task.line] = taskLine(task.text, target, task.time, task.done, task.repeats, task.indent);
        }
        await api('/notes/' + note.id, 'PUT', { version: note.version, text: lines.join('\n') });
      }
      await load();
      show('today');
      notice('کارهای عقب‌افتاده به امروز آمدند.', 'success');
    } catch (error) { notice(error.message); }
  }

  function renderToday() {
    const all = tasks().sort(taskOrder);
    const today = key(new Date());
    const tomorrow = tomorrowKey();
    const todayItems = all.filter(task => task.date === today);
    const overdue = all.filter(task => !task.done && task.date && task.date < today);
    const tomorrowItems = all.filter(task => !task.done && task.date === tomorrow);
    const done = todayItems.filter(task => task.done).length;
    const open = todayItems.filter(task => !task.done);
    const pct = todayItems.length ? Math.round(done / todayItems.length * 100) : 0;
    $('todayDate').textContent = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
      weekday: 'long', day: 'numeric', month: 'long', timeZone: 'Asia/Tehran',
    }).format(new Date());
    $('todayProgress').textContent = faNumber(done) + ' از ' + faNumber(todayItems.length);
    $('todayProgressBar').style.width = pct + '%';
    $('todayCount').textContent = faNumber(open.length) + ' کار باز';

    const todayList = $('todayTasksList');
    todayList.replaceChildren(...todayItems.map(task => todayTaskRow(task)));
    if (!todayItems.length) todayList.append(emptyState('امروز کاری ثبت نشده', 'با دکمهٔ آبی یک کار تازه اضافه کن.', '✓'));

    $('reviewBlock').classList.toggle('hidden', !overdue.length);
    $('reviewTitle').textContent = 'از روزهای قبل مانده · ' + faNumber(overdue.length);
    $('reviewList').replaceChildren(...overdue.map(task => todayTaskRow(task, { review: true })));
    $('moveAllToday').onclick = () => moveAllToToday(overdue);

    const timed = open.filter(task => task.time).sort((a, b) => a.time.localeCompare(b.time));
    $('nextBlock').classList.toggle('hidden', !timed.length);
    if (timed.length) {
      const next = timed[0];
      $('nextTask').replaceChildren(element('strong', '', faDate(next.time)), element('span', '', next.text), element('small', '', next.note.path.split('/').pop()));
      $('nextTask').onclick = () => openTask(next, 'today');
    }

    $('tomorrowBlock').classList.toggle('hidden', !tomorrowItems.length);
    $('tomorrowText').textContent = tomorrowItems.map(task => (task.time ? faDate(task.time) + ' ' : '') + task.text).join('، ');
    $('openTomorrow').onclick = () => {
      selectedDay = tomorrow;
      show('calendar');
    };
  }

  function emptyState(title, detail, icon = '✦') {
    const box = element('div', 'empty');
    box.append(
      element('span', 'empty-icon', icon),
      element('strong', '', title),
      element('span', '', detail),
    );
    return box;
  }

  function renderNotes() {
    const list = $('notesList');
    list.replaceChildren();
    const query = $('search').value.trim().toLowerCase();
    const visible = active().filter(note =>
      (note.path + ' ' + note.text).toLowerCase().includes(query));
    $('noteCount').textContent = faNumber(visible.length);
    for (const note of visible) {
      const lines = note.text.split('\n').map(line => line.trim()).filter(Boolean);
      const first = lines[0] || '';
      const taskOnly = taskRe.test(first);
      const file = note.path.split('/').pop();
      const folder = note.path.includes('/') ? note.path.split('/')[0] : 'یادداشت‌های من';
      const title = taskOnly ? file.replace(/\.(md|txt|markdown)$/i, '')
        : first.replace(/^#+\s*/, '').slice(0, 90) || 'یادداشت خالی';
      const preview = taskOnly ? first.replace(/^-\s+\[[ xX]\]\s*/, '')
        : (lines[1] || (first.length > 90 ? first.slice(90) : 'برای ویرایش لمس کن'));
      const card = element('button', 'note-card row');
      card.type = 'button';
      const icon = element('span', 'note-icon' + (taskOnly ? ' tasks' : ''), taskOnly ? '✓' : '≡');
      icon.setAttribute('aria-hidden', 'true');
      const body = element('span', 'note-body');
      body.append(
        element('span', 'note-title', title),
        element('span', 'note-preview', preview.slice(0, 100)),
        element('span', 'note-meta', folder === 'Inbox' ? 'ورودی' : folder),
      );
      card.append(icon, body, element('span', 'chevron', '‹'));
      card.onclick = () => openNote(note);
      list.append(card);
    }
    if (!visible.length) {
      list.append(emptyState(query ? 'نتیجه‌ای پیدا نشد' : 'هنوز یادداشتی نداری',
        query ? 'عبارت دیگری را جست‌وجو کن.' : 'اولین یادداشتت را با دکمهٔ بالا بساز.'));
    }
  }

  function openNote(note) {
    current = note || null;
    $('editorTitle').textContent = note ? 'ویرایش یادداشت' : 'یادداشت جدید';
    $('notePath').value = note?.path || '';
    $('notePath').disabled = Boolean(note);
    $('noteText').value = note?.text || '';
    $('deleteNote').classList.toggle('hidden', !note);
    noteSnapshot = $('notePath').value + '\0' + $('noteText').value;
    notice('');
    show('editor');
    if (!note) $('notePath').focus();
  }

  function leaveNote() {
    if (noteSnapshot !== $('notePath').value + '\0' + $('noteText').value
        && !confirm('تغییرات ذخیره‌نشده‌اند. خارج شوی؟')) return;
    notice('');
    show('notes');
  }

  async function saveNote() {
    const path = $('notePath').value.trim();
    const text = $('noteText').value;
    if (!/^[^\\/:]+(?:\/[^\\/:]+)*\.(md|txt|markdown)$/i.test(path)) {
      notice('نام فایل باید به md یا txt ختم شود.'); return;
    }
    const button = $('saveNote');
    button.disabled = true;
    try {
      if (current) await api('/notes/' + current.id, 'PUT', { version: current.version, text });
      else await api('/notes', 'POST', { path, text });
      await load();
      show('notes');
      notice('یادداشت ذخیره شد.', 'success');
    } catch (error) {
      notice(error.message);
    } finally {
      button.disabled = false;
    }
  }

  async function deleteNote() {
    if (!current || !confirm('این یادداشت حذف شود؟')) return;
    try {
      await api('/notes/' + current.id, 'DELETE', { version: current.version });
      await load();
      show('notes');
      notice('یادداشت حذف شد.', 'success');
    } catch (error) { notice(error.message); }
  }

  function tasks() {
    const found = [];
    for (const note of active()) {
      note.text.split('\n').forEach((line, index) => {
        const match = taskRe.exec(line);
        if (!match) return;
        const normalized = digits(match[3]);
        const stamp = normalized.match(/\s*@(\d{3,4}[/-]\d{1,2}[/-]\d{1,2})(?:\s+(\d{1,2}:\d{2}))?(\s*↻)?\s*$/);
        let date = stamp?.[1]?.replace(/-/g, '/') || '';
        if (date) {
          const [year, month, day] = date.split('/').map(Number);
          date = year >= 1600 ? key(new Date(Date.UTC(year, month - 1, day, 12)))
            : year + '/' + String(month).padStart(2, '0') + '/' + String(day).padStart(2, '0');
        }
        found.push({
          note, line: index, indent: match[1], text: (stamp
            ? match[3].slice(0, stamp.index) : match[3]).trim(),
          done: match[2] !== ' ', date, time: stamp?.[2] || '',
          repeats: Boolean(stamp?.[3]),
        });
      });
    }
    return found;
  }

  function taskOrder(a, b) {
    if (a.done !== b.done) return Number(a.done) - Number(b.done);
    const today = key(new Date());
    const rank = task => !task.date ? 3 : task.date < today ? 0 : task.date === today ? 1 : 2;
    const difference = rank(a) - rank(b);
    if (difference) return difference;
    if (rank(a) === 0) return b.date.localeCompare(a.date);
    return (a.date || '9999').localeCompare(b.date || '9999');
  }

  function renderTasks() {
    const list = $('tasksList');
    list.replaceChildren();
    const all = tasks();
    const open = all.filter(task => !task.done).length;
    $('taskSummary').textContent = faNumber(open) + ' کار باز از ' + faNumber(all.length) + ' کار';
    $('openCount').textContent = faNumber(open);
    const query = $('taskSearch').value.trim().toLowerCase();
    const today = key(new Date());
    const visible = all.filter(task =>
      (task.text + ' ' + task.date).toLowerCase().includes(query) &&
      (taskFilter === 'all' || taskFilter === 'open' && !task.done ||
       taskFilter === 'done' && task.done ||
       taskFilter === 'today' && !task.done && task.date === today)).sort(taskOrder);
    for (const task of visible) {
      const row = element('div', 'task-card row');
      const box = element('input', 'task-check');
      box.type = 'checkbox';
      box.checked = task.done;
      box.setAttribute('aria-label', 'انجام کار: ' + task.text);
      box.onchange = () => toggleTask(task, box);
      const main = element('button', 'task-main');
      main.type = 'button';
      main.append(element('span', 'task-title' + (task.done ? ' done' : ''), task.text));
      const meta = element('span', 'task-meta');
      const when = task.date ? (task.date === today ? 'امروز'
        : task.date < today && !task.done ? 'عقب‌افتاده · ' + faDate(task.date)
          : faDate(task.date)) : 'بدون تاریخ';
      meta.append(element('span', 'due' + (!task.done && task.date === today ? ' today'
        : !task.done && task.date && task.date < today ? ' late' : ''),
        when + (task.time ? ' · ' + faDate(task.time) : '') + (task.repeats ? ' ↻' : '')));
      meta.append(element('span', 'task-source', task.note.path.split('/').pop()));
      main.append(meta);
      main.onclick = () => openTask(task, 'tasks');
      row.append(box, main);
      list.append(row);
    }
    if (!visible.length) {
      list.append(emptyState(query ? 'کاری پیدا نشد' : taskFilter === 'today'
        ? 'برای امروز کاری نداری' : 'اینجا فعلاً خالی است',
      query ? 'عبارت دیگری را جست‌وجو کن.' : 'می‌توانی یک کار تازه بسازی.', '✓'));
    }
  }

  function openTask(task, origin = view === 'calendar' ? 'calendar' : 'tasks') {
    taskCurrent = task || null;
    taskOrigin = origin;
    $('taskEditorTitle').textContent = task ? 'ویرایش کار' : 'کار جدید';
    $('taskText').value = task?.text || '';
    $('taskDate').value = task?.date || (origin === 'calendar' ? selectedDay : origin === 'today' ? key(new Date()) : '') || '';
    $('taskTime').value = task?.time || '';
    $('deleteTask').classList.toggle('hidden', !task);
    taskSnapshot = $('taskText').value + '\0' + $('taskDate').value + '\0' + $('taskTime').value;
    notice('');
    show('taskEditor');
    if (!task) $('taskText').focus();
  }

  function leaveTask() {
    if (taskSnapshot !== $('taskText').value + '\0' + $('taskDate').value + '\0' + $('taskTime').value
        && !confirm('تغییرات ذخیره‌نشده‌اند. خارج شوی؟')) return;
    notice('');
    show(taskOrigin);
  }

  async function changeTask(task, newLine) {
    // New tasks land in the same tasks.md the desktop app writes to.
    const note = task?.note || active().find(item => item.path === TASKS_FILE);
    const lines = note?.text.split('\n') || [];
    if (task) {
      if (!taskRe.test(lines[task.line] || '')) throw Error('کار تغییر کرده است؛ تازه‌سازی کن.');
      if (newLine === null) lines.splice(task.line, 1);
      else lines[task.line] = newLine;
    } else lines.push(newLine);
    const text = lines.join('\n');
    if (note) await api('/notes/' + note.id, 'PUT', { version: note.version, text });
    else await api('/notes', 'POST', { path: TASKS_FILE, text });
    await load();
  }

  function taskLine(text, date, time, done = false, repeats = false, indent = '') {
    return indent + '- [' + (done ? 'x' : ' ') + '] ' + text
      + (date ? ' @' + date + (time ? ' ' + time : '') + (repeats ? ' ↻' : '') : '');
  }

  async function saveTask() {
    const title = $('taskText').value.trim();
    const date = digits($('taskDate').value.trim()).replace(/-/g, '/');
    const time = $('taskTime').value;
    if (!title) { notice('عنوان کار را بنویس.'); return; }
    if (date) {
      const match = /^(\d{3,4})\/(\d{1,2})\/(\d{1,2})$/.exec(date);
      const month = Number(match?.[2]), day = Number(match?.[3]);
      if (!match || month < 1 || month > 12 || day < 1 || day > (month <= 6 ? 31 : 30)) {
        notice('تاریخ را مثل ۱۴۰۵/۰۷/۰۲ بنویس.'); return;
      }
    }
    const button = $('saveTask');
    button.disabled = true;
    try {
      await changeTask(taskCurrent, taskLine(title, date, time,
        taskCurrent?.done, taskCurrent?.repeats, taskCurrent?.indent));
      show(taskOrigin);
      notice('کار ذخیره شد.', 'success');
    } catch (error) { notice(error.message); }
    finally { button.disabled = false; }
  }

  async function deleteTask() {
    if (!taskCurrent || !confirm('این کار حذف شود؟')) return;
    try {
      await changeTask(taskCurrent, null);
      show(taskOrigin);
      notice('کار حذف شد.', 'success');
    } catch (error) { notice(error.message); }
  }

  async function toggleTask(task, box) {
    box.disabled = true;
    const line = task.note.text.split('\n')[task.line];
    try {
      await changeTask(task, line.replace(/\[([ xX])\]/, task.done ? '[ ]' : '[x]'));
      notice(task.done ? 'کار دوباره باز شد.' : 'کار انجام شد.', 'success');
    } catch (error) {
      notice(error.message);
      renderTasks();
    }
  }

  function parts(date) {
    return Object.fromEntries(fmt.formatToParts(date)
      .filter(part => ['year', 'month', 'day'].includes(part.type))
      .map(part => [part.type, Number(digits(part.value))]));
  }
  function key(date) {
    const part = parts(date);
    return part.year + '/' + String(part.month).padStart(2, '0')
      + '/' + String(part.day).padStart(2, '0');
  }
  function add(date, days) {
    const copy = new Date(date);
    copy.setUTCDate(copy.getUTCDate() + days);
    return copy;
  }
  function startOfMonth(date) {
    let first = new Date(date);
    first.setUTCHours(12, 0, 0, 0);
    while (parts(add(first, -1)).month === parts(first).month) first = add(first, -1);
    return first;
  }

  function renderCalendar() {
    if (!monthStart) monthStart = startOfMonth(new Date());
    if (!selectedDay) selectedDay = key(new Date());
    $('monthTitle').textContent = monthFmt.format(monthStart);
    const grid = $('calendarGrid');
    grid.replaceChildren();
    for (const name of ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج']) grid.append(element('div', 'dayhead', name));
    const offset = (monthStart.getUTCDay() + 1) % 7;
    for (let i = 0; i < offset; i++) grid.append(element('div', 'other', ''));
    const month = parts(monthStart).month;
    const allTasks = tasks();
    const today = key(new Date());
    for (let day = monthStart; parts(day).month === month; day = add(day, 1)) {
      const date = key(day);
      const count = allTasks.filter(task => task.date === date).length;
      const button = element('button', 'day' + (date === today ? ' current' : '')
        + (date === selectedDay ? ' selected' : '') + (count ? ' has-task' : ''),
      faNumber(parts(day).day));
      button.type = 'button';
      button.setAttribute('aria-label', faDate(date) + (count ? '، ' + faNumber(count) + ' کار' : ''));
      button.onclick = () => { selectedDay = date; renderCalendar(); };
      grid.append(button);
    }
    $('dayTitle').textContent = 'برنامهٔ ' + faDate(selectedDay);
    const list = $('dayTasks');
    list.replaceChildren();
    const dayTasks = allTasks.filter(task => task.date === selectedDay);
    for (const task of dayTasks) {
      const card = element('button', 'agenda-card' + (task.done ? ' done' : ''), task.text);
      card.type = 'button';
      card.onclick = () => openTask(task, 'calendar');
      list.append(card);
    }
    if (!dayTasks.length) list.append(emptyState('این روز خلوت است',
      'برای این روز کاری ثبت نشده است.', '◦'));
  }

  document.querySelectorAll('.nav-button').forEach(button => {
    button.onclick = () => show(button.dataset.view);
  });
  document.querySelectorAll('.filter-chip').forEach(button => {
    button.onclick = () => {
      taskFilter = button.dataset.filter;
      document.querySelectorAll('.filter-chip').forEach(item =>
        item.classList.toggle('active', item === button));
      renderTasks();
    };
  });
  $('refresh').onclick = () => load().catch(error => notice(error.message));
  $('search').oninput = renderNotes;
  $('taskSearch').oninput = renderTasks;
  $('newNote').onclick = () => openNote(null);
  $('saveNote').onclick = saveNote;
  $('deleteNote').onclick = deleteNote;
  $('back').onclick = leaveNote;
  $('newTask').onclick = () => openTask(null, 'tasks');
  $('quickCapture').onclick = openCapture;
  $('closeCapture').onclick = closeSheets;
  $('captureTask').onclick = () => setCaptureKind('task');
  $('captureNote').onclick = () => setCaptureKind('note');
  $('captureDates').querySelectorAll('button').forEach(button => {
    button.onclick = () => {
      captureDays = Number(button.dataset.days);
      $('captureDates').querySelectorAll('button').forEach(item => item.classList.toggle('active', item === button));
      $('captureSummary').textContent = 'برای ' + faDate(captureDate()) + ' · بدون ساعت';
    };
  });
  $('saveCapture').onclick = saveCapture;
  $('desktopSync').onclick = openSyncSheet;
  $('closeSync').onclick = closeSheets;
  $('syncNow').onclick = async () => { await loadSyncStatus(); openSyncSheet(); };
  $('sheetBackdrop').onclick = event => { if (event.target === $('sheetBackdrop')) closeSheets(); };
  $('addDayTask').onclick = () => openTask(null, 'calendar');
  $('saveTask').onclick = saveTask;
  $('deleteTask').onclick = deleteTask;
  $('taskBack').onclick = leaveTask;
  $('todayButton').onclick = () => {
    monthStart = startOfMonth(new Date());
    selectedDay = key(new Date());
    renderCalendar();
  };
  $('prevMonth').onclick = () => {
    monthStart = startOfMonth(add(monthStart, -1));
    selectedDay = key(monthStart);
    renderCalendar();
  };
  $('nextMonth').onclick = () => {
    let next = add(monthStart, 28);
    while (parts(next).month === parts(monthStart).month) next = add(next, 1);
    monthStart = startOfMonth(next);
    selectedDay = key(monthStart);
    renderCalendar();
  };
  if (tg?.colorScheme) document.documentElement.dataset.theme = tg.colorScheme;
  tg?.onEvent?.('themeChanged', () => {
    document.documentElement.dataset.theme = tg.colorScheme;
  });
  load().catch(error => notice(error.message));
  setInterval(loadSyncStatus, 60_000);
})();`;
