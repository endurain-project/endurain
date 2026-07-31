import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useSsoLogin } from '@/features/auth/composables/useSsoLogin'

const mocks = vi.hoisted(() => ({
  route: { query: {} as Record<string, unknown> },
  isAuthenticated: false,
  completeTokenLogin: vi.fn<(...args: unknown[]) => Promise<void>>(),
  navigateAfterLogin: vi.fn<(...args: unknown[]) => void>(),
  exchangeSessionForTokens: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  routerReplace: vi.fn<(...args: unknown[]) => Promise<void>>(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => ({ replace: mocks.routerReplace }),
}))

vi.mock('@/features/auth/stores/auth', () => ({
  useAuthStore: () => ({
    completeTokenLogin: mocks.completeTokenLogin,
    get isAuthenticated() {
      return mocks.isAuthenticated
    },
  }),
}))

vi.mock('@/composables/useSafeRedirect', () => ({
  getQueryString: (value: unknown) =>
    Array.isArray(value) ? String(value[0] ?? '') : typeof value === 'string' ? value : '',
  useSafeRedirect: () => ({
    getSafeRedirect: (value: unknown) =>
      typeof value === 'string' && value.startsWith('/') ? value : '/',
    getSsoRedirect: () => '',
    navigateAfterLogin: mocks.navigateAfterLogin,
  }),
}))

vi.mock('@/composables/useTelemetry', () => ({
  useTelemetry: () => ({ trackEvent: vi.fn<() => void>(), captureError: vi.fn<() => void>() }),
}))

vi.mock('@/services/identityProviders', () => ({
  getIdentityProviderLoginUrl: (slug: string, params: URLSearchParams) =>
    `https://idp.test/${slug}?${params.toString()}`,
  exchangeSessionForTokens: mocks.exchangeSessionForTokens,
}))

vi.mock('@/features/auth/utils/pkce', () => ({
  generateCodeVerifier: () => 'verifier-123',
  generateCodeChallenge: () => Promise.resolve('challenge-xyz'),
}))

const tokenExchange = {
  session_id: 'sso-session',
  access_token: 'sso-access',
  csrf_token: 'sso-csrf',
  refresh_token: null,
  token_type: 'bearer',
  expires_in: 900,
  refresh_token_expires_in: 604_800,
}

let assignMock: ReturnType<typeof vi.fn>
const originalLocation = window.location

beforeEach(() => {
  mocks.route.query = {}
  mocks.isAuthenticated = false
  vi.clearAllMocks()
  sessionStorage.clear()
  // jsdom's window.location.assign isn't spyable; replace the whole location.
  assignMock = vi.fn<(url: string) => void>()
  Reflect.deleteProperty(window, 'location')
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { assign: assignMock, href: '', origin: 'http://localhost' },
  })
})

afterEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation })
})

describe('startSsoLogin', () => {
  it('stores the PKCE verifier and redirects with an S256 challenge', async () => {
    const { startSsoLogin } = useSsoLogin()

    const result = await startSsoLogin('acme')

    expect(result).toEqual({ status: 'redirecting' })
    expect(JSON.parse(sessionStorage.getItem('pkce_verifier_acme') ?? '{}')).toMatchObject({
      verifier: 'verifier-123',
    })
    expect(assignMock).toHaveBeenCalledTimes(1)
    const url = assignMock.mock.calls[0]?.[0] as string
    expect(url).toContain('code_challenge=challenge-xyz')
    expect(url).toContain('code_challenge_method=S256')
  })
})

describe('processSsoCallback', () => {
  it('does nothing when the route is not an SSO success callback', async () => {
    const { processSsoCallback } = useSsoLogin()

    expect(await processSsoCallback()).toEqual({ status: 'none' })
    expect(mocks.completeTokenLogin).not.toHaveBeenCalled()
  })

  it('exchanges the session + stored verifier for tokens and completes login', async () => {
    sessionStorage.setItem(
      'pkce_verifier_acme',
      JSON.stringify({ verifier: 'verifier-123', createdAt: Date.now() }),
    )
    mocks.route.query = { sso: 'success', session_id: 'sso-session' }
    mocks.exchangeSessionForTokens.mockResolvedValue(tokenExchange)

    const { processSsoCallback } = useSsoLogin()
    const result = await processSsoCallback()

    expect(result).toEqual({ status: 'completed' })
    expect(mocks.exchangeSessionForTokens).toHaveBeenCalledWith('sso-session', 'verifier-123')
    expect(mocks.completeTokenLogin).toHaveBeenCalledWith(
      expect.objectContaining({ access_token: 'sso-access', csrf_token: 'sso-csrf' }),
    )
    expect(mocks.navigateAfterLogin).toHaveBeenCalled()
    // The single-use verifier is cleared after a successful exchange.
    expect(sessionStorage.getItem('pkce_verifier_acme')).toBeNull()
  })

  it('fails when no PKCE verifier is stored', async () => {
    mocks.route.query = { sso: 'success', session_id: 'sso-session' }

    const { processSsoCallback } = useSsoLogin()
    const result = await processSsoCallback()

    expect(result).toEqual({ status: 'error', messageKey: 'login.ssoTokenExchangeFailed' })
    expect(mocks.exchangeSessionForTokens).not.toHaveBeenCalled()
    expect(mocks.completeTokenLogin).not.toHaveBeenCalled()
  })

  it('fails and removes expired PKCE verifiers', async () => {
    sessionStorage.setItem(
      'pkce_verifier_acme',
      JSON.stringify({ verifier: 'verifier-123', createdAt: Date.now() - 10 * 60 * 1000 - 1 }),
    )
    mocks.route.query = { sso: 'success', session_id: 'sso-session' }

    const { processSsoCallback } = useSsoLogin()
    const result = await processSsoCallback()

    expect(result).toEqual({ status: 'error', messageKey: 'login.ssoTokenExchangeFailed' })
    expect(mocks.exchangeSessionForTokens).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('pkce_verifier_acme')).toBeNull()
  })

  it('fails when the token exchange omits the CSRF token', async () => {
    sessionStorage.setItem(
      'pkce_verifier_acme',
      JSON.stringify({ verifier: 'verifier-123', createdAt: Date.now() }),
    )
    mocks.route.query = { sso: 'success', session_id: 'sso-session' }
    mocks.exchangeSessionForTokens.mockResolvedValue({ ...tokenExchange, csrf_token: null })

    const { processSsoCallback } = useSsoLogin()
    const result = await processSsoCallback()

    expect(result).toEqual({ status: 'error', messageKey: 'login.ssoTokenExchangeFailed' })
    expect(mocks.completeTokenLogin).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('pkce_verifier_acme')).toBeNull()
  })

  it('does not clear unrelated PKCE verifiers on callback failure', async () => {
    sessionStorage.setItem(
      'pkce_verifier_acme',
      JSON.stringify({ verifier: 'verifier-123', createdAt: Date.now() }),
    )
    sessionStorage.setItem(
      'pkce_verifier_beta',
      JSON.stringify({ verifier: 'verifier-beta', createdAt: Date.now() }),
    )
    mocks.route.query = { sso: 'success', session_id: 'sso-session' }
    mocks.exchangeSessionForTokens.mockResolvedValue({ ...tokenExchange, csrf_token: null })

    const { processSsoCallback } = useSsoLogin()
    const result = await processSsoCallback()

    expect(result).toEqual({ status: 'error', messageKey: 'login.ssoTokenExchangeFailed' })
    expect(sessionStorage.getItem('pkce_verifier_acme')).toBeNull()
    expect(JSON.parse(sessionStorage.getItem('pkce_verifier_beta') ?? '{}')).toMatchObject({
      verifier: 'verifier-beta',
    })
  })

  describe('mobile app handoff (external_redirect)', () => {
    it('forwards the session_id to the app scheme without touching the browser session', async () => {
      mocks.route.query = {
        sso: 'success',
        session_id: 'sso-session',
        external_redirect: 'true',
        redirect: '/native-callback',
      }

      const { processSsoCallback } = useSsoLogin()
      const result = await processSsoCallback()

      expect(result).toEqual({ status: 'completed' })
      expect(window.location.href).toBe('/native-callback?session_id=sso-session')
      expect(mocks.completeTokenLogin).not.toHaveBeenCalled()
      expect(mocks.routerReplace).not.toHaveBeenCalled()
    })

    it('falls back to the dashboard when the browser already has an authenticated session', async () => {
      mocks.isAuthenticated = true
      mocks.route.query = {
        sso: 'success',
        session_id: 'sso-session',
        external_redirect: 'true',
        redirect: '/native-callback',
      }

      const { processSsoCallback } = useSsoLogin()
      const result = await processSsoCallback()

      expect(result).toEqual({ status: 'completed' })
      expect(window.location.href).toBe('/native-callback?session_id=sso-session')
      expect(mocks.routerReplace).toHaveBeenCalledWith({ name: 'home' })
    })
  })
})
