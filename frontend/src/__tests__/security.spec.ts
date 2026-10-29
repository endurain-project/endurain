import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { SecuritySessionDto } from '@/features/security/types'

import { apiFetch } from '@/services/http'
import {
  changeEmail,
  changePassword,
  deleteAccount,
  disableMfa,
  enableMfa,
  fetchBackupCodeStatus,
  fetchMfaStatus,
  fetchSessions,
  mapBackupCodeStatus,
  mapBackupCodes,
  mapMfaSetup,
  mapMfaStatus,
  mapSecuritySession,
  regenerateBackupCodes,
  revokeOtherSessions,
  revokeSession,
  setupMfa,
} from '@/features/security/services/security'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const sessionDto: SecuritySessionDto = {
  id: 'sess-1',
  user_id: 5,
  ip_address: '1.2.3.4',
  device_type: 'desktop',
  operating_system: 'macOS',
  operating_system_version: '14',
  browser: 'Firefox',
  browser_version: '120',
  created_at: '2026-01-01T00:00:00Z',
  last_activity_at: '2026-01-02T00:00:00Z',
  expires_at: '2026-02-01T00:00:00Z',
}

const mappedSession = {
  id: 'sess-1',
  ipAddress: '1.2.3.4',
  deviceType: 'desktop',
  operatingSystem: 'macOS',
  operatingSystemVersion: '14',
  browser: 'Firefox',
  browserVersion: '120',
  createdAt: '2026-01-01T00:00:00Z',
  lastActivityAt: '2026-01-02T00:00:00Z',
  expiresAt: '2026-02-01T00:00:00Z',
}

describe('security mappers', () => {
  it('maps MFA status', () => {
    expect(mapMfaStatus({ mfa_enabled: true })).toEqual({ enabled: true })
  })

  it('maps MFA setup (drops the app name)', () => {
    expect(
      mapMfaSetup({ secret: 'SEC', qr_code: 'data:image/png;base64,AAA', app_name: 'Endurain' }),
    ).toEqual({ secret: 'SEC', qrCode: 'data:image/png;base64,AAA' })
  })

  it('maps backup-code status', () => {
    expect(
      mapBackupCodeStatus({ has_codes: true, total: 10, unused: 8, used: 2, created_at: null }),
    ).toEqual({ hasCodes: true, total: 10, unused: 8, used: 2 })
  })

  it('maps regenerated backup codes', () => {
    expect(mapBackupCodes({ codes: ['x', 'y'], created_at: '2026-01-01' })).toEqual({
      codes: ['x', 'y'],
      createdAt: '2026-01-01',
    })
  })

  it('maps a session DTO to the clean model', () => {
    expect(mapSecuritySession(sessionDto)).toEqual(mappedSession)
  })
})

describe('security service requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('changePassword PUTs the snake-cased step-up body', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await changePassword({
      currentPassword: 'old',
      newPassword: 'new',
      mfaCode: '123456',
      revokeOtherSessions: true,
    })

    expect(apiFetch).toHaveBeenCalledWith('/profile/password/change', {
      method: 'POST',
      body: JSON.stringify({
        current_password: 'old',
        password: 'new',
        mfa_code: '123456',
        revoke_other_sessions: true,
      }),
      responseType: 'void',
    })
  })

  it('fetchMfaStatus reads the status path and maps it', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ mfa_enabled: false })

    expect(await fetchMfaStatus()).toEqual({ enabled: false })
    expect(apiFetch).toHaveBeenCalledWith(
      '/profile/mfa/status',
      expect.objectContaining({ signal: undefined }),
    )
  })

  it('setupMfa POSTs to the setup path and maps the response', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      secret: 'SEC',
      qr_code: 'data:image/png;base64,AAA',
      app_name: 'Endurain',
    })

    expect(await setupMfa()).toEqual({ secret: 'SEC', qrCode: 'data:image/png;base64,AAA' })
    expect(apiFetch).toHaveBeenCalledWith('/profile/mfa/setup', { method: 'POST' })
  })

  it('enableMfa POSTs the code and returns the backup codes', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ backup_codes: ['a', 'b'] })

    const codes = await enableMfa({ mfaCode: '123456', currentPassword: 'pw' })

    expect(apiFetch).toHaveBeenCalledWith('/profile/mfa/enable', {
      method: 'POST',
      body: JSON.stringify({ mfa_code: '123456', current_password: 'pw' }),
    })
    expect(codes).toEqual(['a', 'b'])
  })

  it('disableMfa POSTs the step-up body', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await disableMfa({ currentPassword: 'pw', mfaCode: '123456' })

    expect(apiFetch).toHaveBeenCalledWith('/profile/mfa/disable', {
      method: 'POST',
      body: JSON.stringify({ mfa_code: '123456', current_password: 'pw' }),
      responseType: 'void',
    })
  })

  it('fetchBackupCodeStatus maps the counts', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      has_codes: true,
      total: 10,
      unused: 9,
      used: 1,
      created_at: null,
    })

    expect(await fetchBackupCodeStatus()).toEqual({
      hasCodes: true,
      total: 10,
      unused: 9,
      used: 1,
    })
  })

  it('regenerateBackupCodes POSTs the step-up body and maps the result', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ codes: ['x'], created_at: '2026-01-01' })

    const result = await regenerateBackupCodes({ currentPassword: 'pw', mfaCode: '123456' })

    expect(apiFetch).toHaveBeenCalledWith('/profile/mfa/backup-codes', {
      method: 'POST',
      body: JSON.stringify({ current_password: 'pw', mfa_code: '123456' }),
    })
    expect(result).toEqual({ codes: ['x'], createdAt: '2026-01-01' })
  })

  it('fetchSessions reads the sessions path and maps the records', async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ items: [sessionDto], next: 2 })
      .mockResolvedValueOnce({ items: [sessionDto], next: null })

    expect(await fetchSessions()).toEqual([mappedSession, mappedSession])
    expect(apiFetch).toHaveBeenNthCalledWith(
      1,
      '/profile/sessions?page_number=1',
      expect.objectContaining({ signal: undefined }),
    )
    expect(apiFetch).toHaveBeenNthCalledWith(
      2,
      '/profile/sessions?page_number=2',
      expect.objectContaining({ signal: undefined }),
    )
  })

  it('fetchSessions maps a null payload to an empty array', async () => {
    vi.mocked(apiFetch).mockResolvedValue(null)
    await expect(fetchSessions()).resolves.toEqual([])
  })

  it('revokeSession DELETEs the session path', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await revokeSession('sess-1')

    expect(apiFetch).toHaveBeenCalledWith('/profile/sessions/sess-1', {
      method: 'DELETE',
      responseType: 'void',
    })
  })

  it('revokeOtherSessions DELETEs the bulk sessions path', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await revokeOtherSessions()

    expect(apiFetch).toHaveBeenCalledWith('/profile/sessions', {
      method: 'DELETE',
      responseType: 'void',
    })
  })
})

describe('deleteAccount', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('POSTs the step-up body to the delete-account path', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteAccount({ currentPassword: 'pw', mfaCode: '123456' })

    expect(apiFetch).toHaveBeenCalledWith('/profile/delete-account', {
      method: 'POST',
      body: JSON.stringify({ current_password: 'pw', mfa_code: '123456' }),
      responseType: 'void',
    })
  })

  it('sends null for step-up fields that do not apply', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteAccount({ currentPassword: null, mfaCode: null })

    expect(apiFetch).toHaveBeenCalledWith(
      '/profile/delete-account',
      expect.objectContaining({ body: JSON.stringify({ current_password: null, mfa_code: null }) }),
    )
  })
})

describe('changeEmail', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('PUTs the new address together with the step-up credentials', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await changeEmail('new@example.com', { currentPassword: 'pw', mfaCode: '123456' }, true)

    expect(apiFetch).toHaveBeenCalledWith('/profile/email/change', {
      method: 'POST',
      body: JSON.stringify({
        email: 'new@example.com',
        current_password: 'pw',
        mfa_code: '123456',
        revoke_other_sessions: true,
      }),
      responseType: 'void',
    })
  })
})
