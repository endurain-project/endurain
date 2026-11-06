import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { ActivityIngestionJob } from '@/features/upload/types'

import { invalidateActivityData } from '@/composables/useInvalidatingMutation'
import { editActivity, refreshActivities } from '@/features/activities/services/activities'
import { useEditActivityMutation } from '@/features/activities/composables/useActivityDetail'
import { useRefreshActivitiesMutation } from '@/features/home/composables/useHome'
import { useBulkImportJobQuery } from '@/features/import/composables/useImport'
import { fetchIngestionJob, uploadActivityFile } from '@/features/upload/services/upload'
import { useUploadActivityFileMutation } from '@/features/upload/composables/useUpload'
import { useProfileImportQuery } from '@/features/profile/composables/useDataTransfer'
import { fetchProfileImport } from '@/features/profile/services/dataTransfer'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/features/activities/services/activities', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/activities/services/activities')>()),
  editActivity: vi.fn<typeof editActivity>(),
  refreshActivities: vi.fn<typeof refreshActivities>(),
}))
vi.mock('@/features/upload/services/upload', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/upload/services/upload')>()),
  fetchIngestionJob: vi.fn<typeof fetchIngestionJob>(),
  uploadActivityFile: vi.fn<typeof uploadActivityFile>(),
}))
vi.mock('@/features/profile/services/dataTransfer', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/profile/services/dataTransfer')>()),
  fetchProfileImport: vi.fn<typeof fetchProfileImport>(),
}))
vi.mock('@/composables/useRealtime', () => ({
  watchJob: () => ({ wait: () => Promise.resolve(), stop: vi.fn<() => void>() }),
}))
vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))
vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))

const completedJob = {
  id: 'job-1',
  status: 'succeeded',
  activity_ids: [],
} as unknown as ActivityIngestionJob

let wrapper: ReturnType<typeof mount> | undefined

/** A client with a goal-results entry and one activities list cached, both fresh. */
function seededClient(): QueryClient {
  const client = new QueryClient()
  client.setQueryData(queryKeys.goals.results(), [])
  client.setQueryData(queryKeys.activities.stats(1, 'week'), {})
  return client
}

const goalResultsStale = (client: QueryClient): boolean | undefined =>
  client.getQueryState(queryKeys.goals.results())?.isInvalidated

function mountHook<T>(client: QueryClient, hook: () => T): T {
  let result: T | undefined
  wrapper = mount(
    defineComponent({
      setup() {
        result = hook()
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
  )
  return result as T
}

beforeEach(() => {
  vi.mocked(fetchIngestionJob).mockResolvedValue(completedJob)
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

describe('goal results follow activity changes', () => {
  it('invalidateActivityData marks goal results and activities stale, honouring exclusions', async () => {
    const client = seededClient()
    client.setQueryData(queryKeys.activities.owners(), [])

    await invalidateActivityData(client, [queryKeys.activities.owners()])

    expect(goalResultsStale(client)).toBe(true)
    expect(client.getQueryState(queryKeys.activities.stats(1, 'week'))?.isInvalidated).toBe(true)
    expect(client.getQueryState(queryKeys.activities.owners())?.isInvalidated).toBe(false)
  })

  it('an activity edit refreshes goal results', async () => {
    const client = seededClient()
    vi.mocked(editActivity).mockResolvedValue({ id: 3 } as Awaited<ReturnType<typeof editActivity>>)
    const mutation = mountHook(client, useEditActivityMutation)

    await mutation.mutateAsync({ id: 3, input: {} as never, version: 1 })
    await flushPromises()

    expect(goalResultsStale(client)).toBe(true)
  })

  it('a provider refresh refreshes goal results', async () => {
    const client = seededClient()
    vi.mocked(refreshActivities).mockResolvedValue(completedJob)
    const mutation = mountHook(client, useRefreshActivitiesMutation)

    await mutation.mutateAsync()
    await flushPromises()

    expect(goalResultsStale(client)).toBe(true)
  })

  it('an activity upload refreshes goal results', async () => {
    const client = seededClient()
    vi.mocked(uploadActivityFile).mockResolvedValue(completedJob)
    const mutation = mountHook(client, useUploadActivityFileMutation)

    await mutation.mutateAsync(new File(['x'], 'a.fit'))
    await flushPromises()

    expect(goalResultsStale(client)).toBe(true)
  })

  it('a finished bulk import refreshes goal results', async () => {
    const client = seededClient()
    mountHook(client, () => useBulkImportJobQuery(ref<string | null>('job-1')))

    await vi.waitFor(() => expect(goalResultsStale(client)).toBe(true))
  })

  it('a finished profile import refreshes goal results', async () => {
    const client = seededClient()
    const running = { status: 'running', error_code: null, imported: null }
    vi.mocked(fetchProfileImport).mockResolvedValue(running as never)
    mountHook(client, useProfileImportQuery)
    await flushPromises()

    client.setQueryData(queryKeys.profile.import(), { ...running, status: 'succeeded' })
    await flushPromises()

    expect(goalResultsStale(client)).toBe(true)
  })
})
