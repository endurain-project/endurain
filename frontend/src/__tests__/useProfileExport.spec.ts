import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ProfileExportStatus } from '@/features/profile/types'

import { useAuthStore } from '@/features/auth/stores/auth'
import {
  useExportProfileMutation,
  useProfileExportQuery,
} from '@/features/profile/composables/useDataTransfer'
import { fetchProfileExport, requestProfileExport } from '@/features/profile/services/dataTransfer'
import { isTerminalProfileExport } from '@/features/profile/types'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/features/profile/services/dataTransfer', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/profile/services/dataTransfer')>()),
  fetchProfileExport: vi.fn<() => Promise<ProfileExportStatus | null>>(),
  requestProfileExport: vi.fn<() => Promise<ProfileExportStatus>>(),
}))

const queued: ProfileExportStatus = { status: 'queued', failure: null, size_bytes: null }

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
  let query!: ReturnType<typeof useProfileExportQuery>
  let mutation!: ReturnType<typeof useExportProfileMutation>
  const TestComponent = defineComponent({
    setup() {
      query = useProfileExportQuery()
      mutation = useExportProfileMutation()
      return () => h('div')
    },
  })
  wrapper = mount(TestComponent, {
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  })
  return { query, mutation }
}

describe('profile export composables', () => {
  it('starts as no export when nothing is recorded', async () => {
    vi.mocked(fetchProfileExport).mockResolvedValue(null)
    const { query } = mountComposables(new QueryClient())
    await flushPromises()

    expect(query.data.value).toBeNull()
  })

  it('seeds the export state with the queued export the mutation returns', async () => {
    vi.mocked(fetchProfileExport).mockResolvedValue(null)
    vi.mocked(requestProfileExport).mockResolvedValue(queued)
    const queryClient = new QueryClient()
    const { mutation } = mountComposables(queryClient)
    await flushPromises()

    await mutation.mutateAsync()

    expect(queryClient.getQueryData(queryKeys.profile.export())).toEqual(queued)
  })

  it('treats completed and failed as terminal', () => {
    expect(isTerminalProfileExport(queued)).toBe(false)
    expect(isTerminalProfileExport({ ...queued, status: 'running' })).toBe(false)
    expect(isTerminalProfileExport({ ...queued, status: 'completed' })).toBe(true)
    expect(isTerminalProfileExport({ ...queued, status: 'failed' })).toBe(true)
  })
})
