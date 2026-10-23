<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { Schemas } from '@/types'
import type { WaterEntry } from '@/features/health/types'

import { themeColor } from '@/lib/themeColor'
import { mlToFlOz } from '@/utils/units'
import HealthChartCard from '@/features/health/components/HealthChartCard.vue'
import { useHealthMetricChart } from '@/features/health/composables/useHealthMetricChart'
import { formatHealthEntryDate } from '@/features/health/utils/healthFormat'

const props = defineProps<{
  /** The water entries to plot (newest first, as returned by the backend). */
  entries: WaterEntry[]
  /** The user's water target in millilitres, drawn as a flat reference line. */
  targetMl: number | null
  /** The viewer's measurement system, controlling the displayed unit. */
  units: Schemas['Units']
}>()

const { t, locale } = useI18n()

const WATER_COLOR = themeColor('--color-brand-mid')
const TARGET_COLOR = themeColor('--color-goal')

/** Whether the viewer reads volumes in US fluid ounces rather than millilitres. */
const isImperial = computed(() => props.units === 'imperial')

/** Converts a stored millilitre value into the viewer's display unit. */
function toDisplay(ml: number): number {
  return isImperial.value ? mlToFlOz(ml) : ml
}

/** Rounds a display value: one decimal for fluid ounces, whole millilitres otherwise. */
function roundDisplay(value: number): number {
  return isImperial.value ? Math.round(value * 10) / 10 : Math.round(value)
}

/** Unit suffix shown on the y-axis ticks and tooltip. */
const unitLabel = computed(() => (isImperial.value ? t('app.units.flOz') : t('app.units.ml')))

/**
 * Entries that carry a water value, oldest-first so the line reads left → right
 * in chronological order (the backend returns newest-first for the list).
 */
const plotted = computed(() =>
  props.entries
    .filter((entry) => entry.amountMl !== null)
    .slice()
    .reverse(),
)

/** Render options for the chart provider: a water line plus an optional target line. */
const chartRender = computed<ChartRenderOptions>(() => {
  const labels = plotted.value.map((entry) => formatHealthEntryDate(entry.date, locale.value))
  const data = plotted.value.map((entry) => roundDisplay(toDisplay(entry.amountMl as number)))
  const series: ChartRenderOptions['series'] = [
    { label: t('health.water.chartWaterSeries'), data, color: WATER_COLOR },
  ]
  if (props.targetMl !== null && labels.length > 0) {
    const target = roundDisplay(toDisplay(props.targetMl))
    series.push({
      label: t('health.water.chartTargetSeries'),
      data: labels.map(() => target),
      color: TARGET_COLOR,
      dashed: true,
    })
  }
  return {
    kind: 'bar',
    series,
    labels,
    valueFormat: (value) =>
      `${isImperial.value ? value.toFixed(1) : Math.round(value)} ${unitLabel.value}`,
  }
})

useHealthMetricChart(chartRender)
</script>

<template>
  <HealthChartCard :title="t('health.water.chartTitle')" :accent-color="WATER_COLOR">
    <!-- min-w-0 lets the canvas shrink inside the grid on mobile. -->
    <div ref="chartContainer" class="relative h-56 w-full min-w-0" />
  </HealthChartCard>
</template>
