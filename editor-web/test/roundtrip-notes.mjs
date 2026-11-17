// Spike: does TipTap's Markdown round-trip every real note byte for byte?
import { Window } from 'happy-dom';
import fs from 'node:fs';
import path from 'node:path';
const win = new Window();
for (const k of ['window','document','navigator','Node','HTMLElement','Element','DocumentFragment','MutationObserver','getComputedStyle','Text','DOMParser','Range','Selection','KeyboardEvent','Event','CustomEvent']) {
  try { globalThis[k] = k === 'window' ? win : (win[k] && typeof win[k] === 'function' && k === 'getComputedStyle') ? win.getComputedStyle.bind(win) : win[k]; } catch {}
}
const { Editor } = await import('@tiptap/core');
const { default: StarterKit } = await import('@tiptap/starter-kit');
const { Markdown } = await import('@tiptap/markdown');
const { TaskList, TaskItem } = await import('@tiptap/extension-list');
const { TableKit } = await import('@tiptap/extension-table');

const root = process.argv[2];
const files = [];
(function walk(d) { for (const e of fs.readdirSync(d, { withFileTypes: true })) {
  const p = path.join(d, e.name);
  if (e.isDirectory()) walk(p); else if (/\.(md|txt)$/i.test(e.name)) files.push(p);
}})(root);
let same = 0; const diffs = [];
for (const f of files) {
  const src = fs.readFileSync(f, 'utf8');
  const el = document.createElement('div');
  const ed = new Editor({ element: el, extensions: [StarterKit, Markdown, TaskList, TaskItem.configure({ nested: true }), TableKit], content: src, contentType: 'markdown' });
  const out = ed.getMarkdown();
  ed.destroy();
  if (out === src) same++;
  else {
    const a = src.split('\n'), b = out.split('\n');
    let i = 0; while (i < a.length && a[i] === b[i]) i++;
    diffs.push({ f: path.relative(root, f), line: i + 1, src: (a[i] ?? '<EOF>').slice(0, 70), out: (b[i] ?? '<EOF>').slice(0, 70), lenSrc: src.length, lenOut: out.length });
  }
}
console.log(`files ${files.length}, identical ${same}, different ${diffs.length}`);
for (const d of diffs.slice(0, 25)) console.log(JSON.stringify(d));
