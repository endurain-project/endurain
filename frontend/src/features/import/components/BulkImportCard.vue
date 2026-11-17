<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { FolderInput, LoaderCircle, Upload } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useToasts } from '@/composables/useToasts'
import BulkImportProgress from '@/features/import/components/BulkImportProgress.vue'
import {
  useBulkImportFromArchiveMutation,
  useBulkImportFromFolderMutation,
  useBulkImportJob,
} from '@/features/import/composables/useImport'
import { isTerminalIngestionJob } from '@/features/upload/types'
import { isProblem } from '@/services/problems'

const { t } = useI18n()
const toasts = useToasts()

const fromFolder = useBulkImportFromFolderMutation()
const fromArchive = useBulkImportFromArchiveMutation()

const job = useBulkImportJob('generic')
const archiveInput = ref<HTMLInputElement | null>(null)

const running = computed(
  () =>
    fromFolder.isPending.value ||
    fromArchive.isPending.value ||
    (job.value !== null && !isTerminalIngestionJob(job.value)),
)

function onAccepted(): void {
  toasts.info(t('settings.import.bulk.started'))
}

function onError(error: Error): void {
  if (isProblem(error, 'conflict')) {
    toasts.error(t('settings.import.bulk.alreadyRunning'))
    return
  }
  toasts.error(t('settings.import.bulk.error'))
}

function importFromFolder(): void {
  fromFolder.mutate('generic', {
    onSuccess: onAccepted,
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
  fromArchive.mutate({ file, source: 'generic' }, { onSuccess: onAccepted, onError })
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-3">
        <div
          class="flex size-10 shrink-0 items-center justify-center rounded-full bg-muted-foreground/15 text-muted-foreground"
        >
          <FolderInput class="size-5" aria-hidden="true" />
        </div>
        <div class="min-w-0">
          <h2 class="text-card-heading">{{ t('settings.import.bulk.title') }}</h2>
          <p class="text-hint">{{ t('settings.import.bulk.subtitle') }}</p>
        </div>
      </div>

      <div class="flex flex-wrap gap-2">
        <input
          ref="archiveInput"
          type="file"
          accept=".zip,application/zip"
          class="hidden"
          :aria-label="t('settings.import.bulk.uploadButton')"
          @change="onArchiveChosen"
        />
        <Button variant="outline" size="sm" :disabled="running" @click="chooseArchive">
          <LoaderCircle
            v-if="fromArchive.isPending.value"
            class="size-4 animate-spin"
            aria-hidden="true"
          />
          <Upload v-else class="size-4" aria-hidden="true" />
          {{ t('settings.import.bulk.uploadButton') }}
        </Button>
        <Button size="sm" :disabled="running" @click="importFromFolder">
          <LoaderCircle
            v-if="fromFolder.isPending.value"
            class="size-4 animate-spin"
            aria-hidden="true"
          />
          {{ t('settings.import.bulk.folderButton') }}
        </Button>
      </div>
    </div>

    <BulkImportProgress v-if="job" :job="job" />
  </Card>
</template>
