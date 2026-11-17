import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { IdentityProviderPublic } from '@/types'
import type { PublicServerSettings } from '@/features/config/types'

import { useSsoLogin } from '@/features/auth/composables/useSsoLogin'
import { HttpError } from '@/services/http'

const mocks = vi.hoisted(() => ({
  route: { query: {} as Record<string, unknown> },
  isAuthenticated: false,
  verifier: 'verifier-123',
  exchangeSsoSession: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  navigateAfterLogin: vi.fn<(...args: unknown[]) => void>(),
  routerReplace: vi.fn<(...args: unknown[]) => Promise<void>>(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => ({ replace: mocks.routerReplace }),
}))

vi.mock('@/features/auth/stores/auth', () => ({
  useAuthStore: () => ({
    exchangeSsoSession: mocks.exchangeSsoSession,
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

vi.mock('@/services/identityProviders', () => ({
  getIdentityProviderLoginUrl: (slug: string, params: URLSearchParams) =>
    `https://idp.test/${slug}?${params.toString()}`,
}))

vi.mock('@/features/auth/utils/pkce', () => ({
  generateCodeVerifier: () => mocks.verifier,
  generateCodeChallenge: () => Promise.resolve('challenge-xyz'),
}))

const signedIn = { status: 'authenticated', user: { id: 'user-1' } }

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
    expect(mocks.exchangeSsoSession).not.toHaveBeenCalled()
  })

  it('exchanges the session + stored verifier for tokens and completes login', async () => {
    sessionStorage.setItem(
      'pkce_verifier',
      JSON.stringify({ verifier: 'verifier-123', createdAt: Date.now() }),
    )
    mocks.route.query = { sso: 'success', session_id: '00000000-0000-4000-8000-0000000000f2' }
    mocks.exchangeSsoSession.mockResolvedValue(signedIn)

    const { processSsoCallback } = useSsoLogin()
    const result = await processSsoCallback()

    expect(result).toEqual({ status: 'completed' })
    expect(mocks.exchangeSsoSession).toHaveBeenCalledWith(
      '00000000-0000-4000-8000-0000000000f2',
      'verifier-123',
    )
    expect(mocks.navigateAfterLogin).toHaveBeenCalled()
    // The single-use verifier is cleared after a successful exchange.
    expect(sessionStorage.getItem('pkce_verifier')).toBeNull()
  })

  it('fails when no PKCE verifier is stored', async () => {
    mocks.route.query = { sso: 'success', session_id: '00000000-0000-4000-8000-0000000000f2' }

    const { processSsoCallback } = useSsoLogin()
    const result = await processSsoCallback()

    expect(result).toEqual({ status: 'error', messageKey: 'login.ssoTokenExchangeFailed' })
    expect(mocks.exchangeSsoSession).not.toHaveBeenCalled()
    expect(mocks.exchangeSsoSession).not.toHaveBeenCalled()
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
    expect(mocks.exchangeSsoSession).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('pkce_verifier')).toBeNull()
  })

  it('uses the verifier of the latest start when a second start overwrites the first', async () => {
    const { startSsoLogin, processSsoCallback } = useSsoLogin()
    mocks.verifier = 'verifier-first'
    await startSsoLogin('acme')
    mocks.verifier = 'verifier-second'
    await startSsoLogin('beta')
    mocks.route.query = { sso: 'success', session_id: '00000000-0000-4000-8000-0000000000f2' }
    mocks.exchangeSsoSession.mockResolvedValue(signedIn)

    const result = await processSsoCallback()

    expect(result).toEqual({ status: 'completed' })
    expect(mocks.exchangeSsoSession).toHaveBeenCalledWith(
      '00000000-0000-4000-8000-0000000000f2',
      'verifier-second',
    )
    expect(sessionStorage.getItem('pkce_verifier')).toBeNull()
  })

  describe('an account with MFA enabled', () => {
    function storeVerifier(): void {
      sessionStorage.setItem(
        'pkce_verifier',
        JSON.stringify({ verifier: 'verifier-123', createdAt: Date.now() }),
      )
      mocks.route.query = { sso: 'success', session_id: '00000000-0000-4000-8000-0000000000f2' }
    }

    it('hands the MFA step to the login form and clears the verifier the exchange used', async () => {
      storeVerifier()
      mocks.exchangeSsoSession.mockResolvedValue({ status: 'mfa-required', challenge: 'sso-chal' })

      const { processSsoCallback } = useSsoLogin()
      const result = await processSsoCallback()

      expect(result).toEqual({
        status: 'next-step',
        result: { status: 'mfa-required', challenge: 'sso-chal' },
      })
      expect(mocks.navigateAfterLogin).not.toHaveBeenCalled()
      expect(sessionStorage.getItem('pkce_verifier')).toBeNull()
    })

    it('treats a refused exchange as a failed exchange and keeps the verifier', async () => {
      storeVerifier()
      mocks.exchangeSsoSession.mockRejectedValue(new HttpError(409, 'Conflict'))

      const { processSsoCallback } = useSsoLogin()
      const result = await processSsoCallback()

      expect(result).toEqual({ status: 'error', messageKey: 'login.ssoTokenExchangeFailed' })
      expect(sessionStorage.getItem('pkce_verifier')).not.toBeNull()
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
    it('waits for a tap before forwarding the session_id to a custom scheme', async () => {
      mocks.route.query = {
        sso: 'success',
        session_id: '00000000-0000-4000-8000-0000000000f2',
        external_redirect: 'true',
        redirect: 'endurain://native-callback',
      }

      const { processSsoCallback } = useSsoLogin()
      const result = await processSsoCallback()

      expect(result).toEqual({
        status: 'app-handoff',
        target: 'endurain://native-callback?session_id=00000000-0000-4000-8000-0000000000f2',
      })
      expect(window.location.href).toBe('')
      expect(mocks.exchangeSsoSession).not.toHaveBeenCalled()
      expect(mocks.routerReplace).not.toHaveBeenCalledWith({ name: 'home' })
    })

    it('navigates to the custom-scheme target only when the user continues', async () => {
      const { continueAppHandoff } = useSsoLogin()
      await continueAppHandoff('endurain://native-callback?session_id=abc')

      expect(window.location.href).toBe('endurain://native-callback?session_id=abc')
      expect(mocks.routerReplace).not.toHaveBeenCalled()
    })

    it('falls back to the dashboard after continuing when the browser is authenticated', async () => {
      mocks.isAuthenticated = true
      const { continueAppHandoff } = useSsoLogin()
      await continueAppHandoff('endurain://native-callback?session_id=abc')

      expect(mocks.routerReplace).toHaveBeenCalledWith({ name: 'home' })
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
      expect(mocks.exchangeSsoSession).not.toHaveBeenCalled()
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
        const result = await processSsoCallback()

        expect(result).toEqual({ status: 'app-handoff', target: expected })
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
      expect(mocks.exchangeSsoSession).not.toHaveBeenCalled()
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

  it('does not auto-redirect when several providers are enabled', async () => {
    const { maybeAutoRedirect } = useSsoLogin()

    maybeAutoRedirect(
      settings,
      [{ slug: 'acme' }, { slug: 'other' }] as IdentityProviderPublic[],
      false,
    )
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(assignMock).not.toHaveBeenCalled()
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
