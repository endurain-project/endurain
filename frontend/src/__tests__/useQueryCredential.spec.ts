import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useQueryCredential } from '@/composables/useRouteQuery'

const route = vi.hoisted(() => ({
  path: '/reset-password',
  query: {} as Record<string, unknown>,
  hash: '',
}))
const replace = vi.hoisted(() => vi.fn<(to: unknown) => Promise<void>>(() => Promise.resolve()))

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace }),
}))

beforeEach(() => {
  route.path = '/reset-password'
  route.query = {}
  replace.mockClear()
  sessionStorage.clear()
})
afterEach(() => {
  vi.restoreAllMocks()
})

describe('useQueryCredential', () => {
  it('returns the credential from the URL and removes it from the address bar', () => {
    route.query = { token: 'abc', other: 'kept' }

    expect(useQueryCredential('token').value).toBe('abc')
    expect(replace).toHaveBeenCalledWith(expect.objectContaining({ query: { other: 'kept' } }))
  })

  it('survives a reload: reads it back from session storage once the URL has none', () => {
    route.query = { token: 'abc' }
    useQueryCredential('token')

    route.query = {}
    expect(useQueryCredential('token').value).toBe('abc')
    expect(replace).toHaveBeenCalledTimes(1)
  })

  it('prefers a new credential in the URL over a stored one', () => {
    route.query = { token: 'old' }
    useQueryCredential('token')

    route.query = { token: 'new' }
    expect(useQueryCredential('token').value).toBe('new')

    route.query = {}
    expect(useQueryCredential('token').value).toBe('new')
  })

  it('forgets the credential once cleared', () => {
    route.query = { token: 'abc' }
    const credential = useQueryCredential('token')

    credential.clear()

    route.query = {}
    expect(useQueryCredential('token').value).toBe('')
  })

  it('keeps credentials of different pages apart', () => {
    route.query = { token: 'reset-token' }
    useQueryCredential('token')

    route.path = '/verify-email'
    route.query = {}
    expect(useQueryCredential('token').value).toBe('')
  })

  it('works when session storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    route.query = { token: 'abc' }

    const credential = useQueryCredential('token')

    expect(credential.value).toBe('abc')
    expect(() => credential.clear()).not.toThrow()
    route.query = {}
    expect(useQueryCredential('token').value).toBe('')
  })
})
