import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import type { AuthTokenResponse } from '@/types'
import type { User } from '@/features/auth/types'

import { clearAuthTokens, setAuthTokens } from '@/services/authTokens'
import { HttpError } from '@/services/http'
import { queryKeys } from '@/services/queryKeys'
import { fetchCurrentUser } from '@/features/auth/services/profile'
import {
  changePasswordAtLogin,
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

const { broadcastSessionEnded } = vi.hoisted(() => ({ broadcastSessionEnded: vi.fn<() => void>() }))
vi.mock('@/lib/sessionChannel', () => ({ broadcastSessionEnded }))

vi.mock('@/features/auth/services/profile', () => ({
  fetchCurrentUser: vi.fn<typeof fetchCurrentUser>(),
}))

vi.mock('@/features/auth/services/session', () => ({
  loginWithPassword: vi.fn<typeof loginWithPassword>(),
  logoutSession: vi.fn<typeof logoutSession>(),
  refreshSession: vi.fn<typeof refreshSession>(),
  verifyMfaLogin: vi.fn<typeof verifyMfaLogin>(),
  changePasswordAtLogin: vi.fn<typeof changePasswordAtLogin>(),
}))

const realtimeConnect = vi.fn<() => void>()
const realtimeDisconnect = vi.fn<() => void>()
vi.mock('@/composables/useRealtime', () => ({
  useRealtime: () => ({ connect: realtimeConnect, disconnect: realtimeDisconnect }),
}))

const tokenResponse: AuthTokenResponse = {
  next_step: 'tokens',
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
  weightUnits: 'metric',
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
      next_step: 'mfa',
      mfa_challenge: 'challenge-123',
    })

    const auth = useAuthStore()
    const result = await auth.login('demo', 'password123')

    expect(result).toEqual({ status: 'mfa-required', challenge: 'challenge-123' })
    expect(setAuthTokens).not.toHaveBeenCalled()
    expect(fetchCurrentUser).not.toHaveBeenCalled()
    expect(auth.isAuthenticated).toBe(false)
  })

  it('returns a password-change state without storing tokens', async () => {
    vi.mocked(loginWithPassword).mockResolvedValue({
      next_step: 'password_change',
      password_change_challenge: 'change-123',
    })

    const auth = useAuthStore()
    const result = await auth.login('demo', 'password123')

    expect(result).toEqual({ status: 'password-change-required', challenge: 'change-123' })
    expect(setAuthTokens).not.toHaveBeenCalled()
    expect(fetchCurrentUser).not.toHaveBeenCalled()
    expect(auth.isAuthenticated).toBe(false)
  })

  it.each([
    ['an exchange session', { next_step: 'exchange', session_id: 's', device_id: null }],
    ['a step it does not know', { next_step: 'passkey' }],
  ])('stops at %s without touching the session', async (_label, answer) => {
    vi.mocked(loginWithPassword).mockResolvedValue(answer as never)

    const auth = useAuthStore()
    const result = await auth.login('demo', 'password123')

    expect(result).toEqual({ status: 'unsupported-step' })
    expect(setAuthTokens).not.toHaveBeenCalled()
    expect(auth.isAuthenticated).toBe(false)
  })

  it('verifies MFA with the challenge the password step returned', async () => {
    vi.mocked(verifyMfaLogin).mockResolvedValue(tokenResponse)
    vi.mocked(fetchCurrentUser).mockResolvedValue(authUser)

    const auth = useAuthStore()
    const result = await auth.verifyMfa('challenge-123', '123456')

    expect(verifyMfaLogin).toHaveBeenCalledWith({
      mfa_challenge: 'challenge-123',
      mfa_code: '123456',
    })
    expect(result).toEqual({ status: 'authenticated', user: authUser })
  })

  it('moves on to the password change after a verified MFA code', async () => {
    vi.mocked(verifyMfaLogin).mockResolvedValue({
      next_step: 'password_change',
      password_change_challenge: 'change-123',
    })

    const auth = useAuthStore()
    const result = await auth.verifyMfa('challenge-123', '123456')

    expect(result).toEqual({ status: 'password-change-required', challenge: 'change-123' })
    expect(setAuthTokens).not.toHaveBeenCalled()
  })

  it('signs in once the new password is chosen', async () => {
    vi.mocked(changePasswordAtLogin).mockResolvedValue(tokenResponse)
    vi.mocked(fetchCurrentUser).mockResolvedValue(authUser)

    const auth = useAuthStore()
    const result = await auth.changePassword('change-123', 'a new passphrase')

    expect(changePasswordAtLogin).toHaveBeenCalledWith({
      password_change_challenge: 'change-123',
      password: 'a new passphrase',
    })
    expect(result).toEqual({ status: 'authenticated', user: authUser })
    expect(setAuthTokens).toHaveBeenCalledWith('access-token', 'csrf-token')
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
    vi.mocked(logoutSession).mockResolvedValue({ idp_logout_url: null })

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

  it('returns the provider logout URL when the session signed in through a provider', async () => {
    vi.mocked(loginWithPassword).mockResolvedValue(tokenResponse)
    vi.mocked(fetchCurrentUser).mockResolvedValue(authUser)
    vi.mocked(logoutSession).mockResolvedValue({
      idp_logout_url: 'https://idp.example.com/logout?id_token_hint=abc',
    })

    const auth = useAuthStore()
    await auth.login('demo', 'password123')

    await expect(auth.logout()).resolves.toBe('https://idp.example.com/logout?id_token_hint=abc')
    expect(auth.isAuthenticated).toBe(false)
  })

  it.each(['http://idp.example.com/logout', 'javascript:alert(1)', 'not a url', ''])(
    'ignores a provider logout URL that is not https (%s)',
    async (idpLogoutUrl) => {
      vi.mocked(loginWithPassword).mockResolvedValue(tokenResponse)
      vi.mocked(fetchCurrentUser).mockResolvedValue(authUser)
      vi.mocked(logoutSession).mockResolvedValue({ idp_logout_url: idpLogoutUrl })

      const auth = useAuthStore()
      await auth.login('demo', 'password123')

      await expect(auth.logout()).resolves.toBeNull()
      expect(auth.isAuthenticated).toBe(false)
    },
  )

  it('clears local state and returns no URL when the backend logout fails', async () => {
    vi.mocked(loginWithPassword).mockResolvedValue(tokenResponse)
    vi.mocked(fetchCurrentUser).mockResolvedValue(authUser)
    vi.mocked(logoutSession).mockRejectedValue(new HttpError(401, 'Unauthorized'))

    const auth = useAuthStore()
    await auth.login('demo', 'password123')

    await expect(auth.logout()).resolves.toBeNull()
    expect(auth.isAuthenticated).toBe(false)
  })

  it.each([401, 403])('clears local state when logout is refused with %i', async (status) => {
    vi.mocked(loginWithPassword).mockResolvedValue(tokenResponse)
    vi.mocked(fetchCurrentUser).mockResolvedValue(authUser)
    vi.mocked(logoutSession).mockRejectedValue(new HttpError(status, 'Refused'))

    const auth = useAuthStore()
    await auth.login('demo', 'password123')

    await expect(auth.logout()).resolves.toBeNull()
    expect(auth.isAuthenticated).toBe(false)
  })

  it.each([
    ['a network error', new TypeError('Failed to fetch')],
    ['a 503', new HttpError(503, 'Service Unavailable')],
    ['a 429', new HttpError(429, 'Too Many Requests')],
  ])('keeps the session and rethrows when logout fails with %s', async (_label, failure) => {
    vi.mocked(loginWithPassword).mockResolvedValue(tokenResponse)
    vi.mocked(fetchCurrentUser).mockResolvedValue(authUser)
    vi.mocked(logoutSession).mockRejectedValue(failure)

    const auth = useAuthStore()
    await auth.login('demo', 'password123')
    vi.mocked(clearAuthTokens).mockClear()
    broadcastSessionEnded.mockClear()

    await expect(auth.logout()).rejects.toBe(failure)
    expect(auth.isAuthenticated).toBe(true)
    expect(clearAuthTokens).not.toHaveBeenCalled()
    expect(broadcastSessionEnded).not.toHaveBeenCalled()
  })

  it('tells the other tabs when logout succeeds', async () => {
    vi.mocked(logoutSession).mockResolvedValue({ idp_logout_url: null })

    await useAuthStore().logout()

    expect(broadcastSessionEnded).toHaveBeenCalledOnce()
  })

  it('tells the other tabs when the session expires while signed in', async () => {
    vi.mocked(loginWithPassword).mockResolvedValue(tokenResponse)
    vi.mocked(fetchCurrentUser).mockResolvedValue(authUser)
    const auth = useAuthStore()
    await auth.login('demo', 'password123')

    auth.expireSession()

    expect(broadcastSessionEnded).toHaveBeenCalledOnce()
  })

  it('clears the session on a 403 from the restore request', async () => {
    vi.mocked(refreshSession).mockRejectedValue(new HttpError(403, 'Forbidden'))

    const auth = useAuthStore()
    await auth.restoreSession()

    expect(clearAuthTokens).toHaveBeenCalled()
    expect(auth.restoreFailed).toBe(false)
    expect(auth.isReady).toBe(true)
  })

  it.each([
    ['a network error', new TypeError('Failed to fetch')],
    ['a 500', new HttpError(500, 'Internal Server Error')],
    ['a 429', new HttpError(429, 'Too Many Requests')],
  ])('keeps the session and flags a failed restore on %s', async (_label, failure) => {
    vi.mocked(refreshSession).mockRejectedValue(failure)

    const auth = useAuthStore()
    await auth.restoreSession()

    expect(clearAuthTokens).not.toHaveBeenCalled()
    expect(auth.restoreFailed).toBe(true)
    expect(auth.isAuthenticated).toBe(false)
  })

  it('clears user-scoped storage while preserving device preferences on logout', async () => {
    localStorage.setItem('endurain:activity-draft', JSON.stringify({ name: 'Morning ride' }))
    localStorage.setItem('endurain:theme', JSON.stringify('dark'))
    localStorage.setItem('endurain:locale', JSON.stringify('en'))
    vi.mocked(loginWithPassword).mockResolvedValue(tokenResponse)
    vi.mocked(fetchCurrentUser).mockResolvedValue(authUser)
    vi.mocked(logoutSession).mockResolvedValue({ idp_logout_url: null })

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
