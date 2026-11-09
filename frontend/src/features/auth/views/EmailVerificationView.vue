<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import AppLogo from '@/components/AppLogo.vue'
import { useQueryCredential } from '@/composables/useRouteQuery'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ui/error-state'
import { FormField } from '@/components/ui/form-field'
import { LoadingState } from '@/components/ui/loading-state'
import { useForm } from '@/composables/useForm'
import ResendVerificationForm from '@/features/auth/components/ResendVerificationForm.vue'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import PasswordStrengthMeter from '@/features/security/components/PasswordStrengthMeter.vue'
import {
  usePasswordConfirmation,
  usePasswordPolicy,
} from '@/features/security/composables/usePasswordPolicy'
import { HttpError } from '@/services/http'
import { confirmSignUp } from '@/features/auth/services/signUp'
import { compose, required } from '@/utils/validators'

type Status = 'pending' | 'password' | 'success' | 'error' | 'resend'

/** Problem type the backend answers for a sign-up link confirmed without a password. */
const PASSWORD_REQUIRED_TYPE = 'urn:endurain:error:password-required'
const EMAIL_VERIFICATION_DISABLED_TYPE = 'urn:endurain:error:email-verification-disabled'

/** Form field shape backing the choose-password form. */
interface ChoosePasswordValues {
  password: string
  confirmPassword: string
}

const { t } = useI18n()

const status = ref<Status>('pending')
const errorMessage = ref('')
/** Whether the shown error may clear on its own, so trying again can succeed. */
const errorRetryable = ref(false)
const adminApprovalRequired = ref(false)

/** Verification token from the emailed link; empty when absent or malformed. */
const verifyCredential = useQueryCredential('token')
const token = ref(verifyCredential.value)

// The account tier is unknown before submitting, so the regular policy applies;
// a stricter server-side policy answers 422 (see `submitPassword`).
const { hint: passwordHint, validate: validatePassword, policyError } = usePasswordPolicy('regular')

/**
 * Confirms the sign-up with the chosen password. A 422 keeps the form and
 * shows the policy message through `submitError`; other failures leave the form.
 *
 * @param formValues - Validated form values.
 */
async function submitPassword(formValues: ChoosePasswordValues): Promise<void> {
  try {
    const response = await confirmSignUp({ token: token.value, password: formValues.password })
    adminApprovalRequired.value = response.admin_approval_required === true
    verifyCredential.clear()
    status.value = 'success'
  } catch (error) {
    if (error instanceof HttpError && error.status === 422) {
      throw new Error(policyError(error) ?? t('resetPassword.errorWeakPassword'))
    }
    if (error instanceof HttpError && error.status === 400) {
      verifyCredential.clear()
      showError(t('verifyEmail.errorInvalidToken'))
      return
    }
    throw new Error(t('verifyEmail.errorGeneral'))
  }
}

const { values, errors, isValid, isSubmitting, submitError, handleSubmit, handleBlur } =
  useForm<ChoosePasswordValues>({
    initialValues: { password: '', confirmPassword: '' },
    validators: {
      password: compose(required<string>(t('signup.requiredField')), validatePassword),
    },
    onSubmit: submitPassword,
  })

// Mismatch is surfaced via this computed rather than a validator, which cannot
// read a sibling field of the `useForm(...)` call it is declared in.
const { matches: passwordsMatch, error: confirmPasswordError } = usePasswordConfirmation(
  () => values.password,
  () => values.confirmPassword,
)

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
 * Verifies the email token from the link and maps the outcome to a display
 * status. A missing token (the "didn't get the email" entry) shows the resend
 * form; backend rejections surface as errors, retryable only when transient.
 */
async function verify(): Promise<void> {
  if (token.value.length === 0) {
    status.value = 'resend'
    return
  }

  status.value = 'pending'
  try {
    const response = await confirmSignUp({ token: token.value })
    adminApprovalRequired.value = response.admin_approval_required === true
    verifyCredential.clear()
    status.value = 'success'
  } catch (error) {
    if (error instanceof HttpError && error.type === PASSWORD_REQUIRED_TYPE) {
      status.value = 'password'
    } else if (error instanceof HttpError && error.type === EMAIL_VERIFICATION_DISABLED_TYPE) {
      verifyCredential.clear()
      showError(t('verifyEmail.errorVerificationDisabled'))
    } else if (error instanceof HttpError && error.status === 404) {
      verifyCredential.clear()
      showError(t('verifyEmail.errorNotFound'))
    } else if (error instanceof HttpError && error.status === 400) {
      verifyCredential.clear()
      showError(t('verifyEmail.errorInvalidToken'))
    } else if (error instanceof HttpError && error.status === 409) {
      showError(t('verifyEmail.errorEmailTaken'))
    } else {
      showError(t('verifyEmail.errorGeneral'), true)
    }
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

      <form
        v-else-if="status === 'password'"
        class="flex flex-col"
        novalidate
        @submit.prevent="handleSubmit"
      >
        <h1 class="text-center text-card-heading">
          {{ t('verifyEmail.choosePasswordTitle') }}
        </h1>
        <p class="mt-2 text-center text-body">{{ t('verifyEmail.choosePasswordBody') }}</p>

        <Alert v-if="submitError" kind="error" class="mt-5">
          {{ submitError }}
        </Alert>

        <div class="mt-5 flex flex-col gap-3">
          <FormField :label="t('signup.password')" required :error="errors.password">
            <template #default="{ fieldId, describedBy, invalid }">
              <PasswordInput
                :id="fieldId"
                v-model="values.password"
                :aria-describedby="describedBy"
                :aria-invalid="invalid"
                name="new-password"
                autocomplete="new-password"
                :disabled="isSubmitting"
                @blur="handleBlur('password')"
              />
              <PasswordStrengthMeter :password="values.password" />
              <p class="text-hint">{{ passwordHint }}</p>
            </template>
          </FormField>

          <FormField :label="t('signup.confirmPassword')" required :error="confirmPasswordError">
            <template #default="{ fieldId, describedBy, invalid }">
              <PasswordInput
                :id="fieldId"
                v-model="values.confirmPassword"
                :aria-describedby="describedBy"
                :aria-invalid="invalid"
                name="confirm-password"
                autocomplete="new-password"
                :disabled="isSubmitting"
              />
            </template>
          </FormField>

          <Button
            type="submit"
            class="w-full"
            :disabled="!isValid || !passwordsMatch || isSubmitting"
          >
            <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
            <span>{{
              isSubmitting ? t('verifyEmail.submittingPassword') : t('verifyEmail.submitPassword')
            }}</span>
          </Button>
        </div>
      </form>

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

      <div v-else-if="status === 'resend'" class="flex flex-col items-center gap-4">
        <ResendVerificationForm class="w-full" />
        <Button as-child variant="ghost">
          <RouterLink :to="{ name: 'login' }">{{ t('verifyEmail.backToLogin') }}</RouterLink>
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
            <Button v-if="errorRetryable" variant="outline" @click="retry">{{
              t('verifyEmail.retry')
            }}</Button>
            <Button as-child variant="ghost">
              <RouterLink :to="{ name: 'login' }">{{ t('verifyEmail.backToLogin') }}</RouterLink>
            </Button>
          </div>
        </template>
      </ErrorState>

      <ResendVerificationForm v-if="status === 'error'" class="mt-6 border-t border-border pt-6" />
    </div>
  </section>
</template>
