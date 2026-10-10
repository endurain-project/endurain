<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Layers, RefreshCw, RotateCcw } from '@lucide/vue'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { formatRelativeTime } from '@/utils/datetime'
import { useJobsSummaryQuery, useReplayJobMutation } from '@/features/jobs/composables/useJobs'
import { formatAgeSeconds } from '@/features/jobs/utils/format'

const { t, locale } = useI18n()

// Native <select> binds strings; convert to the numeric window the query needs.
const windowValue = ref<'24' | '168'>('24')
const hours = computed(() => Number(windowValue.value))

const summaryQuery = useJobsSummaryQuery(hours)
const summary = computed(() => summaryQuery.data.value ?? null)

const replayMutation = useReplayJobMutation()
const replayingId = ref<string | null>(null)

/**
 * Requeue a dead-lettered job; the summary is invalidated on success so the
 * replayed row leaves the dead-letter table.
 *
 * @param jobId - The dead-letter job id to replay.
 */
function replay(jobId: string): void {
  replayingId.value = jobId
  replayMutation.mutate(jobId, {
    onSettled: () => {
      replayingId.value = null
    },
  })
}

/**
 * Relative "time ago" label for a dead-lettered job's terminal time.
 *
 * @param iso - ISO timestamp.
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
        <h1 class="text-page-title">{{ t('settings.jobs.title') }}</h1>
        <p class="text-body">{{ t('settings.jobs.subtitle') }}</p>
      </div>
      <div class="flex items-center gap-2">
        <Select v-model="windowValue" class="w-44" :aria-label="t('settings.jobs.window.label')">
          <option value="24">{{ t('settings.jobs.window.last24h') }}</option>
          <option value="168">{{ t('settings.jobs.window.last7d') }}</option>
        </Select>
        <Button
          variant="outline"
          size="icon"
          :aria-label="t('settings.jobs.refresh')"
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
        :title="t('settings.jobs.loadError.title')"
        :description="t('settings.jobs.loadError.description')"
      >
        <template #action>
          <Button variant="outline" @click="summaryQuery.refetch()">
            {{ t('settings.jobs.loadError.retry') }}
          </Button>
        </template>
      </ErrorState>
    </Card>

    <template v-else-if="summary">
      <!-- Overview tiles -->
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Card class="flex flex-col gap-1">
          <span class="text-caption text-muted-foreground">{{
            t('settings.jobs.overview.total')
          }}</span>
          <span class="text-metric">{{ summary.totalJobs }}</span>
        </Card>
        <Card class="flex flex-col gap-1">
          <span class="text-caption text-muted-foreground">{{
            t('settings.jobs.overview.pending')
          }}</span>
          <span class="text-metric" :class="summary.pending > 0 ? 'text-effort' : ''">{{
            summary.pending
          }}</span>
          <span class="text-caption text-muted-foreground">
            {{ t('settings.jobs.overview.oldestPending') }}:
            {{ formatAgeSeconds(summary.oldestPendingSeconds) }}
          </span>
        </Card>
        <Card class="flex flex-col gap-1">
          <span class="text-caption text-muted-foreground">{{
            t('settings.jobs.overview.deadLetter')
          }}</span>
          <span class="text-metric" :class="summary.deadLetter > 0 ? 'text-destructive' : ''">{{
            summary.deadLetter
          }}</span>
        </Card>
      </div>

      <!-- No jobs recorded at all -->
      <Card v-if="summary.bySubscriber.length === 0" padding="none">
        <EmptyState
          :title="t('settings.jobs.empty.title')"
          :description="t('settings.jobs.empty.description')"
        >
          <template #icon>
            <Layers class="size-8" aria-hidden="true" />
          </template>
        </EmptyState>
      </Card>

      <template v-else>
        <!-- By subscriber -->
        <Card class="flex flex-col gap-3">
          <h2 class="text-card-heading">{{ t('settings.jobs.bySubscriber.title') }}</h2>
          <div class="overflow-x-auto">
            <table class="w-full min-w-[40rem] border-collapse text-body">
              <thead>
                <tr class="border-b border-border text-caption text-muted-foreground">
                  <th scope="col" class="py-2 pr-3 text-left font-medium">
                    {{ t('settings.jobs.bySubscriber.subscriber') }}
                  </th>
                  <th scope="col" class="px-3 py-2 text-left font-medium">
                    {{ t('settings.jobs.bySubscriber.eventType') }}
                  </th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">
                    {{ t('settings.jobs.bySubscriber.total') }}
                  </th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">
                    {{ t('settings.jobs.bySubscriber.completed') }}
                  </th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">
                    {{ t('settings.jobs.bySubscriber.pending') }}
                  </th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">
                    {{ t('settings.jobs.bySubscriber.claimed') }}
                  </th>
                  <th scope="col" class="py-2 pl-3 text-right font-medium">
                    {{ t('settings.jobs.bySubscriber.deadLetter') }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in summary.bySubscriber"
                  :key="`${row.subscriberId}-${row.eventType}`"
                  class="border-b border-border"
                >
                  <td class="py-2 pr-3 font-medium">{{ row.subscriberId }}</td>
                  <td class="px-3 py-2 text-muted-foreground">{{ row.eventType }}</td>
                  <td class="px-3 py-2 text-right tabular-nums">{{ row.total }}</td>
                  <td class="px-3 py-2 text-right tabular-nums text-muted-foreground">
                    {{ row.completed }}
                  </td>
                  <td
                    class="px-3 py-2 text-right tabular-nums"
                    :class="row.pending > 0 ? 'text-effort' : 'text-muted-foreground'"
                  >
                    {{ row.pending }}
                  </td>
                  <td class="px-3 py-2 text-right tabular-nums text-muted-foreground">
                    {{ row.claimed }}
                  </td>
                  <td
                    class="py-2 pl-3 text-right tabular-nums"
                    :class="row.deadLetter > 0 ? 'text-destructive' : 'text-muted-foreground'"
                  >
                    {{ row.deadLetter }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>

        <!-- Dead-letter queue -->
        <Card class="flex flex-col gap-3">
          <h2 class="text-card-heading">{{ t('settings.jobs.deadLetter.title') }}</h2>
          <EmptyState
            v-if="summary.recentDeadLetter.length === 0"
            variant="filtered"
            :title="t('settings.jobs.deadLetter.empty')"
          />
          <ul v-else class="flex flex-col divide-y divide-border">
            <li
              v-for="job in summary.recentDeadLetter"
              :key="job.id"
              class="flex flex-col gap-1 py-3 first:pt-0 last:pb-0"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="text-item-title">{{ job.subscriberId }}</span>
                <Badge variant="secondary">{{ job.eventType }}</Badge>
                <span class="text-caption text-muted-foreground">
                  {{ t('settings.jobs.deadLetter.attempts', { count: job.attempts }) }}
                </span>
                <span class="text-caption text-muted-foreground">·</span>
                <span class="text-caption text-muted-foreground">{{ timeAgo(job.updatedAt) }}</span>
                <Button
                  class="ml-auto"
                  variant="outline"
                  size="sm"
                  :disabled="replayingId === job.id"
                  @click="replay(job.id)"
                >
                  <RotateCcw
                    class="size-4"
                    :class="{ 'animate-spin': replayingId === job.id }"
                    aria-hidden="true"
                  />
                  {{ t('settings.jobs.deadLetter.replay') }}
                </Button>
              </div>
              <p v-if="job.lastError" class="text-caption break-words text-destructive">
                {{ job.lastError }}
              </p>
            </li>
          </ul>
        </Card>
      </template>
    </template>
  </div>
</template>
