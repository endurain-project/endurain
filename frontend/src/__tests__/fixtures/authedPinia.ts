import { createPinia, type Pinia } from 'pinia'

import { useAuthStore } from '@/features/auth/stores/auth'

/**
 * Builds a Pinia whose auth store reports a signed-in session, so the queries gated on
 * authentication run in a component test.
 *
 * @returns The Pinia to install as a plugin.
 */
export function authedPinia(): Pinia {
  const pinia = createPinia()
  useAuthStore(pinia).isAuthenticated = true
  return pinia
}
