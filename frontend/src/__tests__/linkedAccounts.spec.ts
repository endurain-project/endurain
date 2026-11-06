import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { LinkedProviderDto, StepUpInput } from '@/features/security/types'

import { apiFetch } from '@/services/http'
import {
  fetchLinkedProviders,
  mapLinkedProvider,
  startProviderLink,
  unlinkProvider,
} from '@/features/security/services/linkedAccounts'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
  API_BASE_URL: '/api/v1',
}))

const linkedDto: LinkedProviderDto = {
  id: 3,
  user_id: 7,
  idp_id: 2,
  idp_subject: 'sub-abc',
  idp_name: 'Keycloak',
  idp_slug: 'keycloak',
  idp_icon: 'keycloak',
  idp_icon_uploaded: false,
  idp_provider_type: 'oidc',
  linked_at: '2026-01-01T00:00:00Z',
  last_login: '2026-01-02T00:00:00Z',
}

const mappedLinked = {
  id: 3,
  idpId: 2,
  name: 'Keycloak',
  slug: 'keycloak',
  icon: 'keycloak',
  iconUploaded: false,
  providerType: 'oidc',
  subject: 'sub-abc',
  linkedAt: '2026-01-01T00:00:00Z',
  lastLogin: '2026-01-02T00:00:00Z',
}

const stepUp: StepUpInput = { currentPassword: 'pw', mfaCode: '123456' }

describe('mapLinkedProvider', () => {
  it('maps the snake-cased DTO to the clean model', () => {
    expect(mapLinkedProvider(linkedDto)).toEqual(mappedLinked)
  })

  it('collapses absent enriched fields to null', () => {
    expect(
      mapLinkedProvider({
        id: 1,
        user_id: 1,
        idp_id: 9,
        idp_icon_uploaded: false,
        idp_subject: 'x',
        linked_at: '2026-01-01',
      }),
    ).toEqual({
      id: 1,
      idpId: 9,
      name: null,
      slug: null,
      icon: null,
      iconUploaded: false,
      providerType: null,
      subject: 'x',
      linkedAt: '2026-01-01',
      lastLogin: null,
    })
  })
})

describe('linked-accounts service requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetchLinkedProviders reads /profile/identity-providers and maps the records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [linkedDto], next: null })

    expect(await fetchLinkedProviders()).toEqual([mappedLinked])
    expect(apiFetch).toHaveBeenCalledWith('/profile/identity-providers?page_number=1', {
      signal: undefined,
    })
  })

  it('startProviderLink POSTs the step-up body and return path and returns the provider URL', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ authorization_url: 'https://idp.example.com/auth' })

    const url = await startProviderLink(2, stepUp)

    expect(apiFetch).toHaveBeenCalledWith('/profile/identity-providers/2/link', {
      method: 'POST',
      body: JSON.stringify({
        redirect: '/settings/security',
        step_up: { current_password: 'pw', mfa_code: '123456' },
      }),
    })
    expect(url).toBe('https://idp.example.com/auth')
  })

  it('startProviderLink honors an explicit return path', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ authorization_url: 'https://idp.example.com/auth' })

    await startProviderLink(3, stepUp, '/settings/security?foo=bar')

    expect(apiFetch).toHaveBeenCalledWith('/profile/identity-providers/3/link', {
      method: 'POST',
      body: JSON.stringify({
        redirect: '/settings/security?foo=bar',
        step_up: { current_password: 'pw', mfa_code: '123456' },
      }),
    })
  })

  it('unlinkProvider POSTs the step-up body to the unlink path', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await unlinkProvider(2, stepUp)

    expect(apiFetch).toHaveBeenCalledWith('/profile/identity-providers/2/unlink', {
      method: 'POST',
      body: JSON.stringify({ step_up: { current_password: 'pw', mfa_code: '123456' } }),
      responseType: 'void',
    })
  })
})
