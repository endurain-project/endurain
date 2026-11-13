import { computed } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import HealthChartCard from '@/features/health/components/HealthChartCard.vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: computed(() => 'en') }),
}))

const NOTE = '[data-testid="chart-bucket-note"]'

describe('HealthChartCard bucket caption', () => {
  it.each(['week', 'month'] as const)('explains a %s aggregation', (bucket) => {
    const wrapper = mount(HealthChartCard, {
      props: { title: 'Steps', accentColor: '#000', bucket },
    })

    expect(wrapper.get(NOTE).text()).toBe(`health.chartBucket.${bucket}`)
  })

  it('shows nothing for daily bars or when no bucket is given', () => {
    const daily = mount(HealthChartCard, {
      props: { title: 'Steps', accentColor: '#000', bucket: 'day' },
    })
    const none = mount(HealthChartCard, { props: { title: 'Steps', accentColor: '#000' } })

    expect(daily.find(NOTE).exists()).toBe(false)
    expect(none.find(NOTE).exists()).toBe(false)
  })
})
