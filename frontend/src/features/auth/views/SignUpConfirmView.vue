<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import AppLogo from '@/components/AppLogo.vue'
import { useQueryCredential } from '@/composables/useRouteQuery'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ui/error-state'
import { FormField } from '@/components/ui/form-field'
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

type Status = 'password' | 'success' | 'error' | 'resend'

const EMAIL_VERIFICATION_DISABLED_TYPE = 'urn:endurain:error:email-verification-disabled'
const SIGN_UP_DISABLED_TYPE = 'urn:endurain:error:permission-denied'

/** Form field shape backing the choose-password form. */
interface ChoosePasswordValues {
  password: string
  confirmPassword: string
}

const { t } = useI18n()

/** Verification token from the emailed link; empty when absent or malformed. */
const verifyCredential = useQueryCredential('token')
const token = ref(verifyCredential.value)

// Without a token (the "didn't get the email" entry) the page offers a new email instead of the form.
const status = ref<Status>(token.value.length > 0 ? 'password' : 'resend')
const errorMessage = ref('')
const adminApprovalRequired = ref(false)
// A new email is refused too while sign-up is off, so the error state does not offer one.
const signUpDisabled = ref(false)

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
    adminApprovalRequired.value = response.next_step === 'await_approval'
    verifyCredential.clear()
    status.value = 'success'
  } catch (error) {
    if (error instanceof HttpError && error.status === 422) {
      throw new Error(policyError(error) ?? t('resetPassword.errorWeakPassword'))
    }
    if (error instanceof HttpError && error.type === SIGN_UP_DISABLED_TYPE) {
      signUpDisabled.value = true
      showError(t('signup.errorSignupDisabled'))
      return
    }
    if (error instanceof HttpError && error.type === EMAIL_VERIFICATION_DISABLED_TYPE) {
      verifyCredential.clear()
      showError(t('verifyEmail.errorVerificationDisabled'))
      return
    }
    if (error instanceof HttpError && error.status === 404) {
      verifyCredential.clear()
      showError(t('verifyEmail.errorNotFound'))
      return
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
 */
function showError(message: string): void {
  errorMessage.value = message
  status.value = 'error'
}
</script>

<template>
  <section class="mx-auto w-full max-w-md">
    <div class="rounded-card border border-border bg-card p-6 sm:p-8">
      <AppLogo width="40" height="40" class="mx-auto mb-3 size-10" />

      <form
        v-if="status === 'password'"
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
      >
        <template #action>
          <Button as-child variant="ghost">
            <RouterLink :to="{ name: 'login' }">{{ t('verifyEmail.backToLogin') }}</RouterLink>
          </Button>
        </template>
      </ErrorState>

      <ResendVerificationForm
        v-if="status === 'error' && !signUpDisabled"
        class="mt-6 border-t border-border pt-6"
      />
    </div>
  </section>
</template>
