<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Download, RefreshCw, Trash2 } from '@lucide/vue'

import type { LogFilters, LogLevel } from '@/features/serverSettings/types'

import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { EmptyState } from '@/components/ui/empty-state'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { useToasts } from '@/composables/useToasts'
import {
  useClearLogsMutation,
  useDownloadLogsMutation,
  useLogsQuery,
} from '@/features/serverSettings/composables/useServerSettings'
import { downloadBlob } from '@/lib/download'
import { cn } from '@/lib/utils'

/**
 * The server log viewer: the newest records of the application log, filterable
 * by severity and text, with an optional live tail and a download of the file.
 * Only mounted while its tab is open, so it polls only while it is visible.
 */
const { t } = useI18n()
const toasts = useToasts()

const LEVELS: readonly LogLevel[] = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

/** Text colour per severity, from the semantic tokens. */
const LEVEL_CLASSES: Record<string, string> = {
  WARNING: 'text-effort',
  ERROR: 'text-hr',
  CRITICAL: 'text-hr font-semibold',
}

const level = ref<LogLevel | ''>('')
const searchDraft = ref('')
const appliedSearch = ref('')
const live = ref(false)

const filters = computed<LogFilters>(() => ({
  level: level.value || null,
  search: appliedSearch.value,
}))

const logsQuery = useLogsQuery(filters, live)
const downloadMutation = useDownloadLogsMutation()
const clearMutation = useClearLogsMutation()
const confirmClearOpen = ref(false)

const entries = computed(() => logsQuery.data.value?.entries ?? [])

/** Applies the typed search text; the query refetches because its key changed. */
function applySearch(): void {
  appliedSearch.value = searchDraft.value.trim()
}

/** Saves the current log file to disk. */
function handleDownload(): void {
  downloadMutation.mutate(undefined, {
    onSuccess: (blob) => downloadBlob(blob, 'endurain-app.log'),
    onError: () => toasts.error(t('settings.server.logs.downloadError')),
  })
}

/** Empties the server log once the admin has confirmed. */
function handleClear(): void {
  clearMutation.mutate(undefined, {
    onSuccess: () => {
      confirmClearOpen.value = false
      toasts.success(t('settings.server.logs.cleared'))
    },
    onError: () => toasts.error(t('settings.server.logs.clearError')),
  })
}
</script>

<template>
  <Card class="flex flex-col gap-3" data-setting="section-logs">
    <div class="flex flex-col gap-1">
      <h2 class="text-card-heading">{{ t('settings.server.logs.title') }}</h2>
      <p class="text-body">{{ t('settings.server.logs.description') }}</p>
    </div>

    <div class="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
      <FormField :label="t('settings.server.logs.level')">
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="level">
            <option value="">{{ t('settings.server.logs.allLevels') }}</option>
            <option v-for="option in LEVELS" :key="option" :value="option">{{ option }}</option>
          </Select>
        </template>
      </FormField>

      <form class="sm:min-w-64 sm:flex-1" role="search" @submit.prevent="applySearch">
        <FormField :label="t('settings.server.logs.search')">
          <template #default="{ fieldId }">
            <Input
              :id="fieldId"
              v-model="searchDraft"
              type="search"
              maxlength="200"
              :placeholder="t('settings.server.logs.searchPlaceholder')"
            />
          </template>
        </FormField>
      </form>

      <Switch v-model="live" :aria-label="t('settings.server.logs.live')">
        {{ t('settings.server.logs.live') }}
      </Switch>

      <div class="flex gap-2">
        <Button
          variant="outline"
          :disabled="logsQuery.isFetching.value"
          @click="logsQuery.refetch()"
        >
          <RefreshCw
            :class="cn('size-4', logsQuery.isFetching.value && 'animate-spin')"
            aria-hidden="true"
          />
          {{ t('settings.server.logs.refresh') }}
        </Button>
        <Button
          variant="outline"
          :disabled="downloadMutation.isPending.value"
          @click="handleDownload"
        >
          <Download class="size-4" aria-hidden="true" />
          {{ t('settings.server.logs.download') }}
        </Button>
        <Button variant="outline" @click="confirmClearOpen = true">
          <Trash2 class="size-4" aria-hidden="true" />
          {{ t('settings.server.logs.clear') }}
        </Button>
      </div>
    </div>

    <Skeleton v-if="logsQuery.isPending.value" class="h-48 w-full" />
    <Alert v-else-if="logsQuery.isError.value" kind="error">
      {{ t('settings.server.logs.loadError') }}
    </Alert>
    <EmptyState
      v-else-if="entries.length === 0"
      variant="filtered"
      :title="t('settings.server.logs.empty')"
    />
    <ol v-else class="flex max-h-[32rem] flex-col gap-1 overflow-auto font-mono text-meta">
      <li v-for="(entry, index) in entries" :key="index" class="rounded-input border px-2 py-1">
        <div class="flex flex-wrap gap-x-2">
          <time v-if="entry.timestamp" class="text-muted-foreground">{{ entry.timestamp }}</time>
          <span :class="cn('shrink-0', LEVEL_CLASSES[entry.level])">{{ entry.level }}</span>
          <span v-if="entry.logger" class="text-muted-foreground">{{ entry.logger }}</span>
          <span v-if="entry.request_id" class="text-muted-foreground"
            >[{{ entry.request_id }}]</span
          >
        </div>
        <p class="break-words whitespace-pre-wrap">{{ entry.message }}</p>
        <pre v-if="entry.context" class="whitespace-pre-wrap text-muted-foreground">{{
          JSON.stringify(entry.context)
        }}</pre>
        <pre v-if="entry.exception" class="whitespace-pre-wrap text-hr">{{ entry.exception }}</pre>
      </li>
    </ol>

    <ConfirmDialog
      v-model:open="confirmClearOpen"
      :title="t('settings.server.logs.clearConfirm.title')"
      :description="t('settings.server.logs.clearConfirm.description')"
      :confirm-label="t('settings.server.logs.clearConfirm.confirm')"
      :cancel-label="t('settings.server.logs.clearConfirm.cancel')"
      :close-label="t('settings.server.logs.clearConfirm.close')"
      :pending="clearMutation.isPending.value"
      @confirm="handleClear"
    />
  </Card>
</template>
