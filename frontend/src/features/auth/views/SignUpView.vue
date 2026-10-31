<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import type { SignUpRequest } from '@/features/auth/types'

import AppLogo from '@/components/AppLogo.vue'
import AuthScreenLayout from '@/components/layout/AuthScreenLayout.vue'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { useForm } from '@/composables/useForm'
import { usePublicServerSettings } from '@/features/config/composables/usePublicServerSettings'
import { useToasts } from '@/composables/useToasts'
import { DEFAULT_LOCALE, isSupportedLocale } from '@/i18n'
import { HttpError } from '@/services/http'
import { requestSignUp } from '@/features/auth/services/signUp'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import {
  usePasswordConfirmation,
  usePasswordPolicy,
} from '@/features/security/composables/usePasswordPolicy'
import { compose, email, required } from '@/utils/validators'

/** Form field shape backing the sign-up form. */
interface SignUpFormValues {
  name: string
  username: string
  email: string
  password: string
  confirmPassword: string
}

const router = useRouter()
const { t, locale } = useI18n()
const { serverSettings, loginImageUrl, isSettingsLoading, load } = usePublicServerSettings()
const toasts = useToasts()

// Standalone ref (not read from `values`) so the password validator and the
// submit gate can depend on it without a circular reference.
const passwordRequired = computed(() => !serverSettings.value.signup_require_email_verification)

// Sign-up creates a regular account, so the regular policy applies.
const { hint: passwordHint, validate: validatePassword } = usePasswordPolicy('regular')

/**
 * Maps a backend HTTP error to a non-enumerating user-facing message.
 *
 * @param error - Caught sign-up error.
 * @returns Translated error message.
 */
function getSignUpErrorMessage(error: unknown): string {
  if (!(error instanceof HttpError)) {
    return t('signup.errorGeneral')
  }
  switch (error.status) {
    case 409:
      return t('signup.errorUserExists')
    case 403:
      return t('signup.errorSignupDisabled')
    case 400:
    case 422:
      return t('signup.errorValidation')
    case 429:
      return t('signup.errorTooManyAttempts')
    default:
      return t('signup.errorGeneral')
  }
}

/**
 * Builds the payload, requests sign-up, and redirects to login with the
 * appropriate verification/approval flags. Throws a translated message on
 * failure so `useForm` surfaces it via `submitError`.
 *
 * @param formValues - Validated form values.
 */
async function submitForm(formValues: SignUpFormValues): Promise<void> {
  const payload: SignUpRequest = {
    name: formValues.name.trim(),
    username: formValues.username.trim().toLowerCase(),
    email: formValues.email.trim().toLowerCase(),
    // With email verification the password is chosen from the emailed link.
    ...(passwordRequired.value ? { password: formValues.password } : {}),
    // The account's emails and interface start in the language the form is shown in.
    preferred_language: isSupportedLocale(locale.value) ? locale.value : DEFAULT_LOCALE,
  }

  try {
    const response = await requestSignUp(payload)

    const query: Record<string, string> = {}
    if (response.email_verification_required) {
      query.emailVerificationSent = 'true'
    }
    if (response.admin_approval_required) {
      query.adminApprovalRequired = 'true'
    }

    toasts.success(t('signup.success'))
    await router.push({ name: 'login', query })
  } catch (error) {
    throw new Error(getSignUpErrorMessage(error))
  }
}

const { values, errors, isValid, isSubmitting, submitError, handleSubmit, handleBlur } =
  useForm<SignUpFormValues>({
    initialValues: {
      name: '',
      username: '',
      email: '',
      password: '',
      confirmPassword: '',
    },
    validators: {
      name: required(t('signup.requiredField')),
      username: required(t('signup.requiredField')),
      email: compose(required<string>(t('signup.requiredField')), email(t('signup.emailInvalid'))),
      password: (value: string) =>
        passwordRequired.value
          ? compose(required<string>(t('signup.requiredField')), validatePassword)(value)
          : null,
    },
    onSubmit: submitForm,
  })

// A validator can't safely read the sibling `password` field (`values` is
// destructured from this same `useForm(...)` call, so referencing it inside a
// validator here would be a circular reference) — the mismatch is surfaced via
// this computed + the `confirmPasswordError` below instead.
const { matches: passwordsMatch, error: confirmPasswordError } = usePasswordConfirmation(
  () => values.password,
  () => values.confirmPassword,
)

onMounted(async () => {
  await load()

  if (!serverSettings.value.signup_enabled) {
    toasts.error(t('signup.signupDisabled'))
    await router.replace({ name: 'login' })
  }
})
</script>

<template>
  <AuthScreenLayout :image-url="loginImageUrl" :image-alt="t('signup.imageAlt')">
    <form class="mx-auto flex w-full max-w-sm flex-col" novalidate @submit.prevent="handleSubmit">
      <AppLogo width="40" height="40" class="mx-auto mb-3 size-10" />
      <h1 class="text-center text-page-title">
        {{ t('signup.title') }}
      </h1>
      <p class="mt-2 text-center text-body">
        {{ t('signup.subtitle') }}
      </p>

      <Alert v-if="submitError" kind="error" class="mt-5">
        {{ submitError }}
      </Alert>

      <div class="mt-5 flex flex-col gap-3">
        <FormField :label="t('signup.name')" required :error="errors.name">
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

        <FormField :label="t('signup.username')" required :error="errors.username">
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

        <FormField :label="t('signup.email')" required :error="errors.email">
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

        <p v-if="!passwordRequired" class="text-hint">
          {{ t('signup.passwordByEmailHint') }}
        </p>

        <FormField
          v-if="passwordRequired"
          :label="t('signup.password')"
          :placeholder="t('signup.password')"
          required
          :error="errors.password"
        >
          <template #default="{ fieldId, describedBy, invalid, placeholder }">
            <PasswordInput
              :id="fieldId"
              v-model="values.password"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              :placeholder="placeholder"
              name="new-password"
              autocomplete="new-password"
              :disabled="isSubmitting"
              @blur="handleBlur('password')"
            />
            <p class="text-hint">{{ passwordHint }}</p>
          </template>
        </FormField>

        <FormField
          v-if="passwordRequired"
          :label="t('signup.confirmPassword')"
          :placeholder="t('signup.confirmPassword')"
          required
          :error="confirmPasswordError"
        >
          <template #default="{ fieldId, describedBy, invalid, placeholder }">
            <PasswordInput
              :id="fieldId"
              v-model="values.confirmPassword"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              :placeholder="placeholder"
              name="confirm-password"
              autocomplete="new-password"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>

        <p class="text-hint">* {{ t('signup.requiredField') }}</p>

        <Button
          class="w-full"
          type="submit"
          :disabled="
            !isValid || (passwordRequired && !passwordsMatch) || isSubmitting || isSettingsLoading
          "
        >
          <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
          <span>{{ isSubmitting ? t('signup.signingUp') : t('signup.signUpButton') }}</span>
        </Button>

        <RouterLink
          :to="{ name: 'login' }"
          class="self-center text-meta text-muted-foreground hover:text-foreground"
        >
          {{ t('signup.alreadyHaveAccount') }}
        </RouterLink>
      </div>
    </form>
  </AuthScreenLayout>
</template>
