import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { PublicUser } from '@/features/users/types'

import { useUserSearchQuery } from '@/features/users/composables/usePublicUser'
import { MIN_USER_SEARCH_LENGTH, searchPublicUsers } from '@/features/users/services/publicUsers'

vi.mock('@/features/users/services/publicUsers', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/users/services/publicUsers')>()),
  searchPublicUsers: vi.fn<(username: string) => Promise<PublicUser[]>>(),
}))

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

/** Mounts a component that runs the user search for the given reactive term. */
function mountSearch(term: ReturnType<typeof ref<string>>): void {
  wrapper = mount(
    defineComponent({
      setup() {
        useUserSearchQuery(() => term.value ?? '')
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]] } },
  )
}

describe('useUserSearchQuery', () => {
  it('asks the server for at least three characters', () => {
    expect(MIN_USER_SEARCH_LENGTH).toBe(3)
  })

  it('does not query until the term reaches the minimum length', async () => {
    vi.mocked(searchPublicUsers).mockResolvedValue([])
    const term = ref('ab')
    mountSearch(term)
    await flushPromises()

    expect(searchPublicUsers).not.toHaveBeenCalled()

    term.value = ' abc '
    await flushPromises()

    expect(searchPublicUsers).toHaveBeenCalledTimes(1)
    expect(vi.mocked(searchPublicUsers).mock.calls[0]?.[0]).toBe('abc')
  })
})
