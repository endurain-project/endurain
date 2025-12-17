import { createApp } from 'vue'
import { createNotivue } from 'notivue'
import { createPinia } from 'pinia'

import { useAuthStore } from './stores/authStore'
import { useThemeStore } from './stores/themeStore'
import { useServerSettingsStore } from './stores/serverSettingsStore'

// PWA service worker registration (required for `injectRegister: 'auto'`)
import { registerSW } from 'virtual:pwa-register'
registerSW()

import 'bootstrap/dist/css/bootstrap.min.css'
//import 'bootstrap/dist/js/bootstrap.bundle.min.js' // Not needed

import 'leaflet/dist/leaflet.css'

import App from './App.vue'
import router from './router'
import { setupI18n } from './i18n'

/* import the fontawesome core */
import { library } from '@fortawesome/fontawesome-svg-core'
/* import font awesome icon component */
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'

/* import icons */
import { fas } from '@fortawesome/free-solid-svg-icons'
import { fab } from '@fortawesome/free-brands-svg-icons'
import { far } from '@fortawesome/free-regular-svg-icons'

/* add icons to the library */
library.add(fas, fab, far)

/* add flag icons */
import 'flag-icons/css/flag-icons.min.css'

/* import notivue components */
import 'notivue/notification.css'
import 'notivue/animations.css'
import 'notivue/notification-progress.css'

const notivue = createNotivue({
  position: 'top-center',
  limit: 4,
  enqueue: true,
  notifications: {
    global: {
      duration: 5000
    }
  }
})

// Initialize app asynchronously
async function initApp() {
  const app = createApp(App)

  app.use(createPinia())
  app.use(notivue)
  app.component('font-awesome-icon', FontAwesomeIcon)

  // Setup i18n asynchronously
  const i18n = await setupI18n()
  app.use(i18n)

  // Import the store and load the user from the storage
  const authStore = useAuthStore()
  authStore.loadUserFromStorage(i18n)

  // OAuth 2.1: Restore tokens on app initialization
  // Access and CSRF tokens are stored in-memory only, so they're lost on page refresh.
  // If user is authenticated but has no access token, refresh to get new tokens.
  if (authStore.isAuthenticated && !authStore.getAccessToken()) {
    try {
      await authStore.refreshAccessToken()
    } catch (error) {
      // If refresh fails, clear user and redirect to login
      console.error('Failed to restore session on app init:', error)
      authStore.clearUser(i18n)
      router.push('/login?sessionExpired=true')
    }
  }

  const themeStore = useThemeStore()
  themeStore.loadThemeFromStorage()

  const serverSettingsStore = useServerSettingsStore()
  await serverSettingsStore.loadServerSettingsFromServer()

  // Setup router
  app.use(router)

  app.mount('#app')
}

// Initialize the app
initApp()
