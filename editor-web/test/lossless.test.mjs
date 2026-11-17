// The promise: a note opened and saved without editing is byte-identical,
// and an edit changes only what was edited.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { makeEditor } from './dom.mjs';
import { load, remember, save, splitChunks } from '../src/lossless.js';

function open(text) {
  const editor = makeEditor();
  const { doc, state } = load(editor.markdown, text);
  editor.commands.setContent(doc);
  remember(state, editor.getJSON());
  return { editor, state, write: () => save(editor.markdown, state, editor.getJSON()) };
}

const SAMPLES = {
  crlf: '# عنوان\r\n\r\nخط اول\r\nخط دوم  \r\n',
  noFinalNewline: 'تنها خط',
  empty: '',
  blankLines: 'الف\n\n\nب\n',
  table: '| پروژه | وضعیت |\n| :--- | :---: |\n| ایونت | فعال |\n',
  tasks: '- [ ] یک\n- [x] دو\n  ادامهٔ دو\n- [ ] سه\n',
  numbered: '1. اول\n2. دوم\n',
  mixed: 'متن & علامت\nhttps://example.com\n---\n```\ncode\n```\n> نقل\n',
  stamps: 'یادداشت @۱۴۰۵/۰۸/۲۶\n[[mypetty]] پیوند\n',
};

for (const [name, text] of Object.entries(SAMPLES)) {
  test(`unchanged round trip: ${name}`, () => {
    const { write, editor } = open(text);
    assert.equal(write(), text);
    editor.destroy();
  });
}

test('lines written one under another stay separate paragraphs', () => {
  const chunks = splitChunks('اول\nدوم\n');
  assert.deepEqual(chunks.map((c) => c.kind), ['paragraph', 'paragraph']);
});

test('editing one line rewrites only that line', () => {
  const text = 'اول\r\nدوم  \r\n| a | b |\r\n|---|---|\r\n| 1 | 2 |\r\n';
  const { editor, write } = open(text);
  // Replace the first paragraph's text.
  editor.commands.setTextSelection({ from: 1, to: 4 });
  editor.commands.insertContent('تازه');
  assert.equal(write(), 'تازه\r\nدوم  \r\n| a | b |\r\n|---|---|\r\n| 1 | 2 |\r\n');
  editor.destroy();
});

test('ticking one task rewrites only that item', () => {
  const text = '* [ ] یک\n- [ ]   دو   \n- [ ] سه\n';
  const { editor, write } = open(text);
  // Find the second task item and check it.
  let pos = null;
  let seen = 0;
  editor.state.doc.descendants((node, p) => {
    if (node.type.name === 'taskItem') { seen += 1; if (seen === 2) pos = p; }
  });
  editor.view.dispatch(editor.state.tr.setNodeMarkup(pos, undefined, {
    ...editor.state.doc.nodeAt(pos).attrs, checked: true,
  }));
  const out = write().split('\n');
  assert.equal(out[0], '* [ ] یک');
  assert.match(out[1], /^- \[x\] +دو/);
  assert.equal(out[2], '- [ ] سه');
  editor.destroy();
});

test('a new line typed at the end is added, the rest untouched', () => {
  const text = 'اول\nدوم';
  const { editor, write } = open(text);
  editor.commands.setTextSelection(editor.state.doc.content.size - 1);
  editor.commands.splitBlock();
  editor.commands.insertContent('سوم');
  assert.equal(write(), 'اول\nدوم\nسوم');
  editor.destroy();
});

test('deleting a line removes just that line', () => {
  const text = 'اول\nدوم\nسوم\n';
  const { editor, write } = open(text);
  const json = editor.getJSON();
  json.content.splice(1, 1);
  editor.commands.setContent(json);
  assert.equal(write(), 'اول\nسوم\n');
  editor.destroy();
});

// The real notes, when they are on this machine.
const NOTES = process.env.NOTES_DIR || 'C:/Users/Sajjad-PC/Documents/Notepad';
const files = [];
if (fs.existsSync(NOTES)) {
  (function walk(d) {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (/\.(md|txt)$/i.test(e.name)) files.push(p);
    }
  })(NOTES);
}
for (const file of files) {
  test(`real note unchanged: ${path.relative(NOTES, file)}`, () => {
    const text = fs.readFileSync(file, 'utf8');
    const { write, editor } = open(text);
    assert.equal(write(), text);
    editor.destroy();
  });
}

// An edited line is written as typed, not as escaped Markdown.
function appendToFirstBlock(text, extra) {
  const { editor, write } = open(text);
  let end = null;
  editor.state.doc.descendants((n, p) => {
    if (end === null && n.isTextblock) end = p + n.nodeSize - 1;
  });
  editor.commands.setTextSelection(end);
  editor.commands.insertContent(extra);
  const out = write();
  editor.destroy();
  return out;
}

const VERBATIM = {
  'x & y\n': 'x & y +\n',
  'قیمت ۱۵٪ * ۲\n': 'قیمت ۱۵٪ * ۲ +\n',
  'snake_case_name\n': 'snake_case_name +\n',
  'https://example.com/a_b\n': 'https://example.com/a_b +\n',
  '[[mypetty]] و یادداشت\n': '[[mypetty]] و یادداشت +\n',
  '@۱۴۰۵/۰۸/۲۶ جلسه\n': '@۱۴۰۵/۰۸/۲۶ جلسه +\n',
  '**پررنگ** و متن\n': '**پررنگ** و متن +\n',
};
for (const [before, after] of Object.entries(VERBATIM)) {
  test(`an edited line keeps what was typed: ${JSON.stringify(before)}`, () => {
    assert.equal(appendToFirstBlock(before, ' +'), after);
  });
}

test('an edited table does not gain a blank line above it', () => {
  const out = appendToFirstBlock('| a | b |\n|---|---|\n| 1 | 2 |\n', '+');
  assert.ok(out.startsWith('| a'), out);
  assert.ok(!out.includes('\n\n'), out);
});

test('a line added inside a Windows (CRLF) note uses CRLF too', () => {
  const text = 'اول\r\nدوم\r\n';
  const { editor, write } = open(text);
  editor.commands.setTextSelection(4); // end of the first line
  editor.commands.splitBlock();
  editor.commands.insertContent('وسط');
  assert.equal(write(), 'اول\r\nوسط\r\nدوم\r\n');
  editor.destroy();
});

test('editing a table leaves the lines around it alone', () => {
  const text = 'بالا  \n| a | b |\n|:---|---:|\n| 1 | 2 |\nپایین\t\n';
  const { editor, write } = open(text);
  let cell = null;
  editor.state.doc.descendants((n, p) => {
    if (cell === null && n.type.name === 'tableCell') cell = p + n.nodeSize - 2;
  });
  editor.commands.setTextSelection(cell);
  editor.commands.insertContent('9');
  const out = write().split('\n');
  assert.equal(out[0], 'بالا  ');
  assert.equal(out[out.length - 2], 'پایین\t');
  assert.ok(out.some((l) => l.includes('19') || l.includes('29')), out.join('\n'));
  editor.destroy();
});
