import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ProfileImportStatus } from '@/features/profile/types'

import { useAuthStore } from '@/features/auth/stores/auth'
import {
  useImportProfileMutation,
  useProfileImportQuery,
} from '@/features/profile/composables/useDataTransfer'
import { fetchProfileImport, importProfileData } from '@/features/profile/services/dataTransfer'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/features/profile/services/dataTransfer', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/profile/services/dataTransfer')>()),
  fetchProfileImport: vi.fn<() => Promise<ProfileImportStatus | null>>(),
  importProfileData: vi.fn<(file: File) => Promise<ProfileImportStatus>>(),
}))

const running: ProfileImportStatus = { status: 'running', failure: null, imported: null }
const completed: ProfileImportStatus = {
  status: 'completed',
  failure: null,
  imported: { activities: 2 },
}

let wrapper: ReturnType<typeof mount> | undefined

beforeEach(() => {
  setActivePinia(createPinia())
  useAuthStore().isAuthenticated = true
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

function mountComposables(queryClient: QueryClient) {
  let query!: ReturnType<typeof useProfileImportQuery>
  let mutation!: ReturnType<typeof useImportProfileMutation>
  const TestComponent = defineComponent({
    setup() {
      query = useProfileImportQuery()
      mutation = useImportProfileMutation()
      return () => h('div')
    },
  })
  wrapper = mount(TestComponent, {
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  })
  return { query, mutation }
}

describe('profile import composables', () => {
  it('starts as no import when nothing is recorded', async () => {
    vi.mocked(fetchProfileImport).mockResolvedValue(null)
    const { query } = mountComposables(new QueryClient())
    await flushPromises()

    expect(query.data.value).toBeNull()
  })

  it('seeds the import state with the queued import the mutation returns', async () => {
    vi.mocked(fetchProfileImport).mockResolvedValue(null)
    vi.mocked(importProfileData).mockResolvedValue({
      status: 'queued',
      failure: null,
      imported: null,
    })
    const queryClient = new QueryClient()
    const { mutation } = mountComposables(queryClient)
    await flushPromises()

    await mutation.mutateAsync(new File(['x'], 'a.zip'))

    expect(queryClient.getQueryData(queryKeys.profile.import())).toMatchObject({ status: 'queued' })
  })

  it('refetches what the import changed once it goes from running to completed', async () => {
    vi.mocked(fetchProfileImport).mockResolvedValue(running)
    const queryClient = new QueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    mountComposables(queryClient)
    await flushPromises()
    expect(invalidate).not.toHaveBeenCalled()

    queryClient.setQueryData(queryKeys.profile.import(), completed)
    await flushPromises()

    const keys = invalidate.mock.calls.map((call) =>
      JSON.stringify((call[0] as { queryKey?: unknown } | undefined)?.queryKey),
    )
    expect(keys).toContain(JSON.stringify(queryKeys.activities.all()))
    expect(keys).toContain(JSON.stringify(queryKeys.profile.detail()))
    expect(keys).not.toContain(JSON.stringify(queryKeys.profile.all()))
  })

  it('does not refetch anything for an import that was already finished when the page loaded', async () => {
    vi.mocked(fetchProfileImport).mockResolvedValue(completed)
    const queryClient = new QueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    mountComposables(queryClient)
    await flushPromises()

    expect(invalidate).not.toHaveBeenCalled()
  })
})
