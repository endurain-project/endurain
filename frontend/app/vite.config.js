import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

import { VitePWA } from 'vite-plugin-pwa'

// https://vitejs.dev/config/
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          // Core Vue framework and state management
          'vue-vendor': ['vue', 'vue-router', 'pinia'],
          
          // Large charting library - only needed on stats/activity pages
          'chart': ['chart.js', 'chartjs-plugin-datalabels'],
          
          // Map library - only needed on activity detail pages with GPS data
          'leaflet': ['leaflet'],
          
          // UI framework - used across the app
          'bootstrap': ['bootstrap'],
          
          // FontAwesome icons - used throughout the app
          'fontawesome': [
            '@fortawesome/fontawesome-svg-core',
            '@fortawesome/free-solid-svg-icons',
            '@fortawesome/free-regular-svg-icons',
            '@fortawesome/free-brands-svg-icons',
            '@fortawesome/vue-fontawesome'
          ],
          
          // Date/time utilities and notifications
          'utils': ['luxon', 'notivue', 'vue-i18n']
        }
      }
    }
  },
  server: {
    proxy: {
      // Proxy all /api requests to the backend server during development
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        secure: false
      }
    }
  },
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      strategies: 'generateSW',
      injectRegister: 'auto',
      minify: true,
      manifest: {
        name: 'Endurain',
        short_name: 'Endurain',
        description: 'A self-hosted fitness tracking service',
        start_url: '/',
        display: 'standalone',
        background_color: '#212529',
        theme_color: '#FFFFFF',
        icons: [
          {
            src: '/logo/pwa-192x192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: '/logo/pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: '/logo/pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: '/logo/pwa-maskable-192x192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'maskable'
          },
          {
            src: '/logo/pwa-maskable-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable'
          }
        ]
      },
      workbox: {
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
        globPatterns: ['**/*.{js,css,html,ico,png,svg,json,webmanifest,woff2}'],
        clientsClaim: true,
        skipWaiting: true,
        sourcemap: false,
        navigateFallback: '/',
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => /^\/api\/v1(?:\/|$)/.test(url.pathname),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: {
                maxEntries: 100,
                maxAgeSeconds: 86400
              }
            }
          }
        ]
      },
      devOptions: {
        enabled: false,
        type: 'module',
      }
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  }
})