import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ProfileImportStatus } from '@/features/profile/types'

import {
  useImportProfileMutation,
  useProfileImportQuery,
} from '@/features/profile/composables/useDataTransfer'
import { importProfileData } from '@/features/profile/services/dataTransfer'
import { HttpError } from '@/services/http'
import { fetchJob, listJobs } from '@/services/jobStatus'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/features/profile/services/dataTransfer', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/profile/services/dataTransfer')>()),
  importProfileData: vi.fn<(file: File) => Promise<ProfileImportStatus>>(),
}))
vi.mock('@/services/jobStatus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/jobStatus')>()),
  fetchJob: vi.fn<typeof fetchJob>(),
  listJobs: vi.fn<typeof listJobs>(),
}))

const running: ProfileImportStatus = {
  id: 'import-1',
  kind: 'profile_import',
  status: 'running',
  created_at: '2026-01-01T00:00:00Z',
  error_code: null,
  imported: null,
}
const completed: ProfileImportStatus = {
  ...running,
  status: 'succeeded',
  imported: { activities: 2 },
}

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

function mountComposables(queryClient: QueryClient) {
  let job!: ReturnType<typeof useProfileImportQuery>
  let mutation!: ReturnType<typeof useImportProfileMutation>
  const TestComponent = defineComponent({
    setup() {
      job = useProfileImportQuery()
      mutation = useImportProfileMutation()
      return () => h('div')
    },
  })
  wrapper = mount(TestComponent, {
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  })
  return { job, mutation }
}

describe('profile import composables', () => {
  it('starts as no import when the user has none', async () => {
    vi.mocked(listJobs).mockResolvedValue({ items: [], num_records: 0 })
    const { job } = mountComposables(new QueryClient())
    await flushPromises()

    expect(job.value).toBeNull()
  })

  it('seeds both caches with the queued import the mutation returns', async () => {
    vi.mocked(listJobs).mockResolvedValue({ items: [], num_records: 0 })
    vi.mocked(fetchJob).mockResolvedValue({ ...running, status: 'queued' })
    vi.mocked(importProfileData).mockResolvedValue({ ...running, status: 'queued' })
    const queryClient = new QueryClient()
    const { mutation, job } = mountComposables(queryClient)
    await flushPromises()

    await mutation.mutateAsync(new File(['x'], 'a.zip'))
    await flushPromises()

    expect(queryClient.getQueryData(queryKeys.jobs.detail('import-1'))).toMatchObject({
      status: 'queued',
    })
    expect(queryClient.getQueryData(queryKeys.jobs.latest('profile_import'))).toMatchObject({
      id: 'import-1',
    })
    expect(job.value?.id).toBe('import-1')
  })

  it('refetches what the import changed once it goes from running to completed', async () => {
    vi.mocked(listJobs).mockResolvedValue({ items: [running], num_records: 1 })
    vi.mocked(fetchJob).mockResolvedValue(running)
    const queryClient = new QueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    mountComposables(queryClient)
    await flushPromises()
    expect(invalidate).not.toHaveBeenCalled()

    queryClient.setQueryData(queryKeys.jobs.detail('import-1'), completed)
    await flushPromises()

    const keys = invalidate.mock.calls.map((call) =>
      JSON.stringify((call[0] as { queryKey?: unknown } | undefined)?.queryKey),
    )
    expect(keys).toContain(JSON.stringify(queryKeys.activities.all()))
    expect(keys).toContain(JSON.stringify(queryKeys.profile.detail()))
    expect(keys).not.toContain(JSON.stringify(queryKeys.profile.all()))
  })

  it('does not refetch anything for an import that was already finished when the page loaded', async () => {
    vi.mocked(listJobs).mockResolvedValue({ items: [completed], num_records: 1 })
    vi.mocked(fetchJob).mockResolvedValue(completed)
    const queryClient = new QueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    mountComposables(queryClient)
    await flushPromises()

    expect(invalidate).not.toHaveBeenCalled()
  })

  it('picks up the import a 409 names by reading the latest import again', async () => {
    vi.mocked(listJobs).mockResolvedValue({ items: [], num_records: 0 })
    vi.mocked(fetchJob).mockResolvedValue(running)
    vi.mocked(importProfileData).mockRejectedValue(
      new HttpError(
        409,
        'Conflict',
        null,
        'urn:endurain:error:conflict',
        null,
        [],
        null,
        'import-1',
      ),
    )
    const { mutation, job } = mountComposables(new QueryClient())
    await flushPromises()
    expect(job.value).toBeNull()

    vi.mocked(listJobs).mockResolvedValue({ items: [running], num_records: 1 })
    await expect(mutation.mutateAsync(new File(['x'], 'a.zip'))).rejects.toBeInstanceOf(HttpError)
    await flushPromises()

    expect(job.value?.id).toBe('import-1')
  })
})
