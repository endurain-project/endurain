<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import AppLogo from '@/components/AppLogo.vue'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ui/error-state'
import { Label } from '@/components/ui/label'
import { usePublicServerSettings } from '@/features/config/composables/usePublicServerSettings'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import {
  usePasswordConfirmation,
  usePasswordPolicy,
} from '@/features/security/composables/usePasswordPolicy'
import { HttpError } from '@/services/http'
import { confirmPasswordReset } from '@/features/auth/services/passwordReset'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { load } = usePublicServerSettings()

/** Reset token from the emailed link; empty when absent or malformed. */
const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))

const password = ref('')
const confirmPassword = ref('')
const isLoading = ref(false)
const alert = ref<{ kind: 'error'; message: string } | null>(null)

// The account tier is unknown before submitting; see the 422 handling below.
const { hint: passwordHint, isValid: isValidPassword } = usePasswordPolicy('regular')
const { matches: passwordsMatch, error: confirmError } = usePasswordConfirmation(
  password,
  confirmPassword,
)

const isPasswordValid = computed(
  () => password.value.length === 0 || isValidPassword(password.value),
)

const canSubmit = computed(
  () => token.value.length > 0 && isValidPassword(password.value) && passwordsMatch.value,
)

/**
 * Validates the form and confirms the password reset, then redirects to the
 * sign-in page with the appropriate status flag.
 */
async function submitForm(): Promise<void> {
  if (!canSubmit.value || isLoading.value) {
    return
  }

  isLoading.value = true
  alert.value = null

  try {
    await confirmPasswordReset({ token: token.value, new_password: password.value })
    await router.replace({ name: 'login', query: { passwordResetSuccess: 'true' } })
  } catch (error) {
    // The client only knows the regular-user length policy (the token's
    // account tier isn't known before submitting), so an admin account
    // requiring a longer/stricter password can still fail server-side even
    // though `canSubmit` passed. The backend distinguishes that case (422)
    // from an invalid/expired token (400) so this doesn't show as the wrong
    // error.
    let message = t('resetPassword.errorGeneral')
    if (error instanceof HttpError) {
      if (error.status === 400) {
        message = t('resetPassword.errorInvalidToken')
      } else if (error.status === 422) {
        message = t('resetPassword.errorWeakPassword')
      }
    }
    alert.value = { kind: 'error', message }
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="mx-auto w-full max-w-md">
    <div class="rounded-card border border-border bg-card p-6 sm:p-8">
      <ErrorState
        v-if="token.length === 0"
        :title="t('resetPassword.invalidLinkTitle')"
        :description="t('resetPassword.invalidLinkBody')"
      >
        <template #action>
          <Button as-child variant="outline">
            <RouterLink :to="{ name: 'login' }">{{ t('resetPassword.backToLogin') }}</RouterLink>
          </Button>
        </template>
      </ErrorState>

      <form v-else class="flex flex-col" novalidate @submit.prevent="submitForm">
        <AppLogo width="40" height="40" class="mx-auto mb-3 size-10" />
        <h1 class="text-center text-card-heading">
          {{ t('resetPassword.title') }}
        </h1>
        <p class="mt-2 text-center text-body">
          {{ t('resetPassword.subtitle') }}
        </p>

        <Alert v-if="alert" :kind="alert.kind" class="mt-5">
          {{ alert.message }}
        </Alert>

        <div class="mt-5 flex flex-col gap-1.5">
          <Label for="new-password">{{ t('resetPassword.newPassword') }}</Label>
          <PasswordInput
            id="new-password"
            v-model="password"
            name="new-password"
            autocomplete="new-password"
            :aria-invalid="!isPasswordValid"
          />
          <p class="text-hint">
            {{ passwordHint }}
          </p>
          <p v-if="!isPasswordValid" class="text-field-error">
            {{ t('app.password.invalid') }}
          </p>
        </div>

        <div class="mt-4 flex flex-col gap-1.5">
          <Label for="confirm-password">{{ t('resetPassword.confirmPassword') }}</Label>
          <PasswordInput
            id="confirm-password"
            v-model="confirmPassword"
            name="confirm-password"
            autocomplete="new-password"
            :aria-invalid="confirmError !== undefined"
          />
          <p v-if="confirmError" class="text-field-error">
            {{ confirmError }}
          </p>
        </div>

        <Button type="submit" class="mt-6" :disabled="!canSubmit || isLoading">
          <LoaderCircle v-if="isLoading" class="size-4 animate-spin" aria-hidden="true" />
          {{ isLoading ? t('resetPassword.submitting') : t('resetPassword.submitButton') }}
        </Button>

        <RouterLink
          :to="{ name: 'login' }"
          class="mt-4 text-center text-meta text-primary hover:underline"
        >
          {{ t('resetPassword.backToLogin') }}
        </RouterLink>
      </form>
    </div>
  </section>
</template>
