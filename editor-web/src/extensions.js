// The one list of TipTap extensions, shared by the desktop app, the
// Telegram Mini App and the PWA, so all three read a note the same way.
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from '@tiptap/markdown';
import Link from '@tiptap/extension-link';
import HardBreak from '@tiptap/extension-hard-break';
import { TaskList, TaskItem } from '@tiptap/extension-list';
import { TableKit } from '@tiptap/extension-table';
import { Placeholder } from '@tiptap/extensions';
import { SourceKey } from './lossless.js';
import { Chips } from './chips.js';

export function createExtensions() {
  return [
    StarterKit.configure({ link: false, hardBreak: false }),
    // An address written as itself is saved as itself, not as [url](url),
    // and typing or pasting one does not turn it into a link.
    Link.extend({
      renderMarkdown(node, h, context) {
        const href = (node.attrs && node.attrs.href) || '';
        const text = h.renderChildren(node);
        // Marks are rendered around a placeholder; the real words arrive
        // in meta.markText.
        const words = context && context.meta && context.meta.markText;
        return words === href ? text : `[${text}](${href})`;
      },
    }).configure({ autolink: false, linkOnPaste: false, openOnClick: false }),
    // A line break inside a line is written the way the notes already
    // write it (in table cells especially): <br>.
    HardBreak.extend({ renderMarkdown: () => '<br>' }),
    Markdown,
    TaskList,
    TaskItem.configure({ nested: true }),
    TableKit,
    SourceKey,
    Chips,
    Placeholder.configure({ placeholder: 'بنویس…' }),
  ];
}
