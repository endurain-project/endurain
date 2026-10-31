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
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogos'
import { useToasts } from '@/composables/useToasts'
import BulkImportProgress from '@/features/import/components/BulkImportProgress.vue'
import {
  useBulkImportFromArchiveMutation,
  useBulkImportFromFolderMutation,
  useBulkImportJobQuery,
  useImportStravaBikesMutation,
  useImportStravaShoesMutation,
} from '@/features/import/composables/useImport'
import { isTerminalIngestionJob } from '@/features/upload/types'
import { HttpError } from '@/services/http'

type PendingChoice = 'archive' | 'bikes' | 'shoes'

const { t } = useI18n()
const toasts = useToasts()

const fromFolder = useBulkImportFromFolderMutation()
const fromArchive = useBulkImportFromArchiveMutation()
const bikesMutation = useImportStravaBikesMutation()
const shoesMutation = useImportStravaShoesMutation()

const jobId = ref<string | null>(null)
const jobQuery = useBulkImportJobQuery(jobId)
const fileInput = ref<HTMLInputElement | null>(null)
const pendingChoice = ref<PendingChoice | null>(null)

const job = computed(() => jobQuery.data.value ?? null)
const importing = computed(
  () =>
    fromFolder.isPending.value ||
    fromArchive.isPending.value ||
    (job.value !== null && !isTerminalIngestionJob(job.value)),
)
const isPending = computed(
  () => importing.value || bikesMutation.isPending.value || shoesMutation.isPending.value,
)
const accept = computed(() =>
  pendingChoice.value === 'archive' ? '.zip,application/zip' : '.csv,text/csv',
)

function onAccepted(id: string): void {
  jobId.value = id
  toasts.info(t('settings.import.strava.activitiesQueued'))
}

function onActivitiesError(error: Error): void {
  if (error instanceof HttpError && error.status === 409) {
    toasts.error(t('settings.import.bulk.alreadyRunning'))
    return
  }
  toasts.error(t('settings.import.strava.activitiesError'))
}

function importFromFolder(): void {
  fromFolder.mutate('strava', {
    onSuccess: (accepted) => onAccepted(accepted.id),
    onError: onActivitiesError,
  })
}

function choose(choice: PendingChoice): void {
  pendingChoice.value = choice
  // The input's `accept` is bound to the choice, so let Vue apply it first.
  void Promise.resolve().then(() => fileInput.value?.click())
}

function onFileChosen(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  const choice = pendingChoice.value
  input.value = ''
  pendingChoice.value = null
  if (!file || choice === null) {
    return
  }
  if (choice === 'archive') {
    fromArchive.mutate(
      { file, source: 'strava' },
      { onSuccess: (accepted) => onAccepted(accepted.id), onError: onActivitiesError },
    )
  } else if (choice === 'bikes') {
    bikesMutation.mutate(file, {
      onSuccess: () => toasts.success(t('settings.import.strava.bikesSuccess')),
      onError: () => toasts.error(t('settings.import.strava.bikesError')),
    })
  } else {
    shoesMutation.mutate(file, {
      onSuccess: () => toasts.success(t('settings.import.strava.shoesSuccess')),
      onError: () => toasts.error(t('settings.import.strava.shoesError')),
    })
  }
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-3">
        <img
          :src="INTEGRATION_LOGOS.stravaMark"
          :alt="t('settings.import.strava.title')"
          class="size-10 shrink-0 object-contain rounded"
        />
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <h2 class="text-card-heading">{{ t('settings.import.strava.title') }}</h2>
            <Badge variant="secondary">{{ t('settings.import.beta') }}</Badge>
          </div>
          <p class="text-hint">{{ t('settings.import.strava.subtitle') }}</p>
        </div>
      </div>

      <input ref="fileInput" type="file" :accept="accept" class="hidden" @change="onFileChosen" />

      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button variant="outline" size="sm" :disabled="isPending">
            {{ t('settings.import.strava.import') }}
            <ChevronDown class="size-4" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-64">
          <DropdownMenuItem @select="choose('archive')">
            {{ t('settings.import.strava.activitiesUpload') }}
          </DropdownMenuItem>
          <DropdownMenuItem @select="importFromFolder">
            {{ t('settings.import.strava.activitiesFolder') }}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem @select="choose('bikes')">
            {{ t('settings.import.strava.bikes') }}
          </DropdownMenuItem>
          <DropdownMenuItem @select="choose('shoes')">
            {{ t('settings.import.strava.shoes') }}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>

    <BulkImportProgress v-if="job" :job="job" />
  </Card>
</template>
