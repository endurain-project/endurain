<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { SleepEntry } from '@/features/health/types'

import { themeColor } from '@/lib/themeColor'
import HealthChartCard from '@/features/health/components/HealthChartCard.vue'
import { useHealthMetricChart } from '@/features/health/composables/useHealthMetricChart'
import { formatHealthEntryDate, formatHoursMinutes } from '@/features/health/utils/healthFormat'

const props = defineProps<{
  /** The sleep entries to plot (newest first, as returned by the backend). */
  entries: SleepEntry[]
  /** The user's sleep target in seconds, drawn as a flat reference line. */
  targetSeconds: number | null
}>()

const { t, locale } = useI18n()

const SLEEP_COLOR = themeColor('--color-brand-mid')
const TARGET_COLOR = themeColor('--color-goal')

/** Rounds seconds to one-decimal hours for a readable y-axis. */
function toHours(seconds: number): number {
  return Math.round((seconds / 3600) * 10) / 10
}

/**
 * Entries that carry a total-sleep value, oldest-first so the line reads
 * left → right in chronological order (the backend returns newest-first).
 */
const plotted = computed(() =>
  props.entries
    .filter((entry) => entry.totalSleepSeconds !== null)
    .slice()
    .reverse(),
)

/** Render options for the chart provider: a sleep line plus an optional target line. */
const chartRender = computed<ChartRenderOptions>(() => {
  const labels = plotted.value.map((entry) => formatHealthEntryDate(entry.date, locale.value))
  const data = plotted.value.map((entry) => toHours(entry.totalSleepSeconds as number))
  const series: ChartRenderOptions['series'] = [
    { label: t('health.sleep.chartSleepSeries'), data, color: SLEEP_COLOR },
  ]
  if (props.targetSeconds !== null && props.targetSeconds > 0 && labels.length > 0) {
    const target = toHours(props.targetSeconds)
    series.push({
      label: t('health.sleep.chartTargetSeries'),
      data: labels.map(() => target),
      color: TARGET_COLOR,
      dashed: true,
    })
  }
  return {
    kind: 'bar',
    series,
    labels,
    valueFormat: (value) => formatHoursMinutes(value * 3600, t),
  }
})

useHealthMetricChart(chartRender)
</script>

<template>
  <HealthChartCard :title="t('health.sleep.chartTitle')" :accent-color="SLEEP_COLOR">
    <!-- min-w-0 lets the canvas shrink inside the grid on mobile. -->
    <div ref="chartContainer" class="relative h-56 w-full min-w-0" />
  </HealthChartCard>
</template>
