import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { confirmPasswordReset, requestPasswordReset } from '@/features/auth/services/passwordReset'
import { completeOnboarding, fetchOnboardingStatus } from '@/features/auth/services/onboarding'
import { loginWithPassword, refreshSession } from '@/features/auth/services/session'
import { getAccessToken, getCsrfToken } from '@/services/authTokens'
import { confirmEmailChange, confirmSignUp } from '@/features/auth/services/signUp'
import { exchangeSessionForTokens } from '@/services/identityProviders'
import { userUuid } from './fixtures/activity'

vi.mock('@/services/runtime', () => ({
  getApiBaseUrl: () => '',
  getRuntimeBackendHost: () => null,
  getBackendAssetUrl: (path: string) => path,
}))

vi.mock('@/services/authTokens', () => ({
  getAccessToken: vi.fn<() => string | null>(() => null),
  getCsrfToken: vi.fn<() => string | null>(() => null),
  setAuthTokens: vi.fn<() => void>(),
  clearAuthTokens: vi.fn<() => void>(),
}))

/**
 * Builds a JSON Response for a single read.
 *
 * @param body - Object to serialize.
 * @param status - HTTP status code.
 * @returns A Response instance.
 */
function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<Response>>()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('passwordReset service', () => {
  it('requests a reset without auth', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await requestPasswordReset({ email: 'user@example.com' })
    const call = fetchMock.mock.calls[0]
    expect(call?.[0]).toContain('/public/password-reset/request')
    expect(call?.[1].method).toBe('POST')
    expect(call?.[1].body).toBe(JSON.stringify({ email: 'user@example.com' }))
  })

  it('confirms a reset with the token and new password', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))
    const result = await confirmPasswordReset({ token: 'tok', password: 'supersecret' })
    const call = fetchMock.mock.calls[0]
    expect(call?.[0]).toContain('/public/password-reset/confirm')
    expect(call?.[1].method).toBe('POST')
    expect(call?.[1].body).toBe(JSON.stringify({ token: 'tok', password: 'supersecret' }))
    expect(result).toBeUndefined()
  })
})

describe('signUp service', () => {
  it('confirms a sign-up with the verification token and the chosen password', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ next_step: 'await_approval' }))
    const result = await confirmSignUp({ token: 'verify-tok', password: 'chosen-pass' })
    const call = fetchMock.mock.calls[0]
    expect(call?.[0]).toContain('/public/sign-up/confirm')
    expect(call?.[1].method).toBe('POST')
    expect(call?.[1].body).toBe(JSON.stringify({ token: 'verify-tok', password: 'chosen-pass' }))
    expect(result.next_step).toBe('await_approval')
  })

  it('confirms an email change with the token alone', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ next_step: 'sign_in' }))
    const result = await confirmEmailChange({ token: 'change-tok' })
    const call = fetchMock.mock.calls[0]
    expect(call?.[0]).toContain('/public/email-change/confirm')
    expect(call?.[1].method).toBe('POST')
    expect(call?.[1].body).toBe(JSON.stringify({ token: 'change-tok' }))
    expect(result.next_step).toBe('sign_in')
  })
})

describe('SSO token exchange service', () => {
  it('posts the verifier to the session exchange under /auth', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ next_step: 'tokens', session_id: 'sid' }))
    await exchangeSessionForTokens('sid/1', 'verifier-123', '123456')
    const call = fetchMock.mock.calls[0]
    expect(call?.[0]).toContain('/auth/sessions/sid%2F1/tokens')
    expect(call?.[0]).not.toContain('/public/idp/session')
    expect(call?.[1].method).toBe('POST')
    expect(call?.[1].body).toBe(
      JSON.stringify({ code_verifier: 'verifier-123', mfa_code: '123456' }),
    )
  })
})

describe('onboarding service', () => {
  it('reads the status without auth and maps it to the clean model', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ onboarding_required: true }))
    const status = await fetchOnboardingStatus()
    const call = fetchMock.mock.calls[0]
    expect(call?.[0]).toContain('/public/onboarding')
    expect(status).toEqual({ onboardingRequired: true })
  })

  it('posts the setup token and the administrator details', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: userUuid(1) }, 201))
    const request = {
      token: 'tok',
      name: 'Ada',
      username: 'ada',
      email: 'ada@example.com',
      password: 'Sup3r-secret!',
    }
    await completeOnboarding(request)
    const call = fetchMock.mock.calls[0]
    expect(call?.[0]).toContain('/public/onboarding')
    expect(call?.[1].method).toBe('POST')
    expect(call?.[1].body).toBe(JSON.stringify(request))
  })
})

describe('session service', () => {
  it('signs in with the username and password only', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ next_step: 'mfa' }))

    await loginWithPassword('bob', 'secret')

    const [url, init] = fetchMock.mock.calls[0] ?? ['', {}]
    expect(url).toContain('/auth/login')
    expect(new URLSearchParams(init.body as URLSearchParams).toString()).toBe(
      'username=bob&password=secret',
    )
  })

  it('refreshes without the CSRF token even when one is held', async () => {
    vi.mocked(getAccessToken).mockReturnValueOnce('access-old')
    vi.mocked(getCsrfToken).mockReturnValueOnce('csrf-old')
    fetchMock.mockResolvedValueOnce(jsonResponse({ access_token: 'a', csrf_token: 'c' }))

    await refreshSession()

    const [url, init] = fetchMock.mock.calls[0] ?? ['', {}]
    expect(url).toContain('/auth/refresh')
    expect((init.headers as Headers).get('X-CSRF-Token')).toBeNull()
  })
})
