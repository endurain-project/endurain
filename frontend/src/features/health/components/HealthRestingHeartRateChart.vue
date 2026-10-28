<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { HealthChartSeries } from '@/features/health/types'

import { themeColor } from '@/lib/themeColor'
import HealthChartCard from '@/features/health/components/HealthChartCard.vue'
import { useHealthMetricChart } from '@/features/health/composables/useHealthMetricChart'
import {
  formatHealthChartLabel,
  formatRestingHeartRate,
} from '@/features/health/utils/healthFormat'

const props = defineProps<{
  /** The metric aggregated over the selected interval, oldest bucket first. */
  series: HealthChartSeries
}>()

const { t, locale } = useI18n()

const RHR_COLOR = themeColor('--color-brand-mid')

/** Render options for the chart provider: a single resting-heart-rate line. */
const chartRender = computed<ChartRenderOptions>(() => {
  const labels = props.series.points.map((point) =>
    formatHealthChartLabel(point.date, props.series.bucket, locale.value),
  )
  const data = props.series.points.map((point) => Math.round(point.value))
  return {
    kind: 'line',
    series: [{ label: t('health.rhr.chartSeries'), data, color: RHR_COLOR }],
    labels,
    valueFormat: (value) => formatRestingHeartRate(value),
  }
})

useHealthMetricChart(chartRender)
</script>

<template>
  <HealthChartCard
    :title="t('health.rhr.chartTitle')"
    :accent-color="RHR_COLOR"
    :bucket="series.bucket"
  >
    <!-- min-w-0 lets the canvas shrink inside the grid on mobile. -->
    <div ref="chartContainer" class="relative h-56 w-full min-w-0" />
  </HealthChartCard>
</template>
