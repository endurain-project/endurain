<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown } from '@lucide/vue'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogos'
import { useToasts } from '@/composables/useToasts'
import BulkImportProgress from '@/features/import/components/BulkImportProgress.vue'
import {
  useBulkImportFromArchiveMutation,
  useBulkImportFromFolderMutation,
  useBulkImportJobQuery,
} from '@/features/import/composables/useImport'
import { isTerminalIngestionJob } from '@/features/upload/types'
import { HttpError } from '@/services/http'

const { t } = useI18n()
const toasts = useToasts()

const fromFolder = useBulkImportFromFolderMutation()
const fromArchive = useBulkImportFromArchiveMutation()

const jobId = ref<string | null>(null)
const jobQuery = useBulkImportJobQuery(jobId)
const archiveInput = ref<HTMLInputElement | null>(null)

const job = computed(() => jobQuery.data.value ?? null)
const running = computed(
  () =>
    fromFolder.isPending.value ||
    fromArchive.isPending.value ||
    (job.value !== null && !isTerminalIngestionJob(job.value)),
)

function onAccepted(id: string): void {
  jobId.value = id
  toasts.info(t('settings.import.garmin.activitiesQueued'))
}

function onError(error: Error): void {
  if (error instanceof HttpError && error.status === 409) {
    toasts.error(t('settings.import.bulk.alreadyRunning'))
    return
  }
  toasts.error(t('settings.import.garmin.activitiesError'))
}

function importFromFolder(): void {
  fromFolder.mutate('garmin', {
    onSuccess: (accepted) => onAccepted(accepted.id),
    onError,
  })
}

function chooseArchive(): void {
  archiveInput.value?.click()
}

function onArchiveChosen(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  // Reset so choosing the same file again still fires `change`.
  input.value = ''
  if (!file) {
    return
  }
  fromArchive.mutate(
    { file, source: 'garmin' },
    { onSuccess: (accepted) => onAccepted(accepted.id), onError },
  )
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-3">
        <img
          :src="INTEGRATION_LOGOS.garminApp"
          :alt="t('settings.import.garmin.title')"
          class="size-10 shrink-0 object-contain rounded"
        />
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <h2 class="text-card-heading">{{ t('settings.import.garmin.title') }}</h2>
            <Badge variant="secondary">{{ t('settings.import.beta') }}</Badge>
          </div>
          <p class="text-hint">{{ t('settings.import.garmin.subtitle') }}</p>
        </div>
      </div>

      <input
        ref="archiveInput"
        type="file"
        accept=".zip,application/zip"
        class="hidden"
        :aria-label="t('settings.import.garmin.activitiesUpload')"
        @change="onArchiveChosen"
      />

      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button variant="outline" size="sm" :disabled="running">
            {{ t('settings.import.garmin.import') }}
            <ChevronDown class="size-4" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-64">
          <DropdownMenuItem @select="chooseArchive">
            {{ t('settings.import.garmin.activitiesUpload') }}
          </DropdownMenuItem>
          <DropdownMenuItem @select="importFromFolder">
            {{ t('settings.import.garmin.activitiesFolder') }}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>

    <BulkImportProgress v-if="job" :job="job" />
  </Card>
</template>
