<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { Units } from '@/features/activities/utils/format'
import type { SummaryBreakdownRow, SummaryViewType } from '@/features/summary/types'

import { Card } from '@/components/ui/card'
import { monthNameLabel, weekdayLabel } from '@/features/summary/utils/period'
import {
  combineSummaryMetric,
  formatSummaryCalories,
  formatSummaryDistance,
  formatSummaryDuration,
  formatSummaryElevation,
} from '@/features/summary/utils/summaryFormat'

const props = defineProps<{
  /** The active view type (drives the period-column label per row). */
  viewType: SummaryViewType
  /** The breakdown rows, in chronological order. */
  rows: SummaryBreakdownRow[]
  /** The viewer's unit system. */
  units: Units
}>()

const { t, locale } = useI18n()

/** Resolves the period-column label for a row's bucket, per view type. */
function periodLabel(bucket: number): string {
  switch (props.viewType) {
    case 'week':
      return weekdayLabel(bucket, locale.value)
    case 'month':
      return t('summary.breakdown.weekNumber', { number: bucket })
    case 'year':
      return monthNameLabel(bucket, locale.value)
    case 'lifetime':
      return bucket.toString()
  }
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <h2 class="text-item-title">{{ t('summary.breakdown.title') }}</h2>

    <p v-if="rows.length === 0" class="text-hint">{{ t('summary.empty.description') }}</p>

    <div v-else class="overflow-x-auto">
      <table class="w-full border-collapse text-body">
        <thead>
          <tr class="border-b border-border">
            <th scope="col" class="py-2 pe-3 text-start text-caption">
              {{ t('summary.breakdown.period') }}
            </th>
            <th scope="col" class="px-3 py-2 text-end text-caption">
              {{ t('summary.metrics.distance') }}
            </th>
            <th scope="col" class="px-3 py-2 text-end text-caption">
              {{ t('summary.metrics.duration') }}
            </th>
            <th scope="col" class="hidden px-3 py-2 text-end text-caption sm:table-cell">
              {{ t('summary.metrics.elevation') }}
            </th>
            <th scope="col" class="hidden px-3 py-2 text-end text-caption sm:table-cell">
              {{ t('summary.metrics.calories') }}
            </th>
            <th scope="col" class="hidden py-2 ps-3 text-end text-caption md:table-cell">
              {{ t('summary.metrics.activities') }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.bucket" class="border-b border-border last:border-0">
            <td class="py-2 pe-3">{{ periodLabel(row.bucket) }}</td>
            <td class="px-3 py-2 text-end tabular-nums">
              {{ combineSummaryMetric(formatSummaryDistance(row.totalDistance, units), t) }}
            </td>
            <td class="px-3 py-2 text-end tabular-nums">
              {{ combineSummaryMetric(formatSummaryDuration(row.totalDuration), t) }}
            </td>
            <td class="hidden px-3 py-2 text-end tabular-nums sm:table-cell">
              {{ combineSummaryMetric(formatSummaryElevation(row.totalElevationGain, units), t) }}
            </td>
            <td class="hidden px-3 py-2 text-end tabular-nums sm:table-cell">
              {{ combineSummaryMetric(formatSummaryCalories(row.totalCalories), t) }}
            </td>
            <td class="hidden py-2 ps-3 text-end tabular-nums md:table-cell">
              {{ row.activityCount }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </Card>
</template>
