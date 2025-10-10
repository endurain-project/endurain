<template>
  <div class="bg-body-tertiary shadow-sm rounded p-3">
    <div class="row justify-content-center align-items-center">
      <div class="col d-none d-lg-block">
        <img
          width="auto"
          height="auto"
          :src="loginPhotoUrl || '/src/assets/login.png'"
          alt="Endurain login illustration"
          class="img-fluid rounded"
        />
      </div>
      <div class="col form-signin text-center m-3">
        <form @submit.prevent="submitForm">
          <h1>Endurain</h1>
          <p class="mb-4">{{ $t('loginView.subtitle') }}</p>

          <div class="form-floating mb-3" v-if="!mfaRequired">
            <input
              type="text"
              class="form-control"
              id="loginUsername"
              name="loginUsername"
              :placeholder="$t('loginView.username')"
              v-model="username"
              required
            />
            <label for="loginUsername">{{ $t('loginView.username') }}</label>
          </div>
          <div class="form-floating position-relative mb-3" v-if="!mfaRequired">
            <input
              :type="showPassword ? 'text' : 'password'"
              class="form-control"
              id="loginPassword"
              name="loginPassword"
              :placeholder="$t('loginView.password')"
              v-model="password"
              required
            />
            <label for="loginPassword">{{ $t('loginView.password') }}</label>
            <button
              type="button"
              class="btn position-absolute top-50 end-0 translate-middle-y me-2"
              :aria-label="
                showPassword ? $t('loginView.hidePassword') : $t('loginView.showPassword')
              "
              @click="togglePasswordVisibility"
            >
              <font-awesome-icon :icon="showPassword ? ['fas', 'eye-slash'] : ['fas', 'eye']" />
            </button>
          </div>

          <!-- MFA input field (shown when MFA is required) -->
          <div v-if="mfaRequired" class="form-floating mb-3">
            <input
              type="text"
              class="form-control"
              id="mfaCode"
              name="mfaCode"
              :placeholder="$t('loginView.mfaCode')"
              v-model="mfaCode"
              required
              autocomplete="one-time-code"
            />
            <label for="mfaCode">{{ $t('loginView.mfaCode') }}</label>
          </div>

          <button class="w-100 btn btn-lg btn-primary" type="submit" :disabled="loading">
            <span
              v-if="loading"
              class="spinner-border spinner-border-sm me-2"
              role="status"
              aria-hidden="true"
            ></span>
            {{ mfaRequired ? $t('loginView.verifyMFAButton') : $t('loginView.signInButton') }}
          </button>
          <div class="mt-3 text-center" v-if="!mfaRequired">
            <a
              href="#"
              @click.prevent="showForgotPasswordModal"
              class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
            >
              {{ $t('loginView.forgotPassword') }}
            </a>
          </div>
          <div
            class="mt-3 text-center"
            v-if="!mfaRequired && serverSettingsStore.serverSettings.signup_enabled"
          >
            <router-link
              to="/signup"
              class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
            >
              {{ $t('loginView.signUpLink') }}
            </router-link>
          </div>
        </form>
      </div>
    </div>
  </div>

  <!-- Forgot Password Modal -->
  <ModalComponentEmailInput
    ref="forgotPasswordModalRef"
    modal-id="forgotPasswordModal"
    :title="$t('loginView.forgotPasswordModalTitle')"
    :email-field-label="$t('loginView.forgotPasswordModalEmailLabel')"
    :email-help-text="$t('loginView.forgotPasswordModalEmailHelp')"
    action-button-type="success"
    :action-button-text="$t('loginView.forgotPasswordModalSubmitButton')"
    :is-loading="forgotPasswordLoading"
    @emailToEmitAction="handleForgotPasswordSubmit"
  />
</template>

<script setup lang="ts">
/**
 * LoginView Component
 *
 * Handles user authentication with support for:
 * - Standard username/password login
 * - Multi-Factor Authentication (MFA)
 * - Password reset functionality
 * - Route-based notification handling
 *
 * @component
 */

// Vue composition API
import { ref, computed, onMounted, onUnmounted, type Ref, type ComputedRef } from 'vue'
// Router
import { useRoute, useRouter } from 'vue-router'
// Internationalization
import { useI18n } from 'vue-i18n'
// Notifications
import { push } from 'notivue'
// Stores
import { useAuthStore } from '@/stores/authStore'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
// Services
import { session } from '@/services/sessionService'
import { passwordReset } from '@/services/passwordResetService'
import { profile } from '@/services/profileService'
// Components
import ModalComponentEmailInput from '@/components/Modals/ModalComponentEmailInput.vue'
// Composables
import { useBootstrapModal } from '@/composables/useBootstrapModal'
// Types
import type { RouteQueryHandlers, LoginResponse, ErrorWithResponse } from '@/types'
// Constants
import { HTTP_STATUS, QUERY_PARAM_TRUE, extractStatusCode } from '@/constants/httpConstants'
// Utils
import { isNotEmpty, sanitizeInput } from '@/utils/validationUtils'

/**
 * Route query parameter handlers configuration
 * Maps URL query parameters to notification types and i18n keys
 */
const ROUTE_QUERY_HANDLERS: RouteQueryHandlers = {
  sessionExpired: { type: 'warning', key: 'loginView.sessionExpired' },
  logoutSuccess: { type: 'success', key: 'loginView.logoutSuccess' },
  errorPublicActivityNotFound: { type: 'error', key: 'loginView.errorPublicActivityNotFound' },
  errorpublic_shareable_links: { type: 'error', key: 'loginView.errorPublic_shareable_links' },
  passwordResetSuccess: { type: 'success', key: 'loginView.passwordResetSuccess' },
  passwordResetInvalidLink: { type: 'error', key: 'loginView.passwordResetInvalidLink' },
  emailVerificationSent: { type: 'info', key: 'loginView.emailVerificationSent' },
  adminApprovalRequired: { type: 'info', key: 'loginView.adminApprovalRequired' },
  verifyEmailInvalidLink: { type: 'error', key: 'loginView.verifyEmailInvalidLink' }
} as const

// ============================================================================
// Composables & Store Initialization
// ============================================================================

const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const authStore = useAuthStore()
const serverSettingsStore = useServerSettingsStore()

// ============================================================================
// Modal Management
// ============================================================================

const forgotPasswordModalRef: Ref<typeof ModalComponentEmailInput | null> = ref(null)
const {
  initializeModal,
  showModal: showForgotModal,
  hideModal: hideForgotModal,
  disposeModal
} = useBootstrapModal()
const forgotPasswordLoading: Ref<boolean> = ref(false)

// ============================================================================
// Form State
// ============================================================================

const username: Ref<string> = ref('')
const password: Ref<string> = ref('')
const mfaCode: Ref<string> = ref('')
const mfaRequired: Ref<boolean> = ref(false)
const loading: Ref<boolean> = ref(false)
const pendingUsername: Ref<string> = ref('')
const showPassword: Ref<boolean> = ref(false)

// ============================================================================
// Computed Properties
// ============================================================================

/**
 * Compute the login photo URL from server settings
 * Returns null if no custom photo is set, triggering fallback to default
 */
const loginPhotoUrl: ComputedRef<string | null> = computed(() => {
  return serverSettingsStore.serverSettings.login_photo_set
    ? `${window.env.ENDURAIN_HOST}/server_images/login.png`
    : null
})

// ============================================================================
// UI Interaction Handlers
// ============================================================================

/**
 * Show the forgot password modal
 */
const showForgotPasswordModal = (): void => {
  showForgotModal()
}

/**
 * Toggle password field visibility
 */
const togglePasswordVisibility = (): void => {
  showPassword.value = !showPassword.value
}

// ============================================================================
// Authentication Logic
// ============================================================================

/**
 * Main form submission handler
 * Routes to either MFA verification or standard login based on state
 */
const submitForm = async (): Promise<void> => {
  if (mfaRequired.value) {
    await submitMFAVerification()
  } else {
    await submitLogin()
  }
}

/**
 * Handle standard username/password login
 * Initiates authentication and checks for MFA requirement
 */
const submitLogin = async (): Promise<void> => {
  // Create the form data
  const formData = new URLSearchParams()
  formData.append('grant_type', 'password')
  formData.append('username', username.value)
  formData.append('password', password.value)

  try {
    loading.value = true
    // Get the token
    const response = (await session.authenticateUser(formData)) as LoginResponse

    // Check if MFA is required
    if (response && response.mfa_required) {
      mfaRequired.value = true
      pendingUsername.value = response.username || ''
      push.info(t('loginView.mfaRequired'))
      return
    }

    // Complete login if no MFA required
    await completeLogin(response.session_id)
  } catch (error) {
    handleLoginError(error as ErrorWithResponse)
  } finally {
    loading.value = false
  }
}

/**
 * Handle Multi-Factor Authentication verification
 * Validates MFA code and completes login if successful
 */
const submitMFAVerification = async (): Promise<void> => {
  try {
    loading.value = true
    const response = (await session.verifyMFAAndLogin({
      username: pendingUsername.value,
      mfa_code: mfaCode.value
    })) as LoginResponse

    await completeLogin(response.session_id)
  } catch (error) {
    const statusCode = extractStatusCode(error)

    if (statusCode === HTTP_STATUS.UNAUTHORIZED || statusCode === HTTP_STATUS.BAD_REQUEST) {
      push.error(t('loginView.invalidMFACode'))
    } else {
      handleLoginError(error as ErrorWithResponse)
    }
  } finally {
    loading.value = false
  }
}

/**
 * Complete the login process after successful authentication
 * Fetches user profile, updates auth store, and redirects to home
 *
 * @param session_id - Session identifier from authentication response
 */
const completeLogin = async (session_id: string): Promise<void> => {
  // Get logged user information
  const userProfile = await profile.getProfileInfo()

  // Store the user in the auth store
  authStore.setUser(userProfile, session_id, locale)

  // Redirect to the home page
  await router.push('/')
}

// ============================================================================
// Error Handling
// ============================================================================

/**
 * Handle login errors with appropriate user feedback
 * Maps HTTP status codes to localized error messages
 *
 * @param error - Error object from authentication attempt
 */
const handleLoginError = (error: ErrorWithResponse): void => {
  const statusCode = extractStatusCode(error)

  switch (statusCode) {
    case HTTP_STATUS.UNAUTHORIZED:
      push.error(`${t('loginView.error401')} - ${error}`)
      break
    case HTTP_STATUS.FORBIDDEN:
      push.error(`${t('loginView.error403')} - ${error}`)
      break
    case HTTP_STATUS.INTERNAL_SERVER_ERROR:
      push.error(`${t('loginView.error500')} - ${error}`)
      break
    default:
      push.error(`${t('loginView.errorUndefined')} - ${error}`)
  }
}

// ============================================================================
// Password Reset Logic
// ============================================================================

/**
 * Handle forgot password form submission
 * Validates email and sends password reset request
 *
 * @param email - User's email address for password reset
 */
const handleForgotPasswordSubmit = async (email: string): Promise<void> => {
  // Validate email input
  const sanitizedEmail = sanitizeInput(email)
  if (!isNotEmpty(sanitizedEmail)) {
    push.error(t('loginView.forgotPasswordModalEmailRequired'))
    return
  }

  forgotPasswordLoading.value = true

  try {
    await passwordReset.requestPasswordReset({ email: sanitizedEmail })
    push.success(t('loginView.forgotPasswordModalRequestSuccess'))
  } catch (error) {
    const statusCode = extractStatusCode(error)

    if (statusCode === HTTP_STATUS.INTERNAL_SERVER_ERROR) {
      push.error(t('loginView.forgotPasswordModalUnableToSendEmail'))
    } else if (statusCode === HTTP_STATUS.SERVICE_UNAVAILABLE) {
      push.error(t('loginView.forgotPasswordModalEmailNotConfigured'))
    } else {
      push.error(`${t('loginView.forgotPasswordModalRequestError')} - ${error}`)
    }
  } finally {
    forgotPasswordLoading.value = false
    hideForgotModal()
  }
}

// ============================================================================
// Route & Notification Handling
// ============================================================================

/**
 * Process route query parameters and display appropriate notifications
 * Checks for specific query parameters and shows corresponding messages
 */
const processRouteQueryParameters = (): void => {
  Object.entries(ROUTE_QUERY_HANDLERS).forEach(([param, config]) => {
    if (route.query[param] === QUERY_PARAM_TRUE) {
      push[config.type](t(config.key))
    }
  })
}

// ============================================================================
// Lifecycle Hooks
// ============================================================================

/**
 * Component mounted lifecycle hook
 * Initializes modal and processes route parameters
 */
onMounted(async () => {
  // Initialize forgot password modal
  await initializeModal(forgotPasswordModalRef)

  // Process any route query parameters for notifications
  processRouteQueryParameters()
})

/**
 * Component unmounted lifecycle hook
 * Cleanup modal resources
 */
onUnmounted(() => {
  disposeModal()
})
</script>
