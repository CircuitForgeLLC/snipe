import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import UnoCSS from 'unocss/vite'

export default defineConfig({
  plugins: [vue(), UnoCSS()],
  base: process.env.VITE_BASE_URL ?? '/',
  build: {
    // 16-char content hash prevents filename collisions that break immutable caching
    rollupOptions: { output: { hashCharacters: 'base64', entryFileNames: 'assets/[name]-[hash:16].js', chunkFileNames: 'assets/[name]-[hash:16].js', assetFileNames: 'assets/[name]-[hash:16].[ext]' } },
  },
  server: {
    host: '0.0.0.0',
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://localhost:8510',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
})
