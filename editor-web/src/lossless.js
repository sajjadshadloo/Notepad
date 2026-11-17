// Lossless Markdown for TipTap.
//
// A note is the user's file, not ours. TipTap's own Markdown round trip
// rewrites it: tables are re-padded, CRLF and trailing spaces vanish, lines
// written one under another are merged into a paragraph. Measured on the
// owner's 29 real notes, only 2 came back unchanged.
//
// So the file is cut into chunks whose exact source text is kept, every
// top-level node (and every list item) remembers which chunk it came from,
// and on save a chunk the user did not touch is written back byte for byte.
// Only what was edited goes through TipTap's serializer.
//
// Chunks follow how a Notepad user writes, not how CommonMark parses:
//   - every ordinary line is its own paragraph (lines never merge)
//   - a blank line is an empty paragraph you can see and delete
//   - a heading, a rule, a fenced code block, a table, a quote, a list
//     (with its indented continuation lines) are one chunk each.

import { Extension } from '@tiptap/core';

export const KEY = 'srcKey';

const TOP_TYPES = [
  'paragraph', 'heading', 'bulletList', 'orderedList', 'taskList',
  'table', 'codeBlock', 'blockquote', 'horizontalRule',
];
const ITEM_TYPES = ['listItem', 'taskItem'];
const LIST_TYPES = ['bulletList', 'orderedList', 'taskList'];

/** Gives top-level nodes and list items an invisible source key. */
export const SourceKey = Extension.create({
  name: 'sourceKey',
  addGlobalAttributes() {
    return [{
      types: [...TOP_TYPES, ...ITEM_TYPES],
      attributes: {
        [KEY]: {
          default: null,
          rendered: false,
          // A split or a new line is new text: it must not claim the
          // original's bytes.
          keepOnSplit: false,
        },
      },
    }];
  },
});

// Line classification

const BLANK = /^[ \t]*$/;
const HEADING = /^ {0,3}#{1,6}(\s|$)/;
const RULE = /^ {0,3}([-*_])([ \t]*\1){2,}[ \t]*$/;
const FENCE = /^ {0,3}(`{3,}|~{3,})/;
const TABLE = /^[ \t]*\|/;
const QUOTE = /^ {0,3}>/;
const LIST = /^([ \t]*)([-*+]|\d{1,9}[.)])([ \t]+|$)/;

/** Split text into lines, each with the exact terminator that ended it. */
function lines(text) {
  const out = [];
  const re = /\r\n|\n|\r/g;
  let start = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    out.push({ body: text.slice(start, m.index), term: m[0] });
    start = m.index + m[0].length;
  }
  if (start < text.length) out.push({ body: text.slice(start), term: '' });
  return out;
}

/**
 * Cut a note into chunks. Each chunk keeps its exact text: `body` is every
 * line with its terminator except the last line's, `term` is that last one.
 */
export function splitChunks(text) {
  const ls = lines(text);
  const chunks = [];
  const push = (kind, from, to, extra = {}) => {
    const part = ls.slice(from, to);
    const body = part.map((l, i) => l.body + (i < part.length - 1 ? l.term : '')).join('');
    chunks.push({ kind, body, term: part[part.length - 1].term, lines: part, ...extra });
  };
  let i = 0;
  while (i < ls.length) {
    const line = ls[i].body;
    if (BLANK.test(line)) { push('blank', i, i + 1); i += 1; continue; }
    const fence = FENCE.exec(line);
    if (fence) {
      const mark = fence[1][0];
      const size = fence[1].length;
      let j = i + 1;
      while (j < ls.length && !new RegExp(`^ {0,3}\\${mark}{${size},}[ \\t]*$`).test(ls[j].body)) j += 1;
      j = Math.min(j + 1, ls.length);
      push('code', i, j); i = j; continue;
    }
    if (HEADING.test(line)) { push('heading', i, i + 1); i += 1; continue; }
    if (RULE.test(line)) { push('rule', i, i + 1); i += 1; continue; }
    if (TABLE.test(line)) {
      let j = i + 1;
      while (j < ls.length && TABLE.test(ls[j].body)) j += 1;
      push('table', i, j); i = j; continue;
    }
    if (QUOTE.test(line)) {
      let j = i + 1;
      while (j < ls.length && QUOTE.test(ls[j].body)) j += 1;
      push('quote', i, j); i = j; continue;
    }
    const list = LIST.exec(line);
    if (list) {
      const base = list[1].length;
      const items = [[i, i + 1]];
      let j = i + 1;
      while (j < ls.length && !BLANK.test(ls[j].body)) {
        const next = LIST.exec(ls[j].body);
        const indent = ls[j].body.length - ls[j].body.trimStart().length;
        if (next && next[1].length === base) items.push([j, j + 1]);
        else if (indent > base) items[items.length - 1][1] = j + 1;
        else break;
        j += 1;
      }
      push('list', i, j, { items: items.map(([a, b]) => ({ from: a - i, to: b - i })) });
      i = j; continue;
    }
    push('paragraph', i, i + 1); i += 1;
  }
  return chunks;
}

// Loading

const strip = (node) => {
  if (!node || typeof node !== 'object') return node;
  const copy = { ...node };
  if (copy.attrs) {
    const { [KEY]: _drop, ...rest } = copy.attrs;
    copy.attrs = rest;
  }
  if (copy.content) copy.content = copy.content.map(strip);
  return copy;
};
const canon = (nodes) => JSON.stringify(nodes.map(strip));

const plainParagraph = (text) => (
  text ? { type: 'paragraph', content: [{ type: 'text', text }] } : { type: 'paragraph' }
);

function chunkNodes(markdown, chunk) {
  if (chunk.kind === 'blank') return [{ type: 'paragraph' }];
  const source = chunk.lines.map((l) => l.body).join('\n');
  let nodes = [];
  try {
    nodes = markdown.parse(source).content || [];
  } catch {
    nodes = [];
  }
  // A line the parser has no node for (stray HTML, say) still has to be on
  // screen, as the words that are in the file.
  if (!nodes.length) nodes = [plainParagraph(source)];
  return nodes;
}

/**
 * Parse a note into a TipTap document plus the state needed to write it
 * back. Pass the document to `editor.commands.setContent`, then call
 * `remember(state, editor.getJSON())` so comparisons use the editor's own
 * normalised form.
 */
/**
 * Write typed text as typed. The stock serializer turns `&` into `&amp;`
 * and puts a backslash before `* _ [ ]`; in a notepad that is the program
 * rewriting what the user wrote. `[[note]]` links rely on this too.
 */
export function verbatim(markdown) {
  if (!markdown.__verbatim) {
    markdown.encodeTextForMarkdown = (value) => value;
    markdown.__verbatim = true;
  }
  return markdown;
}

export function load(markdown, text) {
  verbatim(markdown);
  const chunks = splitChunks(text);
  const content = [];
  chunks.forEach((chunk, c) => {
    const nodes = chunkNodes(markdown, chunk);
    let item = 0;
    for (const node of nodes) {
      node.attrs = { ...(node.attrs || {}), [KEY]: String(c) };
      if (chunk.kind === 'list' && LIST_TYPES.includes(node.type)) {
        for (const child of node.content || []) {
          child.attrs = { ...(child.attrs || {}), [KEY]: `${c}.${item}` };
          item += 1;
        }
      }
      content.push(node);
    }
    // Item-level write-back needs one parsed item per source item.
    chunk.itemsMatch = chunk.kind === 'list' && chunk.items && item === chunk.items.length;
  });
  if (!content.length) content.push({ type: 'paragraph' });
  const state = {
    chunks,
    original: new Map(),
    items: new Map(),
    eol: (text.match(/\r\n|\n|\r/) || ['\n'])[0],
    endsWithNewline: /(\r\n|\n|\r)$/.test(text),
  };
  return { doc: { type: 'doc', content }, state };
}

/** Record how the editor itself holds every chunk, after setContent. */
export function remember(state, json) {
  state.original.clear();
  state.items.clear();
  for (const [key, group] of groups(json.content || [])) {
    if (!state.original.has(key)) state.original.set(key, canon(group));
    for (const node of group) {
      for (const child of node.content || []) {
        const k = child.attrs && child.attrs[KEY];
        if (k != null && !state.items.has(k)) state.items.set(k, canon([child]));
      }
    }
  }
}

function groups(nodes) {
  const out = [];
  let i = 0;
  while (i < nodes.length) {
    const key = nodes[i].attrs && nodes[i].attrs[KEY];
    let j = i + 1;
    if (key != null) while (j < nodes.length && nodes[j].attrs && nodes[j].attrs[KEY] === key) j += 1;
    out.push([key ?? null, nodes.slice(i, j)]);
    i = j;
  }
  return out;
}

// Saving

const trimEnd = (s) => s.replace(/(\r\n|\n|\r)+$/, '');

function serializeNodes(markdown, nodes, eol) {
  return nodes.map((node) => {
    if (node.type === 'paragraph' && !(node.content && node.content.length)) return '';
    return trimEnd(markdown.serialize({ type: 'doc', content: [strip(node)] }))
      .replace(/^(\r\n|\n|\r)+/, '');
  }).join(eol).replace(/\r\n|\n|\r/g, eol);
}

function writeList(markdown, state, chunk, group) {
  // Keep untouched items byte for byte; rewrite only the changed ones.
  const out = [];
  for (const node of group) {
    if (!LIST_TYPES.includes(node.type)) {
      out.push(serializeNodes(markdown, [node], state.eol));
      continue;
    }
    let number = node.attrs && node.attrs.start != null ? node.attrs.start : 1;
    for (const child of node.content || []) {
      const key = child.attrs && child.attrs[KEY];
      const idx = key != null && key.includes('.') ? Number(key.split('.')[1]) : -1;
      const raw = idx >= 0 && chunk.items[idx];
      if (raw && state.items.get(key) === canon([child])) {
        const part = chunk.lines.slice(raw.from, raw.to);
        out.push(part.map((l, i) => l.body + (i < part.length - 1 ? l.term : '')).join(''));
      } else {
        const attrs = { ...(node.attrs || {}) };
        if (node.type === 'orderedList') attrs.start = number;
        out.push(serializeNodes(markdown, [{ ...node, attrs, content: [child] }], state.eol));
      }
      number += 1;
    }
  }
  return out.join(state.eol);
}

/** Write the editor's document back as the note's text. */
export function save(markdown, state, json) {
  const nodes = [...(json.content || [])];
  // TipTap keeps an empty paragraph after a final table or list so the
  // cursor has somewhere to go. It is the editor's, not the user's.
  const tail = nodes[nodes.length - 1];
  if (nodes.length > 1 && tail && tail.type === 'paragraph'
      && !(tail.content && tail.content.length) && !(tail.attrs && tail.attrs[KEY] != null)) {
    nodes.pop();
  }
  const pieces = [];
  for (const [key, group] of groups(nodes)) {
    const chunk = key != null ? state.chunks[Number(key)] : null;
    if (chunk && state.original.get(key) === canon(group)) {
      pieces.push({ body: chunk.body, term: chunk.term });
    } else if (chunk && chunk.itemsMatch && group.every((n) => LIST_TYPES.includes(n.type))) {
      pieces.push({ body: writeList(markdown, state, chunk, group), term: chunk.term });
    } else {
      pieces.push({ body: serializeNodes(markdown, group, state.eol), term: null });
    }
  }
  let text = '';
  pieces.forEach((piece, i) => {
    const last = i === pieces.length - 1;
    text += piece.body;
    if (!last) text += piece.term || state.eol;
    else if (state.endsWithNewline) text += piece.term || state.eol;
  });
  // An untouched empty note stays empty, not one blank line.
  if (pieces.length === 1 && pieces[0].body === '' && !state.chunks.length) return '';
  return text;
}

