import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ProfileExportStatus } from '@/features/profile/types'

import {
  useExportProfileMutation,
  useProfileExportQuery,
} from '@/features/profile/composables/useDataTransfer'
import { requestProfileExport } from '@/features/profile/services/dataTransfer'
import { fetchJob, listJobs } from '@/services/jobStatus'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/features/profile/services/dataTransfer', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/profile/services/dataTransfer')>()),
  requestProfileExport: vi.fn<() => Promise<ProfileExportStatus>>(),
}))
vi.mock('@/services/jobStatus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/jobStatus')>()),
  fetchJob: vi.fn<typeof fetchJob>(),
  listJobs: vi.fn<typeof listJobs>(),
}))

const queued: ProfileExportStatus = {
  id: 'export-1',
  kind: 'profile_export',
  status: 'queued',
  created_at: '2026-01-01T00:00:00Z',
  error_code: null,
  size_bytes: null,
}

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

function mountComposables(queryClient: QueryClient) {
  let job!: ReturnType<typeof useProfileExportQuery>
  let mutation!: ReturnType<typeof useExportProfileMutation>
  const TestComponent = defineComponent({
    setup() {
      job = useProfileExportQuery()
      mutation = useExportProfileMutation()
      return () => h('div')
    },
  })
  wrapper = mount(TestComponent, {
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  })
  return { job, mutation }
}

describe('profile export composables', () => {
  it('starts as no export when the user has none', async () => {
    vi.mocked(listJobs).mockResolvedValue({ items: [], num_records: 0 })
    const { job } = mountComposables(new QueryClient())
    await flushPromises()

    expect(listJobs).toHaveBeenCalledWith(
      { kind: 'profile_export', numRecords: 1 },
      expect.anything(),
    )
    expect(job.value).toBeNull()
  })

  it('finds an export started before the page loaded and follows it', async () => {
    vi.mocked(listJobs).mockResolvedValue({ items: [queued], num_records: 1 })
    vi.mocked(fetchJob).mockResolvedValue({ ...queued, status: 'succeeded', size_bytes: 9 })
    const { job } = mountComposables(new QueryClient())
    await flushPromises()

    expect(fetchJob).toHaveBeenCalledWith('export-1', expect.anything())
    expect(job.value?.status).toBe('succeeded')
  })

  it('seeds both caches with the queued export the mutation returns', async () => {
    vi.mocked(listJobs).mockResolvedValue({ items: [], num_records: 0 })
    vi.mocked(fetchJob).mockResolvedValue(queued)
    vi.mocked(requestProfileExport).mockResolvedValue(queued)
    const queryClient = new QueryClient()
    const { mutation } = mountComposables(queryClient)
    await flushPromises()

    await mutation.mutateAsync({ currentPassword: 'pw', mfaCode: null, idpReauth: null })

    expect(queryClient.getQueryData(queryKeys.jobs.detail('export-1'))).toEqual(queued)
    expect(queryClient.getQueryData(queryKeys.jobs.latest('profile_export'))).toEqual(queued)
  })
})
