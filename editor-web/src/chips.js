// Date stamps and [[note links]] drawn as small chips. They are decorations
// only: the characters stay in the file exactly as written.
import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';
import { pill, toAscii } from './jalali.js';

const STAMP = /@([\d۰-۹٠-٩]{3,4})[/-]([\d۰-۹٠-٩]{1,2})[/-]([\d۰-۹٠-٩]{1,2})/g;
const NOTE = /\[\[([^\]\n]+)\]\]/g;

function scan(doc) {
  const out = [];
  doc.descendants((node, pos, parent) => {
    if (!node.isText || (parent && parent.type.name === 'codeBlock')) return;
    if (node.marks.some((m) => m.type.name === 'code')) return;
    const text = node.text;
    let m;
    STAMP.lastIndex = 0;
    while ((m = STAMP.exec(text)) !== null) {
      const p = pill(Number(toAscii(m[1])), Number(toAscii(m[2])), Number(toAscii(m[3])));
      if (!p) continue;
      const tone = p.delta < 0 ? 'late' : p.delta === 0 ? 'today' : 'soon';
      out.push(Decoration.inline(pos + m.index, pos + m.index + m[0].length, {
        class: `chip chip-date chip-${tone}`,
        'data-label': p.label,
      }));
    }
    NOTE.lastIndex = 0;
    while ((m = NOTE.exec(text)) !== null) {
      out.push(Decoration.inline(pos + m.index, pos + m.index + m[0].length, {
        class: 'chip chip-note',
        'data-target': m[1].split('|')[0].trim(),
      }));
    }
  });
  return DecorationSet.create(doc, out);
}

export const Chips = Extension.create({
  name: 'chips',
  addProseMirrorPlugins() {
    return [new Plugin({
      key: new PluginKey('chips'),
      state: {
        init: (_, { doc }) => scan(doc),
        apply: (tr, old) => (tr.docChanged ? scan(tr.doc) : old),
      },
      props: {
        decorations(state) { return this.getState(state); },
        handleClick: (view, pos, event) => {
          const el = event.target;
          if (el && el.classList && el.classList.contains('chip-note') && (event.ctrlKey || event.metaKey || !view.editable)) {
            const target = el.getAttribute('data-target');
            if (target && window.__noteLink) { window.__noteLink(target); return true; }
          }
          return false;
        },
      },
    })];
  },
});
