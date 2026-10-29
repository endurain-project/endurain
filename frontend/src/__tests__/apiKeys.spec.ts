import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ApiKeyCreatedDto, ApiKeyDto } from '@/features/security/types'

import { apiFetch } from '@/services/http'
import {
  createApiKey,
  deleteApiKey,
  fetchApiKeys,
  mapApiKey,
  revokeApiKey,
} from '@/features/security/services/security'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const apiKeyDto: ApiKeyDto = {
  id: 'key-1',
  user_id: 5,
  name: 'CI upload',
  key_prefix: 'endurain',
  scopes: '["activities:upload"]',
  expires_at: '2026-12-31T00:00:00Z',
  last_used_at: '2026-06-01T00:00:00Z',
  created_at: '2026-01-01T00:00:00Z',
  is_active: true,
}

describe('mapApiKey', () => {
  it('maps a full payload and parses the JSON scopes string', () => {
    expect(mapApiKey(apiKeyDto)).toEqual({
      id: 'key-1',
      name: 'CI upload',
      keyPrefix: 'endurain',
      scopes: ['activities:upload'],
      expiresAt: '2026-12-31T00:00:00Z',
      lastUsedAt: '2026-06-01T00:00:00Z',
      createdAt: '2026-01-01T00:00:00Z',
      isActive: true,
    })
  })

  it('defaults nullable fields and tolerates a malformed scopes string', () => {
    const mapped = mapApiKey({
      ...apiKeyDto,
      scopes: 'not-json',
      expires_at: null,
      last_used_at: null,
      is_active: false,
    })
    expect(mapped.scopes).toEqual([])
    expect(mapped.expiresAt).toBeNull()
    expect(mapped.lastUsedAt).toBeNull()
    expect(mapped.isActive).toBe(false)
  })
})

describe('api key service', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('fetchApiKeys reads the path and maps the records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [apiKeyDto], next: null })

    const keys = await fetchApiKeys()

    expect(apiFetch).toHaveBeenCalledWith(
      '/profile/api-keys?page_number=1',
      expect.objectContaining({ signal: undefined }),
    )
    expect(keys).toHaveLength(1)
    expect(keys[0]?.scopes).toEqual(['activities:upload'])
  })

  it('fetchApiKeys maps a null payload to an empty list', async () => {
    vi.mocked(apiFetch).mockResolvedValue(null)
    await expect(fetchApiKeys()).resolves.toEqual([])
  })

  it('createApiKey POSTs the body and returns the one-time raw key', async () => {
    const created: ApiKeyCreatedDto = { ...apiKeyDto, key: 'endurain_rawsecret' }
    vi.mocked(apiFetch).mockResolvedValue(created)

    const rawKey = await createApiKey({
      name: 'CI upload',
      scopes: ['activities:upload'],
      expiresAt: '2026-12-31',
      currentPassword: 'pw',
      mfaCode: '123456',
    })

    expect(rawKey).toBe('endurain_rawsecret')
    expect(apiFetch).toHaveBeenCalledWith('/profile/api-keys', {
      method: 'POST',
      body: JSON.stringify({
        name: 'CI upload',
        scopes: ['activities:upload'],
        expires_at: '2026-12-31',
        current_password: 'pw',
        mfa_code: '123456',
      }),
    })
  })

  it('revokeApiKey POSTs the revoke path (void, id encoded)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await revokeApiKey('key 1')

    expect(apiFetch).toHaveBeenCalledWith('/profile/api-keys/key%201/revoke', {
      method: 'POST',
      responseType: 'void',
    })
  })

  it('deleteApiKey DELETEs the key path (void, id encoded)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteApiKey('key 1')

    expect(apiFetch).toHaveBeenCalledWith('/profile/api-keys/key%201', {
      method: 'DELETE',
      responseType: 'void',
    })
  })
})
