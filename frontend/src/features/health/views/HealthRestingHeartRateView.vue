<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { HeartPulse } from '@lucide/vue'

import type { HealthInterval } from '@/features/health/types'

import HealthRestingHeartRateChart from '@/features/health/components/HealthRestingHeartRateChart.vue'
import HealthRestingHeartRateListItem from '@/features/health/components/HealthRestingHeartRateListItem.vue'
import { Alert } from '@/components/ui/alert'
import { EmptyState } from '@/components/ui/empty-state'
import { ListPanel } from '@/components/ui/list-panel'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useChartProvider } from '@/composables/useChartProvider'
import { useListPagination } from '@/composables/useListPagination'
import { useRecordsPerPage } from '@/features/config/composables/useRecordsPerPage'
import { useHealthChartQuery, useRhrEntriesQuery } from '@/features/health/composables/useHealth'

const { t } = useI18n()
const chart = useChartProvider()

/** Selectable time windows for the resting-heart-rate history, in display order. */
const INTERVAL_OPTIONS: HealthInterval[] = [
  'last_7_days',
  'last_30_days',
  'last_90_days',
  'last_year',
  'all_time',
]

const interval = ref<HealthInterval>('last_7_days')
const page = ref(1)

// Page size follows the server's enforced `num_records_per_page` setting.
const { recordsPerPage } = useRecordsPerPage()

const listQuery = useRhrEntriesQuery(page, recordsPerPage, interval)
const chartQuery = useHealthChartQuery('rhr', interval)

/** Resting-heart-rate entries on the current page (newest first). */
const entries = computed(() => listQuery.data.value?.records ?? [])
/** Server-reported total across all pages. */
const totalCount = computed(() => listQuery.data.value?.total ?? 0)

// Numbered pagination: derives the page count and clamps the page when the
// total shrinks.
const { totalPages, reset: resetPage } = useListPagination(page, totalCount, recordsPerPage)

const isPending = computed(() => listQuery.isPending.value)
const isError = computed(() => listQuery.isError.value)
const isEmpty = computed(() => !isPending.value && !isError.value && entries.value.length === 0)

/**
 * The whole interval's chart series, independent of the list's page. `null` when no chart
 * provider is bundled or the interval holds nothing to plot.
 */
const chartSeries = computed(() => {
  const series = chartQuery.data.value
  return chart.isAvailable && series && series.points.length > 0 ? series : null
})

// Changing the interval changes the result set, so restart at the first page.
watch(interval, resetPage)
</script>

<template>
  <section class="flex flex-col gap-3">
    <header class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('health.rhr.title') }}</h1>
      <p class="text-body">{{ t('health.rhr.subtitle') }}</p>
    </header>

    <!-- Action bar: read-only zone, so just the interval filter. -->
    <div class="flex flex-wrap items-center gap-2">
      <div class="ms-auto w-full sm:w-36">
        <Select v-model="interval" :aria-label="t('health.rhr.interval.label')">
          <option v-for="option in INTERVAL_OPTIONS" :key="option" :value="option">
            {{ t(`health.rhr.interval.${option}`) }}
          </option>
        </Select>
      </div>
    </div>

    <HealthRestingHeartRateChart v-if="chartSeries" :series="chartSeries" />
    <Alert v-else-if="chartQuery.isError.value" kind="error">
      {{ t('health.chartError') }}
    </Alert>

    <ListPanel
      v-model:page="page"
      :is-loading="isPending"
      :is-error="isError"
      :is-empty="isEmpty"
      :show-header="false"
      :error-title="t('health.rhr.error.title')"
      :error-description="t('health.rhr.error.description')"
      :retry-label="t('health.rhr.error.retry')"
      paginated
      :total-pages="totalPages"
      @retry="listQuery.refetch()"
    >
      <template #loading>
        <div class="divide-y divide-border" aria-busy="true">
          <div v-for="n in 6" :key="n" class="px-4 py-3">
            <Skeleton class="h-4 w-1/4" />
            <Skeleton class="mt-2 h-3 w-1/3" />
          </div>
        </div>
      </template>

      <template #empty>
        <EmptyState
          :title="t('health.rhr.empty.title')"
          :description="t('health.rhr.empty.description')"
          variant="first-time"
        >
          <template #icon>
            <HeartPulse class="size-8" aria-hidden="true" />
          </template>
        </EmptyState>
      </template>

      <ul class="divide-y divide-border">
        <li v-for="entry in entries" :key="entry.id">
          <HealthRestingHeartRateListItem :entry="entry" />
        </li>
      </ul>
    </ListPanel>
  </section>
</template>
