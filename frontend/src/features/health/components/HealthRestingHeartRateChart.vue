<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { RestingHeartRateEntry } from '@/features/health/types'

import { themeColor } from '@/lib/themeColor'
import HealthChartCard from '@/features/health/components/HealthChartCard.vue'
import { useHealthMetricChart } from '@/features/health/composables/useHealthMetricChart'
import { formatHealthEntryDate, formatRestingHeartRate } from '@/features/health/utils/healthFormat'

const props = defineProps<{
  /** The resting-heart-rate entries to plot (newest first, as returned by the backend). */
  entries: RestingHeartRateEntry[]
}>()

const { t, locale } = useI18n()

const RHR_COLOR = themeColor('--color-brand-mid')

/**
 * Entries that carry a resting heart rate, oldest-first so the line reads
 * left → right in chronological order (the backend returns newest-first).
 */
const plotted = computed(() =>
  props.entries
    .filter((entry) => entry.restingHeartRate !== null)
    .slice()
    .reverse(),
)

/** Render options for the chart provider: a single resting-heart-rate line. */
const chartRender = computed<ChartRenderOptions>(() => {
  const labels = plotted.value.map((entry) => formatHealthEntryDate(entry.date, locale.value))
  const data = plotted.value.map((entry) => Math.round(entry.restingHeartRate as number))
  return {
    kind: 'line',
    series: [{ label: t('health.rhr.chartSeries'), data, color: RHR_COLOR }],
    labels,
    valueFormat: (value) => formatRestingHeartRate(value, t),
  }
})

useHealthMetricChart(chartRender)
</script>

<template>
  <HealthChartCard :title="t('health.rhr.chartTitle')" :accent-color="RHR_COLOR">
    <!-- min-w-0 lets the canvas shrink inside the grid on mobile. -->
    <div ref="chartContainer" class="relative h-56 w-full min-w-0" />
  </HealthChartCard>
</template>
