<template>
  <div class="bg-body-tertiary shadow-sm rounded p-3">
    <div class="row justify-content-center align-items-center">
      <div class="col d-none d-lg-block">
        <img
          width="auto"
          height="auto"
          :src="loginPhotoUrl"
          alt="Endurain reset password illustration"
          class="img-fluid rounded"
        />
      </div>
      <div class="col form-signin m-3">
        <form @submit.prevent="submitResetForm">
          <h1 class="mb-3">{{ $t('resetPassword.title') }}</h1>

          <!-- New password field -->
          <div class="form-floating mb-3 position-relative">
            <input
              :type="showNewPassword ? 'text' : 'password'"
              class="form-control"
              id="newPassword"
              name="newPassword"
              :placeholder="$t('resetPassword.newPasswordLabel')"
              :class="{ 'is-invalid': !isNewPasswordValid && newPassword }"
              v-model="newPassword"
              required
            />
            <label for="newPassword">* {{ $t('resetPassword.newPasswordLabel') }}</label>
            <button
              type="button"
              class="btn position-absolute top-50 end-0 translate-middle-y"
              :class="{ 'me-4': !isNewPasswordValid && newPassword }"
              :aria-label="
                showNewPassword ? $t('loginView.hidePassword') : $t('loginView.showPassword')
              "
              @click="toggleNewPasswordVisibility"
            >
              <font-awesome-icon :icon="showNewPassword ? ['fas', 'eye-slash'] : ['fas', 'eye']" />
            </button>
          </div>
          <div
            v-if="!isNewPasswordValid && newPassword"
            class="invalid-feedback d-block mb-3"
            aria-live="polite"
          >
            {{ $t('resetPassword.passwordComplexityError') }}
          </div>

          <!-- Confirm password field -->
          <div class="form-floating mb-3 position-relative">
            <input
              :type="showConfirmPassword ? 'text' : 'password'"
              class="form-control"
              id="confirmPassword"
              name="confirmPassword"
              :placeholder="$t('resetPassword.confirmPasswordLabel')"
              :class="{ 'is-invalid': !isPasswordMatch && confirmPassword }"
              v-model="confirmPassword"
              required
            />
            <label for="confirmPassword">* {{ $t('resetPassword.confirmPasswordLabel') }}</label>
            <button
              type="button"
              class="btn position-absolute top-50 end-0 translate-middle-y"
              :class="{ 'me-4': !isPasswordMatch && confirmPassword }"
              :aria-label="
                showConfirmPassword ? $t('loginView.hidePassword') : $t('loginView.showPassword')
              "
              @click="toggleConfirmPasswordVisibility"
            >
              <font-awesome-icon
                :icon="showConfirmPassword ? ['fas', 'eye-slash'] : ['fas', 'eye']"
              />
            </button>
          </div>
          <div
            v-if="!isPasswordMatch && confirmPassword"
            class="invalid-feedback d-block mb-3"
            aria-live="polite"
          >
            {{ $t('resetPassword.passwordMismatchError') }}
          </div>

          <!-- Required fields note -->
          <p class="text-muted small mb-3">* {{ $t('generalItems.requiredField') }}</p>

          <!-- Submit button -->
          <button
            class="w-100 btn btn-lg btn-primary"
            type="submit"
            :disabled="!isNewPasswordValid || !isPasswordMatch || resetLoading"
          >
            <span
              v-if="resetLoading"
              class="spinner-border spinner-border-sm me-2"
              role="status"
              aria-hidden="true"
            ></span>
            {{ $t('resetPassword.submitButton') }}
          </button>

          <!-- Back to login link -->
          <div class="mt-3 text-center">
            <router-link
              to="/login"
              class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
            >
              {{ $t('resetPassword.backToLogin') }}
            </router-link>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * @fileoverview Password Reset View Component
 *
 * Provides a secure password reset interface for users who have requested
 * a password reset via email. Validates the reset token, enforces password
 * complexity requirements, and handles the password update process.
 *
 * Features:
 * - Token validation from URL query parameters
 * - Password complexity validation (uppercase, digit, special char, min 8 chars)
 * - Password confirmation matching
 * - Password visibility toggle
 * - Centralized validation using validationUtils
 * - Error handling with user-friendly messages
 * - Automatic redirect on success/invalid token
 *
 * Security:
 * - Validates token server-side
 * - Enforces strong password requirements
 * - Single-use tokens with expiration
 * - No password exposure in URLs or logs
 *
 * Related Components:
 * - LoginView (redirect destination)
 * - ModalComponentEmailInput (forgot password request)
 *
 * @component
 * @example
 * // URL with token: /reset-password?token=abc123...
 * <ResetPasswordView />
 */

// ============================================================================
// Imports
// ============================================================================
import { ref, computed, onMounted, type Ref, type ComputedRef } from 'vue'
import { useRoute, useRouter, type Router, type RouteLocationNormalizedLoaded } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { passwordReset } from '@/services/passwordResetService'
import { isValidPassword, passwordsMatch, buildPasswordRequirements } from '@/utils/validationUtils'
import { HTTP_STATUS, extractStatusCode } from '@/constants/httpConstants'
import type { ErrorWithResponse } from '@/types'
import defaultLoginImage from '@/assets/login.png'

// ============================================================================
// Composables & Stores
// ============================================================================
const route: RouteLocationNormalizedLoaded = useRoute()
const router: Router = useRouter()
const { t } = useI18n()
const serverSettingsStore = useServerSettingsStore()

// ============================================================================
// Reactive State
// ============================================================================

// Form fields
const newPassword: Ref<string> = ref('')
const confirmPassword: Ref<string> = ref('')

// UI state
const showNewPassword: Ref<boolean> = ref(false)
const showConfirmPassword: Ref<boolean> = ref(false)
const resetLoading: Ref<boolean> = ref(false)

// Token from URL query parameter
const token: Ref<string | undefined> = ref(route.query.token as string | undefined)

// ============================================================================
// Computed Properties
// ============================================================================

/**
 * Compute the login photo URL from server settings
 * Returns custom photo from server if set, otherwise default image
 */
const loginPhotoUrl: ComputedRef<string> = computed(() => {
  return serverSettingsStore.serverSettings.login_photo_set
    ? `${window.env.ENDURAIN_HOST}/server_images/login.png`
    : defaultLoginImage
})

/**
 * Validate new password against server-configured requirements.
 * Applies password policy from server settings.
 *
 * Returns true if field is empty (not yet touched) to avoid showing
 * errors before user interaction.
 */
const isNewPasswordValid: ComputedRef<boolean> = computed(() => {
  if (!newPassword.value) return true

  const passwordType = serverSettingsStore.serverSettings.password_type
  const minLength = serverSettingsStore.serverSettings.password_length_admin_users
  const requirements = buildPasswordRequirements(passwordType, minLength)

  return isValidPassword(newPassword.value, requirements)
})

/**
 * Validate password confirmation matches new password
 * Returns true if field is empty (not yet touched) to avoid showing
 * errors before user interaction
 */
const isPasswordMatch: ComputedRef<boolean> = computed(() => {
  if (!confirmPassword.value) return true
  return passwordsMatch(newPassword.value, confirmPassword.value)
})

// ============================================================================
// UI Interaction Handlers
// ============================================================================

/**
 * Toggle new password field visibility
 * Toggles between 'text' and 'password' input types
 */
const toggleNewPasswordVisibility = (): void => {
  showNewPassword.value = !showNewPassword.value
}

/**
 * Toggle confirm password field visibility
 * Toggles between 'text' and 'password' input types
 */
const toggleConfirmPasswordVisibility = (): void => {
  showConfirmPassword.value = !showConfirmPassword.value
}

// ============================================================================
// Password Reset Logic
// ============================================================================

/**
 * Submit password reset form
 *
 * Process:
 * 1. Validate password complexity and matching
 * 2. Send reset request with token and new password
 * 3. Handle success: redirect to login with success message
 * 4. Handle errors: display appropriate error messages
 *
 * Error Handling:
 * - 400: Invalid or expired token
 * - Other: Generic error with details
 *
 * @async
 * @throws {Error} Network or validation errors
 */
const submitResetForm = async (): Promise<void> => {
  // Validate before submission
  if (!isNewPasswordValid.value || !isPasswordMatch.value) {
    return
  }

  // Validate token presence
  if (!token.value) {
    push.error(t('resetPassword.invalidOrExpiredToken'))
    router.push('/login?passwordResetInvalidLink=true')
    return
  }

  resetLoading.value = true

  try {
    await passwordReset.confirmPasswordReset({
      token: token.value,
      new_password: newPassword.value
    })

    // Success: redirect to login
    router.push('/login?passwordResetSuccess=true')
  } catch (error) {
    const statusCode = extractStatusCode(error as ErrorWithResponse)

    if (statusCode === HTTP_STATUS.BAD_REQUEST) {
      push.error(t('resetPassword.invalidOrExpiredToken'))
    } else {
      push.error(`${t('resetPassword.resetError')} - ${error}`)
    }
  } finally {
    resetLoading.value = false
  }
}

// ============================================================================
// Lifecycle Hooks
// ============================================================================

/**
 * Component mount lifecycle hook
 *
 * Validates that a reset token is present in the URL
 * If no token is found, redirects to login with error message
 *
 * This prevents users from accessing the reset form without a valid
 * token link from their email
 */
onMounted(() => {
  if (!token.value) {
    push.error(t('resetPassword.invalidOrExpiredToken'))
    router.push('/login?passwordResetInvalidLink=true')
  }
})
</script>
