import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ActivityIngestionJob } from '@/features/upload/types'

import i18n from '@/i18n'
import BulkImportProgress from '@/features/import/components/BulkImportProgress.vue'
import {
  useBulkImportFromArchiveMutation,
  useBulkImportFromFolderMutation,
  useBulkImportJob,
} from '@/features/import/composables/useImport'
import { bulkImportFromArchive, bulkImportFromFolder } from '@/features/import/services/import'
import { HttpError } from '@/services/http'
import { fetchJob, listJobs } from '@/services/jobStatus'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/features/import/services/import', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/import/services/import')>()),
  bulkImportFromArchive: vi.fn<typeof bulkImportFromArchive>(),
  bulkImportFromFolder: vi.fn<typeof bulkImportFromFolder>(),
}))
vi.mock('@/services/jobStatus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/jobStatus')>()),
  fetchJob: vi.fn<typeof fetchJob>(),
  listJobs: vi.fn<typeof listJobs>(),
}))

const running = {
  id: 'import-1',
  kind: 'activity_bulk_import',
  status: 'running',
  files_total: 10,
  files_done: 3,
  files_failed: 0,
  activity_ids: [],
  import_source: 'generic',
  created_at: '2026-01-01T00:00:00Z',
} as unknown as ActivityIngestionJob

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

function mountComposables(queryClient: QueryClient, source: 'generic' | 'strava' = 'generic') {
  let job!: ReturnType<typeof useBulkImportJob>
  let archive!: ReturnType<typeof useBulkImportFromArchiveMutation>
  let folder!: ReturnType<typeof useBulkImportFromFolderMutation>
  wrapper = mount(
    defineComponent({
      setup() {
        job = useBulkImportJob(source)
        archive = useBulkImportFromArchiveMutation()
        folder = useBulkImportFromFolderMutation()
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  )
  return { job, archive, folder }
}

describe('useBulkImportJob', () => {
  it('shows an import that was running before the page loaded', async () => {
    vi.mocked(listJobs).mockResolvedValue({ items: [running], num_records: 1 } as never)
    vi.mocked(fetchJob).mockResolvedValue(running as never)
    const { job } = mountComposables(new QueryClient())
    await flushPromises()

    expect(listJobs).toHaveBeenCalledWith(
      { kind: 'activity_bulk_import', numRecords: 1 },
      expect.anything(),
    )
    expect(job.value?.id).toBe('import-1')
  })

  it('shows no import when the user has none', async () => {
    vi.mocked(listJobs).mockResolvedValue({ items: [], num_records: 0 })
    const { job } = mountComposables(new QueryClient())
    await flushPromises()

    expect(job.value).toBeNull()
  })

  it('follows the running import a 409 names, from either start route', async () => {
    vi.mocked(listJobs).mockResolvedValue({ items: [], num_records: 0 })
    vi.mocked(fetchJob).mockResolvedValue(running as never)
    const conflict = new HttpError(409, 'Conflict', null, null, null, [], null, 'import-1')
    vi.mocked(bulkImportFromFolder).mockRejectedValue(conflict)
    vi.mocked(bulkImportFromArchive).mockRejectedValue(conflict)
    const { job, folder, archive } = mountComposables(new QueryClient())
    await flushPromises()
    expect(job.value).toBeNull()

    vi.mocked(listJobs).mockResolvedValue({ items: [running], num_records: 1 } as never)
    await expect(folder.mutateAsync('generic')).rejects.toBe(conflict)
    await flushPromises()
    expect(job.value?.id).toBe('import-1')

    vi.mocked(listJobs).mockResolvedValue({ items: [], num_records: 0 })
    await expect(
      archive.mutateAsync({ file: new File(['x'], 'a.zip'), source: 'generic' }),
    ).rejects.toBe(conflict)
  })
})

describe('useBulkImportJob scoping', () => {
  const finished = { ...running, status: 'succeeded' } as unknown as ActivityIngestionJob

  it('ignores the job of the other source', async () => {
    vi.mocked(listJobs).mockResolvedValue({ items: [running], num_records: 1 } as never)
    vi.mocked(fetchJob).mockResolvedValue(running as never)
    const { job } = mountComposables(new QueryClient(), 'strava')
    await flushPromises()

    expect(job.value).toBeNull()
  })

  it('does not show a job that was already finished when first read', async () => {
    vi.mocked(listJobs).mockResolvedValue({ items: [finished], num_records: 1 } as never)
    vi.mocked(fetchJob).mockResolvedValue(finished as never)
    const { job } = mountComposables(new QueryClient())
    await flushPromises()

    expect(job.value).toBeNull()
  })

  it('keeps showing a job it saw running once it finishes', async () => {
    vi.mocked(listJobs).mockResolvedValue({ items: [running], num_records: 1 } as never)
    vi.mocked(fetchJob).mockResolvedValue(running as never)
    const queryClient = new QueryClient()
    const { job } = mountComposables(queryClient)
    await flushPromises()
    expect(job.value?.status).toBe('running')

    queryClient.setQueryData(queryKeys.jobs.detail('import-1'), finished)
    await flushPromises()
    expect(job.value?.status).toBe('succeeded')
  })
})

describe('archive import idempotency', () => {
  it('sends a fresh key for every submit', async () => {
    vi.mocked(bulkImportFromArchive).mockResolvedValue(running)
    const { archive } = mountComposables(new QueryClient())
    const file = new File(['x'], 'a.zip')

    await archive.mutateAsync({ file, source: 'generic' })
    await archive.mutateAsync({ file, source: 'strava' })

    const keys = vi.mocked(bulkImportFromArchive).mock.calls.map((call) => call[2]?.idempotencyKey)
    expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/)
    expect(keys[1]).toMatch(/^[0-9a-f-]{36}$/)
    expect(keys[0]).not.toBe(keys[1])
  })
})

describe('BulkImportProgress', () => {
  function textFor(job: Partial<ActivityIngestionJob>): string {
    const view = mount(BulkImportProgress, {
      props: { job: { ...running, ...job } as ActivityIngestionJob },
      global: { plugins: [i18n] },
    })
    const text = view.text()
    view.unmount()
    return text
  }

  it('explains a failed import by its error code', () => {
    const texts = (
      [
        'unsupported_format',
        'invalid_file',
        'no_activities_found',
        'processing_failed',
        'provider_unavailable',
      ] as const
    ).map((error_code) => textFor({ status: 'failed', error_code }))

    expect(new Set(texts).size).toBe(texts.length)
  })

  it('falls back to the generic text for a failure without a known code', () => {
    const generic = textFor({ status: 'failed', error_code: null })
    expect(generic).toBe('The import could not be completed.')
    expect(textFor({ status: 'failed', error_code: 'unheard_of' as never })).toBe(generic)
  })
})
