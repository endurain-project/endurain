<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { Schemas } from '@/types'
import type { WeightEntry } from '@/features/health/types'

import { themeColor } from '@/lib/themeColor'
import { kgToLbs } from '@/utils/units'
import HealthChartCard from '@/features/health/components/HealthChartCard.vue'
import { useHealthMetricChart } from '@/features/health/composables/useHealthMetricChart'
import { formatHealthEntryDate } from '@/features/health/utils/healthFormat'

const props = defineProps<{
  /** The weight entries to plot (newest first, as returned by the backend). */
  entries: WeightEntry[]
  /** The user's weight target in kilograms, drawn as a flat reference line. */
  targetKg: number | null
  /** The viewer's measurement system, controlling the displayed unit. */
  units: Schemas['Units']
}>()

const { t, locale } = useI18n()

const WEIGHT_COLOR = themeColor('--color-brand-mid')
const TARGET_COLOR = themeColor('--color-goal')

/** Converts a stored kg value into the viewer's display unit. */
function toDisplay(kg: number): number {
  return props.units === 'imperial' ? kgToLbs(kg) : kg
}

/** Unit suffix shown on the y-axis ticks and tooltip. */
const unitLabel = computed(() =>
  props.units === 'imperial' ? t('app.units.lb') : t('app.units.kg'),
)

/**
 * Entries that carry a weight value, oldest-first so the line reads left → right
 * in chronological order (the backend returns newest-first for the list).
 */
const plotted = computed(() =>
  props.entries
    .filter((entry) => entry.weightKg !== null)
    .slice()
    .reverse(),
)

/** Render options for the chart provider: a weight line plus an optional target line. */
const chartRender = computed<ChartRenderOptions>(() => {
  const labels = plotted.value.map((entry) => formatHealthEntryDate(entry.date, locale.value))
  const data = plotted.value.map(
    (entry) => Math.round(toDisplay(entry.weightKg as number) * 10) / 10,
  )
  const series: ChartRenderOptions['series'] = [
    { label: t('health.weight.chartWeightSeries'), data, color: WEIGHT_COLOR },
  ]
  if (props.targetKg !== null && labels.length > 0) {
    const target = Math.round(toDisplay(props.targetKg) * 10) / 10
    series.push({
      label: t('health.weight.chartTargetSeries'),
      data: labels.map(() => target),
      color: TARGET_COLOR,
      dashed: true,
    })
  }
  return {
    kind: 'line',
    series,
    labels,
    valueFormat: (value) => `${value.toFixed(1)} ${unitLabel.value}`,
  }
})

useHealthMetricChart(chartRender)
</script>

<template>
  <HealthChartCard :title="t('health.weight.chartTitle')" :accent-color="WEIGHT_COLOR">
    <!-- min-w-0 lets the canvas shrink inside the grid on mobile. -->
    <div ref="chartContainer" class="relative h-56 w-full min-w-0" />
  </HealthChartCard>
</template>
