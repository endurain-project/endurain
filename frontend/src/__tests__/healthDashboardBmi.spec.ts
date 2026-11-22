import { describe, expect, it, vi } from 'vitest'

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

function bmiNoDataLabel(weightKg: number | null): unknown {
  dashboard.value = {
    weightKg,
    bmi: null,
    fasting: null,
    targets: null,
  } as unknown as HealthDashboard
  const wrapper = mount(HealthDashboardView, { global: { plugins: [i18n] } })
  const label = wrapper
    .findAllComponents(HealthDashboardCard)
    .find((card) => card.props('title') === i18n.global.t('health.dashboard.bmi'))
    ?.props('noDataLabel')
  wrapper.unmount()
  return label
}

describe('HealthDashboardView BMI card', () => {
  it('asks for the height when there is a weight but no BMI', () => {
    expect(bmiNoDataLabel(70)).toBe(i18n.global.t('health.dashboard.noHeightData'))
  })

  it('reports missing weight when there is no weight', () => {
    expect(bmiNoDataLabel(null)).toBe(i18n.global.t('health.dashboard.noWeightData'))
  })
})
