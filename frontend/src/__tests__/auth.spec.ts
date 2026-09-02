import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import type { AuthTokenResponse } from '@/types'
import type { User } from '@/features/auth/types'

import { clearAuthTokens, setAuthTokens } from '@/services/authTokens'
import { HttpError } from '@/services/http'
import { queryKeys } from '@/services/queryKeys'
import { fetchCurrentUser } from '@/features/auth/services/profile'
import {
  loginWithPassword,
  logoutSession,
  refreshSession,
  verifyMfaLogin,
} from '@/features/auth/services/session'
import { queryClient } from '@/plugins/vueQuery'
import { useAuthStore } from '@/features/auth/stores/auth'

vi.mock('@/services/authTokens', () => ({
  clearAuthTokens: vi.fn<typeof clearAuthTokens>(),
  setAuthTokens: vi.fn<typeof setAuthTokens>(),
}))

vi.mock('@/features/auth/services/profile', () => ({
  fetchCurrentUser: vi.fn<typeof fetchCurrentUser>(),
}))

vi.mock('@/features/auth/services/session', () => ({
  loginWithPassword: vi.fn<typeof loginWithPassword>(),
  logoutSession: vi.fn<typeof logoutSession>(),
  refreshSession: vi.fn<typeof refreshSession>(),
  verifyMfaLogin: vi.fn<typeof verifyMfaLogin>(),
}))

const realtimeConnect = vi.fn<() => void>()
const realtimeDisconnect = vi.fn<() => void>()
vi.mock('@/composables/useRealtime', () => ({
  useRealtime: () => ({ connect: realtimeConnect, disconnect: realtimeDisconnect }),
}))

const tokenResponse: AuthTokenResponse = {
  session_id: 'session-1',
  access_token: 'access-token',
  csrf_token: 'csrf-token',
  token_type: 'bearer',
  expires_in: 900,
  refresh_token_expires_in: 604_800,
}

const authUser: User = {
  id: 1,
  name: 'Demo User',
  username: 'demo',
  email: 'demo@example.com',
  preferredLanguage: 'en',
  accessType: 'user',
  active: true,
  mfaEnabled: false,
  avatarUrl: null,
  isStravaLinked: false,
  isGarminConnectLinked: false,
  hasLocalPassword: true,
  units: 'metric',
  currency: 'euro',
  firstDayOfWeek: 'sunday',
}

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorage.clear()
    queryClient.clear()
  })

  it('returns an MFA-required state without storing tokens', async () => {
    vi.mocked(loginWithPassword).mockResolvedValue({
      mfa_required: true,
      username: 'demo',
      message: 'MFA verification required',
    })

    const auth = useAuthStore()
    const result = await auth.login('demo', 'password123')

    expect(result).toEqual({ status: 'mfa-required', username: 'demo' })
    expect(setAuthTokens).not.toHaveBeenCalled()
    expect(fetchCurrentUser).not.toHaveBeenCalled()
    expect(auth.isAuthenticated).toBe(false)
  })

  it('hydrates the user after successful login', async () => {
    vi.mocked(loginWithPassword).mockResolvedValue(tokenResponse)
    vi.mocked(fetchCurrentUser).mockResolvedValue(authUser)

    const auth = useAuthStore()
    const result = await auth.login('demo', 'password123')

    expect(result).toEqual({ status: 'authenticated', user: authUser })
    expect(setAuthTokens).toHaveBeenCalledWith('access-token', 'csrf-token')
    expect(auth.sessionId).toBe('session-1')
    expect(queryClient.getQueryData(queryKeys.currentUser())).toEqual(authUser)
    expect(auth.isAuthenticated).toBe(true)
    expect(realtimeConnect).toHaveBeenCalled()
    expect(auth.isReady).toBe(true)
  })

  it('clears local auth state when restore has no valid refresh session', async () => {
    vi.mocked(refreshSession).mockRejectedValue(new HttpError(401, 'Unauthorized'))

    const auth = useAuthStore()
    await auth.restoreSession()

    expect(clearAuthTokens).toHaveBeenCalled()
    expect(queryClient.getQueryData(queryKeys.currentUser())).toBeUndefined()
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.sessionId).toBeNull()
    expect(auth.isReady).toBe(true)
  })

  it('logs out remotely and clears local auth state', async () => {
    vi.mocked(loginWithPassword).mockResolvedValue(tokenResponse)
    vi.mocked(fetchCurrentUser).mockResolvedValue(authUser)
    vi.mocked(logoutSession).mockResolvedValue({ message: 'Logout successful' })

    const auth = useAuthStore()
    await auth.login('demo', 'password123')
    await auth.logout()

    expect(logoutSession).toHaveBeenCalled()
    expect(clearAuthTokens).toHaveBeenCalled()
    expect(queryClient.getQueryData(queryKeys.currentUser())).toBeUndefined()
    expect(auth.sessionId).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
    expect(realtimeDisconnect).toHaveBeenCalled()
  })

  it('clears user-scoped storage while preserving device preferences on logout', async () => {
    localStorage.setItem('endurain:activity-draft', JSON.stringify({ name: 'Morning ride' }))
    localStorage.setItem('endurain:theme', JSON.stringify('dark'))
    localStorage.setItem('endurain:locale', JSON.stringify('en'))
    vi.mocked(loginWithPassword).mockResolvedValue(tokenResponse)
    vi.mocked(fetchCurrentUser).mockResolvedValue(authUser)
    vi.mocked(logoutSession).mockResolvedValue({ message: 'Logout successful' })

    const auth = useAuthStore()
    await auth.login('demo', 'password123')
    await auth.logout()

    expect(localStorage.getItem('endurain:activity-draft')).toBeNull()
    expect(localStorage.getItem('endurain:theme')).toBe(JSON.stringify('dark'))
    expect(localStorage.getItem('endurain:locale')).toBe(JSON.stringify('en'))
  })

  it('clears auth state on session expiry and reports the prior status', async () => {
    vi.mocked(loginWithPassword).mockResolvedValue(tokenResponse)
    vi.mocked(fetchCurrentUser).mockResolvedValue(authUser)

    const auth = useAuthStore()
    await auth.login('demo', 'password123')

    expect(auth.handleSessionExpired()).toBe(true)
    expect(clearAuthTokens).toHaveBeenCalled()
    expect(queryClient.getQueryData(queryKeys.currentUser())).toBeUndefined()
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.isReady).toBe(true)

    // Already cleared — a second signal reports no active session.
    expect(auth.handleSessionExpired()).toBe(false)
  })
})
