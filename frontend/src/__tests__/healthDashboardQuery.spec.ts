import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { HealthDashboard, HealthTargets } from '@/features/health/types'

import { queryKeys } from '@/services/queryKeys'
import { useHealthDashboardQuery } from '@/features/health/composables/useHealth'
import { fetchHealthDashboard } from '@/features/health/services/health'

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))

vi.mock('@/features/health/services/health', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/health/services/health')>()),
  fetchHealthDashboard: vi.fn<typeof fetchHealthDashboard>(),
}))

const targets: HealthTargets = {
  id: 2,
  userId: 9,
  version: 3,
  sleepSeconds: 28800,
  steps: 8000,
  weightKg: 70,
  fastingSeconds: 57600,
  waterMl: 2000,
  poopCount: 1,
}

const dashboard: HealthDashboard = {
  sleepSeconds: null,
  restingHeartRate: null,
  hrvStatus: null,
  skinTempDeviation: null,
  weightKg: null,
  bmi: null,
  steps: 7500,
  fasting: null,
  waterMl: null,
  poopCount: null,
  targets,
}

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

describe('useHealthDashboardQuery', () => {
  it('seeds the health-targets cache from the dashboard response', async () => {
    vi.mocked(fetchHealthDashboard).mockResolvedValue(dashboard)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    wrapper = mount(
      defineComponent({
        setup() {
          useHealthDashboardQuery()
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    )
    await flushPromises()

    expect(client.getQueryData(queryKeys.health.targets())).toEqual(targets)
    expect(fetchHealthDashboard).toHaveBeenCalledOnce()
    const query = client.getQueryCache().find({ queryKey: queryKeys.health.dashboard() })
    expect((query?.options as { staleTime?: number } | undefined)?.staleTime).toBe(60_000)
  })
})
