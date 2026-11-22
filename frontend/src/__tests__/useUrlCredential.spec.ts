import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useUrlCredential } from '@/composables/useRouteQuery'

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
  route.hash = ''
  replace.mockClear()
  sessionStorage.clear()
})

describe('useUrlCredential', () => {
  it('reads the credential from the fragment and clears the fragment', () => {
    route.hash = '#token=abc'

    expect(useUrlCredential('token')).toBe('abc')
    expect(replace).toHaveBeenCalledWith({ query: {}, hash: '' })
  })

  it('keeps the other fragment parameters', () => {
    route.hash = '#token=abc&section=a'

    expect(useUrlCredential('token')).toBe('abc')
    expect(replace).toHaveBeenCalledWith({ query: {}, hash: '#section=a' })
  })

  it('falls back to the query string of a link sent before the move, and clears it', () => {
    route.query = { token: 'abc', other: 'kept' }

    expect(useUrlCredential('token')).toBe('abc')
    expect(replace).toHaveBeenCalledWith({ query: { other: 'kept' }, hash: '' })
  })

  it('prefers the fragment over the query string', () => {
    route.hash = '#token=fragment'
    route.query = { token: 'query' }

    expect(useUrlCredential('token')).toBe('fragment')
    expect(replace).toHaveBeenCalledWith({ query: {}, hash: '' })
  })

  it('returns an empty string and leaves the address alone when there is none', () => {
    expect(useUrlCredential('token')).toBe('')
    expect(replace).not.toHaveBeenCalled()
  })

  it('does not keep the credential in session storage or after the URL lost it', () => {
    route.hash = '#token=abc'
    useUrlCredential('token')

    expect(sessionStorage.length).toBe(0)
    route.hash = ''
    expect(useUrlCredential('token')).toBe('')
  })
})
