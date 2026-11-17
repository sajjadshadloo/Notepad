// A browser-like DOM for running TipTap under Node.
import { Window } from 'happy-dom';

const win = new Window();
for (const name of [
  'document', 'navigator', 'Node', 'HTMLElement', 'Element', 'DocumentFragment',
  'MutationObserver', 'Text', 'DOMParser', 'Range', 'Selection', 'KeyboardEvent',
  'Event', 'CustomEvent', 'ClipboardEvent', 'DragEvent', 'InputEvent',
]) {
  if (win[name] !== undefined && globalThis[name] === undefined) globalThis[name] = win[name];
}
globalThis.window = win;
globalThis.getComputedStyle = win.getComputedStyle.bind(win);

const { Editor } = await import('@tiptap/core');
const { createExtensions } = await import('../src/extensions.js');

/** A real TipTap editor with the app's extensions, detached from any page. */
export function makeEditor() {
  return new Editor({ element: document.createElement('div'), extensions: createExtensions() });
}
