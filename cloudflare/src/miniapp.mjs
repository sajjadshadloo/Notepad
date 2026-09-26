// The Mini App shell. Everything inside #screen and #sheetBody is drawn by
// /app.js; what is here is the frame that never changes: the bar, the bottom
// navigation with its central capture button, the sheet and the toast.
// The page's CSP allows no inline styles, so every look lives in /app.css.
const icon = (size, body, extra = '') =>
  `<svg width="${size}" height="${size}" viewBox="0 0 16 16" fill="none" stroke="currentColor" ${extra} stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

export const miniAppHtml = `<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#16171b">
  <title>نوت‌پد پلاس</title>
  <link rel="stylesheet" href="/app.css">
</head>
<body>
<div id="app" class="app">
  <header class="bar">
    <button id="closeApp" class="bar-close" type="button">بستن</button>
    <div class="bar-title"><span>نوت‌پد پلاس</span><small>مینی‌اپ</small></div>
    <button id="syncButton" class="bar-sync" type="button" title="وضعیت همگام‌سازی">
      <span id="syncDot" class="sync-dot"></span>
      ${icon(18, '<path d="M13 6.5A5 5 0 0 0 3.6 5M3 9.5A5 5 0 0 0 12.4 11"></path><path d="M3.3 2.5v2.8h2.8M12.7 13.5v-2.8H9.9"></path>', 'stroke-width="1.5"')}
    </button>
  </header>

  <div id="scroll" class="scroll"><div id="screen"></div></div>

  <div id="edbar" class="edbar hidden"></div>

  <nav id="nav" class="nav">
    <button class="nav-item" data-tab="today" type="button">
      ${icon(22, '<circle cx="8" cy="8" r="3"></circle><path d="M8 1.5v1.3M8 13.2v1.3M1.5 8h1.3M13.2 8h1.3M3.4 3.4l.9.9M11.7 11.7l.9.9M3.4 12.6l.9-.9M11.7 4.3l.9-.9"></path>', 'stroke-width="1.35"')}امروز
    </button>
    <button class="nav-item" data-tab="notes" type="button">
      ${icon(22, '<path d="M4 1.5h5.5L13 5v8.5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1z"></path><path d="M9.5 1.5V5H13"></path><path d="M5.5 8.5h5M5.5 11h3.5"></path>', 'stroke-width="1.35"')}یادداشت‌ها
    </button>
    <div class="nav-fab-slot">
      <button id="fab" class="nav-fab" type="button" title="ضبط سریع">
        ${icon(22, '<path d="M8 3v10M3 8h10"></path>', 'stroke-width="2"')}
      </button>
    </div>
    <button class="nav-item" data-tab="tasks" type="button">
      ${icon(22, '<rect x="2" y="2.5" width="12" height="11" rx="2.2"></rect><polyline points="5,8 7,10 11,5.6"></polyline>', 'stroke-width="1.35"')}کارها
      <span id="navBadge" class="nav-badge hidden"></span>
    </button>
    <button class="nav-item" data-tab="cal" type="button">
      ${icon(22, '<rect x="2" y="3" width="12" height="11" rx="2.2"></rect><path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3"></path><path d="M5 9.5h.8M7.6 9.5h.8M10.2 9.5h.8M5 12h.8M7.6 12h.8"></path>', 'stroke-width="1.35"')}تقویم
    </button>
  </nav>

  <div id="sheet" class="backdrop hidden"><div id="sheetBody" class="sheet"></div></div>

  <div id="toast" class="toast hidden" role="status" aria-live="polite">
    <span id="toastText"></span>
    <button id="toastUndo" class="toast-undo hidden" type="button">بازگردانی</button>
  </div>
</div>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script src="/app.js"></script>
</body></html>`;
