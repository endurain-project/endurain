import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '@/services/http'
import type { IdentityProviderPublic } from '@/types'
import { fetchEnabledIdentityProviders } from '@/services/identityProviders'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
  API_BASE_URL: '/api/v1',
}))

describe('fetchEnabledIdentityProviders', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('reads every page of the public list without credentials', async () => {
    const provider: IdentityProviderPublic = {
      id: '00000000-0000-4000-8000-000000000001',
      name: 'Pocket ID',
      slug: 'pocket-id',
      icon_uploaded: false,
    }
    vi.mocked(apiFetch).mockResolvedValueOnce({ items: [provider], next: null })

    expect(await fetchEnabledIdentityProviders()).toEqual([provider])
    expect(apiFetch).toHaveBeenCalledWith('/public/idp?num_records=200&page_number=1', {
      auth: false,
      retryOnUnauthorized: false,
    })
  })
})
