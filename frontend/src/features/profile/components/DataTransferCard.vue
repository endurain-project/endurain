<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Download, LoaderCircle, Upload } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useToasts } from '@/composables/useToasts'
import { HttpError } from '@/services/http'
import { downloadBlob } from '@/lib/download'
import { isTerminalProfileExport, isTerminalProfileImport } from '@/features/profile/types'
import {
  useDownloadProfileExportMutation,
  useExportProfileMutation,
  useImportProfileMutation,
  useProfileExportQuery,
  useProfileImportQuery,
} from '@/features/profile/composables/useDataTransfer'

const props = defineProps<{
  /** The current user's id, used to name the export archive. */
  userId: number
}>()

const { t } = useI18n()
const toasts = useToasts()
const exportMutation = useExportProfileMutation()
const exportQuery = useProfileExportQuery()
const downloadMutation = useDownloadProfileExportMutation()
const importMutation = useImportProfileMutation()
const importQuery = useProfileImportQuery()

const exportStatus = computed(() => exportQuery.data.value ?? null)
/** Whether an export is queued or being built, so a second one cannot start. */
const isExportActive = computed(
  () => exportStatus.value !== null && !isTerminalProfileExport(exportStatus.value),
)
/** Whether a finished export is waiting to be downloaded. */
const isExportReady = computed(() => exportStatus.value?.status === 'completed')

/** The one-line progress or outcome of the latest export. */
const exportMessage = computed<string | null>(() => {
  const status = exportStatus.value
  if (!status) {
    return null
  }
  if (status.status === 'failed') {
    const reason = t(
      `settings.profile.dataTransfer.exportFailure.${status.failure ?? 'processing_failed'}`,
    )
    return t('settings.profile.dataTransfer.exportStatus.failed', { reason })
  }
  return t(`settings.profile.dataTransfer.exportStatus.${status.status}`)
})

const importStatus = computed(() => importQuery.data.value ?? null)
/** Whether an import is queued or running, so a second one cannot start. */
const isImportActive = computed(
  () => importStatus.value !== null && !isTerminalProfileImport(importStatus.value),
)

/** The one-line progress or outcome of the latest import. */
const importMessage = computed<string | null>(() => {
  const status = importStatus.value
  if (!status) {
    return null
  }
  if (status.status === 'failed') {
    const reason = t(
      `settings.profile.dataTransfer.failure.${status.failure ?? 'processing_failed'}`,
    )
    return t('settings.profile.dataTransfer.status.failed', { reason })
  }
  return t(`settings.profile.dataTransfer.status.${status.status}`, {
    activities: status.imported?.activities ?? 0,
    gears: status.imported?.gears ?? 0,
  })
})

const fileInput = ref<HTMLInputElement | null>(null)

/** Queues an export of the user's data; the finished archive is downloaded from the card. */
function handleExport(): void {
  exportMutation.mutate(undefined, {
    onSuccess: () => toasts.success(t('settings.profile.dataTransfer.exportQueued')),
    onError: (error) =>
      toasts.error(
        error instanceof HttpError && error.status === 409
          ? t('settings.profile.dataTransfer.exportInProgress')
          : t('settings.profile.dataTransfer.exportError'),
      ),
  })
}

/** Downloads the finished export archive and saves it to disk. */
function handleDownload(): void {
  downloadMutation.mutate(undefined, {
    onSuccess: (blob) => {
      const stamp = new Date().toISOString().slice(0, 16).replace(':', '-')
      downloadBlob(blob, `endurain_user_${props.userId}_${stamp}.zip`)
      toasts.success(t('settings.profile.dataTransfer.downloadSuccess'))
    },
    onError: () => toasts.error(t('settings.profile.dataTransfer.downloadError')),
  })
}

/** Opens the native file picker for the import archive. */
function pickArchive(): void {
  fileInput.value?.click()
}

/**
 * Validates the chosen file is a ZIP archive and imports it. The input is
 * always reset so re-selecting the same file fires `change` again.
 *
 * @param event - The file input change event.
 */
function onArchiveChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  const isZip =
    file.type === 'application/zip' ||
    file.type === 'application/x-zip-compressed' ||
    file.name.toLowerCase().endsWith('.zip')
  if (!isZip) {
    toasts.error(t('settings.profile.dataTransfer.invalidType'))
    return
  }
  importMutation.mutate(file, {
    onSuccess: () => toasts.success(t('settings.profile.dataTransfer.importQueued')),
    onError: (error) =>
      toasts.error(
        error instanceof HttpError && error.status === 409
          ? t('settings.profile.dataTransfer.importInProgress')
          : t('settings.profile.dataTransfer.importError'),
      ),
  })
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-col gap-1">
      <h2 class="text-card-heading">{{ t('settings.profile.dataTransfer.title') }}</h2>
      <p class="text-body">{{ t('settings.profile.dataTransfer.subtitle') }}</p>
    </div>

    <input
      ref="fileInput"
      type="file"
      accept=".zip,application/zip"
      class="sr-only"
      @change="onArchiveChange"
    />

    <div class="flex flex-col gap-3 sm:flex-row">
      <Button
        variant="outline"
        class="w-full sm:w-auto"
        :disabled="exportMutation.isPending.value || isExportActive"
        @click="handleExport"
      >
        <LoaderCircle
          v-if="exportMutation.isPending.value || isExportActive"
          class="size-4 animate-spin"
          aria-hidden="true"
        />
        <Download v-else class="size-4" aria-hidden="true" />
        {{ t('settings.profile.dataTransfer.export') }}
      </Button>
      <Button
        v-if="isExportReady"
        class="w-full sm:w-auto"
        :disabled="downloadMutation.isPending.value"
        @click="handleDownload"
      >
        <LoaderCircle
          v-if="downloadMutation.isPending.value"
          class="size-4 animate-spin"
          aria-hidden="true"
        />
        <Download v-else class="size-4" aria-hidden="true" />
        {{ t('settings.profile.dataTransfer.download') }}
      </Button>
      <Button
        variant="outline"
        class="w-full sm:w-auto"
        :disabled="importMutation.isPending.value || isImportActive"
        @click="pickArchive"
      >
        <LoaderCircle
          v-if="importMutation.isPending.value || isImportActive"
          class="size-4 animate-spin"
          aria-hidden="true"
        />
        <Upload v-else class="size-4" aria-hidden="true" />
        {{ t('settings.profile.dataTransfer.import') }}
      </Button>
    </div>

    <p v-if="exportMessage" class="text-hint" role="status" aria-live="polite">
      {{ exportMessage }}
    </p>

    <p v-if="importMessage" class="text-hint" role="status" aria-live="polite">
      {{ importMessage }}
    </p>

    <p class="text-hint">{{ t('settings.profile.dataTransfer.note') }}</p>
  </Card>
</template>
