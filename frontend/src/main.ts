import '@fontsource-variable/inter'
import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import i18n, { getInitialLocale, loadLocaleMessages, setI18nLocale } from './i18n'
import { initTheme } from './composables/useTheme'
import { loadAppConfig, useAppConfig } from './features/config/composables/useAppConfig'
import { useTelemetry } from './composables/useTelemetry'
import { useToasts } from './composables/useToasts'
import { VueQueryPlugin, vueQueryOptions } from './plugins/vueQuery'
import { registerRenderProviders } from './providers'
import { onSessionExpired } from './services/sessionExpiry'
import { useAuthStore } from './features/auth/stores/auth'

// Apply the theme synchronously, before any async work, to avoid a flash of
// the wrong color scheme on first paint.
initTheme()

/**
 * Boots the application after runtime config and the initial locale are
 * loaded, avoiding a flash of untranslated content.
 */
async function bootstrap(): Promise<void> {
  const initialLocale = getInitialLocale()
  await Promise.all([loadAppConfig(), loadLocaleMessages(initialLocale)])
  setI18nLocale(initialLocale)

  // Register the concrete map/chart renderers in the background so their heavy
  // libraries load as separate chunks without delaying first paint.
  const { config } = useAppConfig()
  void registerRenderProviders({
    tileUrl: config.value.map.tileUrl,
    attribution: config.value.map.attribution,
  }).catch((error: unknown) => {
    useTelemetry().captureError(error, { scope: 'registerRenderProviders' })
  })

  const app = createApp(App)
  const pinia = createPinia()

  app.config.errorHandler = (error, _instance, info) => {
    useTelemetry().captureError(error, { info })
    useToasts().error(i18n.global.t('app.error.toast'))
  }

  app.use(pinia)
  app.use(i18n)
  app.use(VueQueryPlugin, vueQueryOptions)

  // When a mid-session token refresh fails terminally, drop local auth state
  // and send the user to the login screen with an explanatory message.
  const authStore = useAuthStore()
  onSessionExpired(() => {
    if (authStore.handleSessionExpired() && router.currentRoute.value.name !== 'login') {
      void router.replace({ name: 'login', query: { sessionExpired: 'true' } })
    }
  })

  await authStore.restoreSession()

  app.use(router)

  await router.isReady()

  app.mount('#app')
}

void bootstrap().catch((error: unknown) => {
  useTelemetry().captureError(error, { scope: 'bootstrap', fatal: true })
  const message = document.createElement('p')
  message.className = 'p-8 font-sans'
  message.textContent = 'Something went wrong while starting the app. Please refresh.'
  document.body.replaceChildren(message)
})
