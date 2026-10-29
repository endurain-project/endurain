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

/** Builds a full `UsersSessionsRead` wire payload, overridable per case. */
function makeSessionDto(overrides: Partial<UserSessionDto> = {}): UserSessionDto {
  return {
    id: 'sess-1',
    user_id: 7,
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
      id: 'sess-1',
      ipAddress: '203.0.113.5',
      deviceType: 'desktop',
      operatingSystem: 'macOS',
      operatingSystemVersion: '15',
      browser: 'Chrome',
      browserVersion: '148',
      createdAt: '2026-06-01T10:00:00Z',
      lastActivityAt: '2026-06-02T11:00:00Z',
      expiresAt: '2026-06-08T10:00:00Z',
    })
  })

  it('fetchUserSessions calls the user-sessions endpoint and maps records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [makeSessionDto()], next: null })

    const sessions = await fetchUserSessions(7)

    expect(apiFetch).toHaveBeenCalledWith('/users/7/sessions?page_number=1', { signal: undefined })
    expect(sessions[0]?.browser).toBe('Chrome')
  })

  it('fetchUserSessions follows the pages until the last one', async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ items: [makeSessionDto()], next: 2 })
      .mockResolvedValueOnce({ items: [makeSessionDto({ id: 'sess-2' })], next: null })

    const sessions = await fetchUserSessions(7)

    expect(apiFetch).toHaveBeenNthCalledWith(
      2,
      '/users/7/sessions?page_number=2',
      expect.anything(),
    )
    expect(sessions.map((session) => session.id)).toEqual(['sess-1', 'sess-2'])
  })

  it('fetchUserSessions maps a null payload to an empty array', async () => {
    vi.mocked(apiFetch).mockResolvedValue(null)

    expect(await fetchUserSessions(7)).toEqual([])
  })

  it('revokeUserSession issues a scoped DELETE', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await revokeUserSession('sess-1', 7)

    expect(apiFetch).toHaveBeenCalledWith('/users/7/sessions/sess-1', {
      method: 'DELETE',
      responseType: 'void',
    })
  })

  it('revokeOtherUserSessions DELETEs with the exclude query param', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await revokeOtherUserSessions(7, 'sess-1')

    expect(apiFetch).toHaveBeenCalledWith('/users/7/sessions?exclude_session_id=sess-1', {
      method: 'DELETE',
      responseType: 'void',
    })
  })

  it('revokeOtherUserSessions omits the exclude param when not given', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await revokeOtherUserSessions(7)

    expect(apiFetch).toHaveBeenCalledWith('/users/7/sessions', {
      method: 'DELETE',
      responseType: 'void',
    })
  })
})
