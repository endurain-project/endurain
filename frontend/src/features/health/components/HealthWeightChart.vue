<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { Schemas } from '@/types'
import type { HealthChartSeries } from '@/features/health/types'

import { themeColor } from '@/lib/themeColor'
import { kgToLbs } from '@/utils/units'
import HealthChartCard from '@/features/health/components/HealthChartCard.vue'
import { useHealthMetricChart } from '@/features/health/composables/useHealthMetricChart'
import { formatHealthChartLabel } from '@/features/health/utils/healthFormat'

const props = defineProps<{
  /** The metric aggregated over the selected interval, oldest bucket first. */
  series: HealthChartSeries
  /** The user's weight target in kilograms, drawn as a flat reference line. */
  targetKg: number | null
  /** The measurement system used to present body mass (kg or lb). */
  weightUnits: Schemas['Units']
}>()

const { t, locale } = useI18n()

const WEIGHT_COLOR = themeColor('--color-brand-mid')
const TARGET_COLOR = themeColor('--color-goal')

/** Converts a stored kg value into the viewer's display unit. */
function toDisplay(kg: number): number {
  return props.weightUnits === 'imperial' ? kgToLbs(kg) : kg
}

/** Unit suffix shown on the y-axis ticks and tooltip. */
const unitLabel = computed(() => (props.weightUnits === 'imperial' ? 'lb' : 'kg'))

/** Render options for the chart provider: a weight line plus an optional target line. */
const chartRender = computed<ChartRenderOptions>(() => {
  const labels = props.series.points.map((point) =>
    formatHealthChartLabel(point.date, props.series.bucket, locale.value),
  )
  const data = props.series.points.map((point) => Math.round(toDisplay(point.value) * 10) / 10)
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
  <HealthChartCard
    :title="t('health.weight.chartTitle')"
    :accent-color="WEIGHT_COLOR"
    :bucket="series.bucket"
  >
    <!-- min-w-0 lets the canvas shrink inside the grid on mobile. -->
    <div ref="chartContainer" class="relative h-56 w-full min-w-0" />
  </HealthChartCard>
</template>
