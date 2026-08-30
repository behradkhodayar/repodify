import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import { defineConfig } from 'vitest/config'

export default defineConfig(() => {
  const apiTarget = process.env.API_PROXY_TARGET || 'http://localhost:8000'
  return {
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
            { urlPattern: /\/(jobs|feeds|health|voices|settings)(\/.*)?$/, handler: 'NetworkOnly' },
          ],
        },
      }),
    ],
    server: {
      proxy: {
        '/feeds': apiTarget,
        '/jobs': apiTarget,
        '/voices': apiTarget,
        '/settings': apiTarget,
        '/health': apiTarget,
      },
    },
    test: {
      environment: 'jsdom',
      environmentOptions: { jsdom: { url: 'http://localhost' } },
      globals: true,
      setupFiles: './src/test/setup.ts',
    },
  }
})
