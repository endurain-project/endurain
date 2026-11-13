import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ref } from 'vue'
import { mount } from '@vue/test-utils'

import type { HealthDashboard } from '@/features/health/types'

import i18n from '@/i18n'
import HealthDashboardView from '@/features/health/views/HealthDashboardView.vue'
import HealthDashboardCard from '@/features/health/components/HealthDashboardCard.vue'

const dashboard = ref<HealthDashboard | undefined>()

vi.mock('@/features/health/composables/useHealth', () => ({
  useHealthDashboardQuery: () => ({
    data: dashboard,
    isPending: ref(false),
    isError: ref(false),
    refetch: vi.fn<() => void>(),
  }),
}))
vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: ref({ units: 'metric', weightUnits: 'metric' }) }),
}))

function base(fasting: HealthDashboard['fasting']): HealthDashboard {
  return {
    sleepSeconds: null,
    restingHeartRate: null,
    hrvStatus: null,
    skinTempDeviation: null,
    weightKg: null,
    bmi: null,
    steps: null,
    fasting,
    waterMl: null,
    poopCount: null,
    targets: null,
  } as unknown as HealthDashboard
}

function fastingValue(wrapper: ReturnType<typeof mount>): unknown {
  return wrapper
    .findAllComponents(HealthDashboardCard)
    .find((card) => card.props('title') === i18n.global.t('health.dashboard.fasting'))
    ?.props('value')
}

describe('HealthDashboardView fasting card', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-30T12:00:00Z'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('keeps an in-progress fast current as time passes', async () => {
    dashboard.value = base({
      startTime: '2026-10-30T11:00:00Z',
      status: 'in_progress',
      actualDurationSeconds: null,
    })
    const wrapper = mount(HealthDashboardView, { global: { plugins: [i18n] } })
    const before = fastingValue(wrapper)

    await vi.advanceTimersByTimeAsync(5 * 60_000)

    expect(fastingValue(wrapper)).not.toBe(before)
    wrapper.unmount()
  })

  it('does not tick for a finished fast', async () => {
    dashboard.value = base({
      startTime: '2026-10-30T08:00:00Z',
      status: 'completed',
      actualDurationSeconds: 3600,
    })
    const wrapper = mount(HealthDashboardView, { global: { plugins: [i18n] } })
    expect(vi.getTimerCount()).toBe(0)
    wrapper.unmount()
  })
})
