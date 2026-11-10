<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import AppLogo from '@/components/AppLogo.vue'
import { useQueryCredential } from '@/composables/useRouteQuery'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { cancelEmailChange } from '@/features/auth/services/emailChange'
import { HttpError } from '@/services/http'

type Status = 'confirm' | 'working' | 'cancelled' | 'restored' | 'notRestored' | 'invalid' | 'error'

const { t } = useI18n()

/** The title and body messages of each outcome the server reported. */
const outcomes = {
  cancelled: { title: 'verifyEmail.cancelledTitle', body: 'verifyEmail.cancelledBody' },
  restored: { title: 'verifyEmail.restoredTitle', body: 'verifyEmail.restoredBody' },
  notRestored: { title: 'verifyEmail.notRestoredTitle', body: 'verifyEmail.notRestoredBody' },
} as const

/** Token from the emailed link; empty when absent or malformed. */
const credential = useQueryCredential('token')
const status = ref<Status>(credential.value.length > 0 ? 'confirm' : 'invalid')

/**
 * Reports the change as not made by the owner. Opening the link changes nothing: this runs only when the button is
 * pressed, so a mail scanner that fetches the link cannot cancel anything.
 */
async function cancel(): Promise<void> {
  status.value = 'working'
  try {
    const result = await cancelEmailChange({ token: credential.value })
    credential.clear()
    if (!result.change_applied) status.value = 'cancelled'
    else status.value = result.email_restored ? 'restored' : 'notRestored'
  } catch (error) {
    if (error instanceof HttpError && error.status === 400) {
      credential.clear()
      status.value = 'invalid'
    } else {
      status.value = 'error'
    }
  }
}
</script>

<template>
  <section class="mx-auto w-full max-w-md">
    <div class="rounded-card border border-border bg-card p-6 sm:p-8">
      <AppLogo width="40" height="40" class="mx-auto mb-3 size-10" />

      <div
        v-if="status === 'confirm' || status === 'working' || status === 'error'"
        class="flex flex-col items-center text-center"
      >
        <h1 class="text-card-heading">{{ t('verifyEmail.cancelTitle') }}</h1>
        <p class="mt-2 text-body">{{ t('verifyEmail.cancelBody') }}</p>
        <Alert v-if="status === 'error'" kind="error" class="mt-5 w-full">
          {{ t('verifyEmail.cancelError') }}
        </Alert>
        <Button
          variant="destructive"
          class="mt-6 w-full"
          :disabled="status === 'working'"
          @click="cancel"
        >
          <LoaderCircle
            v-if="status === 'working'"
            class="size-4 animate-spin"
            aria-hidden="true"
          />
          <span>{{
            status === 'working' ? t('verifyEmail.cancelling') : t('verifyEmail.cancelButton')
          }}</span>
        </Button>
      </div>

      <div
        v-else-if="status === 'cancelled' || status === 'restored' || status === 'notRestored'"
        class="flex flex-col items-center text-center"
      >
        <h1 class="text-card-heading">{{ t(outcomes[status].title) }}</h1>
        <p class="mt-2 text-body">{{ t(outcomes[status].body) }}</p>
        <Button as-child class="mt-6">
          <RouterLink :to="{ name: 'login' }">{{ t('verifyEmail.continueButton') }}</RouterLink>
        </Button>
      </div>

      <div v-else class="flex flex-col items-center text-center">
        <h1 class="text-card-heading">{{ t('verifyEmail.cancelInvalidTitle') }}</h1>
        <p class="mt-2 text-body">{{ t('verifyEmail.cancelInvalidBody') }}</p>
        <Button as-child variant="ghost" class="mt-6">
          <RouterLink :to="{ name: 'login' }">{{ t('verifyEmail.backToLogin') }}</RouterLink>
        </Button>
      </div>
    </div>
  </section>
</template>
