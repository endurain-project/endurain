import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { UserSessionDto } from '@/features/users/types'

import { apiFetch } from '@/services/http'
import {
  fetchUserSessions,
  mapUserSession,
  revokeOtherUserSessions,
  revokeUserSession,
} from '@/features/users/services/sessions'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

/** Builds a full `UserSessionsRead` wire payload, overridable per case. */
function makeSessionDto(overrides: Partial<UserSessionDto> = {}): UserSessionDto {
  return {
    id: '00000000-0000-4000-8000-0000000000e1',
    user_id: '00000000-0000-4000-8000-000000000007',
    ip_address: '203.0.113.5',
    device_type: 'desktop',
    operating_system: 'macOS',
    operating_system_version: '15',
    browser: 'Chrome',
    browser_version: '148',
    created_at: '2026-06-01T10:00:00Z',
    last_activity_at: '2026-06-02T11:00:00Z',
    expires_at: '2026-06-08T10:00:00Z',
    ...overrides,
  }
}

describe('user sessions service', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mapUserSession camel-cases the wire shape', () => {
    expect(mapUserSession(makeSessionDto())).toEqual({
      id: '00000000-0000-4000-8000-0000000000e1',
      ipAddress: '203.0.113.5',
      deviceType: 'desktop',
      operatingSystem: 'macOS',
      operatingSystemVersion: '15',
      browser: 'Chrome',
      browserVersion: '148',
      createdAt: '2026-06-01T10:00:00Z',
      lastActivityAt: '2026-06-02T11:00:00Z',
      expiresAt: '2026-06-08T10:00:00Z',
      appRedirectUri: null,
    })
  })

  it('mapUserSession carries the app the session was signed in through', () => {
    const dto = makeSessionDto({ app_redirect_uri: 'com.example.app:/callback' })

    expect(mapUserSession(dto).appRedirectUri).toBe('com.example.app:/callback')
  })

  it('fetchUserSessions calls the user-sessions endpoint and maps records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [makeSessionDto()], next: null })

    const sessions = await fetchUserSessions('00000000-0000-4000-8000-000000000007')

    expect(apiFetch).toHaveBeenCalledWith(
      '/users/00000000-0000-4000-8000-000000000007/sessions?num_records=200&page_number=1',
      {
        signal: undefined,
      },
    )
    expect(sessions[0]?.browser).toBe('Chrome')
  })

  it('fetchUserSessions follows the pages until the last one', async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ items: [makeSessionDto()], next: 2 })
      .mockResolvedValueOnce({
        items: [makeSessionDto({ id: '00000000-0000-4000-8000-0000000000e2' })],
        next: null,
      })

    const sessions = await fetchUserSessions('00000000-0000-4000-8000-000000000007')

    expect(apiFetch).toHaveBeenNthCalledWith(
      2,
      '/users/00000000-0000-4000-8000-000000000007/sessions?num_records=200&page_number=2',
      expect.anything(),
    )
    expect(sessions.map((session) => session.id)).toEqual([
      '00000000-0000-4000-8000-0000000000e1',
      '00000000-0000-4000-8000-0000000000e2',
    ])
  })

  it('fetchUserSessions maps a null payload to an empty array', async () => {
    vi.mocked(apiFetch).mockResolvedValue(null)

    expect(await fetchUserSessions('00000000-0000-4000-8000-000000000007')).toEqual([])
  })

  const stepUp = { currentPassword: 'admin-pw', mfaCode: '123456' }
  const stepUpWire = { current_password: 'admin-pw', mfa_code: '123456' }

  it('revokeUserSession POSTs the revoke route with the administrator step-up', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await revokeUserSession(
      '00000000-0000-4000-8000-0000000000e1',
      '00000000-0000-4000-8000-000000000007',
      stepUp,
    )

    expect(apiFetch).toHaveBeenCalledWith(
      '/users/00000000-0000-4000-8000-000000000007/sessions/00000000-0000-4000-8000-0000000000e1/revoke',
      {
        method: 'POST',
        body: JSON.stringify({ step_up: stepUpWire }),
        responseType: 'void',
      },
    )
  })

  it('revokeUserSession sends the identity-provider proof of an administrator without a password', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await revokeUserSession(
      '00000000-0000-4000-8000-0000000000e1',
      '00000000-0000-4000-8000-000000000007',
      {
        currentPassword: null,
        mfaCode: null,
        idpReauth: { ticket: 't', codeVerifier: 'v' },
      },
    )

    expect(JSON.parse(vi.mocked(apiFetch).mock.calls[0]?.[1]?.body as string)).toEqual({
      step_up: {
        current_password: null,
        mfa_code: null,
        idp_reauth: { ticket: 't', code_verifier: 'v' },
      },
    })
  })

  it('revokeOtherUserSessions POSTs with the exclude query param and the step-up', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await revokeOtherUserSessions(
      '00000000-0000-4000-8000-000000000007',
      stepUp,
      '00000000-0000-4000-8000-0000000000e1',
    )

    expect(apiFetch).toHaveBeenCalledWith(
      '/users/00000000-0000-4000-8000-000000000007/sessions/revoke?exclude_session_id=00000000-0000-4000-8000-0000000000e1',
      {
        method: 'POST',
        body: JSON.stringify({ step_up: stepUpWire }),
        responseType: 'void',
      },
    )
  })

  it('revokeOtherUserSessions omits the exclude param when not given', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await revokeOtherUserSessions('00000000-0000-4000-8000-000000000007', stepUp)

    expect(apiFetch).toHaveBeenCalledWith(
      '/users/00000000-0000-4000-8000-000000000007/sessions/revoke',
      {
        method: 'POST',
        body: JSON.stringify({ step_up: stepUpWire }),
        responseType: 'void',
      },
    )
  })
})
