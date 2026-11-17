// Entry for pages that embed the editor (the Mini App, the PWA). It only
// hands over `createApp`; the host page decides where to mount it and what
// to do with what the editor reports. No standalone page styles come along.
import './styles.css';
import { createApp } from './app.js';

window.NotepadEditorEmbed = { createApp };
