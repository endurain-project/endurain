import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { UserDeletionStatus } from '@/features/users/types'

import { useAuthStore } from '@/features/auth/stores/auth'
import { useUserDeletionQuery } from '@/features/users/composables/useUsers'
import { fetchUserDeletion } from '@/features/users/services/users'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/features/users/services/users', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/users/services/users')>()),
  fetchUserDeletion: vi.fn<(id: number) => Promise<UserDeletionStatus | null>>(),
}))

const queued: UserDeletionStatus = { status: 'queued' }
const succeeded: UserDeletionStatus = { status: 'succeeded' }
const failed: UserDeletionStatus = { status: 'failed' }

let wrapper: ReturnType<typeof mount> | undefined

beforeEach(() => {
  setActivePinia(createPinia())
  useAuthStore().isAuthenticated = true
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.useRealTimers()
  vi.clearAllMocks()
})

function mountQuery(queryClient: QueryClient) {
  const TestComponent = defineComponent({
    setup() {
      useUserDeletionQuery(() => 7)
      return () => h('div')
    },
  })
  wrapper = mount(TestComponent, {
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  })
}

/** The query keys invalidated so far, serialized for comparison. */
function invalidatedKeys(invalidate: ReturnType<typeof vi.spyOn>): string[] {
  return invalidate.mock.calls.map((call: unknown[]) =>
    JSON.stringify((call[0] as { queryKey?: unknown } | undefined)?.queryKey),
  )
}

describe('useUserDeletionQuery', () => {
  it('reads the deletion of the given user', async () => {
    vi.mocked(fetchUserDeletion).mockResolvedValue(queued)
    mountQuery(new QueryClient())
    await flushPromises()

    expect(fetchUserDeletion).toHaveBeenCalledWith(7, expect.anything())
  })

  it('refetches the users lists and details once the deletion succeeds', async () => {
    vi.mocked(fetchUserDeletion).mockResolvedValue(queued)
    const queryClient = new QueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    mountQuery(queryClient)
    await flushPromises()
    expect(invalidate).not.toHaveBeenCalled()

    queryClient.setQueryData(queryKeys.users.deletion(7), succeeded)
    await flushPromises()

    const keys = invalidatedKeys(invalidate)
    expect(keys).toContain(JSON.stringify(queryKeys.users.lists()))
    expect(keys).toContain(JSON.stringify(queryKeys.users.details()))
  })

  it('refetches the users lists when the deletion had already succeeded at the first read', async () => {
    vi.mocked(fetchUserDeletion).mockResolvedValue(succeeded)
    const queryClient = new QueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    mountQuery(queryClient)
    await flushPromises()

    expect(invalidatedKeys(invalidate)).toContain(JSON.stringify(queryKeys.users.lists()))
  })

  it('refetches nothing when the deletion failed, since the account is still there', async () => {
    vi.mocked(fetchUserDeletion).mockResolvedValue(failed)
    const queryClient = new QueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    mountQuery(queryClient)
    await flushPromises()

    expect(invalidate).not.toHaveBeenCalled()
  })

  it('polls while the deletion runs and stops once it ends', async () => {
    vi.useFakeTimers()
    vi.mocked(fetchUserDeletion).mockResolvedValue(queued)
    mountQuery(new QueryClient())
    await flushPromises()
    expect(fetchUserDeletion).toHaveBeenCalledTimes(1)

    vi.mocked(fetchUserDeletion).mockResolvedValue(failed)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(fetchUserDeletion).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(60_000)
    expect(fetchUserDeletion).toHaveBeenCalledTimes(2)
  })
})
