import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { UserIdentityProviderDto } from '@/features/users/types'

import { apiFetch } from '@/services/http'
import {
  fetchUserIdentityProviders,
  mapUserIdentityProvider,
  unlinkUserIdentityProvider,
} from '@/features/users/services/identityProviders'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

/** Builds a full `IdentityProviderLinkRead` wire payload, overridable per case. */
function makeIdpDto(overrides: Partial<UserIdentityProviderDto> = {}): UserIdentityProviderDto {
  return {
    id: 3,
    user_id: 7,
    idp_id: 11,
    idp_name: 'Authelia',
    idp_slug: 'authelia',
    idp_icon: null,
    idp_icon_uploaded: false,
    idp_provider_type: 'oidc',
    idp_subject: 'auth|abc123',
    idp_access_token_expires_at: null,
    idp_refresh_token_updated_at: null,
    last_login: '2026-06-02T11:00:00Z',
    linked_at: '2026-06-01T10:00:00Z',
    ...overrides,
  }
}

describe('user identity providers service', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mapUserIdentityProvider camel-cases the wire shape', () => {
    expect(mapUserIdentityProvider(makeIdpDto())).toEqual({
      id: 3,
      idpId: 11,
      name: 'Authelia',
      slug: 'authelia',
      providerType: 'oidc',
      subject: 'auth|abc123',
      linkedAt: '2026-06-01T10:00:00Z',
      lastLogin: '2026-06-02T11:00:00Z',
    })
  })

  it('mapUserIdentityProvider falls back to null for missing optional fields', () => {
    const mapped = mapUserIdentityProvider(
      makeIdpDto({ idp_name: null, idp_slug: null, idp_provider_type: null, last_login: null }),
    )

    expect(mapped.name).toBeNull()
    expect(mapped.slug).toBeNull()
    expect(mapped.providerType).toBeNull()
    expect(mapped.lastLogin).toBeNull()
  })

  it('fetchUserIdentityProviders calls the endpoint and maps records', async () => {
    vi.mocked(apiFetch).mockResolvedValue([makeIdpDto()])

    const providers = await fetchUserIdentityProviders(7)

    expect(apiFetch).toHaveBeenCalledWith('/users/7/identity-providers', { signal: undefined })
    expect(providers[0]?.name).toBe('Authelia')
  })

  it('fetchUserIdentityProviders maps a null payload to an empty array', async () => {
    vi.mocked(apiFetch).mockResolvedValue(null)

    expect(await fetchUserIdentityProviders(7)).toEqual([])
  })

  it('unlinkUserIdentityProvider issues a scoped DELETE by provider id', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await unlinkUserIdentityProvider(7, 11)

    expect(apiFetch).toHaveBeenCalledWith('/users/7/identity-providers/11', {
      method: 'DELETE',
      responseType: 'void',
    })
  })
})
