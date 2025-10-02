<template>
  <div class="bg-body-tertiary shadow-sm rounded p-3">
    <div class="row justify-content-center align-items-center">
      <div class="col d-none d-lg-block">
        <img
          width="auto"
          height="auto"
          :src="loginPhotoUrl"
          alt="Square login image"
          class="img-fluid rounded"
          v-if="serverSettingsStore.serverSettings.login_photo_set"
        />
        <img
          width="auto"
          height="auto"
          src="/src/assets/login.png"
          alt="Square login image"
          class="img-fluid rounded"
          v-else
        />
      </div>
      <div class="col form-signin text-center m-3">
        <form @submit.prevent="submitForm">
          <h1>Endurain</h1>
          <p>{{ $t('loginView.subtitle') }}</p>
          <br />

          <div class="form-floating" v-if="!mfaRequired">
            <input
              type="text"
              class="form-control"
              id="floatingInput"
              name="loginUsername"
              :placeholder="$t('loginView.username')"
              v-model="username"
              required
            />
            <label for="loginUsername">{{ $t('loginView.username') }}</label>
          </div>
          <br />
          <div class="form-floating position-relative" v-if="!mfaRequired">
            <input
              :type="showPassword ? 'text' : 'password'"
              class="form-control"
              name="loginPassword"
              :placeholder="$t('loginView.password')"
              v-model="password"
              required
            />
            <label for="loginPassword">{{ $t('loginView.password') }}</label>
            <button
              type="button"
              class="btn position-absolute top-50 end-0 translate-middle-y me-2"
              @click="togglePasswordVisibility"
            >
              <font-awesome-icon :icon="showPassword ? ['fas', 'eye-slash'] : ['fas', 'eye']" />
            </button>
          </div>
          <br v-if="!mfaRequired" />

          <!-- MFA input field (shown when MFA is required) -->
          <div v-if="mfaRequired" class="form-floating">
            <input
              type="text"
              class="form-control"
              id="mfaCode"
              name="mfaCode"
              :placeholder="$t('loginView.mfaCode')"
              v-model="mfaCode"
              required
            />
            <label for="mfaCode">{{ $t('loginView.mfaCode') }}</label>
          </div>
          <br v-if="mfaRequired" />

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
              {{ $t('loginView.forgotPassword') }}{{ $t('generalItems.betaTag') }}
            </a>
          </div>
          <!--<div>
						<hr>
						<button class="w-100 btn btn-lg btn-warning disabled" type="submit">{{ $t("loginView.signUpButton") }}</button>
					</div>-->
        </form>
      </div>
    </div>
  </div>

  <!-- Forgot Password Modal -->
  <ModalComponentEmailInput
    ref="forgotPasswordModalRef"
    modal-id="forgotPasswordModal"
    :title="$t('loginView.forgotPasswordModalTitle') + $t('generalItems.betaTag')"
    :email-field-label="$t('loginView.forgotPasswordModalEmailLabel')"
    :email-help-text="$t('loginView.forgotPasswordModalEmailHelp')"
    action-button-type="success"
    :action-button-text="$t('loginView.forgotPasswordModalSubmitButton')"
    :is-loading="forgotPasswordLoading"
    @emailToEmitAction="handleForgotPasswordSubmit"
  />
</template>

<script setup>
// Importing the vue composition API
import { ref, onMounted, nextTick, watch } from 'vue'
// Importing the router
import { useRoute, useRouter } from 'vue-router'
// Importing the i18n
import { useI18n } from 'vue-i18n'
// Import Notivue push
import { push } from 'notivue'
// Importing the stores
import { useAuthStore } from '@/stores/authStore'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
// Importing the services for the login
import { session } from '@/services/sessionService'
import { passwordReset } from '@/services/passwordResetService'
import { profile } from '@/services/profileService'
import { Modal } from 'bootstrap'
// Importing modal component
import ModalComponentEmailInput from '@/components/Modals/ModalComponentEmailInput.vue'

// Variables
const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const username = ref('')
const password = ref('')
const mfaCode = ref('')
const mfaRequired = ref(false)
const loading = ref(false)
const pendingUsername = ref('')
const authStore = useAuthStore()
const serverSettingsStore = useServerSettingsStore()
const showPassword = ref(false)
const loginPhotoUrl = serverSettingsStore.serverSettings.login_photo_set
  ? `${window.env.ENDURAIN_HOST}/server_images/login.png`
  : null

// Forgot password variables
const forgotPasswordLoading = ref(false)
const forgotPasswordModalRef = ref(null)
let forgotPasswordModalInstance = null

// Function to show forgot password modal
const showForgotPasswordModal = () => {
  if (forgotPasswordModalInstance) {
    forgotPasswordModalInstance.show()
  }
}

// Toggle password visibility
const togglePasswordVisibility = () => {
  showPassword.value = !showPassword.value
}

// Handle the form submission
const submitForm = async () => {
  if (mfaRequired.value) {
    // Handle MFA verification
    await submitMFAVerification()
  } else {
    // Handle regular login
    await submitLogin()
  }
}

// Handle regular login
const submitLogin = async () => {
  // Create the form data
  const formData = new URLSearchParams()
  formData.append('grant_type', 'password')
  formData.append('username', username.value)
  formData.append('password', password.value)

  try {
    loading.value = true
    // Get the token
    const response = await session.authenticateUser(formData)

    // Check if MFA is required
    if (response && response.mfa_required) {
      mfaRequired.value = true
      pendingUsername.value = response.username
      push.info(t('loginView.mfaRequired'))
      return
    }

    // Complete login if no MFA required
    await completeLogin(response)
  } catch (error) {
    handleLoginError(error)
  } finally {
    loading.value = false
  }
}

// Handle MFA verification
const submitMFAVerification = async () => {
  try {
    loading.value = true
    const response = await session.verifyMFAAndLogin({
      username: pendingUsername.value,
      mfa_code: mfaCode.value
    })

    await completeLogin(response)
  } catch (error) {
    if (error.toString().includes('401') || error.toString().includes('400')) {
      push.error(t('loginView.invalidMFACode'))
    } else {
      handleLoginError(error)
    }
  } finally {
    loading.value = false
  }
}

// Complete the login process
const completeLogin = async (session_id) => {
  // Get logged user information
  const userProfile = await profile.getProfileInfo()

  // Store the user in the auth store
  authStore.setUser(userProfile, session_id, locale)

  // Redirect to the home page
  return router.push('/')
}

// Handle login errors
const handleLoginError = (error) => {
  if (error.toString().includes('401')) {
    push.error(`${t('loginView.error401')} - ${error}`)
  } else if (error.toString().includes('403')) {
    push.error(`${t('loginView.error403')} - ${error}`)
  } else if (error.toString().includes('500')) {
    push.error(`${t('loginView.error500')} - ${error}`)
  } else {
    push.error(`${t('loginView.errorUndefined')} - ${error}`)
  }
}

// Forgot password form submission
const handleForgotPasswordSubmit = async (email) => {
  if (!email) {
    push.error(t('loginView.forgotPasswordModalEmailRequired'))
    return
  }

  forgotPasswordLoading.value = true

  try {
    await passwordReset.requestPasswordReset({
      email: email
    })

    push.success(t('loginView.forgotPasswordModalRequestSuccess'))
  } catch (error) {
    if (error.toString().includes('500')) {
      push.error(t('loginView.forgotPasswordModalUnableToSendEmail'))
    } else if (error.toString().includes('503')) {
      push.error(t('loginView.forgotPasswordModalEmailNotConfigured'))
    } else {
      push.error(`${t('loginView.forgotPasswordModalRequestError')} - ${error}`)
    }
  } finally {
    forgotPasswordLoading.value = false

    // Close modal
    if (forgotPasswordModalInstance) {
      forgotPasswordModalInstance.hide()
    }
  }
}

onMounted(async () => {
  // Initialize the modal
  await nextTick()
  if (forgotPasswordModalRef.value) {
    // Access the modal element from the component
    const modalElement = forgotPasswordModalRef.value.$el
    forgotPasswordModalInstance = new Modal(modalElement)
  }

  // Check if the session expired
  if (route.query.sessionExpired === 'true') {
    push.warning(t('loginView.sessionExpired'))
  }
  // Check if the logout was successful
  if (route.query.logoutSuccess === 'true') {
    push.success(t('loginView.logoutSuccess'))
  }
  // Check if the public activity was not found
  if (route.query.errorPublicActivityNotFound === 'true') {
    push.error(t('loginView.errorPublicActivityNotFound'))
  }
  // Check if the public shareable links are disabled
  if (route.query.errorpublic_shareable_links === 'true') {
    push.error(t('loginView.errorPublic_shareable_links'))
  }
  // Check for password reset success
  if (route.query.passwordResetSuccess === 'true') {
    push.success(t('loginView.passwordResetSuccess'))
  }
  // Check for password reset invalid link
  if (route.query.passwordResetInvalidLink === 'true') {
    push.error(t('loginView.passwordResetInvalidLink'))
  }
})
</script>
