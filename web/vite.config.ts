import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  base: '/app/',
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'cutcast',
        short_name: 'cutcast',
        start_url: '/app/',
        scope: '/app/',
        display: 'standalone',
        theme_color: '#0b0f0e',
        background_color: '#0b0f0e',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
      workbox: {
        navigateFallback: '/app/index.html',
        runtimeCaching: [
          { urlPattern: /\/(jobs|feeds|health)(\/.*)?$/, handler: 'NetworkOnly' },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      '/feeds': 'http://localhost:8000',
      '/jobs': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    environmentOptions: { jsdom: { url: 'http://localhost' } },
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
})
