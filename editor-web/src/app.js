// The editor page: toolbar + TipTap + the bridge to whoever hosts it (the
// desktop app today; the Mini App and PWA later). Everything the host can do
// is on `window.NotepadEditor`; everything the page tells the host goes
// through `host`.
import { Editor } from '@tiptap/core';
import { createExtensions } from './extensions.js';
import { load, remember, saveDetailed, verbatim } from './lossless.js';
import { buildToolbar, updateToolbar } from './toolbar.js';
import { stampFor } from './jalali.js';

const noop = () => {};

export function createApp(root, host = {}) {
  const h = { changed: noop, dirty: noop, cursor: noop, ready: noop, noteLink: noop, dateRequested: noop, zoom: noop, ...host };
  root.innerHTML = '<div class="toolbar"></div><div class="scroller"><div class="page"></div></div>';
  const toolbarEl = root.querySelector('.toolbar');
  const pageEl = root.querySelector('.page');
  const scroller = root.querySelector('.scroller');

  let editor = null;
  let state = null;
  let lastText = null;
  let starts = [];
  let timer = null;

  const text = () => {
    if (!editor) return '';
    const out = saveDetailed(editor.markdown, state, editor.getJSON());
    starts = out.starts;
    return out.text;
  };

  function push(force = false) {
    clearTimeout(timer);
    timer = null;
    const now = text();
    if (force || now !== lastText) {
      lastText = now;
      h.changed(now);
    }
  }
  const schedulePush = () => {
    if (!timer) timer = setTimeout(() => push(), 80);
  };

  function cursorInfo() {
    if (!editor) return;
    const { selection, doc } = editor.state;
    const $from = selection.$from;
    const top = $from.depth ? $from.index(0) : 0;
    let line = starts[top] ?? 0;
    // Inside a list the caret is on the item's own line, not the list's first.
    for (let d = $from.depth; d >= 1; d -= 1) {
      const key = $from.node(d).attrs && $from.node(d).attrs.srcKey;
      if (key && String(key).includes('.')) {
        const [c, i] = String(key).split('.').map(Number);
        const chunk = state.chunks[c];
        if (chunk && chunk.items && chunk.items[i]) line += chunk.items[i].from;
        break;
      }
    }
    h.cursor({
      line: line + 1,
      column: $from.parentOffset + 1,
      selected: selection.empty ? 0 : doc.textBetween(selection.from, selection.to, ' ').length,
      block: top,
    });
  }

  function mount(markdownText, keepSelection = null) {
    if (editor) editor.destroy();
    pageEl.innerHTML = '';
    editor = new Editor({
      element: pageEl,
      extensions: createExtensions(),
      editorProps: { attributes: { spellcheck: 'false', 'data-gramm': 'false' } },
    });
    verbatim(editor.markdown);
    const loaded = load(editor.markdown, markdownText);
    editor.commands.setContent(loaded.doc, { emitUpdate: false });
    state = loaded.state;
    remember(state, editor.getJSON());
    lastText = text();
    if (keepSelection != null) {
      const size = editor.state.doc.content.size;
      editor.commands.setTextSelection(Math.min(keepSelection, Math.max(1, size - 1)));
    }
    editor.on('update', () => {
      h.dirty();
      schedulePush();
      updateToolbar(toolbarEl, editor);
    });
    editor.on('selectionUpdate', () => {
      updateToolbar(toolbarEl, editor);
      cursorInfo();
    });
    updateToolbar(toolbarEl, editor);
    cursorInfo();
  }

  // Commands

  const insertText = (value) => editor.chain().focus().insertContent(value).run();

  const COMMANDS = {
    undo: () => editor.chain().focus().undo().run(),
    redo: () => editor.chain().focus().redo().run(),
    h1: () => editor.chain().focus().toggleHeading({ level: 1 }).run(),
    h2: () => editor.chain().focus().toggleHeading({ level: 2 }).run(),
    h3: () => editor.chain().focus().toggleHeading({ level: 3 }).run(),
    bullet: () => editor.chain().focus().toggleBulletList().run(),
    ordered: () => editor.chain().focus().toggleOrderedList().run(),
    task: () => editor.chain().focus().toggleTaskList().run(),
    bold: () => editor.chain().focus().toggleBold().run(),
    italic: () => editor.chain().focus().toggleItalic().run(),
    strike: () => editor.chain().focus().toggleStrike().run(),
    code: () => editor.chain().focus().toggleCode().run(),
    quote: () => editor.chain().focus().toggleBlockquote().run(),
    rule: () => editor.chain().focus().setHorizontalRule().run(),
    link: () => askLink(),
    date: () => h.dateRequested(),
    today: () => insertText(`${stampFor()} `),
    table: () => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(),
    addRow: () => editor.chain().focus().addRowAfter().run(),
    delRow: () => editor.chain().focus().deleteRow().run(),
    addCol: () => editor.chain().focus().addColumnAfter().run(),
    delCol: () => editor.chain().focus().deleteColumn().run(),
    delTable: () => editor.chain().focus().deleteTable().run(),
    selectAll: () => editor.chain().focus().selectAll().run(),
  };

  function askLink() {
    const current = editor.getAttributes('link').href || '';
    const box = document.createElement('div');
    box.className = 'popover';
    box.innerHTML = '<input type="text" dir="ltr" placeholder="https://…" /><button type="button">تأیید</button>';
    const input = box.querySelector('input');
    const ok = box.querySelector('button');
    input.value = current;
    const close = () => {
      box.remove();
      editor.commands.focus();
    };
    ok.addEventListener('click', () => {
      const url = input.value.trim();
      if (url) editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run();
      else editor.chain().focus().unsetLink().run();
      close();
    });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); ok.click(); }
      if (e.key === 'Escape') { e.preventDefault(); close(); }
    });
    root.appendChild(box);
    input.focus();
  }

  buildToolbar(toolbarEl, (command) => {
    if (editor && COMMANDS[command]) COMMANDS[command]();
  });

  // The shortcuts the old editor had.
  root.addEventListener('keydown', (e) => {
    if (!editor || !(e.ctrlKey || e.metaKey) || e.altKey) return;
    const k = e.key.toLowerCase();
    const heading = { 1: 'h1', 2: 'h2', 3: 'h3' };
    if (!e.shiftKey && heading[k]) { e.preventDefault(); COMMANDS[heading[k]](); }
    else if (e.shiftKey && k === '8') { e.preventDefault(); COMMANDS.bullet(); }
    else if (e.shiftKey && k === '7') { e.preventDefault(); COMMANDS.ordered(); }
    else if (e.shiftKey && k === '9') { e.preventDefault(); COMMANDS.task(); }
    else if (e.shiftKey && k === 'a') { e.preventDefault(); COMMANDS.date(); }
  });

  // Look

  const theme = (vars = {}) => {
    for (const [k, v] of Object.entries(vars)) root.style.setProperty(`--${k}`, v);
  };
  const direction = (mode) => { root.dataset.direction = mode; };
  const width = (full) => { root.dataset.width = full ? 'full' : 'column'; };
  function font({ families, size, faces } = {}) {
    if (faces && faces.length) {
      let css = document.getElementById('face-css');
      if (!css) {
        css = document.createElement('style');
        css.id = 'face-css';
        document.head.appendChild(css);
      }
      css.textContent = faces
        .map((f) => `@font-face{font-family:"${f.family}";src:url("${f.url}");font-weight:${f.weight || 400};}`)
        .join('\n');
    }
    if (families) root.style.setProperty('--font', families);
    if (size) root.style.setProperty('--size', `${size}px`);
  }

  scroller.addEventListener('wheel', (e) => {
    if (e.ctrlKey) { e.preventDefault(); h.zoom(e.deltaY < 0 ? 1 : -1); }
  }, { passive: false });

  window.__noteLink = (target) => h.noteLink(target);

  const api = {
    open: (value) => mount(value),
    // An outside edit (a task ticked elsewhere): reload, keep the caret.
    replace: (value) => {
      mount(value, editor ? editor.state.selection.from : null);
      push(true);
    },
    text: () => text(),
    flush: () => { push(true); return lastText; },
    cmd: (name, arg) => {
      if (name === 'insertText') insertText(arg);
      else if (COMMANDS[name]) COMMANDS[name](arg);
    },
    focus: () => editor && editor.commands.focus(),
    theme, direction, font, width,
    goToLine: (line) => {
      if (!editor) return;
      let target = 0;
      for (let i = 0; i < starts.length; i += 1) if (starts[i] <= line - 1) target = i;
      let pos = 1;
      let index = 0;
      editor.state.doc.forEach((node, offset) => {
        if (index === target) pos = offset + 1;
        index += 1;
      });
      editor.chain().focus().setTextSelection(pos).scrollIntoView().run();
    },
    selectedText: () => (editor
      ? editor.state.doc.textBetween(editor.state.selection.from, editor.state.selection.to, '\n')
      : ''),
    scrollToTop: () => { scroller.scrollTop = 0; },
  };
  mount('');
  h.ready();
  return api;
}
