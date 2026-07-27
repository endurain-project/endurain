import { fileURLToPath, URL } from 'node:url'

import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'
import tailwindcss from '@tailwindcss/vite'
import vueI18n from '@intlify/unplugin-vue-i18n/vite'
import { VitePWA } from 'vite-plugin-pwa'

/**
 * Fallback Content-Security-Policy for production builds. Injected as a meta
 * tag at build time only, so the Vite dev server (which relies on inline HMR
 * scripts) is unaffected.
 *
 * `connect-src` ships as the tight same-origin default `'self'`. The exact
 * backend API/WebSocket origin is not known at build time (it is resolved at
 * runtime from `/env.js`), so for split-origin deployments `docker/start.sh`
 * pins it into this meta tag at container start from `ENDURAIN_HOST`. The
 * backend response-header CSP remains authoritative wherever it serves the SPA
 * and additionally covers header-only directives such as HSTS.
 */
const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "script-src 'self'",
  // Reka UI / Vue write inline `style` attributes for positioning and
  // transitions, which require 'unsafe-inline' for styles only.
  "style-src 'self' 'unsafe-inline'",
  // Avatars and the login image are served by the (possibly cross-origin)
  // backend over HTTPS; data:/blob: cover bundled and generated images.
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  "form-action 'self'",
  "frame-src 'none'",
  "manifest-src 'self'",
  // Same-origin API + realtime sockets are covered by 'self'. codeberg.org is the
  // release-update check (features/core/services/updateCheck.ts), a direct browser
  // fetch. Split-origin deployments additionally get their exact backend origin
  // pinned here at container start by docker/start.sh (from ENDURAIN_HOST), which
  // rewrites this directive by matching to the end of the meta `content` attribute
  // — so connect-src MUST stay the LAST directive in this list.
  "connect-src 'self' https://codeberg.org",
].join('; ')

/**
 * Injects the production Content-Security-Policy meta tag into index.html.
 *
 * @returns A build-only Vite plugin.
 */
function cspPlugin(): Plugin {
  return {
    name: 'endurain-csp',
    apply: 'build',
    transformIndexHtml(html) {
      return {
        html,
        tags: [
          {
            tag: 'meta',
            attrs: {
              'http-equiv': 'Content-Security-Policy',
              content: CONTENT_SECURITY_POLICY,
            },
            injectTo: 'head-prepend',
          },
        ],
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
    tailwindcss(),
    vueI18n({
      // Precompile locale messages at build time so the runtime ships
      // without the message compiler (smaller, CSP-friendly bundle).
      include: [fileURLToPath(new URL('./src/i18n/locales/**', import.meta.url))],
      strictMessage: true,
      escapeHtml: true,
    }),
    VitePWA({
      // Ship updates silently: a new deploy's service worker activates and
      // reloads clients without an in-app prompt.
      registerType: 'autoUpdate',
      strategies: 'generateSW',
      // Register via an external /registerSW.js script (not an inline script)
      // so registration complies with the strict `script-src 'self'` CSP.
      injectRegister: 'script-defer',
      // The installable manifest is the hand-authored public/site.webmanifest
      // already linked from index.html; let it remain the single source.
      manifest: false,
      workbox: {
        // Precache the hashed app shell for offline launch + installability.
        globPatterns: ['**/*.{js,css,html,ico,png,svg,webmanifest,woff2}'],
        // env.js is written at container start (docker/start.sh) and is NOT
        // content-hashed; precaching it would freeze each tenant's runtime
        // config to a stale build-time snapshot.
        //
        // The default login background is a multi-MB decorative image used on
        // a single screen; it is above Workbox's 2 MiB precache cap and would
        // bloat the install payload for every client, so it is fetched from
        // the network instead.
        globIgnores: ['**/env.js', '**/assets/login-*.png'],
        cleanupOutdatedCaches: true,
        clientsClaim: true,
        skipWaiting: true,
        // SPA navigations fall back to the app shell, except runtime config
        // and API/WebSocket calls which must always hit the network.
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/env\.js$/, /^\/api\//, /^\/ws(?:\/|$)/],
        // Deliberately no runtimeCaching for the API: responses are
        // authenticated (and the backend may be a different origin), so
        // caching them in CacheStorage would persist user data on disk past
        // logout. TanStack Query already provides in-memory server caching.
      },
      // Keep the service worker out of dev so it never interferes with HMR.
      devOptions: {
        enabled: false,
        type: 'module',
      },
    }),
    cspPlugin(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
