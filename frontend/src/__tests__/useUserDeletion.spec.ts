import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { UserDeletionStatus } from '@/features/users/types'

import { useAuthStore } from '@/features/auth/stores/auth'
import UserDeletionWatcher from '@/features/users/components/UserDeletionWatcher.vue'
import { useUserDeletionsStore } from '@/features/users/stores/userDeletions'
import { useUserDeletionQuery, useUserQuery } from '@/features/users/composables/useUsers'
import { fetchUserById } from '@/features/users/services/users'
import { fetchJob } from '@/services/jobStatus'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/services/jobStatus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/jobStatus')>()),
  fetchJob: vi.fn<typeof fetchJob>(),
}))
vi.mock('@/features/users/services/users', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/users/services/users')>()),
  fetchUserById: vi.fn<typeof fetchUserById>(),
}))

const queued: UserDeletionStatus = {
  id: 'job-7',
  kind: 'user_deletion',
  status: 'queued',
  created_at: '2026-01-01T00:00:00Z',
}
const succeeded: UserDeletionStatus = { ...queued, status: 'succeeded' }
const failed: UserDeletionStatus = { ...queued, status: 'failed' }

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
      useUserDeletionQuery(() => 'job-7')
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
  it('reads the deletion job it is given', async () => {
    vi.mocked(fetchJob).mockResolvedValue(queued)
    mountQuery(new QueryClient())
    await flushPromises()

    expect(fetchJob).toHaveBeenCalledWith('job-7', expect.anything())
  })

  it('refetches the users lists and details once the deletion succeeds', async () => {
    vi.mocked(fetchJob).mockResolvedValue(queued)
    const queryClient = new QueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    mountQuery(queryClient)
    await flushPromises()
    expect(invalidate).not.toHaveBeenCalled()

    queryClient.setQueryData(queryKeys.jobs.detail('job-7'), succeeded)
    await flushPromises()

    const keys = invalidatedKeys(invalidate)
    expect(keys).toContain(JSON.stringify(queryKeys.users.lists()))
    expect(keys).toContain(JSON.stringify(queryKeys.users.details()))
  })

  it('refetches the users lists when the deletion had already succeeded at the first read', async () => {
    vi.mocked(fetchJob).mockResolvedValue(succeeded)
    const queryClient = new QueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    mountQuery(queryClient)
    await flushPromises()

    expect(invalidatedKeys(invalidate)).toContain(JSON.stringify(queryKeys.users.lists()))
  })

  it('refetches nothing when the deletion failed, since the account is still there', async () => {
    vi.mocked(fetchJob).mockResolvedValue(failed)
    const queryClient = new QueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    mountQuery(queryClient)
    await flushPromises()

    expect(invalidate).not.toHaveBeenCalled()
  })

  it('polls while the deletion runs and stops once it ends', async () => {
    vi.useFakeTimers()
    vi.mocked(fetchJob).mockResolvedValue(queued)
    mountQuery(new QueryClient())
    await flushPromises()
    expect(fetchJob).toHaveBeenCalledTimes(1)

    vi.mocked(fetchJob).mockResolvedValue(failed)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(fetchJob).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(60_000)
    expect(fetchJob).toHaveBeenCalledTimes(2)
  })
})

describe('useUserQuery', () => {
  function mountUser() {
    wrapper = mount(
      defineComponent({
        setup() {
          useUserQuery(7)
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]] } },
    )
  }

  it('reads the user again while the account waits to be erased', async () => {
    vi.useFakeTimers()
    vi.mocked(fetchUserById).mockResolvedValue({ deletionRequestedAt: '2026-01-01' } as never)
    mountUser()
    await flushPromises()
    expect(fetchUserById).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(10_000)
    expect(fetchUserById).toHaveBeenCalledTimes(2)
  })

  it('does not poll an account that is not being erased', async () => {
    vi.useFakeTimers()
    vi.mocked(fetchUserById).mockResolvedValue({ deletionRequestedAt: null } as never)
    mountUser()
    await flushPromises()

    await vi.advanceTimersByTimeAsync(60_000)
    expect(fetchUserById).toHaveBeenCalledTimes(1)
  })
})

describe('session deletion tracking', () => {
  const queryClient = new QueryClient()

  function mountWatcher(tracked: Array<[number, string]>) {
    wrapper = mount(
      defineComponent({
        setup() {
          const deletions = useUserDeletionsStore()
          return () =>
            deletions.deletions.map((deletion) =>
              h(UserDeletionWatcher, { key: deletion.jobId, jobId: deletion.jobId }),
            )
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
    )
    for (const [userId, jobId] of tracked) {
      useUserDeletionsStore().track(userId, jobId)
    }
  }

  it('does not read the job of a row marked before this session', async () => {
    vi.mocked(fetchJob).mockResolvedValue(queued)
    mountWatcher([])
    await flushPromises()

    expect(fetchJob).not.toHaveBeenCalled()
  })

  it('tracks the user and job id of a queued deletion, once per job', () => {
    const deletions = useUserDeletionsStore()

    deletions.track(7, 'job-7')
    deletions.track(7, 'job-7')
    deletions.track(8, 'job-8')
    expect(deletions.deletions).toEqual([
      { userId: 7, jobId: 'job-7' },
      { userId: 8, jobId: 'job-8' },
    ])

    deletions.release('job-7')
    expect(deletions.deletions).toEqual([{ userId: 8, jobId: 'job-8' }])
  })

  it('follows a deletion queued in this session and drops it once it ends', async () => {
    vi.mocked(fetchJob).mockResolvedValue(queued)
    mountWatcher([[7, 'job-7']])
    await flushPromises()
    expect(fetchJob).toHaveBeenCalledWith('job-7', expect.anything())
    expect(useUserDeletionsStore().deletions).toEqual([{ userId: 7, jobId: 'job-7' }])

    vi.mocked(fetchJob).mockResolvedValue(failed)
    queryClient.setQueryData(queryKeys.jobs.detail('job-7'), failed)
    await flushPromises()
    expect(useUserDeletionsStore().deletions).toEqual([])
  })
})
