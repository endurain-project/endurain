import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { IdentityProviderPublic } from '@/types'
import type { PublicServerSettings } from '@/features/config/types'

import { useSsoLogin } from '@/features/auth/composables/useSsoLogin'
import { HttpError } from '@/services/http'

const mocks = vi.hoisted(() => ({
  route: { query: {} as Record<string, unknown> },
  isAuthenticated: false,
  verifier: 'verifier-123',
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
      typeof value === 'string' &&
      (value.startsWith('/') ||
        value.startsWith('endurain:') ||
        value.startsWith('https://app.example.org/'))
        ? value
        : '/',
    isNativeRedirect: (value: string) =>
      value.startsWith('endurain:') || value.startsWith('https://app.example.org/'),
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
  generateCodeVerifier: () => mocks.verifier,
  generateCodeChallenge: () => Promise.resolve('challenge-xyz'),
}))

const tokenExchange = {
  next_step: 'tokens',
  session_id: '00000000-0000-4000-8000-0000000000f2',
  access_token: 'sso-access',
  csrf_token: 'sso-csrf',
  token_type: 'bearer',
  expires_in: 900,
  refresh_token_expires_in: 604_800,
}

let assignMock: ReturnType<typeof vi.fn>
const originalLocation = window.location

beforeEach(() => {
  mocks.route.query = {}
  mocks.isAuthenticated = false
  mocks.verifier = 'verifier-123'
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
    expect(JSON.parse(sessionStorage.getItem('pkce_verifier') ?? '{}')).toMatchObject({
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
      'pkce_verifier',
      JSON.stringify({ verifier: 'verifier-123', createdAt: Date.now() }),
    )
    mocks.route.query = { sso: 'success', session_id: '00000000-0000-4000-8000-0000000000f2' }
    mocks.exchangeSessionForTokens.mockResolvedValue(tokenExchange)

    const { processSsoCallback } = useSsoLogin()
    const result = await processSsoCallback()

    expect(result).toEqual({ status: 'completed' })
    expect(mocks.exchangeSessionForTokens).toHaveBeenCalledWith(
      '00000000-0000-4000-8000-0000000000f2',
      'verifier-123',
    )
    expect(mocks.completeTokenLogin).toHaveBeenCalledWith(tokenExchange)
    expect(mocks.navigateAfterLogin).toHaveBeenCalled()
    // The single-use verifier is cleared after a successful exchange.
    expect(sessionStorage.getItem('pkce_verifier')).toBeNull()
  })

  it('fails when no PKCE verifier is stored', async () => {
    mocks.route.query = { sso: 'success', session_id: '00000000-0000-4000-8000-0000000000f2' }

    const { processSsoCallback } = useSsoLogin()
    const result = await processSsoCallback()

    expect(result).toEqual({ status: 'error', messageKey: 'login.ssoTokenExchangeFailed' })
    expect(mocks.exchangeSessionForTokens).not.toHaveBeenCalled()
    expect(mocks.completeTokenLogin).not.toHaveBeenCalled()
  })

  it('fails and removes expired PKCE verifiers', async () => {
    sessionStorage.setItem(
      'pkce_verifier',
      JSON.stringify({ verifier: 'verifier-123', createdAt: Date.now() - 10 * 60 * 1000 - 1 }),
    )
    mocks.route.query = { sso: 'success', session_id: '00000000-0000-4000-8000-0000000000f2' }

    const { processSsoCallback } = useSsoLogin()
    const result = await processSsoCallback()

    expect(result).toEqual({ status: 'error', messageKey: 'login.ssoTokenExchangeFailed' })
    expect(mocks.exchangeSessionForTokens).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('pkce_verifier')).toBeNull()
  })

  it('uses the verifier of the latest start when a second start overwrites the first', async () => {
    const { startSsoLogin, processSsoCallback } = useSsoLogin()
    mocks.verifier = 'verifier-first'
    await startSsoLogin('acme')
    mocks.verifier = 'verifier-second'
    await startSsoLogin('beta')
    mocks.route.query = { sso: 'success', session_id: '00000000-0000-4000-8000-0000000000f2' }
    mocks.exchangeSessionForTokens.mockResolvedValue(tokenExchange)

    const result = await processSsoCallback()

    expect(result).toEqual({ status: 'completed' })
    expect(mocks.exchangeSessionForTokens).toHaveBeenCalledWith(
      '00000000-0000-4000-8000-0000000000f2',
      'verifier-second',
    )
    expect(sessionStorage.getItem('pkce_verifier')).toBeNull()
  })

  describe('an account with MFA enabled', () => {
    const mfaRequired = new HttpError(
      403,
      'Forbidden',
      'MFA verification required',
      'urn:endurain:error:mfa-required',
    )

    function storeVerifier(): void {
      sessionStorage.setItem(
        'pkce_verifier',
        JSON.stringify({ verifier: 'verifier-123', createdAt: Date.now() }),
      )
      mocks.route.query = { sso: 'success', session_id: '00000000-0000-4000-8000-0000000000f2' }
    }

    it('asks for a code and keeps the verifier until the exchange succeeds', async () => {
      storeVerifier()
      mocks.exchangeSessionForTokens.mockRejectedValue(mfaRequired)

      const { processSsoCallback } = useSsoLogin()
      const result = await processSsoCallback()

      expect(result).toEqual({ status: 'mfa-required' })
      expect(mocks.completeTokenLogin).not.toHaveBeenCalled()
      expect(sessionStorage.getItem('pkce_verifier')).not.toBeNull()
    })

    it('exchanges the same session with the code and signs in', async () => {
      storeVerifier()
      mocks.exchangeSessionForTokens.mockRejectedValueOnce(mfaRequired)
      mocks.exchangeSessionForTokens.mockResolvedValueOnce(tokenExchange)

      const { processSsoCallback, completeSsoMfa } = useSsoLogin()
      await processSsoCallback()
      await completeSsoMfa('123456')

      expect(mocks.exchangeSessionForTokens).toHaveBeenLastCalledWith(
        '00000000-0000-4000-8000-0000000000f2',
        'verifier-123',
        '123456',
      )
      expect(mocks.completeTokenLogin).toHaveBeenCalledWith(
        expect.objectContaining({ access_token: 'sso-access' }),
      )
      expect(mocks.navigateAfterLogin).toHaveBeenCalled()
      expect(sessionStorage.getItem('pkce_verifier')).toBeNull()
    })

    it('lets the user retry after a wrong code', async () => {
      storeVerifier()
      mocks.exchangeSessionForTokens.mockRejectedValueOnce(mfaRequired)
      mocks.exchangeSessionForTokens.mockRejectedValueOnce(new HttpError(400, 'Bad Request'))
      mocks.exchangeSessionForTokens.mockResolvedValueOnce(tokenExchange)

      const { processSsoCallback, completeSsoMfa } = useSsoLogin()
      await processSsoCallback()
      await expect(completeSsoMfa('000000')).rejects.toBeInstanceOf(HttpError)
      await completeSsoMfa('123456')

      expect(mocks.completeTokenLogin).toHaveBeenCalledTimes(1)
    })

    it('refuses a code when no SSO login is waiting for one', async () => {
      const { completeSsoMfa } = useSsoLogin()

      await expect(completeSsoMfa('123456')).rejects.toThrow('No SSO login is waiting')
      expect(mocks.exchangeSessionForTokens).not.toHaveBeenCalled()
    })

    it('treats any other refusal as a failed exchange', async () => {
      storeVerifier()
      mocks.exchangeSessionForTokens.mockRejectedValue(new HttpError(409, 'Conflict'))

      const { processSsoCallback } = useSsoLogin()
      const result = await processSsoCallback()

      expect(result).toEqual({ status: 'error', messageKey: 'login.ssoTokenExchangeFailed' })
    })
  })

  it('removes the session id from the address bar once it holds it, keeping the rest of the query', async () => {
    mocks.route.query = {
      sso: 'success',
      session_id: '00000000-0000-4000-8000-0000000000f2',
      redirect: '/activities',
    }

    const { processSsoCallback } = useSsoLogin()
    await processSsoCallback()

    expect(mocks.routerReplace).toHaveBeenCalledWith(
      expect.objectContaining({ query: { sso: 'success', redirect: '/activities' } }),
    )
  })

  describe('mobile app handoff (external_redirect)', () => {
    it('forwards the session_id to the app scheme without touching the browser session', async () => {
      mocks.route.query = {
        sso: 'success',
        session_id: '00000000-0000-4000-8000-0000000000f2',
        external_redirect: 'true',
        redirect: 'endurain://native-callback',
      }

      const { processSsoCallback } = useSsoLogin()
      const result = await processSsoCallback()

      expect(result).toEqual({ status: 'completed' })
      expect(window.location.href).toBe(
        'endurain://native-callback?session_id=00000000-0000-4000-8000-0000000000f2',
      )
      expect(mocks.completeTokenLogin).not.toHaveBeenCalled()
      expect(mocks.routerReplace).not.toHaveBeenCalledWith({ name: 'home' })
    })

    it('forwards the session_id to a listed claimed-https address', async () => {
      mocks.route.query = {
        sso: 'success',
        session_id: '00000000-0000-4000-8000-0000000000f2',
        external_redirect: 'true',
        redirect: 'https://app.example.org/auth/sso/callback',
      }

      const { processSsoCallback } = useSsoLogin()
      const result = await processSsoCallback()

      expect(result).toEqual({ status: 'completed' })
      expect(window.location.href).toBe(
        'https://app.example.org/auth/sso/callback?session_id=00000000-0000-4000-8000-0000000000f2',
      )
      expect(mocks.completeTokenLogin).not.toHaveBeenCalled()
    })

    it.each([
      [
        'endurain://native-callback',
        'endurain://native-callback?session_id=00000000-0000-4000-8000-0000000000f2',
      ],
      ['endurain://cb?a=1', 'endurain://cb?a=1&session_id=00000000-0000-4000-8000-0000000000f2'],
      ['endurain://cb#frag', 'endurain://cb?session_id=00000000-0000-4000-8000-0000000000f2#frag'],
      [
        'endurain://cb?a=1#frag',
        'endurain://cb?a=1&session_id=00000000-0000-4000-8000-0000000000f2#frag',
      ],
      [
        'endurain://cb#frag?x=1',
        'endurain://cb?session_id=00000000-0000-4000-8000-0000000000f2#frag?x=1',
      ],
      ['endurain:/cb', 'endurain:/cb?session_id=00000000-0000-4000-8000-0000000000f2'],
      ['endurain:cb#frag', 'endurain:cb?session_id=00000000-0000-4000-8000-0000000000f2#frag'],
    ])(
      'puts the session_id of %s in the query, before any fragment',
      async (redirect, expected) => {
        mocks.route.query = {
          sso: 'success',
          session_id: '00000000-0000-4000-8000-0000000000f2',
          external_redirect: 'true',
          redirect,
        }

        const { processSsoCallback } = useSsoLogin()
        await processSsoCallback()

        expect(window.location.href).toBe(expected)
      },
    )

    it('never navigates the browser to an internal path just because the URL says external_redirect', async () => {
      // The flag is attacker-controllable; with no matching deep link and no stored
      // PKCE verifier the callback must fail rather than navigate anywhere.
      mocks.route.query = {
        sso: 'success',
        session_id: '00000000-0000-4000-8000-0000000000f2',
        external_redirect: 'true',
        redirect: '/\\evil.example',
      }
      const hrefBefore = window.location.href

      const { processSsoCallback } = useSsoLogin()
      const result = await processSsoCallback()

      expect(result).toEqual({ status: 'error', messageKey: 'login.ssoTokenExchangeFailed' })
      expect(window.location.href).toBe(hrefBefore)
      expect(mocks.completeTokenLogin).not.toHaveBeenCalled()
    })

    it('falls back to the dashboard when the browser already has an authenticated session', async () => {
      mocks.isAuthenticated = true
      mocks.route.query = {
        sso: 'success',
        session_id: '00000000-0000-4000-8000-0000000000f2',
        external_redirect: 'true',
        redirect: 'endurain://native-callback',
      }

      const { processSsoCallback } = useSsoLogin()
      const result = await processSsoCallback()

      expect(result).toEqual({ status: 'completed' })
      expect(window.location.href).toBe(
        'endurain://native-callback?session_id=00000000-0000-4000-8000-0000000000f2',
      )
      expect(mocks.routerReplace).toHaveBeenCalledWith({ name: 'home' })
    })
  })
})

describe('maybeAutoRedirect', () => {
  const settings = {
    sso_enabled: true,
    sso_auto_redirect: true,
    local_login_enabled: false,
  } as PublicServerSettings
  const providers = [{ slug: 'acme' }] as IdentityProviderPublic[]

  it('starts the SSO login when nothing on the route blocks it', async () => {
    const { maybeAutoRedirect } = useSsoLogin()

    maybeAutoRedirect(settings, providers, false)

    await vi.waitFor(() => expect(assignMock).toHaveBeenCalledTimes(1))
  })

  it.each([
    'logoutSuccess',
    'sessionExpired',
    'passwordResetSuccess',
    'passwordResetInvalidLink',
    'onboardingComplete',
    'emailVerificationSent',
    'adminApprovalRequired',
    'verifyEmailInvalidLink',
  ])('does not auto-redirect when the route carries %s', async (flag) => {
    mocks.route.query = { [flag]: 'true' }
    const { maybeAutoRedirect } = useSsoLogin()

    maybeAutoRedirect(settings, providers, false)
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(assignMock).not.toHaveBeenCalled()
  })
})
