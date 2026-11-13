<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import AppLogo from '@/components/AppLogo.vue'
import AuthScreenLayout from '@/components/layout/AuthScreenLayout.vue'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { useForm } from '@/composables/useForm'
import { useInvalidatingMutation } from '@/composables/useInvalidatingMutation'
import { useToasts } from '@/composables/useToasts'
import { completeOnboarding } from '@/features/auth/services/onboarding'
import { useAuthStore } from '@/features/auth/stores/auth'
import { usePublicServerSettings } from '@/features/config/composables/usePublicServerSettings'
import BackupCodesDialog from '@/features/security/components/BackupCodesDialog.vue'
import MfaSetupDialog from '@/features/security/components/MfaSetupDialog.vue'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import PasswordStrengthMeter from '@/features/security/components/PasswordStrengthMeter.vue'
import {
  usePasswordConfirmation,
  usePasswordPolicy,
} from '@/features/security/composables/usePasswordPolicy'
import { HttpError } from '@/services/http'
import { isProblem, retryWaitMessage } from '@/services/problems'
import { queryKeys } from '@/services/queryKeys'
import { compose, email, required } from '@/utils/validators'

/** Form field shape backing the onboarding form. */
interface OnboardingFormValues {
  token: string
  name: string
  username: string
  email: string
  password: string
  confirmPassword: string
}

const router = useRouter()
const { t } = useI18n()
const { loginImageUrl, load } = usePublicServerSettings()
const toasts = useToasts()
const auth = useAuthStore()

// After the account exists the owner is signed in and offered MFA before entering the app.
const step = ref<'details' | 'mfa'>('details')
const setupOpen = ref(false)
const backupCodesOpen = ref(false)
const backupCodes = ref<string[]>([])
watch(backupCodesOpen, (isOpen) => {
  if (!isOpen && backupCodes.value.length > 0) {
    void finish()
  }
})

const createAdmin = useInvalidatingMutation({
  mutationKey: queryKeys.public.onboarding(),
  mutationFn: completeOnboarding,
})

// The first account is always an administrator, so the admin policy applies.
const { hint: passwordHint, validate: validatePassword, policyError } = usePasswordPolicy('admin')

/**
 * Maps a failed onboarding request to a user-facing message.
 *
 * @param error - Caught onboarding error.
 * @returns Translated error message.
 */
function getOnboardingErrorMessage(error: unknown): string {
  if (!(error instanceof HttpError)) {
    return t('login.onboarding.errorGeneral')
  }
  const wait = retryWaitMessage(error, t)
  if (wait !== null) {
    return wait
  }
  const refusal = policyError(error)
  if (refusal !== null) {
    return refusal
  }
  if (isProblem(error, 'invalid-input')) {
    return t('login.onboarding.errorInvalidToken')
  }
  if (isProblem(error, 'validation-failed')) {
    return t('login.onboarding.errorValidation')
  }
  if (isProblem(error, 'rate-limited')) {
    return t('login.onboarding.errorTooManyAttempts')
  }
  if (isProblem(error, 'service-unavailable')) {
    return t('login.onboarding.errorUnavailable')
  }
  return t('login.onboarding.errorGeneral')
}

/**
 * Creates the first administrator and signs them in so they can set up MFA. When
 * an account already exists (409) it explains why and goes to sign in instead,
 * as it does when the automatic sign-in does not complete.
 * Throws a translated message on any other failure so `useForm` surfaces it.
 *
 * @param formValues - Validated form values.
 */
async function submitForm(formValues: OnboardingFormValues): Promise<void> {
  try {
    await createAdmin.mutateAsync({
      token: formValues.token.trim(),
      name: formValues.name.trim(),
      username: formValues.username.trim().toLowerCase(),
      email: formValues.email.trim().toLowerCase(),
      password: formValues.password,
    })
  } catch (error) {
    if (isProblem(error, 'conflict')) {
      toasts.error(t('login.onboarding.errorAlreadyDone'))
      await router.replace({ name: 'login' })
      return
    }
    throw new Error(getOnboardingErrorMessage(error))
  }
  if (await signInAdmin(formValues.username.trim().toLowerCase(), formValues.password)) {
    step.value = 'mfa'
    return
  }
  await router.replace({ name: 'login', query: { onboardingComplete: 'true' } })
}

/**
 * Signs the new administrator in with the credentials just chosen.
 *
 * @param username - Normalised username.
 * @param password - The chosen password.
 * @returns Whether a session was established.
 */
async function signInAdmin(username: string, password: string): Promise<boolean> {
  try {
    return (await auth.login(username, password)).status === 'authenticated'
  } catch {
    return false
  }
}

/** Shows the one-time backup codes of the freshly enabled MFA. */
function onMfaEnabled(codes: string[]): void {
  backupCodes.value = codes
  backupCodesOpen.value = true
}

/** Enters the app. */
async function finish(): Promise<void> {
  await router.replace({ name: 'home' })
}

const { values, errors, isValid, isSubmitting, submitError, handleSubmit, handleBlur } =
  useForm<OnboardingFormValues>({
    initialValues: {
      token: '',
      name: '',
      username: '',
      email: '',
      password: '',
      confirmPassword: '',
    },
    validators: {
      token: required(t('login.onboarding.requiredField')),
      name: required(t('login.onboarding.requiredField')),
      username: required(t('login.onboarding.requiredField')),
      email: compose(
        required<string>(t('login.onboarding.requiredField')),
        email(t('login.onboarding.emailInvalid')),
      ),
      password: compose(required<string>(t('login.onboarding.requiredField')), validatePassword),
    },
    onSubmit: submitForm,
  })

// A validator can't read the sibling `password` field (`values` comes from this
// same `useForm(...)` call), so the mismatch is derived here instead.
const { matches: passwordsMatch, error: confirmPasswordError } = usePasswordConfirmation(
  () => values.password,
  () => values.confirmPassword,
)

onMounted(() => {
  void load()
})
</script>

<template>
  <AuthScreenLayout :image-url="loginImageUrl" :image-alt="t('login.imageAlt')">
    <div v-if="step === 'mfa'" class="mx-auto flex w-full max-w-sm flex-col">
      <AppLogo width="40" height="40" class="mx-auto mb-3 size-10" />
      <h1 class="text-center text-page-title">
        {{ t('login.onboarding.mfaTitle') }}
      </h1>
      <p class="mt-2 text-center text-body">
        {{ t('login.onboarding.mfaSubtitle') }}
      </p>
      <div class="mt-5 flex flex-col gap-3">
        <Button class="w-full" data-test="mfa-setup" @click="setupOpen = true">
          {{ t('login.onboarding.mfaSetup') }}
        </Button>
        <Button class="w-full" variant="outline" data-test="mfa-skip" @click="finish">
          {{ t('login.onboarding.mfaSkip') }}
        </Button>
      </div>
      <MfaSetupDialog
        v-model:open="setupOpen"
        require-password
        @enabled="onMfaEnabled"
        @error="(message) => toasts.error(message)"
      />
      <BackupCodesDialog v-model:open="backupCodesOpen" :codes="backupCodes" />
    </div>
    <form
      v-else
      class="mx-auto flex w-full max-w-sm flex-col"
      novalidate
      @submit.prevent="handleSubmit"
    >
      <AppLogo width="40" height="40" class="mx-auto mb-3 size-10" />
      <h1 class="text-center text-page-title">
        {{ t('login.onboarding.title') }}
      </h1>
      <p class="mt-2 text-center text-body">
        {{ t('login.onboarding.subtitle') }}
      </p>

      <Alert v-if="submitError" kind="error" class="mt-5">
        {{ submitError }}
      </Alert>

      <div class="mt-5 flex flex-col gap-3">
        <FormField :label="t('login.onboarding.token')" required :error="errors.token">
          <template #default="{ fieldId, describedBy, invalid }">
            <Input
              :id="fieldId"
              v-model="values.token"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              name="setup-token"
              type="text"
              autocomplete="off"
              autocapitalize="off"
              spellcheck="false"
              required
              :disabled="isSubmitting"
              @blur="handleBlur('token')"
            />
          </template>
        </FormField>

        <FormField :label="t('login.onboarding.name')" required :error="errors.name">
          <template #default="{ fieldId, describedBy, invalid }">
            <Input
              :id="fieldId"
              v-model="values.name"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              name="name"
              type="text"
              autocomplete="name"
              required
              :disabled="isSubmitting"
              @blur="handleBlur('name')"
            />
          </template>
        </FormField>

        <FormField :label="t('login.onboarding.username')" required :error="errors.username">
          <template #default="{ fieldId, describedBy, invalid }">
            <Input
              :id="fieldId"
              v-model="values.username"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              name="username"
              type="text"
              autocomplete="username"
              required
              :disabled="isSubmitting"
              @blur="handleBlur('username')"
            />
          </template>
        </FormField>

        <FormField :label="t('login.onboarding.email')" required :error="errors.email">
          <template #default="{ fieldId, describedBy, invalid }">
            <Input
              :id="fieldId"
              v-model="values.email"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              name="email"
              type="email"
              autocomplete="email"
              required
              :disabled="isSubmitting"
              @blur="handleBlur('email')"
            />
          </template>
        </FormField>

        <FormField :label="t('login.onboarding.password')" required :error="errors.password">
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
            <PasswordStrengthMeter
              :password="values.password"
              :user-inputs="[values.name, values.username, values.email]"
            />
            <p class="text-hint">{{ passwordHint }}</p>
          </template>
        </FormField>

        <FormField
          :label="t('login.onboarding.confirmPassword')"
          required
          :error="confirmPasswordError"
        >
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
          class="w-full"
          type="submit"
          :disabled="!isValid || !passwordsMatch || isSubmitting"
        >
          <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
          <span>{{
            isSubmitting ? t('login.onboarding.submitting') : t('login.onboarding.submitButton')
          }}</span>
        </Button>
      </div>
    </form>
  </AuthScreenLayout>
</template>
