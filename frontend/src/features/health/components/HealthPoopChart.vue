<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { HealthChartSeries } from '@/features/health/types'

import { themeColor } from '@/lib/themeColor'
import HealthChartCard from '@/features/health/components/HealthChartCard.vue'
import { useHealthMetricChart } from '@/features/health/composables/useHealthMetricChart'
import { formatHealthChartLabel } from '@/features/health/utils/healthFormat'

const props = defineProps<{
  /** Bowel movements per day over the selected interval, oldest bucket first. */
  series: HealthChartSeries
  /** The user's daily bowel-movement target, drawn as a dashed reference line. */
  targetCount: number | null
}>()

const { t, locale } = useI18n()

const COUNT_COLOR = themeColor('--color-brand-mid')
const TARGET_COLOR = themeColor('--color-goal')

/** Rounds a movements-per-day value to one decimal, so a weekly or monthly average stays readable. */
function roundPerDay(value: number): number {
  return Math.round(value * 10) / 10
}

/** Render options for the chart provider: a movements-per-day bar series plus an optional target line. */
const chartRender = computed<ChartRenderOptions>(() => {
  const labels = props.series.points.map((point) =>
    formatHealthChartLabel(point.date, props.series.bucket, locale.value),
  )
  const series: ChartRenderOptions['series'] = [
    {
      label: t('health.poop.chartCountSeries'),
      data: props.series.points.map((point) => roundPerDay(point.value)),
      color: COUNT_COLOR,
    },
  ]
  if (props.targetCount !== null && props.targetCount > 0 && labels.length > 0) {
    const target = Math.round(props.targetCount)
    series.push({
      label: t('health.poop.chartTargetSeries'),
      data: labels.map(() => target),
      color: TARGET_COLOR,
      dashed: true,
    })
  }
  return {
    kind: 'bar',
    series,
    labels,
    valueFormat: (value) => String(roundPerDay(value)),
  }
})

useHealthMetricChart(chartRender)
</script>

<template>
  <HealthChartCard
    :title="t('health.poop.chartTitle')"
    :accent-color="COUNT_COLOR"
    :bucket="series.bucket"
  >
    <!-- min-w-0 lets the canvas shrink inside the grid on mobile. -->
    <div ref="chartContainer" class="relative h-56 w-full min-w-0" />
  </HealthChartCard>
</template>
