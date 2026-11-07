import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '@/services/http'
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
    const provider = { id: 1, name: 'Pocket ID', slug: 'pocket-id' }
    vi.mocked(apiFetch).mockResolvedValueOnce({ items: [provider], next: null })

    expect(await fetchEnabledIdentityProviders()).toEqual([provider])
    expect(apiFetch).toHaveBeenCalledWith('/public/idp?page_number=1', {
      auth: false,
      retryOnUnauthorized: false,
    })
  })
})
