import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { confirmPasswordReset, requestPasswordReset } from '@/features/auth/services/passwordReset'
import { completeOnboarding, fetchOnboardingStatus } from '@/features/auth/services/onboarding'
import { confirmSignUp } from '@/features/auth/services/signUp'

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
    fetchMock.mockResolvedValueOnce(jsonResponse({ message: 'ok' }))
    await requestPasswordReset({ email: 'user@example.com' })
    const call = fetchMock.mock.calls[0]
    expect(call?.[0]).toContain('/password-reset/request')
    expect(call?.[1].method).toBe('POST')
    expect(call?.[1].body).toBe(JSON.stringify({ email: 'user@example.com' }))
  })

  it('confirms a reset with the token and new password', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ message: 'reset' }))
    const result = await confirmPasswordReset({ token: 'tok', new_password: 'supersecret' })
    const call = fetchMock.mock.calls[0]
    expect(call?.[0]).toContain('/password-reset/confirm')
    expect(call?.[1].method).toBe('POST')
    expect(call?.[1].body).toBe(JSON.stringify({ token: 'tok', new_password: 'supersecret' }))
    expect(result).toEqual({ message: 'reset' })
  })
})

describe('signUp service', () => {
  it('confirms a sign-up with the verification token', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ message: 'verified', admin_approval_required: true }),
    )
    const result = await confirmSignUp({ token: 'verify-tok' })
    const call = fetchMock.mock.calls[0]
    expect(call?.[0]).toContain('/sign-up/confirm')
    expect(call?.[1].method).toBe('POST')
    expect(call?.[1].body).toBe(JSON.stringify({ token: 'verify-tok' }))
    expect(result.admin_approval_required).toBe(true)
  })

  it('sends the chosen password when confirming a sign-up link', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ message: 'verified' }))
    await confirmSignUp({ token: 'verify-tok', password: 'chosen-pass' })
    expect(fetchMock.mock.calls[0]?.[1].body).toBe(
      JSON.stringify({ token: 'verify-tok', password: 'chosen-pass' }),
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
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1 }, 201))
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
