<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Footprints, Plus, Target } from '@lucide/vue'

import type { HealthInterval, StepsEntry } from '@/features/health/types'

import HealthStepsChart from '@/features/health/components/HealthStepsChart.vue'
import HealthStepsFormDialog from '@/features/health/components/HealthStepsFormDialog.vue'
import HealthStepsListItem from '@/features/health/components/HealthStepsListItem.vue'
import HealthStepsTargetDialog from '@/features/health/components/HealthStepsTargetDialog.vue'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { EmptyState } from '@/components/ui/empty-state'
import { ListPanel } from '@/components/ui/list-panel'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useChartProvider } from '@/composables/useChartProvider'
import { useListPagination } from '@/composables/useListPagination'
import { useToasts } from '@/composables/useToasts'
import { isStaleWrite } from '@/services/ifMatch'
import { useRecordsPerPage } from '@/features/config/composables/useRecordsPerPage'
import {
  useDeleteStepsEntryMutation,
  useHealthTargetsQuery,
  useStepsEntriesQuery,
  useHealthChartQuery,
} from '@/features/health/composables/useHealth'

const { t } = useI18n()
const toasts = useToasts()
const chart = useChartProvider()

/** Selectable time windows for the steps history, in display order. */
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

const targetsQuery = useHealthTargetsQuery()
const targets = computed(() => targetsQuery.data.value ?? null)
const targetSteps = computed(() => targets.value?.steps ?? null)

const listQuery = useStepsEntriesQuery(page, recordsPerPage, interval)
const chartQuery = useHealthChartQuery('steps', interval)

/** Steps entries on the current page (newest first). */
const entries = computed(() => listQuery.data.value?.records ?? [])
/** Server-reported total across all pages. */
const totalCount = computed(() => listQuery.data.value?.total ?? 0)

// Numbered pagination: derives the page count and clamps the page when the
// total shrinks (e.g. after deleting the last entry on the final page).
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

// Add/edit dialog state. `editingEntry` null means "add".
const isFormOpen = ref(false)
const editingEntry = ref<StepsEntry | null>(null)

function openAdd(): void {
  editingEntry.value = null
  isFormOpen.value = true
}

function openEdit(entry: StepsEntry): void {
  editingEntry.value = entry
  isFormOpen.value = true
}

// Target dialog state.
const isTargetOpen = ref(false)

function openTarget(): void {
  isTargetOpen.value = true
}

function onDialogSuccess(message: string): void {
  toasts.success(message)
}

function onDialogError(message: string): void {
  toasts.error(message)
}

// Delete dialog state.
const isDeleteOpen = ref(false)
const entryToDelete = ref<StepsEntry | null>(null)
const deleteMutation = useDeleteStepsEntryMutation()

function openDelete(entry: StepsEntry): void {
  entryToDelete.value = entry
  isDeleteOpen.value = true
}

function confirmDelete(): void {
  const entry = entryToDelete.value
  if (!entry) {
    return
  }
  deleteMutation.mutate(
    { id: entry.id, version: entry.version },
    {
      onSuccess: () => {
        isDeleteOpen.value = false
        toasts.success(t('health.steps.delete.success'))
      },
      onError: (error) =>
        toasts.error(isStaleWrite(error) ? t('app.staleError') : t('health.steps.delete.error')),
    },
  )
}
</script>

<template>
  <section class="flex flex-col gap-3">
    <header class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('health.steps.title') }}</h1>
      <p class="text-body">{{ t('health.steps.subtitle') }}</p>
    </header>

    <!-- Action bar: log / set-target buttons on the left, interval filter on the right. -->
    <div class="flex flex-wrap items-center gap-2">
      <Button @click="openAdd">
        <Plus class="size-4" aria-hidden="true" />
        {{ t('health.steps.logButton') }}
      </Button>
      <Button variant="outline" :disabled="!targets" @click="openTarget">
        <Target class="size-4" aria-hidden="true" />
        {{ t('health.steps.targetButton') }}
      </Button>
      <div class="ms-auto w-full sm:w-36">
        <Select v-model="interval" :aria-label="t('health.steps.interval.label')">
          <option v-for="option in INTERVAL_OPTIONS" :key="option" :value="option">
            {{ t(`health.steps.interval.${option}`) }}
          </option>
        </Select>
      </div>
    </div>

    <HealthStepsChart v-if="chartSeries" :series="chartSeries" :target-steps="targetSteps" />
    <Alert v-else-if="chartQuery.isError.value" kind="error">
      {{ t('health.chartError') }}
    </Alert>

    <ListPanel
      v-model:page="page"
      :is-loading="isPending"
      :is-error="isError"
      :is-empty="isEmpty"
      :show-header="false"
      :error-title="t('health.steps.error.title')"
      :error-description="t('health.steps.error.description')"
      :retry-label="t('health.steps.error.retry')"
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
          :title="t('health.steps.empty.title')"
          :description="t('health.steps.empty.description')"
          variant="first-time"
        >
          <template #icon>
            <Footprints class="size-8" aria-hidden="true" />
          </template>
          <template #action>
            <Button @click="openAdd">
              <Plus class="size-4" aria-hidden="true" />
              {{ t('health.steps.logButton') }}
            </Button>
          </template>
        </EmptyState>
      </template>

      <ul class="divide-y divide-border">
        <li v-for="entry in entries" :key="entry.id">
          <HealthStepsListItem :entry="entry" @edit="openEdit" @delete="openDelete" />
        </li>
      </ul>
    </ListPanel>

    <HealthStepsFormDialog
      v-model:open="isFormOpen"
      :entry="editingEntry"
      @success="onDialogSuccess"
      @error="onDialogError"
    />
    <HealthStepsTargetDialog
      v-if="targets"
      v-model:open="isTargetOpen"
      :targets="targets"
      @success="onDialogSuccess"
      @error="onDialogError"
    />
    <ConfirmDialog
      v-model:open="isDeleteOpen"
      :title="t('health.steps.delete.title')"
      :description="t('health.steps.delete.body')"
      :confirm-label="t('health.steps.delete.confirm')"
      :cancel-label="t('health.steps.delete.cancel')"
      :close-label="t('health.steps.delete.close')"
      :pending="deleteMutation.isPending.value"
      @confirm="confirmDelete"
    />
  </section>
</template>
