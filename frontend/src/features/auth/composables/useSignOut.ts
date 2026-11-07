import { useRouter } from 'vue-router'

import { useAuthStore } from '@/features/auth/stores/auth'

/**
 * Signs the user out of Endurain and, when the session signed in through an
 * identity provider that supports RP-initiated logout, sends the browser to the
 * provider so its session ends too. Otherwise it shows the login page.
 *
 * @returns `signOut`, which resolves once navigation has started.
 */
export function useSignOut(): { signOut: () => Promise<void> } {
  const auth = useAuthStore()
  const router = useRouter()

  async function signOut(): Promise<void> {
    const idpLogoutUrl = await auth.logout()
    if (idpLogoutUrl) {
      window.location.assign(idpLogoutUrl)
      return
    }
    await router.push({ name: 'login', query: { logoutSuccess: 'true' } })
  }

  return { signOut }
}
