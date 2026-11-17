import { defineConfig } from 'vite';

// One plain script and one stylesheet, no ES modules: Chromium inside Qt
// refuses module scripts loaded from file://, and this also keeps the
// bundle usable as-is by the Mini App and the PWA.
export default defineConfig({
  base: './',
  publicDir: 'public',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'chrome120',
    cssCodeSplit: false,
    lib: {
      entry: 'src/main.js',
      name: 'NotepadEditorBundle',
      formats: ['iife'],
      fileName: () => 'editor.js',
      cssFileName: 'editor',
    },
  },
});
