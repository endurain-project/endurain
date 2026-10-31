import { computed, toValue, type Component } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { HealthChartSeries } from '@/features/health/types'

import HealthPoopChart from '@/features/health/components/HealthPoopChart.vue'
import HealthRestingHeartRateChart from '@/features/health/components/HealthRestingHeartRateChart.vue'
import HealthSleepChart from '@/features/health/components/HealthSleepChart.vue'
import HealthStepsChart from '@/features/health/components/HealthStepsChart.vue'
import HealthWaterChart from '@/features/health/components/HealthWaterChart.vue'
import HealthWeightChart from '@/features/health/components/HealthWeightChart.vue'
import { useHealthMetricChart } from '@/features/health/composables/useHealthMetricChart'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: computed(() => 'en') }),
}))

vi.mock('@/lib/themeColor', () => ({ themeColor: () => '#000000' }))

vi.mock('@/features/health/composables/useHealthMetricChart', () => ({
  useHealthMetricChart: vi.fn<typeof useHealthMetricChart>(),
}))

/** The render options a chart handed to the provider lifecycle, resolved at call time. */
function renderedOptions(): ChartRenderOptions {
  return toValue(vi.mocked(useHealthMetricChart).mock.calls[0]![0]) as ChartRenderOptions
}

function mountChart(component: Component, props: Record<string, unknown>): ChartRenderOptions {
  mount(component, { props })
  return renderedOptions()
}

afterEach(() => vi.clearAllMocks())

const weekly = (...values: number[]): HealthChartSeries => ({
  bucket: 'week',
  points: values.map((value, index) => ({
    date: `2026-06-${String(1 + index * 7).padStart(2, '0')}`,
    value,
  })),
})

describe('health charts plot the aggregated series', () => {
  it('sleep converts seconds to one-decimal hours and draws the target', () => {
    const options = mountChart(HealthSleepChart, {
      series: weekly(27000, 30600),
      targetSeconds: 28800,
    })

    expect(options.kind).toBe('bar')
    expect(options.labels).toEqual(['Jun 1, 2026', 'Jun 8, 2026'])
    expect(options.series[0]!.data).toEqual([7.5, 8.5])
    expect(options.series[1]!.data).toEqual([8, 8])
  })

  it('steps rounds to whole steps', () => {
    const options = mountChart(HealthStepsChart, { series: weekly(7999.6), targetSteps: null })

    expect(options.series).toHaveLength(1)
    expect(options.series[0]!.data).toEqual([8000])
  })

  it('resting heart rate is a line of whole bpm', () => {
    const options = mountChart(HealthRestingHeartRateChart, { series: weekly(51.6) })

    expect(options.kind).toBe('line')
    expect(options.series[0]!.data).toEqual([52])
  })

  it('weight converts to the viewer units to one decimal', () => {
    const metric = mountChart(HealthWeightChart, {
      series: weekly(70.04),
      targetKg: null,
      weightUnits: 'metric',
    })
    vi.clearAllMocks()
    const imperial = mountChart(HealthWeightChart, {
      series: weekly(70),
      targetKg: null,
      weightUnits: 'imperial',
    })

    expect(metric.series[0]!.data).toEqual([70])
    expect(imperial.series[0]!.data).toEqual([154.3])
  })

  it('water converts to the viewer units', () => {
    const metric = mountChart(HealthWaterChart, {
      series: weekly(1999.6),
      targetMl: null,
      units: 'metric',
    })
    vi.clearAllMocks()
    const imperial = mountChart(HealthWaterChart, {
      series: weekly(1000),
      targetMl: null,
      units: 'imperial',
    })

    expect(metric.series[0]!.data).toEqual([2000])
    expect(imperial.series[0]!.data).toEqual([33.8])
  })

  it('poop plots movements per day to one decimal', () => {
    const options = mountChart(HealthPoopChart, { series: weekly(1.26, 2), targetCount: 1 })

    expect(options.series[0]!.data).toEqual([1.3, 2])
    expect(options.valueFormat?.(1.26)).toBe('1.3')
    expect(options.series[1]!.data).toEqual([1, 1])
  })

  it('a monthly series is labelled by month and year', () => {
    const options = mountChart(HealthStepsChart, {
      series: { bucket: 'month', points: [{ date: '2026-03-01', value: 5000 }] },
      targetSteps: null,
    })

    expect(options.labels).toEqual(['Mar 2026'])
  })
})
