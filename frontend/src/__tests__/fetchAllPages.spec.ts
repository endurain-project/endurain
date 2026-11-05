import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '@/services/http'
import { fetchAllPages } from '@/services/pagination'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

describe('fetchAllPages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('follows next to the last page and keeps the query parameters', async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ items: [1, 2], next: 2 })
      .mockResolvedValueOnce({ items: [3], next: null })

    const items = await fetchAllPages<number>('/things', new URLSearchParams({ q: 'x' }))

    expect(items).toEqual([1, 2, 3])
    expect(apiFetch).toHaveBeenNthCalledWith(1, '/things?q=x&page_number=1', {})
    expect(apiFetch).toHaveBeenNthCalledWith(2, '/things?q=x&page_number=2', {})
  })

  it('sends the request options on every page', async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ items: ['a'], next: 2 })
      .mockResolvedValueOnce({ items: ['b'], next: null })
    const init = { auth: false, retryOnUnauthorized: false }

    await fetchAllPages<string>('/public/things', undefined, init)

    expect(apiFetch).toHaveBeenNthCalledWith(1, '/public/things?page_number=1', init)
    expect(apiFetch).toHaveBeenNthCalledWith(2, '/public/things?page_number=2', init)
  })
})
