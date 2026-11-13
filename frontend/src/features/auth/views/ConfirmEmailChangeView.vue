<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'

import AppLogo from '@/components/AppLogo.vue'
import { useQueryCredential } from '@/composables/useRouteQuery'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ui/error-state'
import { LoadingState } from '@/components/ui/loading-state'
import { confirmEmailChange } from '@/features/auth/services/signUp'
import { isProblem } from '@/services/problems'

type Status = 'pending' | 'success' | 'error'

const { t } = useI18n()

const status = ref<Status>('pending')
const errorMessage = ref('')
/** Whether the shown error may clear on its own, so trying again can succeed. */
const errorRetryable = ref(false)

/** Token from the emailed link; empty when absent or malformed. */
const credential = useQueryCredential('token')
const token = ref(credential.value)

/**
 * Switches to the error state with a message.
 *
 * @param message - Translated message shown to the user.
 * @param retryable - Whether trying the same link again can succeed.
 */
function showError(message: string, retryable = false): void {
  errorMessage.value = message
  errorRetryable.value = retryable
  status.value = 'error'
}

/**
 * Confirms the email change with the token from the link and maps the outcome to a display status. Backend
 * rejections surface as errors, retryable only when transient.
 */
async function confirm(): Promise<void> {
  if (token.value.length === 0) {
    showError(t('verifyEmail.errorInvalidToken'))
    return
  }

  status.value = 'pending'
  try {
    await confirmEmailChange({ token: token.value })
    credential.clear()
    status.value = 'success'
  } catch (error) {
    if (isProblem(error, 'invalid-input', 'not-found')) {
      credential.clear()
      showError(t('verifyEmail.errorInvalidToken'))
    } else if (isProblem(error, 'conflict')) {
      showError(t('verifyEmail.errorEmailTaken'))
    } else {
      showError(t('verifyEmail.errorGeneral'), true)
    }
  }
}

onMounted(() => {
  void confirm()
})
</script>

<template>
  <section class="mx-auto w-full max-w-md">
    <div class="rounded-card border border-border bg-card p-6 sm:p-8">
      <AppLogo width="40" height="40" class="mx-auto mb-3 size-10" />

      <LoadingState
        v-if="status === 'pending'"
        :label="t('verifyEmail.verifyingBody')"
        class="py-8"
      />

      <div v-else-if="status === 'success'" class="flex flex-col items-center text-center">
        <h1 class="text-card-heading">{{ t('verifyEmail.emailChangeSuccessTitle') }}</h1>
        <p class="mt-2 text-body">{{ t('verifyEmail.emailChangeSuccessBody') }}</p>
        <Button as-child class="mt-6">
          <RouterLink :to="{ name: 'login' }">{{ t('verifyEmail.continueButton') }}</RouterLink>
        </Button>
      </div>

      <ErrorState
        v-else
        :title="t('verifyEmail.invalidTitle')"
        :description="errorMessage"
        class="py-8"
        @retry="confirm"
      >
        <template #action="{ retry }">
          <div class="flex flex-wrap items-center justify-center gap-3">
            <Button v-if="errorRetryable" variant="outline" @click="retry">{{
              t('verifyEmail.retry')
            }}</Button>
            <Button as-child variant="ghost">
              <RouterLink :to="{ name: 'login' }">{{ t('verifyEmail.backToLogin') }}</RouterLink>
            </Button>
          </div>
        </template>
      </ErrorState>
    </div>
  </section>
</template>
