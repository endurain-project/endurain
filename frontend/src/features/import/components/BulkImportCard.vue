<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { FolderInput, LoaderCircle } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useToasts } from '@/composables/useToasts'
import { useBulkImportMutation } from '@/features/import/composables/useImport'

const { t } = useI18n()
const toasts = useToasts()

const bulkImport = useBulkImportMutation()

function onImport(): void {
  bulkImport.mutate(undefined, {
    onSuccess: (jobs) => {
      // The server answers with one job handle per queued file, so an empty
      // list is "the folder held nothing importable" rather than a failure.
      if (jobs.length === 0) {
        toasts.info(t('settings.import.bulk.empty'))
        return
      }
      toasts.info(t('settings.import.bulk.started', jobs.length))
    },
    onError: () => toasts.error(t('settings.import.bulk.error')),
  })
}
</script>

<template>
  <Card class="flex flex-wrap items-center justify-between gap-3">
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

    <Button size="sm" :disabled="bulkImport.isPending.value" @click="onImport">
      <LoaderCircle
        v-if="bulkImport.isPending.value"
        class="size-4 animate-spin"
        aria-hidden="true"
      />
      {{ t('settings.import.bulk.button') }}
    </Button>
  </Card>
</template>
