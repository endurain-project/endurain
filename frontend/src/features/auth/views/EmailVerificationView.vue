<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

import AppLogo from '@/components/AppLogo.vue'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ui/error-state'
import { LoadingState } from '@/components/ui/loading-state'
import { HttpError } from '@/services/http'
import { confirmSignUp } from '@/features/auth/services/signUp'

type Status = 'pending' | 'success' | 'error'

const route = useRoute()
const { t } = useI18n()

const status = ref<Status>('pending')
const errorMessage = ref('')
const adminApprovalRequired = ref(false)

/**
 * Verifies the email token from the link and maps the outcome to a display
 * status. Missing tokens and backend rejections surface as recoverable errors.
 */
async function verify(): Promise<void> {
  const token = typeof route.query.token === 'string' ? route.query.token : ''
  if (token.length === 0) {
    status.value = 'error'
    errorMessage.value = t('verifyEmail.missingTokenBody')
    return
  }

  status.value = 'pending'
  try {
    const response = await confirmSignUp({ token })
    adminApprovalRequired.value = response.admin_approval_required === true
    status.value = 'success'
  } catch (error) {
    if (error instanceof HttpError && error.status === 404) {
      errorMessage.value = t('verifyEmail.errorNotFound')
    } else if (error instanceof HttpError && error.status === 400) {
      errorMessage.value = t('verifyEmail.errorInvalidToken')
    } else if (error instanceof HttpError && error.status === 409) {
      errorMessage.value = t('verifyEmail.errorEmailTaken')
    } else {
      errorMessage.value = t('verifyEmail.errorGeneral')
    }
    status.value = 'error'
  }
}

onMounted(() => {
  void verify()
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
        <h1 class="text-card-heading">
          {{ t('verifyEmail.successTitle') }}
        </h1>
        <p class="mt-2 text-body">{{ t('verifyEmail.successBody') }}</p>
        <Alert v-if="adminApprovalRequired" kind="info" class="mt-5 w-full">
          {{ t('verifyEmail.adminApprovalBody') }}
        </Alert>
        <Button as-child class="mt-6">
          <RouterLink :to="{ name: 'login' }">{{ t('verifyEmail.continueButton') }}</RouterLink>
        </Button>
      </div>

      <ErrorState
        v-else
        :title="t('verifyEmail.invalidTitle')"
        :description="errorMessage"
        class="py-8"
        @retry="verify"
      >
        <template #action="{ retry }">
          <div class="flex flex-wrap items-center justify-center gap-3">
            <Button variant="outline" @click="retry">{{ t('verifyEmail.retry') }}</Button>
            <Button as-child variant="ghost">
              <RouterLink :to="{ name: 'login' }">{{ t('verifyEmail.backToLogin') }}</RouterLink>
            </Button>
          </div>
        </template>
      </ErrorState>
    </div>
  </section>
</template>
