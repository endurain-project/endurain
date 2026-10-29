<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Play, Target, Utensils } from '@lucide/vue'

import type { FastingEntry, FastingStatus, HealthInterval } from '@/features/health/types'

import HealthFastingActiveCard from '@/features/health/components/HealthFastingActiveCard.vue'
import HealthFastingFormDialog from '@/features/health/components/HealthFastingFormDialog.vue'
import HealthFastingListItem from '@/features/health/components/HealthFastingListItem.vue'
import HealthFastingStats from '@/features/health/components/HealthFastingStats.vue'
import HealthFastingTargetDialog from '@/features/health/components/HealthFastingTargetDialog.vue'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { EmptyState } from '@/components/ui/empty-state'
import { ListPanel } from '@/components/ui/list-panel'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useListPagination } from '@/composables/useListPagination'
import { useToasts } from '@/composables/useToasts'
import { useRecordsPerPage } from '@/features/config/composables/useRecordsPerPage'
import {
  useActiveFastingQuery,
  useCompleteFastingEntryMutation,
  useDeleteFastingEntryMutation,
  useFastingEntriesQuery,
  useFastingStatsQuery,
  useHealthTargetsQuery,
} from '@/features/health/composables/useHealth'

const { t } = useI18n()
const toasts = useToasts()

/** Selectable time windows for the fasting history, in display order. */
const INTERVAL_OPTIONS: HealthInterval[] = [
  'last_7_days',
  'last_30_days',
  'last_90_days',
  'last_year',
  'all_time',
]

const interval = ref<HealthInterval>('last_30_days')
const page = ref(1)

// Page size follows the server's enforced `num_records_per_page` setting.
const { recordsPerPage } = useRecordsPerPage()

const targetsQuery = useHealthTargetsQuery()
const targets = computed(() => targetsQuery.data.value ?? null)

const activeQuery = useActiveFastingQuery()
const activeFast = computed(() => activeQuery.data.value ?? null)

const statsQuery = useFastingStatsQuery()
const stats = computed(() => statsQuery.data.value ?? null)

const listQuery = useFastingEntriesQuery(page, recordsPerPage, interval)

/** Fasting sessions on the current page (newest first). */
const entries = computed(() => listQuery.data.value?.records ?? [])
/** Server-reported total across all pages. */
const totalCount = computed(() => listQuery.data.value?.total ?? 0)

// Numbered pagination: derives the page count and clamps the page when the
// total shrinks (e.g. after deleting the last entry on the final page).
const { totalPages, reset: resetPage } = useListPagination(page, totalCount, recordsPerPage)

const isPending = computed(() => listQuery.isPending.value)
const isError = computed(() => listQuery.isError.value)
const isEmpty = computed(() => !isPending.value && !isError.value && entries.value.length === 0)

// Changing the interval changes the result set, so restart at the first page.
watch(interval, resetPage)

// Complete / break / cancel the active fast.
const completeMutation = useCompleteFastingEntryMutation()
const completing = computed(() => completeMutation.isPending.value)

function onComplete(status: FastingStatus): void {
  const active = activeFast.value
  if (!active) {
    return
  }
  completeMutation.mutate(
    { id: active.id, fastEndTime: new Date().toISOString(), status, version: active.version },
    {
      onSuccess: () => toasts.success(t('health.fasting.complete.success')),
      onError: () => toasts.error(t('health.fasting.complete.error')),
    },
  )
}

// Add/edit dialog state. `editingEntry` null means "start a new fast".
const isFormOpen = ref(false)
const editingEntry = ref<FastingEntry | null>(null)

function openAdd(): void {
  editingEntry.value = null
  isFormOpen.value = true
}

function openEdit(entry: FastingEntry): void {
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
const entryToDelete = ref<FastingEntry | null>(null)
const deleteMutation = useDeleteFastingEntryMutation()

function openDelete(entry: FastingEntry): void {
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
        toasts.success(t('health.fasting.delete.success'))
      },
      onError: () => {
        toasts.error(t('health.fasting.delete.error'))
      },
    },
  )
}
</script>

<template>
  <section class="flex flex-col gap-3">
    <header class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('health.fasting.title') }}</h1>
      <p class="text-body">{{ t('health.fasting.subtitle') }}</p>
    </header>

    <!-- Active fast replaces the start/target actions while a fast is running. -->
    <HealthFastingActiveCard
      v-if="activeFast"
      :entry="activeFast"
      :completing="completing"
      @complete="onComplete"
    />
    <div v-else class="flex flex-wrap items-center gap-2">
      <Button @click="openAdd">
        <Play class="size-4" aria-hidden="true" />
        {{ t('health.fasting.startButton') }}
      </Button>
      <Button variant="outline" :disabled="!targets" @click="openTarget">
        <Target class="size-4" aria-hidden="true" />
        {{ t('health.fasting.targetButton') }}
      </Button>
    </div>

    <HealthFastingStats v-if="stats" :stats="stats" />
    <div v-else-if="statsQuery.isPending.value" class="grid grid-cols-2 gap-2 sm:grid-cols-3">
      <Skeleton v-for="n in 6" :key="n" class="h-16" />
    </div>

    <!-- History action bar: interval filter. -->
    <div class="flex flex-wrap items-center gap-2">
      <div class="ms-auto w-full sm:w-36">
        <Select v-model="interval" :aria-label="t('health.fasting.interval.label')">
          <option v-for="option in INTERVAL_OPTIONS" :key="option" :value="option">
            {{ t(`health.fasting.interval.${option}`) }}
          </option>
        </Select>
      </div>
    </div>

    <ListPanel
      v-model:page="page"
      :is-loading="isPending"
      :is-error="isError"
      :is-empty="isEmpty"
      :show-header="false"
      :error-title="t('health.fasting.error.title')"
      :error-description="t('health.fasting.error.description')"
      :retry-label="t('health.fasting.error.retry')"
      paginated
      :total-pages="totalPages"
      @retry="listQuery.refetch()"
    >
      <template #loading>
        <div class="divide-y divide-border" aria-busy="true">
          <div v-for="n in 6" :key="n" class="px-4 py-3">
            <Skeleton class="h-4 w-1/3" />
            <Skeleton class="mt-2 h-3 w-1/2" />
          </div>
        </div>
      </template>

      <template #empty>
        <EmptyState
          :title="t('health.fasting.empty.title')"
          :description="t('health.fasting.empty.description')"
          variant="first-time"
        >
          <template #icon>
            <Utensils class="size-8" aria-hidden="true" />
          </template>
          <template v-if="!activeFast" #action>
            <Button @click="openAdd">
              <Play class="size-4" aria-hidden="true" />
              {{ t('health.fasting.startButton') }}
            </Button>
          </template>
        </EmptyState>
      </template>

      <ul class="divide-y divide-border">
        <li v-for="entry in entries" :key="entry.id">
          <HealthFastingListItem :entry="entry" @edit="openEdit" @delete="openDelete" />
        </li>
      </ul>
    </ListPanel>

    <HealthFastingFormDialog
      v-model:open="isFormOpen"
      :entry="editingEntry"
      @success="onDialogSuccess"
      @error="onDialogError"
    />
    <HealthFastingTargetDialog
      v-if="targets"
      v-model:open="isTargetOpen"
      :targets="targets"
      @success="onDialogSuccess"
      @error="onDialogError"
    />
    <ConfirmDialog
      v-model:open="isDeleteOpen"
      :title="t('health.fasting.delete.title')"
      :description="t('health.fasting.delete.body')"
      :confirm-label="t('health.fasting.delete.confirm')"
      :cancel-label="t('health.fasting.delete.cancel')"
      :close-label="t('health.fasting.delete.close')"
      :pending="deleteMutation.isPending.value"
      @confirm="confirmDelete"
    />
  </section>
</template>
