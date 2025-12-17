<template>
  <div class="bg-body-tertiary shadow-sm rounded p-3">
    <div class="row justify-content-center align-items-center">
      <div class="col d-none d-lg-block">
        <img
          width="auto"
          height="auto"
          :src="loginPhotoUrl"
          alt="Endurain login illustration"
          class="img-fluid rounded"
        />
      </div>
      <div class="col form-signin text-center m-3">
        <form @submit.prevent="submitForm">
          <h1>Endurain</h1>
          <p class="mb-4">{{ $t('loginView.subtitle') }}</p>

          <!-- Local Login Form (shown when local login is enabled or during MFA) -->
          <template v-if="serverSettings.local_login_enabled || mfaRequired || forceLocalLogin">
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
            <div class="mt-3 text-center" v-if="!mfaRequired && serverSettings.signup_enabled">
              <router-link
                to="/signup"
                class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
              >
                {{ $t('loginView.signUpLink') }}
              </router-link>
            </div>
          </template>

          <!-- SSO Providers Section -->
          <LoadingComponent v-if="loadingSSOProviders" />
          <div
            v-else-if="
              !loadingSSOProviders &&
              !mfaRequired &&
              serverSettings.sso_enabled &&
              ssoProviders.length > 0
            "
            class="mt-4"
          >
            <div class="d-flex align-items-center mb-3">
              <hr class="flex-grow-1" />
              <span class="px-2 text-muted">{{ $t('loginView.ssoSection') }}</span>
              <hr class="flex-grow-1" />
            </div>

            <div v-for="provider in ssoProviders" :key="provider.slug" class="mb-2">
              <button
                type="button"
                class="w-100 btn btn-outline-secondary d-flex align-items-center justify-content-center"
                @click="handleSSOLogin(provider.slug)"
                :aria-label="$t('loginView.ssoButton', { provider: provider.name })"
              >
                <!-- Custom logo if available -->
                <img
                  v-if="getProviderCustomLogo(provider.icon)"
                  :src="getProviderCustomLogo(provider.icon)!"
                  :alt="`${provider.name} logo`"
                  class="me-2"
                  style="height: 1.25rem; width: auto"
                />
                {{ $t('loginView.ssoButton', { provider: provider.name }) }}
              </button>
            </div>
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'
import { useAuthStore } from '@/stores/authStore'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { session } from '@/services/sessionService'
import { passwordReset } from '@/services/passwordResetService'
import { profile } from '@/services/profileService'
import { identityProviders } from '@/services/identityProvidersService'
import ModalComponentEmailInput from '@/components/Modals/ModalComponentEmailInput.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import { useBootstrapModal } from '@/composables/useBootstrapModal'
import type {
  RouteQueryHandlers,
  LoginResponse,
  TokenExchangeResponse,
  ErrorWithResponse,
  SSOProvider
} from '@/types'
import { HTTP_STATUS, QUERY_PARAM_TRUE, extractStatusCode } from '@/constants/httpConstants'
import { PROVIDER_CUSTOM_LOGO_MAP } from '@/constants/ssoConstants'
import { isNotEmpty, sanitizeInput } from '@/utils/validationUtils'
import { generateCodeVerifier, generateCodeChallenge } from '@/utils/pkceUtils'
import defaultLoginImage from '@/assets/login.png'

/**
 * Maps URL query parameters to notification types and i18n translation keys.
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
  verifyEmailInvalidLink: { type: 'error', key: 'loginView.verifyEmailInvalidLink' },
  forceLocalLogin: { type: 'info', key: 'loginView.forceLocalLogin' },
  redirect: { type: 'info', key: '' } // Special handling below
} as const

const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const authStore = useAuthStore()
const serverSettingsStore = useServerSettingsStore()

const forgotPasswordModalRef = ref<typeof ModalComponentEmailInput | null>(null)
const {
  initializeModal,
  showModal: showForgotModal,
  hideModal: hideForgotModal,
  disposeModal
} = useBootstrapModal()
const forgotPasswordLoading = ref(false)

const username = ref('')
const password = ref('')
const mfaCode = ref('')
const mfaRequired = ref(false)
const loading = ref(false)
const pendingUsername = ref('')
const showPassword = ref(false)

const ssoProviders = ref<SSOProvider[]>([])
const loadingSSOProviders = ref(true)

const forceLocalLogin = ref(false)

const redirectTo = ref('')

/**
 * Computed reference to server settings from the store.
 *
 * @returns The current server settings object.
 */
const serverSettings = computed(() => serverSettingsStore.serverSettings)

/**
 * Computes the login photo URL based on server settings.
 *
 * @returns The URL of the custom login photo or default image.
 */
const loginPhotoUrl = computed<string>(() =>
  serverSettings.value.login_photo_set
    ? `${window.env.ENDURAIN_HOST}/server_images/login.png`
    : defaultLoginImage
)

/**
 * Shows the forgot password modal.
 *
 * @returns void
 */
const showForgotPasswordModal = (): void => {
  showForgotModal()
}

/**
 * Toggles the visibility of the password field.
 *
 * @returns void
 */
const togglePasswordVisibility = (): void => {
  showPassword.value = !showPassword.value
}

/**
 * Handles form submission by routing to either standard login or MFA verification.
 *
 * @returns A promise that resolves when submission is complete.
 */
const submitForm = async (): Promise<void> => {
  if (mfaRequired.value) {
    await submitMFAVerification()
  } else {
    await submitLogin()
  }
}

/**
 * Handles standard username/password login authentication.
 *
 * @returns A promise that resolves when login attempt is complete.
 * @throws {ErrorWithResponse} When authentication fails.
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

    // Complete login if no MFA required (pass full response for token extraction)
    await completeLogin(response)
  } catch (error) {
    handleLoginError(error as ErrorWithResponse)
  } finally {
    loading.value = false
  }
}

/**
 * Handles multi-factor authentication verification.
 *
 * @returns A promise that resolves when MFA verification is complete.
 * @throws {ErrorWithResponse} When MFA verification fails.
 */
const submitMFAVerification = async (): Promise<void> => {
  try {
    loading.value = true
    const response = (await session.verifyMFAAndLogin({
      username: pendingUsername.value,
      mfa_code: mfaCode.value
    })) as LoginResponse

    // Complete login (pass full response for token extraction)
    await completeLogin(response)
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
 * Completes the login process after successful authentication.
 *
 * OAuth 2.1: Extracts access_token and csrf_token from response body and stores
 * them in authStore (in-memory) for secure token management.
 *
 * @param response - The authentication response containing session_id, access_token, and csrf_token.
 * @returns A promise that resolves when login completion and redirect are done.
 * @throws {Error} When profile fetch or navigation fails.
 */
const completeLogin = async (response: LoginResponse): Promise<void> => {
  // OAuth 2.1: Store tokens in memory (same pattern as SSO)
  if (response.access_token) {
    authStore.setAccessToken(response.access_token)
  }
  if (response.csrf_token) {
    authStore.setCsrfToken(response.csrf_token)
  }

  // Get logged user information
  const userProfile = await profile.getProfileInfo()

  // Store the user in the auth store
  authStore.setUser(userProfile, response.session_id, locale)

  // Redirect to the home page
  if (isNotEmpty(redirectTo.value)) {
    await router.push(redirectTo.value)
  } else {
    await router.push('/')
  }
}

/**
 * Handles login errors and displays appropriate user-friendly messages.
 *
 * @param error - The error object from authentication attempt.
 * @returns void
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

/**
 * Handles forgot password form submission.
 *
 * @param email - The user's email address for password reset.
 * @returns A promise that resolves when the reset request is complete.
 * @throws {Error} When the password reset request fails.
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

/**
 * Fetches enabled SSO providers from the API.
 *
 * @returns A promise that resolves when providers are fetched.
 */
const fetchSSOProviders = async (): Promise<void> => {
  if (!serverSettings.value.sso_enabled) {
    loadingSSOProviders.value = false
    return
  }

  try {
    ssoProviders.value = await identityProviders.getEnabledProviders()
  } catch (error) {
    ssoProviders.value = []
  } finally {
    loadingSSOProviders.value = false
  }
}

/**
 * Gets the custom logo path for an SSO provider.
 *
 * @param iconName - The provider icon name.
 * @returns The custom logo path or `null` if not available.
 */
const getProviderCustomLogo = (iconName?: string): string | null => {
  if (!iconName) return null
  const logoPath =
    PROVIDER_CUSTOM_LOGO_MAP[iconName.toLowerCase() as keyof typeof PROVIDER_CUSTOM_LOGO_MAP]
  return logoPath || null
}

/**
 * Initiates SSO login for the specified provider with PKCE.
 * Generates code verifier and challenge, stores verifier in sessionStorage,
 * and redirects to the backend OAuth endpoint with PKCE parameters.
 *
 * @param slug - The provider slug identifier.
 * @returns A promise that resolves when PKCE generation and redirect are complete.
 */
const handleSSOLogin = async (slug: string): Promise<void> => {
  try {
    // Generate PKCE verifier and challenge
    const codeVerifier = await generateCodeVerifier()
    const codeChallenge = await generateCodeChallenge(codeVerifier)

    // Store verifier in sessionStorage for callback handler
    // Key includes slug to support multiple simultaneous SSO flows
    sessionStorage.setItem(`pkce_verifier_${slug}`, codeVerifier)

    // Build redirect URL with PKCE parameters
    let params = `?code_challenge=${encodeURIComponent(codeChallenge)}&code_challenge_method=S256`

    // Add redirect parameter if present
    if (isNotEmpty(redirectTo.value)) {
      params += `&redirect=${encodeURIComponent(redirectTo.value)}`
    }

    // Redirect to backend SSO endpoint
    identityProviders.initiateLogin(slug, params)
  } catch (error) {
    push.error(t('loginView.ssoInitiationError'))
    console.error('Failed to initiate SSO login:', error)
  }
}

/**
 * Checks if SSO auto-redirect should occur and redirects if conditions are met.
 *
 * @returns void
 */
const checkSSOAutoRedirect = (): void => {
  if (
    serverSettings.value.sso_enabled &&
    serverSettings.value.sso_auto_redirect &&
    !serverSettings.value.local_login_enabled &&
    ssoProviders.value.length === 1 &&
    !forceLocalLogin.value
  ) {
    const provider = ssoProviders.value[0]
    if (provider) {
      handleSSOLogin(provider.slug)
    }
  }
}

/**
 * Processes SSO callback query parameters and handles success or error states.
 * For successful SSO, exchanges the session_id and PKCE code_verifier for JWT tokens.
 *
 * @returns A promise that resolves when callback processing is complete.
 */
const processSSOCallback = async (): Promise<void> => {
  // Handle SSO success with PKCE token exchange
  if (route.query.sso === 'success' && route.query.session_id) {
    try {
      const sessionId = Array.isArray(route.query.session_id)
        ? route.query.session_id[0]
        : route.query.session_id

      if (typeof sessionId !== 'string') {
        throw new Error('Invalid session_id format')
      }

      // Extract IdP slug from URL to retrieve correct PKCE verifier
      // The IdP slug should be stored when initiating login, or we can try to find any stored verifier
      // For now, we'll search for any pkce_verifier_* key in sessionStorage
      let codeVerifier: string | null = null
      let verifierKey: string | null = null

      // Search for PKCE verifier in sessionStorage
      for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i)
        if (key && key.startsWith('pkce_verifier_')) {
          codeVerifier = sessionStorage.getItem(key)
          verifierKey = key
          break
        }
      }

      if (!codeVerifier || !verifierKey) {
        throw new Error('PKCE code verifier not found in session storage')
      }

      // Exchange session_id + code_verifier for tokens
      const tokenData: TokenExchangeResponse = await identityProviders.exchangeSessionForTokens(
        sessionId,
        codeVerifier
      )

      // Clear PKCE verifier from sessionStorage
      sessionStorage.removeItem(verifierKey)

      // Convert to LoginResponse format for completeLogin
      const loginResponse: LoginResponse = {
        session_id: tokenData.session_id,
        access_token: tokenData.access_token,
        csrf_token: tokenData.csrf_token,
        token_type: tokenData.token_type,
        expires_in: tokenData.expires_in
      }

      // Complete login (stores tokens in auth store and fetches profile)
      await completeLogin(loginResponse)

      push.success(t('loginView.ssoSuccess'))
    } catch (error) {
      console.error('SSO token exchange failed:', error)
      push.error(t('loginView.ssoTokenExchangeFailed'))

      // Clear any remaining PKCE verifiers
      for (let i = sessionStorage.length - 1; i >= 0; i--) {
        const key = sessionStorage.key(i)
        if (key && key.startsWith('pkce_verifier_')) {
          sessionStorage.removeItem(key)
        }
      }
    }
    return
  }

  // Handle SSO errors
  if (route.query.error) {
    const errorType = route.query.error as string
    switch (errorType) {
      case 'sso_failed':
        push.error(t('loginView.ssoFailed'))
        break
      case 'sso_cancelled':
        push.info(t('loginView.ssoCancelled'))
        break
      case 'sso_account_not_found':
        push.error(t('loginView.ssoAccountNotFound'))
        break
      case 'sso_account_disabled':
        push.error(t('loginView.ssoAccountDisabled'))
        break
      case 'sso_auto_create_disabled':
        push.error(t('loginView.ssoAutoCreateDisabled'))
        break
      default:
        push.error(t('loginView.ssoErrorUndefined'))
    }
  }
}

/**
 * Processes route query parameters and displays appropriate notifications.
 *
 * @returns A promise that resolves when all query parameters are processed.
 */
const processRouteQueryParameters = async (): Promise<void> => {
  Object.entries(ROUTE_QUERY_HANDLERS).forEach(([param, config]) => {
    if (route.query[param] === QUERY_PARAM_TRUE) {
      push[config.type](t(config.key))
    }
    if (param === 'forceLocalLogin' && route.query[param] === QUERY_PARAM_TRUE) {
      forceLocalLogin.value = true
    }
    if (param === 'redirect') {
      const redirectValue = route.query[param]
      if (typeof redirectValue === 'string' && isNotEmpty(redirectValue)) {
        redirectTo.value = redirectValue
      }
    }
  })

  await processSSOCallback()
}

/**
 * Lifecycle hook that runs when the component is mounted.
 * Initializes modal, fetches SSO providers, processes route parameters, and checks for auto-redirect.
 *
 * @returns A promise that resolves when initialization is complete.
 */
onMounted(async () => {
  await initializeModal(forgotPasswordModalRef)
  await fetchSSOProviders()
  await processRouteQueryParameters()
  checkSSOAutoRedirect()
})

/**
 * Lifecycle hook that runs when the component is unmounted.
 * Cleans up modal resources.
 *
 * @returns void
 */
onUnmounted(() => {
  disposeModal()
})
</script>
