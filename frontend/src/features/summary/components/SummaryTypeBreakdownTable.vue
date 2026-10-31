<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { Units } from '@/features/activities/utils/format'
import type { SummaryTypeBreakdownRow } from '@/features/summary/types'

import { Card } from '@/components/ui/card'
import { useUnitFormat } from '@/composables/useUnitFormat'
import { activityTypeIcon, presentActivityType } from '@/features/activities/utils/activityType'
import {
  formatSummaryCalories,
  formatSummaryDistance,
  formatSummaryDuration,
  formatSummaryElevation,
} from '@/features/summary/utils/summaryFormat'

defineProps<{
  /** The per-activity-type rows, ordered by activity count descending. */
  rows: SummaryTypeBreakdownRow[]
  /** The viewer's unit system. */
  units: Units
}>()

const { t } = useI18n()
const { formatMetric, duration } = useUnitFormat()

/** Renders the aggregate duration in the localized hours-and-minutes format. */
function summaryDuration(seconds: number): string {
  const { hours, minutes } = formatSummaryDuration(seconds)
  return duration(hours, minutes)
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <h2 class="text-item-title">{{ t('summary.typeBreakdown.title') }}</h2>

    <p v-if="rows.length === 0" class="text-hint">{{ t('summary.empty.description') }}</p>

    <div v-else class="overflow-x-auto">
      <table class="w-full border-collapse text-body">
        <thead>
          <tr class="border-b border-border">
            <th scope="col" class="py-2 pe-3 text-start text-caption">
              {{ t('summary.typeBreakdown.type') }}
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
          <tr
            v-for="row in rows"
            :key="row.activityType"
            class="border-b border-border last:border-0"
          >
            <td class="py-2 pe-3">
              <span class="flex items-center gap-2">
                <component
                  :is="activityTypeIcon(row.activityType)"
                  class="size-4 shrink-0 text-muted-foreground"
                  aria-hidden="true"
                />
                <span>{{ t(presentActivityType(row.activityType).labelKey) }}</span>
              </span>
            </td>
            <td class="px-3 py-2 text-end tabular-nums">
              {{ formatMetric(formatSummaryDistance(row.totalDistance, units)) }}
            </td>
            <td class="px-3 py-2 text-end tabular-nums">
              {{ summaryDuration(row.totalDuration) }}
            </td>
            <td class="hidden px-3 py-2 text-end tabular-nums sm:table-cell">
              {{ formatMetric(formatSummaryElevation(row.totalElevationGain, units)) }}
            </td>
            <td class="hidden px-3 py-2 text-end tabular-nums sm:table-cell">
              {{ formatMetric(formatSummaryCalories(row.totalCalories)) }}
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
