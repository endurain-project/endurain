<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ActivityStats } from '@/features/activities/types'
import type { Units } from '@/features/activities/utils/format'

import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  combineMetric,
  formatDistance,
  formatHmsDuration,
} from '@/features/activities/utils/format'
import { type SportStatRow, type StatMetric, topSports } from '@/features/home/utils/sportStats'

const props = defineProps<{
  /** This week's per-sport stats. */
  weekStats: ActivityStats | undefined
  /** This month's per-sport stats. */
  monthStats: ActivityStats | undefined
  /** The viewer's unit system. */
  units: Units
  /** Whether the underlying stats queries are still loading. */
  isLoading?: boolean
}>()

const { t } = useI18n()

/** The metric the user ranks and displays their sports by. */
const metric = ref<StatMetric>('distance')

/** The metric tab options, in display order. */
const METRICS: ReadonlyArray<{ value: StatMetric; labelKey: string }> = [
  { value: 'distance', labelKey: 'home.stats.metric.distance' },
  { value: 'time', labelKey: 'home.stats.metric.time' },
  { value: 'calories', labelKey: 'home.stats.metric.calories' },
]

/**
 * String proxy for the Tabs primitive, whose model is a plain `string`. Reads
 * and writes flow through the typed `metric` ref so the rest of the component
 * keeps full `StatMetric` narrowing; unknown values are ignored.
 */
const metricModel = computed<string>({
  get: () => metric.value,
  set: (value) => {
    const match = METRICS.find((option) => option.value === value)
    if (match) {
      metric.value = match.value
    }
  },
})

const weekRows = computed(() => topSports(props.weekStats, metric.value))
const monthRows = computed(() => topSports(props.monthStats, metric.value))

/** Formats a sport row's value for the currently selected metric. */
function formatValue(row: SportStatRow): string {
  if (metric.value === 'distance') {
    return combineMetric(formatDistance(row.stats.distance, row.activityType, props.units), t)
  }
  if (metric.value === 'time') {
    return formatHmsDuration(row.stats.time)
  }
  return `${Math.round(row.stats.calories)} ${t('app.units.kcal')}`
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex items-center justify-between gap-2">
      <h2 class="text-card-heading">{{ t('home.stats.title') }}</h2>
    </div>

    <!-- Metric toggle -->
    <Tabs v-model="metricModel">
      <TabsList class="grid w-full grid-cols-3" :aria-label="t('home.stats.metricLabel')">
        <TabsTrigger v-for="option in METRICS" :key="option.value" :value="option.value">
          {{ t(option.labelKey) }}
        </TabsTrigger>
      </TabsList>
    </Tabs>

    <!-- Loading -->
    <div v-if="isLoading" class="space-y-4" aria-busy="true">
      <div v-for="n in 2" :key="n" class="space-y-2">
        <Skeleton class="h-3 w-20" />
        <Skeleton class="h-5 w-full" />
        <Skeleton class="h-5 w-2/3" />
      </div>
    </div>

    <template v-else>
      <!-- This week -->
      <div class="space-y-2">
        <p class="text-caption">{{ t('home.stats.thisWeek') }}</p>
        <ul v-if="weekRows.length" class="space-y-2">
          <li v-for="row in weekRows" :key="row.key" class="flex items-center gap-2">
            <component
              :is="row.icon"
              class="size-4 shrink-0 text-muted-foreground"
              aria-hidden="true"
            />
            <span class="min-w-0 flex-1 truncate text-body">{{ t(row.labelKey) }}</span>
            <span class="text-item-title">{{ formatValue(row) }}</span>
          </li>
        </ul>
        <p v-else class="text-hint">{{ t('home.stats.empty') }}</p>
      </div>

      <!-- This month -->
      <div class="space-y-2">
        <p class="text-caption">{{ t('home.stats.thisMonth') }}</p>
        <ul v-if="monthRows.length" class="space-y-2">
          <li v-for="row in monthRows" :key="row.key" class="flex items-center gap-2">
            <component
              :is="row.icon"
              class="size-4 shrink-0 text-muted-foreground"
              aria-hidden="true"
            />
            <span class="min-w-0 flex-1 truncate text-body">{{ t(row.labelKey) }}</span>
            <span class="text-item-title">{{ formatValue(row) }}</span>
          </li>
        </ul>
        <p v-else class="text-hint">{{ t('home.stats.empty') }}</p>
      </div>
    </template>
  </Card>
</template>
