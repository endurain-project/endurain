<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Units } from '@/features/activities/utils/format'
import type { SummaryTotals } from '@/features/summary/types'

import { Card } from '@/components/ui/card'
import {
  formatSummaryCalories,
  formatSummaryDistance,
  formatSummaryDuration,
  formatSummaryElevation,
} from '@/features/summary/utils/summaryFormat'

const props = defineProps<{
  /** The aggregated period totals. */
  totals: SummaryTotals
  /** The viewer's unit system. */
  units: Units
}>()

const { t } = useI18n()

/** The five headline totals, formatted into `{ value, unit }` tiles. */
const tiles = computed(() => [
  {
    key: 'distance',
    label: t('summary.metrics.distance'),
    metric: formatSummaryDistance(props.totals.totalDistance, props.units),
  },
  {
    key: 'duration',
    label: t('summary.metrics.duration'),
    metric: formatSummaryDuration(props.totals.totalDuration, t),
  },
  {
    key: 'elevation',
    label: t('summary.metrics.elevation'),
    metric: formatSummaryElevation(props.totals.totalElevationGain, props.units),
  },
  {
    key: 'calories',
    label: t('summary.metrics.calories'),
    metric: formatSummaryCalories(props.totals.totalCalories),
  },
  {
    key: 'activities',
    label: t('summary.metrics.activities'),
    metric: { value: props.totals.activityCount.toString(), unit: '' },
  },
])
</script>

<template>
  <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
    <Card v-for="tile in tiles" :key="tile.key" class="flex flex-col gap-1">
      <p class="text-caption">{{ tile.label }}</p>
      <p class="text-page-title tabular-nums">
        {{ tile.metric.value }}
        <span v-if="tile.metric.unit" class="text-hint">{{ t(tile.metric.unit) }}</span>
      </p>
    </Card>
  </div>
</template>
