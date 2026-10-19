<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Mail } from '@lucide/vue'

import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useToasts } from '@/composables/useToasts'
import {
  useEmailStatusQuery,
  useSendTestEmailMutation,
} from '@/features/serverSettings/composables/useServerSettings'
import { HttpError } from '@/services/http'

const { t } = useI18n()
const toasts = useToasts()
const statusQuery = useEmailStatusQuery()
const testMutation = useSendTestEmailMutation()

const emailStatus = computed(() => statusQuery.data.value ?? null)

/**
 * The failure detail from the backend (the mail server's failure category and
 * SMTP status code), or null when there is no readable detail.
 */
const failureDetail = computed<string | null>(() => {
  const error = testMutation.error.value
  return error instanceof HttpError && typeof error.detail === 'string' ? error.detail : null
})

/** Sends the test email to the admin's own address and reports the outcome. */
function sendTest(): void {
  testMutation.mutate(undefined, {
    onSuccess: () => toasts.success(t('settings.server.email.sent')),
  })
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex flex-col gap-1">
      <h2 class="text-card-heading">{{ t('settings.server.email.title') }}</h2>
      <p class="text-body">{{ t('settings.server.email.description') }}</p>
    </div>

    <Skeleton v-if="statusQuery.isPending.value" class="h-9 w-full" />

    <Alert v-else-if="statusQuery.isError.value" kind="error">
      {{ t('settings.server.email.statusLoadError') }}
    </Alert>

    <template v-else-if="emailStatus">
      <Alert v-if="emailStatus.configured" kind="success">
        {{ t('settings.server.email.configured') }}
      </Alert>
      <Alert v-else kind="warning">
        {{ t('settings.server.email.notConfigured') }}
        <ul class="mt-1 list-disc pl-5">
          <li v-for="problem in emailStatus.problems" :key="problem">{{ problem }}</li>
        </ul>
      </Alert>

      <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
        <Button
          type="button"
          variant="outline"
          class="w-full sm:w-auto"
          :disabled="!emailStatus.configured || testMutation.isPending.value"
          @click="sendTest"
        >
          <Mail class="size-4" aria-hidden="true" />
          {{
            testMutation.isPending.value
              ? t('settings.server.email.sending')
              : t('settings.server.email.send')
          }}
        </Button>
        <p class="text-meta">{{ t('settings.server.email.sendHint') }}</p>
      </div>

      <Alert v-if="testMutation.isError.value" kind="error">
        {{ t('settings.server.email.failed') }}:
        {{ failureDetail ?? t('settings.server.email.failedUnknown') }}
      </Alert>
    </template>
  </Card>
</template>
