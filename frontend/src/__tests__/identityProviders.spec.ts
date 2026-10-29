import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  IdentityProviderDto,
  IdentityProviderInput,
  IdentityProviderTemplateDto,
} from '@/features/identityProviders/types'

import { apiFetch } from '@/services/http'
import {
  createIdentityProvider,
  deleteIdentityProvider,
  fetchIdentityProviders,
  fetchIdentityProviderTemplates,
  mapIdentityProvider,
  mapIdentityProviderTemplate,
  toProviderInput,
  updateIdentityProvider,
} from '@/features/identityProviders/services/identityProviders'
import {
  isBuiltinProviderIcon,
  resolveProviderLogo,
} from '@/features/identityProviders/utils/providerIcon'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

/** Builds a full `IdentityProvider` wire payload, overridable per case. */
function makeProviderDto(overrides: Partial<IdentityProviderDto> = {}): IdentityProviderDto {
  return {
    id: 3,
    version: 1,
    name: 'Keycloak',
    slug: 'keycloak',
    provider_type: 'oidc',
    enabled: true,
    issuer_url: 'https://idp.test/realms/main',
    authorization_endpoint: 'https://idp.test/auth',
    token_endpoint: 'https://idp.test/token',
    userinfo_endpoint: 'https://idp.test/userinfo',
    jwks_uri: 'https://idp.test/certs',
    scopes: 'openid profile email',
    icon: 'keycloak',
    auto_create_users: true,
    sync_user_info: true,
    client_id: 'endurain',
    user_mapping: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    ...overrides,
  }
}

/** Builds a full `IdentityProviderTemplateRead` wire payload, overridable per case. */
function makeTemplateDto(
  overrides: Partial<IdentityProviderTemplateDto> = {},
): IdentityProviderTemplateDto {
  return {
    template_id: 'keycloak',
    name: 'Keycloak',
    provider_type: 'oidc',
    issuer_url: 'https://idp.test',
    scopes: 'openid profile email',
    icon: 'keycloak',
    user_mapping: null,
    description: 'Keycloak OIDC',
    configuration_notes: 'Create a confidential client',
    ...overrides,
  }
}

/** A clean provider input used by the create/update cases. */
function makeInput(overrides: Partial<IdentityProviderInput> = {}): IdentityProviderInput {
  return {
    name: 'Keycloak',
    slug: 'keycloak',
    providerType: 'oidc',
    enabled: true,
    issuerUrl: 'https://idp.test',
    clientId: 'endurain',
    clientSecret: 'shh',
    scopes: 'openid profile email',
    icon: 'keycloak',
    autoCreateUsers: true,
    syncUserInfo: true,
    ...overrides,
  }
}

describe('mapIdentityProvider', () => {
  it('maps the wire shape to the clean camel-cased model', () => {
    expect(mapIdentityProvider(makeProviderDto())).toEqual({
      id: 3,
      version: 1,
      name: 'Keycloak',
      slug: 'keycloak',
      providerType: 'oidc',
      enabled: true,
      issuerUrl: 'https://idp.test/realms/main',
      clientId: 'endurain',
      scopes: 'openid profile email',
      icon: 'keycloak',
      autoCreateUsers: true,
      syncUserInfo: true,
      authorizationEndpoint: 'https://idp.test/auth',
      tokenEndpoint: 'https://idp.test/token',
      userinfoEndpoint: 'https://idp.test/userinfo',
    })
  })

  it('normalizes absent optional fields to null', () => {
    const provider = mapIdentityProvider(
      makeProviderDto({ issuer_url: null, client_id: null, icon: null }),
    )
    expect(provider.issuerUrl).toBeNull()
    expect(provider.clientId).toBeNull()
    expect(provider.icon).toBeNull()
  })
})

describe('mapIdentityProviderTemplate', () => {
  it('maps the wire shape to the clean model', () => {
    expect(mapIdentityProviderTemplate(makeTemplateDto())).toEqual({
      templateId: 'keycloak',
      name: 'Keycloak',
      providerType: 'oidc',
      issuerUrl: 'https://idp.test',
      scopes: 'openid profile email',
      icon: 'keycloak',
      description: 'Keycloak OIDC',
      configurationNotes: 'Create a confidential client',
    })
  })
})

describe('toProviderInput', () => {
  it('projects a stored provider to an input with no client secret', () => {
    const input = toProviderInput(mapIdentityProvider(makeProviderDto()))
    expect(input.clientSecret).toBeNull()
    expect(input).toMatchObject({ name: 'Keycloak', slug: 'keycloak', enabled: true })
  })
})

describe('identity providers service requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetchIdentityProviders maps the list and tolerates a null payload', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([makeProviderDto()])
    expect(await fetchIdentityProviders()).toHaveLength(1)
    expect(apiFetch).toHaveBeenCalledWith('/identity-providers', { signal: undefined })

    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    expect(await fetchIdentityProviders()).toEqual([])
  })

  it('fetchIdentityProviderTemplates reads the templates endpoint', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([makeTemplateDto()])
    expect(await fetchIdentityProviderTemplates()).toHaveLength(1)
    expect(apiFetch).toHaveBeenCalledWith('/identity-providers/templates', { signal: undefined })
  })

  it('createIdentityProvider posts the wire body including the client secret', async () => {
    let body: unknown
    vi.mocked(apiFetch).mockImplementation((_path, init) => {
      body = init?.body
      return Promise.resolve(makeProviderDto())
    })

    await createIdentityProvider(makeInput())

    expect(apiFetch).toHaveBeenCalledWith(
      '/identity-providers',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(JSON.parse(body as string)).toEqual({
      name: 'Keycloak',
      slug: 'keycloak',
      provider_type: 'oidc',
      enabled: true,
      issuer_url: 'https://idp.test',
      client_id: 'endurain',
      scopes: 'openid profile email',
      icon: 'keycloak',
      auto_create_users: true,
      sync_user_info: true,
      client_secret: 'shh',
    })
  })

  it('updateIdentityProvider omits the client secret when not provided', async () => {
    let body: unknown
    vi.mocked(apiFetch).mockImplementation((_path, init) => {
      body = init?.body
      return Promise.resolve(makeProviderDto())
    })

    await updateIdentityProvider(3, makeInput({ clientSecret: null }), 4)

    expect(apiFetch).toHaveBeenCalledWith(
      '/identity-providers/3',
      expect.objectContaining({ method: 'PUT', headers: { 'If-Match': '"4"' } }),
    )
    const parsed = JSON.parse(body as string) as Record<string, unknown>
    expect(parsed).not.toHaveProperty('client_secret')
    expect(parsed).toMatchObject({ name: 'Keycloak', enabled: true })
  })

  it('updateIdentityProvider includes the client secret when provided', async () => {
    let body: unknown
    vi.mocked(apiFetch).mockImplementation((_path, init) => {
      body = init?.body
      return Promise.resolve(makeProviderDto())
    })

    await updateIdentityProvider(3, makeInput({ clientSecret: 'rotated' }), 4)

    expect((JSON.parse(body as string) as Record<string, unknown>).client_secret).toBe('rotated')
  })

  it('deleteIdentityProvider issues a DELETE', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteIdentityProvider(3, 5)

    expect(apiFetch).toHaveBeenCalledWith('/identity-providers/3', {
      method: 'DELETE',
      headers: { 'If-Match': '"5"' },
      responseType: 'void',
    })
  })
})

describe('resolveProviderLogo', () => {
  it('returns a bundled asset for a built-in icon key', () => {
    const logo = resolveProviderLogo('keycloak')
    expect(logo).toBeTruthy()
    expect(typeof logo).toBe('string')
  })

  it('returns the raw URL for a custom icon', () => {
    expect(resolveProviderLogo('https://example.com/logo.png')).toBe('https://example.com/logo.png')
  })

  it('returns null when no icon is set', () => {
    expect(resolveProviderLogo(null)).toBeNull()
    expect(resolveProviderLogo('')).toBeNull()
  })
})

describe('isBuiltinProviderIcon', () => {
  it('recognizes the built-in keys only', () => {
    expect(isBuiltinProviderIcon('keycloak')).toBe(true)
    expect(isBuiltinProviderIcon('custom')).toBe(false)
    expect(isBuiltinProviderIcon(null)).toBe(false)
  })
})
