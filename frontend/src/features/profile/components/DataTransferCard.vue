<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Download, LoaderCircle, Upload } from '@lucide/vue'

import type { IdpReauth, StepUpInput } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import StepUpDialog from '@/features/security/components/StepUpDialog.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useToasts } from '@/composables/useToasts'
import { isProblem } from '@/services/problems'
import { downloadBlob } from '@/lib/download'
import {
  isStepUpFailed,
  isStepUpLocked,
  useIdpReauthChallenge,
} from '@/features/security/composables/useIdpStepUp'
import { isTerminalJobState } from '@/services/jobStatus'
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
  /** Whether the account has a local password (gates the step-up password field). */
  hasLocalPassword: boolean
  /** Whether MFA is enabled (gates the step-up MFA-code field). */
  mfaEnabled: boolean
  /** The identity-provider sign-in the browser just returned from, if any. */
  resume: IdpStepUpResume | null
}>()

const { t } = useI18n()
const toasts = useToasts()
const exportMutation = useExportProfileMutation()
const exportJob = useProfileExportQuery()
const downloadMutation = useDownloadProfileExportMutation()
const importMutation = useImportProfileMutation()
const importJob = useProfileImportQuery()
const handleIdpChallenge = useIdpReauthChallenge()

const isStepUpOpen = ref(false)
const idpReauth = ref<IdpReauth | null>(null)

/** Reopens the dialog once the identity-provider sign-in returns. */
onMounted(() => {
  if (props.resume?.action === 'profile_export') {
    idpReauth.value = props.resume.reauth
    isStepUpOpen.value = true
  }
})

const exportStatus = exportJob
/** Whether an export is queued or being built, so a second one cannot start. */
const isExportActive = computed(
  () => exportStatus.value !== null && !isTerminalJobState(exportStatus.value.status),
)
/** Whether a finished export is waiting to be downloaded. */
const isExportReady = computed(() => exportStatus.value?.status === 'succeeded')

/** The one-line progress or outcome of the latest export. */
const exportMessage = computed<string | null>(() => {
  const status = exportStatus.value
  if (!status) {
    return null
  }
  if (status.status === 'failed') {
    const reason = t(
      `settings.profile.dataTransfer.exportFailure.${status.error_code ?? 'processing_failed'}`,
    )
    return t('settings.profile.dataTransfer.exportStatus.failed', { reason })
  }
  return t(`settings.profile.dataTransfer.exportStatus.${status.status}`)
})

const importStatus = importJob
/** Whether an import is queued or running, so a second one cannot start. */
const isImportActive = computed(
  () => importStatus.value !== null && !isTerminalJobState(importStatus.value.status),
)

/** The one-line progress or outcome of the latest import. */
const importMessage = computed<string | null>(() => {
  const status = importStatus.value
  if (!status) {
    return null
  }
  if (status.status === 'failed') {
    const reason = t(
      `settings.profile.dataTransfer.failure.${status.error_code ?? 'processing_failed'}`,
    )
    return t('settings.profile.dataTransfer.status.failed', { reason })
  }
  return t(`settings.profile.dataTransfer.status.${status.status}`, {
    activities: status.imported?.activities ?? 0,
    count: status.imported?.activities ?? 0,
    gears: status.imported?.gears ?? 0,
  })
})

const fileInput = ref<HTMLInputElement | null>(null)

/** Queues an export of the user's data after step-up; the finished archive is downloaded from the card. */
function handleExport(input: StepUpInput): void {
  exportMutation.mutate(input, {
    onSuccess: () => {
      isStepUpOpen.value = false
      toasts.success(t('settings.profile.dataTransfer.exportQueued'))
    },
    onError: (error) => {
      if (handleIdpChallenge(error)) {
        return
      }
      if (isProblem(error, 'conflict')) {
        isStepUpOpen.value = false
        toasts.error(t('settings.profile.dataTransfer.exportInProgress'))
      } else if (isStepUpLocked(error)) {
        toasts.error(t('settings.security.stepUp.tooManyAttempts'))
      } else if (isStepUpFailed(error)) {
        toasts.error(t('settings.security.linked.invalidCredentials'))
      } else {
        toasts.error(t('settings.profile.dataTransfer.exportError'))
      }
    },
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
        isProblem(error, 'conflict')
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
        @click="isStepUpOpen = true"
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

    <StepUpDialog
      v-model:open="isStepUpOpen"
      v-model:reauth="idpReauth"
      action="profile_export"
      :title="t('settings.profile.dataTransfer.exportStepUp.title')"
      :description="t('settings.profile.dataTransfer.exportStepUp.description')"
      :confirm-label="t('settings.profile.dataTransfer.export')"
      :require-password="props.hasLocalPassword"
      :require-mfa="props.mfaEnabled"
      :pending="exportMutation.isPending.value"
      @confirm="handleExport"
    />
  </Card>
</template>
