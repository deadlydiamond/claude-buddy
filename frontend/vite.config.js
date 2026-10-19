import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Built files go straight into the Python package, where pywebview loads them.
export default defineConfig({
  plugins: [vue()],
  base: './',
  build: {
    outDir: '../claude_session_copy/web',
    emptyOutDir: true,
    chunkSizeWarningLimit: 2000, // loaded from disk by a desktop window, not over a network
  },
})
