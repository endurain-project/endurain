<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import ForgotPasswordDialog from '@/features/auth/components/ForgotPasswordDialog.vue'
import AppLogo from '@/components/AppLogo.vue'
import AuthScreenLayout from '@/components/layout/AuthScreenLayout.vue'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAppConfig } from '@/features/config/composables/useAppConfig'
import {
  type AlertState,
  useLoginRouteMessages,
} from '@/features/auth/composables/useLoginRouteMessages'
import { usePublicServerSettings } from '@/features/config/composables/usePublicServerSettings'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import PasswordStrengthMeter from '@/features/security/components/PasswordStrengthMeter.vue'
import {
  usePasswordConfirmation,
  usePasswordPolicy,
} from '@/features/security/composables/usePasswordPolicy'
import { useSafeRedirect } from '@/composables/useSafeRedirect'
import { useSsoLogin } from '@/features/auth/composables/useSsoLogin'
import { useToasts } from '@/composables/useToasts'
import type { IdentityProviderPublic } from '@/types'

import { resolveProviderLogo } from '@/features/identityProviders/utils/providerIcon'
import { HttpError } from '@/services/http'
import { type LoginResult, useAuthStore } from '@/features/auth/stores/auth'
import { normalizeMfaCode } from '@/features/auth/utils/mfaCode'

const auth = useAuthStore()
const { t } = useI18n()
const { config } = useAppConfig()
const { serverSettings, ssoProviders, isSettingsLoading, isSsoLoading, loginImageUrl, load } =
  usePublicServerSettings()
const { startSsoLogin, processSsoCallback, completeSsoMfa, maybeAutoRedirect } = useSsoLogin()
const { navigateAfterLogin } = useSafeRedirect()
const route = useRoute()
const { resolveInitialAlert, shouldForceLocalLogin } = useLoginRouteMessages()

/** Whether the user just signed up and was told to check their email. */
const verificationEmailSent = computed(() => route.query.emailVerificationSent === 'true')
const toasts = useToasts()

const username = ref('')
const password = ref('')
const mfaCode = ref('')
const pendingChallenge = ref('')
const pendingPasswordChangeChallenge = ref('')
const newPassword = ref('')
const confirmNewPassword = ref('')
const forceLocalLogin = ref(false)
const isLoading = ref(false)
const isForgotPasswordOpen = ref(false)
const isSsoMfaPending = ref(false)
const alert = ref<AlertState | null>(null)
// A custom icon URL can 404 or be blocked; its button then shows the text alone.
const failedLogos = reactive(new Set<string>())

// The account tier is unknown before signing in; a stricter administrator policy answers 422.
const { hint: passwordHint, isValid: isValidPassword, policyError } = usePasswordPolicy('regular')
const { matches: passwordsMatch, error: confirmError } = usePasswordConfirmation(
  newPassword,
  confirmNewPassword,
)

const isMfaStep = computed(() => pendingChallenge.value.length > 0 || isSsoMfaPending.value)
const isPasswordChangeStep = computed(() => pendingPasswordChangeChallenge.value.length > 0)
const isSecondStep = computed(() => isMfaStep.value || isPasswordChangeStep.value)
const isNewPasswordValid = computed(
  () => newPassword.value.length === 0 || isValidPassword(newPassword.value),
)
const showLocalLogin = computed(
  () => serverSettings.value.local_login_enabled || isSecondStep.value || forceLocalLogin.value,
)
const showSignUpLink = computed(() => !isSecondStep.value && serverSettings.value.signup_enabled)
const showSsoProviders = computed(
  () =>
    !isSsoLoading.value &&
    !isSecondStep.value &&
    serverSettings.value.sso_enabled &&
    ssoProviders.value.length > 0,
)
const noLoginMethods = computed(
  () => !isSettingsLoading.value && !showLocalLogin.value && !showSsoProviders.value,
)
const canSubmit = computed(() => {
  if (isPasswordChangeStep.value) {
    return isValidPassword(newPassword.value) && passwordsMatch.value
  }
  return isMfaStep.value
    ? mfaCode.value.trim().length > 0
    : username.value.trim().length > 0 && password.value.length > 0
})
const statusText = computed(() => {
  if (isPasswordChangeStep.value) {
    return t('login.changingPassword')
  }
  return isMfaStep.value ? t('login.verifyingMfa') : t('login.signingIn')
})
const submitText = computed(() => {
  if (isPasswordChangeStep.value) {
    return t('login.changePasswordButton')
  }
  return isMfaStep.value ? t('login.verifyMfaButton') : t('login.signInButton')
})

/** The step of the sign-in a request belongs to. */
type SignInStep = 'password' | 'mfa' | 'passwordChange'

/**
 * Maps a backend HTTP error to a non-enumerating user-facing message.
 *
 * @param error - Caught auth error.
 * @param step - The step whose request failed.
 * @returns Translated error message.
 */
function getAuthErrorMessage(error: unknown, step: SignInStep): string {
  if (!(error instanceof HttpError)) {
    return t('login.genericError')
  }

  if (step === 'mfa' && [400, 401, 422].includes(error.status)) {
    return t('login.invalidMfa')
  }

  if (step === 'passwordChange' && error.status === 422) {
    return policyError(error) ?? t('login.passwordChangeRejected')
  }

  switch (error.status) {
    case 401:
      // The server answers a pending account like a wrong password, so the hint covers both.
      return `${t('login.invalidCredentials')}\n${t('login.invalidCredentialsPendingHint')}`
    case 403:
      return t('login.forbidden')
    case 429:
      return error.retryAfterSeconds === null
        ? t('login.tooManyAttempts')
        : t('login.tooManyAttemptsWait', { seconds: error.retryAfterSeconds })
    case 503:
      return error.retryAfterSeconds === null
        ? t('login.unavailable')
        : t('login.unavailableWait', { seconds: error.retryAfterSeconds })
    default:
      return t('login.genericError')
  }
}

/**
 * Returns to the sign-in form, forgetting every pending step.
 */
function resetToSignIn(): void {
  pendingChallenge.value = ''
  pendingPasswordChangeChallenge.value = ''
  mfaCode.value = ''
  newPassword.value = ''
  confirmNewPassword.value = ''
  password.value = ''
}

/**
 * Shows the step the server asked for, or reports one this client cannot take.
 *
 * @param result - What the login, MFA or password-change request resolved to.
 * @returns Whether the sign-in completed.
 */
function showNextStep(result: LoginResult): boolean {
  switch (result.status) {
    case 'authenticated':
      return true
    case 'mfa-required':
      pendingChallenge.value = result.challenge
      pendingPasswordChangeChallenge.value = ''
      password.value = ''
      alert.value = { kind: 'info', message: t('login.mfaRequired') }
      return false
    case 'password-change-required':
      pendingPasswordChangeChallenge.value = result.challenge
      pendingChallenge.value = ''
      password.value = ''
      mfaCode.value = ''
      alert.value = { kind: 'info', message: t('login.passwordChangeRequired') }
      return false
    default:
      resetToSignIn()
      alert.value = { kind: 'error', message: t('login.unsupportedStep') }
      return false
  }
}

/**
 * Submits the password form, the MFA verification form or the password-change form.
 */
async function submitForm(): Promise<void> {
  if (!canSubmit.value || isLoading.value) {
    return
  }

  isLoading.value = true
  alert.value = null
  const step: SignInStep = isPasswordChangeStep.value
    ? 'passwordChange'
    : isMfaStep.value
      ? 'mfa'
      : 'password'

  try {
    if (isSsoMfaPending.value) {
      await completeSsoMfa(normalizeMfaCode(mfaCode.value))
      return
    }

    let result: LoginResult
    if (step === 'passwordChange') {
      result = await auth.changePassword(pendingPasswordChangeChallenge.value, newPassword.value)
    } else if (step === 'mfa') {
      result = await auth.verifyMfa(pendingChallenge.value, normalizeMfaCode(mfaCode.value))
    } else {
      result = await auth.login(username.value.trim(), password.value)
    }

    if (showNextStep(result)) {
      await navigateAfterLogin()
    }
  } catch (error) {
    if (step === 'passwordChange') {
      handlePasswordChangeError(error)
      return
    }
    if (step === 'mfa') {
      if (!isSsoMfaPending.value && error instanceof HttpError && error.status === 401) {
        resetToSignIn()
        alert.value = { kind: 'error', message: t('login.mfaChallengeExpired') }
        return
      }
      mfaCode.value = ''
    } else {
      password.value = ''
    }
    alert.value = { kind: 'error', message: getAuthErrorMessage(error, step) }
  } finally {
    isLoading.value = false
  }
}

/**
 * Handles a failed password-change request: an expired or used challenge sends the user back to the sign-in
 * form, a refused password keeps the step so the user can choose another.
 *
 * @param error - Caught request error.
 */
function handlePasswordChangeError(error: unknown): void {
  if (error instanceof HttpError && error.status === 401) {
    resetToSignIn()
    alert.value = { kind: 'error', message: t('login.passwordChangeExpired') }
    return
  }
  newPassword.value = ''
  confirmNewPassword.value = ''
  alert.value = { kind: 'error', message: getAuthErrorMessage(error, 'passwordChange') }
}

/**
 * Resolves the logo shown on a provider's sign-in button.
 *
 * @param provider - The public provider.
 * @returns The logo `src`, or `null` when the provider has none.
 */
function providerLogo(provider: IdentityProviderPublic): string | null {
  return resolveProviderLogo(provider.icon, {
    slug: provider.slug,
    iconUploaded: provider.icon_uploaded ?? false,
  })
}

/**
 * Starts an SSO login, surfacing an inline error when initiation fails.
 *
 * @param slug - Provider slug.
 */
async function handleSsoLogin(slug: string): Promise<void> {
  const result = await startSsoLogin(slug)
  if (result.status === 'error') {
    alert.value = { kind: 'error', message: t('login.ssoInitiationError') }
  }
}

/**
 * Surfaces a successful password reset request as a toast.
 *
 * @param message - Localised success message.
 */
function onForgotPasswordSuccess(message: string): void {
  toasts.success(message)
}

/**
 * Surfaces a failed password reset request as a toast (visible above the
 * still-open dialog).
 *
 * @param message - Localised error message.
 */
function onForgotPasswordError(message: string): void {
  toasts.error(message)
}

onMounted(async () => {
  forceLocalLogin.value = shouldForceLocalLogin()
  await load()

  // Navigation/status messages are shown as toasts (out of layout flow) so the
  // card never grows on load; credential errors stay inline (see submitForm).
  // The force-local-login notice is an instruction for the current attempt
  // (not a past event), so it stays inline where the user can keep reading it.
  const initialAlert = resolveInitialAlert()
  if (initialAlert) {
    if (forceLocalLogin.value) {
      alert.value = initialAlert
    } else {
      toasts.notify(initialAlert.kind, initialAlert.message)
    }
  }

  const callback = await processSsoCallback()
  if (callback.status === 'completed') {
    return
  }
  if (callback.status === 'mfa-required') {
    isSsoMfaPending.value = true
    alert.value = { kind: 'info', message: t('login.mfaRequired') }
    return
  }
  if (callback.status === 'error') {
    toasts.error(t(callback.messageKey))
    return
  }

  maybeAutoRedirect(serverSettings.value, ssoProviders.value, forceLocalLogin.value)
})
</script>

<template>
  <AuthScreenLayout :image-url="loginImageUrl" :image-alt="t('login.imageAlt')">
    <form class="mx-auto flex w-full max-w-sm flex-col" novalidate @submit.prevent="submitForm">
      <AppLogo width="40" height="40" class="mx-auto mb-3 size-10" />
      <h1 class="text-center text-page-title">
        {{ config.branding.appName }}
      </h1>

      <!-- Brand tagline on mobile, where the photo and its overlay are hidden. -->
      <div class="mt-3 text-center text-meta text-muted-foreground lg:hidden">
        <p>{{ t('login.tagline1') }}</p>
        <p>{{ t('login.tagline2') }}</p>
      </div>

      <!-- Subtitle on mobile, where the photo and its overlay are hidden. -->
      <p class="mt-2 text-center text-body">
        {{ t('login.subtitle') }}
      </p>

      <Alert v-if="alert" :kind="alert.kind" class="mt-5 whitespace-pre-line">
        {{ alert.message }}
      </Alert>

      <div v-if="showLocalLogin" class="mt-5 flex flex-col gap-3">
        <template v-if="isPasswordChangeStep">
          <div class="flex flex-col gap-1.5">
            <Label for="login-new-password">
              {{ t('login.newPassword') }}
            </Label>
            <PasswordInput
              id="login-new-password"
              v-model="newPassword"
              name="newPassword"
              autocomplete="new-password"
              :aria-invalid="!isNewPasswordValid"
              :disabled="isLoading"
            />
            <PasswordStrengthMeter :password="newPassword" />
            <p class="text-hint">
              {{ passwordHint }}
            </p>
            <p v-if="!isNewPasswordValid" class="text-field-error">
              {{ t('app.password.invalid') }}
            </p>
          </div>

          <div class="flex flex-col gap-1.5">
            <Label for="login-confirm-new-password">
              {{ t('login.confirmNewPassword') }}
            </Label>
            <PasswordInput
              id="login-confirm-new-password"
              v-model="confirmNewPassword"
              name="confirmNewPassword"
              autocomplete="new-password"
              :aria-invalid="confirmError !== undefined"
              :disabled="isLoading"
            />
            <p v-if="confirmError" class="text-field-error">
              {{ confirmError }}
            </p>
          </div>
        </template>

        <template v-else-if="!isMfaStep">
          <div class="flex flex-col gap-1.5">
            <Label for="login-username">
              {{ t('login.username') }}
            </Label>
            <Input
              id="login-username"
              v-model="username"
              name="username"
              type="text"
              autocomplete="username"
              required
              :placeholder="t('login.username')"
              :disabled="isLoading"
            />
          </div>

          <div class="flex flex-col gap-1.5">
            <div class="flex items-center justify-between gap-2">
              <Label for="login-password">
                {{ t('login.password') }}
              </Label>
              <button
                type="button"
                class="text-meta text-muted-foreground hover:text-foreground"
                @click="isForgotPasswordOpen = true"
              >
                {{ t('login.forgotPassword') }}
              </button>
            </div>
            <PasswordInput
              id="login-password"
              v-model="password"
              name="password"
              autocomplete="current-password"
              :placeholder="t('login.password')"
              :disabled="isLoading"
            />
          </div>
        </template>

        <div v-else class="flex flex-col gap-1.5">
          <Label for="login-mfa-code">
            {{ t('login.mfaCode') }}
          </Label>
          <Input
            id="login-mfa-code"
            v-model="mfaCode"
            name="mfaCode"
            type="text"
            autocomplete="one-time-code"
            required
            :disabled="isLoading"
          />
          <p class="text-hint">{{ t('login.mfaCodeHelp') }}</p>
        </div>

        <Button class="w-full" type="submit" :disabled="!canSubmit || isLoading">
          <LoaderCircle v-if="isLoading" class="size-4 animate-spin" aria-hidden="true" />
          <span>{{ isLoading ? statusText : submitText }}</span>
        </Button>

        <RouterLink
          v-if="showSignUpLink"
          :to="{ name: 'signup' }"
          class="self-center text-meta text-muted-foreground hover:text-foreground"
        >
          {{ t('login.signUpLink') }}
        </RouterLink>

        <RouterLink
          v-if="verificationEmailSent"
          :to="{ name: 'sign-up-confirm' }"
          class="self-center text-meta text-muted-foreground hover:text-foreground"
        >
          {{ t('login.resendVerification') }}
        </RouterLink>
      </div>

      <div
        v-if="isSsoLoading"
        class="mt-5 flex items-center justify-center text-meta text-muted-foreground"
      >
        <LoaderCircle class="me-2 size-4 animate-spin" aria-hidden="true" />
        <span>{{ t('login.loadingSsoProviders') }}</span>
      </div>

      <div v-else-if="showSsoProviders" class="mt-5 flex flex-col gap-3">
        <div class="flex items-center gap-3 text-caption">
          <hr class="flex-1 border-border" />
          <span>{{ t('login.ssoSection') }}</span>
          <hr class="flex-1 border-border" />
        </div>

        <Button
          v-for="provider in ssoProviders"
          :key="provider.slug"
          type="button"
          variant="outline"
          class="w-full"
          :aria-label="t('login.ssoButton', { provider: provider.name })"
          @click="handleSsoLogin(provider.slug)"
        >
          <img
            v-if="providerLogo(provider) && !failedLogos.has(provider.slug)"
            :src="providerLogo(provider)!"
            :alt="t('login.ssoLogoAlt', { provider: provider.name })"
            class="h-5 w-auto"
            @error="failedLogos.add(provider.slug)"
          />
          <span>{{ t('login.ssoButton', { provider: provider.name }) }}</span>
        </Button>
      </div>

      <p
        v-if="noLoginMethods"
        class="mt-5 text-center text-meta text-muted-foreground"
        role="status"
      >
        {{ t('login.noLoginMethods') }}
      </p>
    </form>
  </AuthScreenLayout>

  <ForgotPasswordDialog
    v-model:open="isForgotPasswordOpen"
    @success="onForgotPasswordSuccess"
    @error="onForgotPasswordError"
  />
</template>
