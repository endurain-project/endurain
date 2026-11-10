import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { useToasts } from '@/composables/useToasts'
import { useAuthStore } from '@/features/auth/stores/auth'

/**
 * Signs the user out of Endurain and, when the session signed in through an
 * identity provider that supports RP-initiated logout, sends the browser to the
 * provider so its session ends too. Otherwise it shows the login page. When the server
 * could not be reached the session stays, and an error toast says so.
 *
 * @returns `signOut`, which resolves once navigation has started.
 */
export function useSignOut(): { signOut: () => Promise<void> } {
  const auth = useAuthStore()
  const router = useRouter()
  const { t } = useI18n()
  const toasts = useToasts()

  async function signOut(): Promise<void> {
    let idpLogoutUrl: string | null
    try {
      idpLogoutUrl = await auth.logout()
    } catch {
      toasts.error(t('nav.logoutFailed'))
      return
    }
    if (idpLogoutUrl) {
      window.location.assign(idpLogoutUrl)
      return
    }
    await router.push({ name: 'login', query: { logoutSuccess: 'true' } })
  }

  return { signOut }
}
