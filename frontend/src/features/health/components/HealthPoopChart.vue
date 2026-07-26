<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { PoopEntry } from '@/features/health/types'

import { themeColor } from '@/lib/themeColor'
import HealthChartCard from '@/features/health/components/HealthChartCard.vue'
import { useHealthMetricChart } from '@/features/health/composables/useHealthMetricChart'
import { formatHealthEntryDate, localDayOf } from '@/features/health/utils/healthFormat'

const props = defineProps<{
  /** The poop entries to plot (newest first, as returned by the backend). */
  entries: PoopEntry[]
  /** The user's daily bowel-movement target, drawn as a dashed reference line. */
  targetCount: number | null
}>()

const { t, locale } = useI18n()

const COUNT_COLOR = themeColor('--color-brand-mid')
const TARGET_COLOR = themeColor('--color-goal')

/**
 * Bowel movements aggregated into a count per calendar day, oldest-first so the
 * bars read left → right in chronological order. The backend returns one record
 * per movement (many per day are possible), so the chart shows daily frequency.
 */
const countsByDay = computed(() => {
  const counts = new Map<string, number>()
  for (const entry of props.entries) {
    if (!entry.dateTime) {
      continue
    }
    // Local day, not the UTC slice: an entry logged late evening in an
    // eastern timezone belongs to that day, not the next one.
    const day = localDayOf(entry.dateTime)
    if (!day) {
      continue
    }
    counts.set(day, (counts.get(day) ?? 0) + 1)
  }
  return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b))
})

/** Render options for the chart provider: a daily-count bar series plus an optional target line. */
const chartRender = computed<ChartRenderOptions>(() => {
  const labels = countsByDay.value.map(([day]) => formatHealthEntryDate(day, locale.value))
  const series: ChartRenderOptions['series'] = [
    {
      label: t('health.poop.chartCountSeries'),
      data: countsByDay.value.map(([, count]) => count),
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
    valueFormat: (value) => String(Math.round(value)),
  }
})

useHealthMetricChart(chartRender)
</script>

<template>
  <HealthChartCard :title="t('health.poop.chartTitle')" :accent-color="COUNT_COLOR">
    <!-- min-w-0 lets the canvas shrink inside the grid on mobile. -->
    <div ref="chartContainer" class="relative h-56 w-full min-w-0" />
  </HealthChartCard>
</template>
