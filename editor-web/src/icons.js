// Line icons, 16-unit grid, drawn with currentColor so they follow the theme.
const P = {
  undo: '<path d="M3 7h6.5a3.5 3.5 0 0 1 0 7H6"/><path d="M5.5 4.5 3 7l2.5 2.5"/>',
  redo: '<path d="M13 7H6.5a3.5 3.5 0 0 0 0 7H10"/><path d="m10.5 4.5 2.5 2.5-2.5 2.5"/>',
  bold: '<path d="M4.5 3h4a2.5 2.5 0 0 1 0 5h-4zM4.5 8h4.5a2.5 2.5 0 0 1 0 5H4.5z"/>',
  italic: '<path d="M10 3H6.5M9.5 13H6M9 3 7 13"/>',
  strike: '<path d="M3 8h10"/><path d="M10.5 5A2.5 2.5 0 0 0 8 3.5c-1.5 0-2.5.8-2.5 2 0 3 5.5 1.5 5.5 4.5 0 1.2-1.2 2-2.7 2A2.8 2.8 0 0 1 5 11.5"/>',
  code: '<path d="m5.5 5-3 3 3 3M10.5 5l3 3-3 3"/>',
  link: '<path d="M6.8 9.2a2.6 2.6 0 0 0 3.7 0l2.2-2.2a2.6 2.6 0 0 0-3.7-3.7l-.8.8"/><path d="M9.2 6.8a2.6 2.6 0 0 0-3.7 0L3.3 9a2.6 2.6 0 0 0 3.7 3.7l.8-.8"/>',
  bullets: '<path d="M6 4h7.5M6 8h7.5M6 12h7.5"/><circle cx="3" cy="4" r=".8" fill="currentColor"/><circle cx="3" cy="8" r=".8" fill="currentColor"/><circle cx="3" cy="12" r=".8" fill="currentColor"/>',
  numbered: '<path d="M6.5 4h7M6.5 8h7M6.5 12h7"/><path d="M2.5 3.5 3.5 3v3.2M2.4 9.7c0-.6 1.9-.6 1.9.3 0 .7-1.9 1.4-1.9 2h2"/>',
  task: '<rect x="2.5" y="2.5" width="11" height="11" rx="2.5"/><path d="m5.5 8.2 1.8 1.8 3.2-3.8"/>',
  date: '<rect x="2" y="3" width="12" height="10.5" rx="2"/><path d="M2 6.5h12M5.5 1.8v2.4M10.5 1.8v2.4"/>',
  table: '<rect x="2" y="3" width="12" height="10" rx="1.8"/><path d="M2 7h12M2 10h12M6.5 3v10"/>',
  quote: '<path d="M3 11V8.2C3 6 4 4.8 6 4.5M9 11V8.2C9 6 10 4.8 12 4.5"/><path d="M3 11h3V8H3zM9 11h3V8H9z"/>',
  rule: '<path d="M2.5 8h11"/>',
  rowAdd: '<path d="M2.5 4h11M2.5 8h11"/><path d="M8 10.5v4M6 12.5h4"/>',
  rowDel: '<path d="M2.5 4h11M2.5 8h11"/><path d="m6 11 4 3M10 11l-4 3"/>',
  colAdd: '<path d="M4 2.5v11M8 2.5v11"/><path d="M12.5 6v4M10.5 8h4"/>',
  colDel: '<path d="M4 2.5v11M8 2.5v11"/><path d="m11 6 3 4M14 6l-3 4"/>',
  tableDel: '<rect x="2" y="3" width="12" height="10" rx="1.8"/><path d="m6 6 4 4M10 6l-4 4"/>',
};
export const icon = (name) => `<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[name] || ''}</svg>`;
