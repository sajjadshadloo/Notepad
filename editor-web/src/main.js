// Entry for the Qt WebEngine page. In a plain browser (the Mini App, the PWA,
// a development tab) there is no `qt` object and the host is a stub.
import './styles.css';
import './page.css';
import { createApp } from './app.js';

function start(bridge) {
  const host = bridge
    ? {
      changed: (t) => bridge.changed(t),
      dirty: () => bridge.dirty(),
      zoom: (d) => bridge.zoom(d),
      cursor: (c) => bridge.cursor(c.line, c.column, c.selected, c.endLine),
      ready: () => bridge.ready(),
      noteLink: (t) => bridge.noteLink(t),
      dateRequested: () => bridge.dateRequested(),
      openUrl: (u) => bridge.openUrl(u),
    }
    : {};
  window.NotepadEditor = createApp(document.getElementById('app'), host);
}

if (typeof qt !== 'undefined' && qt.webChannelTransport) {
  const s = document.createElement('script');
  s.src = 'qrc:///qtwebchannel/qwebchannel.js';
  s.onload = () => new window.QWebChannel(qt.webChannelTransport, (ch) => start(ch.objects.bridge));
  document.head.appendChild(s);
} else {
  start(null);
}
