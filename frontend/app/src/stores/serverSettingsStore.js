import { defineStore } from 'pinia'
import { serverSettings } from '@/services/serverSettingsService'

export const useServerSettingsStore = defineStore('serverSettings', {
  state: () => ({
    serverSettings: {
      id: 1,
      units: 1,
      public_shareable_links: false,
      public_shareable_links_user_info: false,
      login_photo_set: false,
      currency: 1,
      num_records_per_page: 5,
      signup_enabled: false,
      signup_require_admin_approval: null,
      signup_require_email_verification: null,
    }
  }),
  actions: {
    setServerSettings(serverSettings) {
      this.serverSettings = serverSettings
      localStorage.setItem('serverSettings', JSON.stringify(this.serverSettings))
    },
    loadServerSettingsFromStorage() {
      const storedServerSettings = localStorage.getItem('serverSettings')
      if (storedServerSettings) {
        this.serverSettings = JSON.parse(storedServerSettings)
      } else {
        this.loadServerSettingsFromServer()
      }
    },
    async loadServerSettingsFromServer() {
      const settings = await serverSettings.getPublicServerSettings()
      this.setServerSettings(settings)
    },
    setServerSettingsOnLogout() {
      this.serverSettings.signup_require_admin_approval = null
      this.serverSettings.signup_require_email_verification = null
    }
  }
})
