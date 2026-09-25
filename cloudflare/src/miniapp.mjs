export const miniAppHtml = `<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#f4f6fa">
  <title>نوت پلاس</title>
  <link rel="stylesheet" href="/app.css">
</head>
<body>
<main>
  <header class="brand-row">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true">ن</span>
      <div><span class="brand-name">نوت پلاس</span><span class="brand-caption">یادداشت‌ها، همیشه همراهت</span></div>
    </div>
    <div class="brand-actions">
      <span id="syncStatus" class="sync-pill" data-state="busy">در حال اتصال</span>
      <button id="refresh" class="icon-button" type="button" title="تازه‌سازی" aria-label="تازه‌سازی">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5"/><path d="M5.5 9A7 7 0 0 1 18 7l2 5M4 12l2 5a7 7 0 0 0 12.5-2"/></svg>
      </button>
    </div>
  </header>
  <div id="notice" class="notice hidden" role="status" aria-live="polite"></div>
  <div id="desktopSync" class="desktop-sync" data-state="unknown" role="status" aria-live="polite">
    <span class="desktop-sync-dot" aria-hidden="true"></span>
    <div><strong id="desktopSyncTitle">وضعیت ویندوز</strong><span id="desktopSyncDetail">در حال بررسی آخرین همگام‌سازی…</span></div>
  </div>

  <section id="notesView">
    <div class="overview">
      <span class="overview-label">فضای شخصی من</span>
      <div class="overview-title">فکرها و کارها، یک‌جا و همیشه در دسترس</div>
      <div class="stats">
        <div class="stat"><strong id="statNotes">—</strong><span>یادداشت</span></div>
        <div class="stat"><strong id="statOpen">—</strong><span>کار باز</span></div>
        <div class="stat"><strong id="statToday">—</strong><span>برای امروز</span></div>
      </div>
    </div>
    <div class="section-heading">
      <div><span class="eyebrow">کتابخانهٔ من</span><h1>یادداشت‌ها <span id="noteCount" class="count"></span></h1></div>
      <button class="primary" id="newNote" type="button">+ یادداشت</button>
    </div>
    <div class="search-box">
      <span class="search-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 5 5"/></svg></span>
      <input id="search" type="search" aria-label="جست‌وجوی یادداشت" placeholder="جست‌وجو در یادداشت‌ها">
    </div>
    <div id="notesList" class="list note-list"></div>
  </section>

  <section id="tasksView" class="hidden">
    <div class="section-heading">
      <div><span class="eyebrow">برنامهٔ من</span><h1>کارها</h1><p id="taskSummary" class="section-subtitle"></p></div>
      <button class="primary" id="newTask" type="button">+ کار</button>
    </div>
    <div class="search-box">
      <span class="search-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 5 5"/></svg></span>
      <input id="taskSearch" type="search" aria-label="جست‌وجوی کار" placeholder="جست‌وجو در کارها">
    </div>
    <div id="taskFilters" class="filters" aria-label="فیلتر کارها">
      <button type="button" class="filter-chip active" data-filter="open">باز <small id="openCount"></small></button>
      <button type="button" class="filter-chip" data-filter="today">امروز</button>
      <button type="button" class="filter-chip" data-filter="all">همه</button>
      <button type="button" class="filter-chip" data-filter="done">انجام‌شده</button>
    </div>
    <div id="tasksList" class="list"></div>
  </section>

  <section id="calendarView" class="hidden">
    <div class="section-heading">
      <div><span class="eyebrow">مرور زمان</span><h1>تقویم</h1><p class="section-subtitle">کارهای هر روز را یک‌جا ببین</p></div>
      <button id="todayButton" class="today-button" type="button">امروز</button>
    </div>
    <div class="month-bar">
      <h2 id="monthTitle" class="month-title"></h2>
      <div class="month-controls">
        <button id="prevMonth" class="icon-button" type="button" aria-label="ماه قبل">→</button>
        <button id="nextMonth" class="icon-button" type="button" aria-label="ماه بعد">←</button>
      </div>
    </div>
    <div class="calendar-surface"><div class="calendar" id="calendarGrid"></div></div>
    <div class="agenda-head"><h2 id="dayTitle"></h2><button id="addDayTask" class="secondary" type="button">+ کار این روز</button></div>
    <div id="dayTasks"></div>
  </section>

  <section id="editorView" class="hidden">
    <div class="editor-top"><button id="back" class="icon-button" type="button" aria-label="بازگشت">→</button><h1 id="editorTitle"></h1><span class="editor-spacer"></span></div>
    <div class="editor-card">
      <div class="field"><label for="notePath">نام و مسیر فایل</label><input id="notePath" placeholder="مثلاً Ideas/طرح-جدید.md" autocomplete="off"><span class="field-hint">یادداشت‌ها به‌صورت فایل Markdown یا TXT در ویندوز هم ذخیره می‌شوند.</span></div>
      <div class="field"><label for="noteText">متن یادداشت</label><textarea id="noteText" placeholder="اینجا بنویس..." spellcheck="true"></textarea></div>
    </div>
    <div class="editor-actions"><button class="primary" id="saveNote" type="button">ذخیرهٔ یادداشت</button><button class="danger" id="deleteNote" type="button">حذف</button></div>
  </section>

  <section id="taskEditorView" class="hidden">
    <div class="editor-top"><button id="taskBack" class="icon-button" type="button" aria-label="بازگشت">→</button><h1 id="taskEditorTitle">کار</h1><span class="editor-spacer"></span></div>
    <div class="editor-card">
      <div class="field"><label for="taskText">عنوان کار</label><input id="taskText" placeholder="مثلاً تماس با علی" autocomplete="off"></div>
      <div class="field"><label for="taskDate">تاریخ شمسی</label><input id="taskDate" inputmode="numeric" placeholder="۱۴۰۵/۰۷/۰۲"><span class="field-hint">اختیاری؛ می‌توانی از تقویم هم روز را انتخاب کنی.</span></div>
      <div class="field"><label for="taskTime">ساعت</label><input id="taskTime" type="time"></div>
    </div>
    <div class="editor-actions"><button class="primary" id="saveTask" type="button">ذخیرهٔ کار</button><button class="danger" id="deleteTask" type="button">حذف</button></div>
  </section>
</main>

<nav id="bottomNav" class="bottom-nav" aria-label="بخش‌های برنامه">
  <button class="nav-button active" data-view="notes" type="button"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg><span>یادداشت‌ها</span></button>
  <button class="nav-button" data-view="tasks" type="button"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="m7 11 2 2 4-4M15 12h3"/></svg><span>کارها</span></button>
  <button class="nav-button" data-view="calendar" type="button"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18M7 14h2M12 14h2"/></svg><span>تقویم</span></button>
</nav>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script src="/app.js"></script>
</body></html>`;
