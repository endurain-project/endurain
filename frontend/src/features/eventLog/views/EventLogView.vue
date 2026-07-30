<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ListChecks, RefreshCw } from '@lucide/vue'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { formatRelativeTime } from '@/utils/datetime'
import { useEventLogSummaryQuery } from '@/features/eventLog/composables/useEventLog'
import {
  activityIdFromMetadata,
  formatAgeSeconds,
  formatLatencyMs,
} from '@/features/eventLog/utils/format'

const { t, locale } = useI18n()

// Native <select> binds strings; convert to the numeric window the query needs.
const windowValue = ref<'24' | '168'>('24')
const hours = computed(() => Number(windowValue.value))

const summaryQuery = useEventLogSummaryQuery(hours)
const summary = computed(() => summaryQuery.data.value ?? null)

const totalFailed = computed(() =>
  (summary.value?.byType ?? []).reduce((sum, stats) => sum + stats.failed + stats.deadLetter, 0),
)
const totalPending = computed(() =>
  (summary.value?.pending ?? []).reduce((sum, group) => sum + group.count, 0),
)
const hasEvents = computed(() => (summary.value?.byType.length ?? 0) > 0)

/**
 * Relative "time ago" label for a failure's publish time.
 *
 * @param iso - ISO timestamp of the event.
 * @returns A localized relative-time string.
 */
function timeAgo(iso: string): string {
  return formatRelativeTime(iso, new Date(), locale.value)
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-col gap-1">
        <h1 class="text-page-title">{{ t('settings.eventLog.title') }}</h1>
        <p class="text-body">{{ t('settings.eventLog.subtitle') }}</p>
      </div>
      <div class="flex items-center gap-2">
        <Select
          v-model="windowValue"
          class="w-44"
          :aria-label="t('settings.eventLog.window.label')"
        >
          <option value="24">{{ t('settings.eventLog.window.last24h') }}</option>
          <option value="168">{{ t('settings.eventLog.window.last7d') }}</option>
        </Select>
        <Button
          variant="outline"
          size="icon"
          :aria-label="t('settings.eventLog.refresh')"
          :disabled="summaryQuery.isFetching.value"
          @click="summaryQuery.refetch()"
        >
          <RefreshCw
            class="size-4"
            :class="{ 'animate-spin': summaryQuery.isFetching.value }"
            aria-hidden="true"
          />
        </Button>
      </div>
    </div>

    <div v-if="summaryQuery.isPending.value" class="flex flex-col gap-3" aria-busy="true">
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Skeleton v-for="tile in 3" :key="tile" class="h-20 w-full" />
      </div>
      <Skeleton class="h-48 w-full" />
    </div>

    <Card v-else-if="summaryQuery.isError.value" padding="none">
      <ErrorState
        :title="t('settings.eventLog.loadError.title')"
        :description="t('settings.eventLog.loadError.description')"
      >
        <template #action>
          <Button variant="outline" @click="summaryQuery.refetch()">
            {{ t('settings.eventLog.loadError.retry') }}
          </Button>
        </template>
      </ErrorState>
    </Card>

    <template v-else-if="summary">
      <!-- Overview tiles -->
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Card class="flex flex-col gap-1">
          <span class="text-caption text-muted-foreground">{{
            t('settings.eventLog.overview.total')
          }}</span>
          <span class="text-metric">{{ summary.totalEvents }}</span>
        </Card>
        <Card class="flex flex-col gap-1">
          <span class="text-caption text-muted-foreground">{{
            t('settings.eventLog.overview.failed')
          }}</span>
          <span class="text-metric" :class="totalFailed > 0 ? 'text-destructive' : ''">{{
            totalFailed
          }}</span>
        </Card>
        <Card class="flex flex-col gap-1">
          <span class="text-caption text-muted-foreground">{{
            t('settings.eventLog.overview.pending')
          }}</span>
          <span class="text-metric" :class="totalPending > 0 ? 'text-effort' : ''">{{
            totalPending
          }}</span>
        </Card>
      </div>

      <!-- No events recorded at all -->
      <Card v-if="!hasEvents" padding="none">
        <EmptyState
          :title="t('settings.eventLog.empty.title')"
          :description="t('settings.eventLog.empty.description')"
        >
          <template #icon>
            <ListChecks class="size-8" aria-hidden="true" />
          </template>
        </EmptyState>
      </Card>

      <template v-else>
        <!-- By event type -->
        <Card class="flex flex-col gap-3">
          <h2 class="text-card-heading">{{ t('settings.eventLog.byType.title') }}</h2>
          <div class="overflow-x-auto">
            <table class="w-full min-w-[40rem] border-collapse text-body">
              <thead>
                <tr class="border-b border-border text-caption text-muted-foreground">
                  <th scope="col" class="py-2 pr-3 text-left font-medium">
                    {{ t('settings.eventLog.byType.eventType') }}
                  </th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">
                    {{ t('settings.eventLog.byType.total') }}
                  </th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">
                    {{ t('settings.eventLog.byType.completed') }}
                  </th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">
                    {{ t('settings.eventLog.byType.queued') }}
                  </th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">
                    {{ t('settings.eventLog.byType.pending') }}
                  </th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">
                    {{ t('settings.eventLog.byType.failed') }}
                  </th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">
                    {{ t('settings.eventLog.byType.deadLetter') }}
                  </th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">
                    {{ t('settings.eventLog.byType.avg') }}
                  </th>
                  <th scope="col" class="py-2 pl-3 text-right font-medium">
                    {{ t('settings.eventLog.byType.max') }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in summary.byType"
                  :key="row.eventType"
                  class="border-b border-border"
                >
                  <td class="py-2 pr-3 font-medium">{{ row.eventType }}</td>
                  <td class="px-3 py-2 text-right tabular-nums">{{ row.total }}</td>
                  <td class="px-3 py-2 text-right tabular-nums text-muted-foreground">
                    {{ row.completed }}
                  </td>
                  <td
                    class="px-3 py-2 text-right tabular-nums"
                    :class="row.queued > 0 ? 'text-effort' : 'text-muted-foreground'"
                  >
                    {{ row.queued }}
                  </td>
                  <td
                    class="px-3 py-2 text-right tabular-nums"
                    :class="
                      row.published + row.processing > 0 ? 'text-effort' : 'text-muted-foreground'
                    "
                  >
                    {{ row.published + row.processing }}
                  </td>
                  <td
                    class="px-3 py-2 text-right tabular-nums"
                    :class="row.failed > 0 ? 'text-destructive' : 'text-muted-foreground'"
                  >
                    {{ row.failed }}
                  </td>
                  <td
                    class="px-3 py-2 text-right tabular-nums"
                    :class="row.deadLetter > 0 ? 'text-destructive' : 'text-muted-foreground'"
                  >
                    {{ row.deadLetter }}
                  </td>
                  <td class="px-3 py-2 text-right tabular-nums text-muted-foreground">
                    {{ formatLatencyMs(row.avgProcessingTimeMs) }}
                  </td>
                  <td class="py-2 pl-3 text-right tabular-nums text-muted-foreground">
                    {{ formatLatencyMs(row.maxProcessingTimeMs) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>

        <!-- Pending work -->
        <Card class="flex flex-col gap-3">
          <h2 class="text-card-heading">{{ t('settings.eventLog.pending.title') }}</h2>
          <EmptyState
            v-if="summary.pending.length === 0"
            variant="filtered"
            :title="t('settings.eventLog.pending.empty')"
          />
          <div v-else class="overflow-x-auto">
            <table class="w-full min-w-[30rem] border-collapse text-body">
              <thead>
                <tr class="border-b border-border text-caption text-muted-foreground">
                  <th scope="col" class="py-2 pr-3 text-left font-medium">
                    {{ t('settings.eventLog.pending.eventType') }}
                  </th>
                  <th scope="col" class="px-3 py-2 text-left font-medium">
                    {{ t('settings.eventLog.pending.status') }}
                  </th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">
                    {{ t('settings.eventLog.pending.count') }}
                  </th>
                  <th scope="col" class="py-2 pl-3 text-right font-medium">
                    {{ t('settings.eventLog.pending.oldest') }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="group in summary.pending"
                  :key="`${group.eventType}-${group.status}`"
                  class="border-b border-border"
                >
                  <td class="py-2 pr-3 font-medium">{{ group.eventType }}</td>
                  <td class="px-3 py-2">
                    <Badge variant="warning">{{ group.status }}</Badge>
                  </td>
                  <td class="px-3 py-2 text-right tabular-nums">{{ group.count }}</td>
                  <td class="py-2 pl-3 text-right tabular-nums text-muted-foreground">
                    {{ formatAgeSeconds(group.oldestSeconds) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>

        <!-- Recent failures -->
        <Card class="flex flex-col gap-3">
          <h2 class="text-card-heading">{{ t('settings.eventLog.failures.title') }}</h2>
          <EmptyState
            v-if="summary.recentFailures.length === 0"
            variant="filtered"
            :title="t('settings.eventLog.failures.empty')"
          />
          <ul v-else class="flex flex-col divide-y divide-border">
            <li
              v-for="failure in summary.recentFailures"
              :key="failure.id"
              class="flex flex-col gap-1 py-3 first:pt-0 last:pb-0"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="text-item-title">{{ failure.eventType }}</span>
                <Badge variant="secondary">{{ failure.eventSource }}</Badge>
                <span
                  v-if="activityIdFromMetadata(failure.eventMetadata)"
                  class="text-caption text-muted-foreground"
                >
                  {{ t('settings.eventLog.failures.activity') }}
                  {{ activityIdFromMetadata(failure.eventMetadata) }}
                </span>
                <span class="ml-auto text-caption text-muted-foreground">{{
                  timeAgo(failure.createdAt)
                }}</span>
              </div>
              <p v-if="failure.errorMessage" class="text-caption text-destructive break-words">
                {{ failure.errorMessage }}
              </p>
              <p v-if="failure.handlerName" class="text-hint">
                {{ t('settings.eventLog.failures.handler') }} {{ failure.handlerName }}
              </p>
            </li>
          </ul>
        </Card>
      </template>
    </template>
  </div>
</template>
