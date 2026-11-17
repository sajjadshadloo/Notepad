import { defineConfig } from 'vite';

// The same editor for pages that are not the desktop's web view: one script
// and one stylesheet, written straight into the Worker's public folder.
export default defineConfig({
  base: './',
  publicDir: false,
  build: {
    outDir: '../cloudflare/public/editor',
    emptyOutDir: true,
    target: 'es2020',
    cssCodeSplit: false,
    lib: {
      entry: 'src/embed.js',
      name: 'NotepadEditorEmbedBundle',
      formats: ['iife'],
      fileName: () => 'editor.js',
      cssFileName: 'editor',
    },
  },
});
