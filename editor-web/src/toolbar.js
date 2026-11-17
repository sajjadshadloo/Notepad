// The toolbar: one quiet row of icon buttons, grouped, with a contextual
// group that appears only while the cursor is inside a table.
import { icon } from './icons.js';

const GROUPS = [
  [['undo', 'undo', 'برگشت  Ctrl+Z'], ['redo', 'redo', 'جلو  Ctrl+Y']],
  [['h1', null, 'عنوان ۱  Ctrl+1', 'H۱'], ['h2', null, 'عنوان ۲  Ctrl+2', 'H۲']],
  [['bullet', 'bullets', 'فهرست نقطه‌ای'], ['ordered', 'numbered', 'فهرست شماره‌دار'], ['task', 'task', 'کار (تیک‌دار)']],
  [['bold', 'bold', 'پررنگ  Ctrl+B'], ['italic', 'italic', 'کج  Ctrl+I'], ['strike', 'strike', 'خط‌خورده'], ['code', 'code', 'کد'], ['link', 'link', 'پیوند']],
  [['date', 'date', 'تاریخ  Ctrl+Shift+A'], ['table', 'table', 'جدول']],
];
const TABLE_GROUP = [
  ['addRow', 'rowAdd', 'ردیف جدید در زیر'], ['delRow', 'rowDel', 'حذف ردیف'],
  ['addCol', 'colAdd', 'ستون جدید'], ['delCol', 'colDel', 'حذف ستون'],
  ['delTable', 'tableDel', 'حذف جدول'],
];

function button([command, glyph, title, text]) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'tb';
  b.dataset.cmd = command;
  b.title = title;
  b.setAttribute('aria-label', title);
  b.innerHTML = glyph ? icon(glyph) : `<span class="tb-text">${text}</span>`;
  // A click must not take the caret out of the text.
  b.addEventListener('mousedown', (e) => e.preventDefault());
  return b;
}

export function buildToolbar(host, run) {
  host.innerHTML = '';
  host.classList.add('toolbar');
  const addGroup = (items, cls = '') => {
    const g = document.createElement('div');
    g.className = `tb-group ${cls}`.trim();
    for (const item of items) {
      const b = button(item);
      b.addEventListener('click', () => run(item[0]));
      g.appendChild(b);
    }
    host.appendChild(g);
    return g;
  };
  GROUPS.forEach((group, i) => {
    addGroup(group);
    if (i < GROUPS.length - 1) {
      const sep = document.createElement('span');
      sep.className = 'tb-sep';
      host.appendChild(sep);
    }
  });
  const sep = document.createElement('span');
  sep.className = 'tb-sep tb-table-only';
  host.appendChild(sep);
  addGroup(TABLE_GROUP, 'tb-table-only');
  return host;
}

/** Light up what is on at the cursor; show table tools only in a table. */
export function updateToolbar(host, editor) {
  const on = {
    h1: editor.isActive('heading', { level: 1 }),
    h2: editor.isActive('heading', { level: 2 }),
    bullet: editor.isActive('bulletList'),
    ordered: editor.isActive('orderedList'),
    task: editor.isActive('taskList'),
    bold: editor.isActive('bold'),
    italic: editor.isActive('italic'),
    strike: editor.isActive('strike'),
    code: editor.isActive('code'),
    link: editor.isActive('link'),
  };
  host.querySelectorAll('.tb').forEach((b) => {
    const c = b.dataset.cmd;
    if (c in on) b.classList.toggle('active', on[c]);
    if (c === 'undo') b.disabled = !editor.can().undo();
    if (c === 'redo') b.disabled = !editor.can().redo();
  });
  host.classList.toggle('in-table', editor.isActive('table'));
}
