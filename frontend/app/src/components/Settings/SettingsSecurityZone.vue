<template>
  <div class="col">
    <div class="bg-body-tertiary rounded p-3 shadow-sm">
      <h4>{{ $t('settingsSecurityZone.subtitleChangePassword') }}</h4>
      <UsersPasswordRequirementsComponent />

      <form @submit.prevent="submitChangeUserPasswordForm">
        <!-- password fields -->
        <label for="validationNewPassword"
          ><b>* {{ $t('settingsSecurityZone.changeUserPasswordPasswordLabel') }}</b></label
        >
        <div class="position-relative">
          <input
            :type="showNewPassword ? 'text' : 'password'"
            class="form-control"
            :class="{ 'is-invalid': !isNewPasswordValid || !isPasswordMatch }"
            id="validationNewPassword"
            aria-describedby="validationNewPasswordFeedback"
            :placeholder="$t('settingsSecurityZone.changeUserPasswordPasswordLabel')"
            v-model="newPassword"
            required
          />
          <button
            type="button"
            class="btn position-absolute top-50 end-0 translate-middle-y"
            :class="{ 'me-4': !isNewPasswordValid || !isPasswordMatch }"
            @click="toggleNewPasswordVisibility"
          >
            <font-awesome-icon :icon="showNewPassword ? ['fas', 'eye-slash'] : ['fas', 'eye']" />
          </button>
        </div>
        <div
          id="validationNewPasswordFeedback"
          class="invalid-feedback d-block"
          v-if="!isNewPasswordValid"
        >
          {{ $t('settingsSecurityZone.changeUserPasswordFeedbackLabel') }}
        </div>
        <div
          id="validationNewPasswordFeedback"
          class="invalid-feedback d-block"
          v-if="!isPasswordMatch"
        >
          {{ $t('settingsSecurityZone.changeUserPasswordPasswordsDoNotMatchFeedbackLabel') }}
        </div>

        <!-- repeat password fields -->
        <label class="mt-1" for="validationNewPasswordRepeat"
          ><b
            >* {{ $t('settingsSecurityZone.changeUserPasswordPasswordConfirmationLabel') }}</b
          ></label
        >
        <div class="position-relative">
          <input
            :type="showNewPasswordRepeat ? 'text' : 'password'"
            class="form-control"
            :class="{ 'is-invalid': !isNewPasswordRepeatValid || !isPasswordMatch }"
            id="validationNewPasswordRepeat"
            aria-describedby="validationNewPasswordRepeatFeedback"
            :placeholder="$t('settingsSecurityZone.changeUserPasswordPasswordConfirmationLabel')"
            v-model="newPasswordRepeat"
            required
          />
          <button
            type="button"
            class="btn position-absolute top-50 end-0 translate-middle-y"
            :class="{ 'me-4': !isNewPasswordRepeatValid || !isPasswordMatch }"
            @click="toggleNewPasswordRepeatVisibility"
          >
            <font-awesome-icon
              :icon="showNewPasswordRepeat ? ['fas', 'eye-slash'] : ['fas', 'eye']"
            />
          </button>
        </div>
        <div
          id="validationNewPasswordRepeatFeedback"
          class="invalid-feedback d-block"
          v-if="!isNewPasswordRepeatValid"
        >
          {{ $t('settingsSecurityZone.changeUserPasswordFeedbackLabel') }}
        </div>
        <div
          id="validationNewPasswordRepeatFeedback"
          class="invalid-feedback d-block"
          v-if="!isPasswordMatch"
        >
          {{ $t('settingsSecurityZone.changeUserPasswordPasswordsDoNotMatchFeedbackLabel') }}
        </div>

        <p>* {{ $t('generalItems.requiredField') }}</p>

        <button
          type="submit"
          class="btn btn-success"
          :disabled="!isNewPasswordValid || !isNewPasswordRepeatValid || !isPasswordMatch"
          name="editUserPassword"
        >
          {{ $t('settingsSecurityZone.subtitleChangePassword') }}
        </button>
      </form>

      <hr />
      <!-- MFA Settings -->
      <h4>{{ $t('settingsSecurityZone.subtitleMFA') }}{{ $t('generalItems.betaTag') }}</h4>
      <div v-if="isMFALoading">
        <LoadingComponent />
      </div>
      <div v-else>
        <div v-if="!mfaEnabled">
          <p>{{ $t('settingsSecurityZone.mfaDisabledDescription') }}</p>
          <button
            type="button"
            class="btn btn-primary"
            @click="setupMFA"
            :disabled="mfaSetupLoading"
          >
            <span
              v-if="mfaSetupLoading"
              class="spinner-border spinner-border-sm me-2"
              role="status"
              aria-hidden="true"
            ></span>
            {{ $t('settingsSecurityZone.enableMFAButton') }}
          </button>
        </div>
        <div v-else>
          <p>{{ $t('settingsSecurityZone.mfaEnabledDescription') }}</p>
          <button
            type="button"
            class="btn btn-danger"
            @click="showDisableMFAModal"
            :disabled="mfaDisableLoading"
          >
            {{ $t('settingsSecurityZone.disableMFAButton') }}
          </button>
        </div>
      </div>

      <!-- MFA Setup Modal -->
      <div
        class="modal fade"
        id="mfaSetupModal"
        tabindex="-1"
        aria-labelledby="mfaSetupModalLabel"
        aria-hidden="true"
        ref="mfaSetupModal"
      >
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title" id="mfaSetupModalLabel">
                {{ $t('settingsSecurityZone.mfaSetupModalTitle') }}
              </h5>
              <button
                type="button"
                class="btn-close"
                data-bs-dismiss="modal"
                aria-label="Close"
              ></button>
            </div>
            <div class="modal-body">
              <div v-if="qrCodeData">
                <p>{{ $t('settingsSecurityZone.mfaSetupInstructions') }}</p>
                <div class="text-center mb-3">
                  <img :src="qrCodeData" alt="QR Code" class="img-fluid" style="max-width: 200px" />
                </div>
                <p>
                  <strong>{{ $t('settingsSecurityZone.mfaSecretLabel') }}:</strong>
                  <code class="ms-1">{{ mfaSecret }}</code>
                </p>
                <form @submit.prevent="enableMFA">
                  <label for="mfaVerificationCode"
                    ><b>* {{ $t('settingsSecurityZone.mfaVerificationCodeLabel') }}</b></label
                  >
                  <input
                    type="text"
                    class="form-control"
                    id="mfaVerificationCode"
                    v-model="mfaVerificationCode"
                    :placeholder="$t('settingsSecurityZone.mfaVerificationCodePlaceholder')"
                    required
                  />
                  <p class="mt-2">* {{ $t('generalItems.requiredField') }}</p>
                  <div class="d-flex justify-content-end">
                    <button type="button" class="btn btn-secondary me-2" data-bs-dismiss="modal">
                      {{ $t('generalItems.cancel') }}
                    </button>
                    <button
                      type="submit"
                      class="btn btn-success"
                      :disabled="!mfaVerificationCode || mfaEnableLoading"
                    >
                      <span
                        v-if="mfaEnableLoading"
                        class="spinner-border spinner-border-sm me-2"
                        role="status"
                        aria-hidden="true"
                      ></span>
                      {{ $t('settingsSecurityZone.enableMFAButton') }}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- MFA Disable Modal -->
      <div
        class="modal fade"
        id="mfaDisableModal"
        tabindex="-1"
        aria-labelledby="mfaDisableModalLabel"
        aria-hidden="true"
        ref="mfaDisableModal"
      >
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title" id="mfaDisableModalLabel">
                {{ $t('settingsSecurityZone.mfaDisableModalTitle') }}
              </h5>
              <button
                type="button"
                class="btn-close"
                data-bs-dismiss="modal"
                aria-label="Close"
              ></button>
            </div>
            <div class="modal-body">
              <p>{{ $t('settingsSecurityZone.mfaDisableConfirmation') }}</p>
              <form @submit.prevent="disableMFA">
                <label for="mfaDisableCode"
                  ><b>* {{ $t('settingsSecurityZone.mfaVerificationCodeLabel') }}</b></label
                >
                <input
                  type="text"
                  class="form-control"
                  id="mfaDisableCode"
                  v-model="mfaDisableCode"
                  :placeholder="$t('settingsSecurityZone.mfaVerificationCodePlaceholder')"
                  required
                />
                <p class="mt-2">* {{ $t('generalItems.requiredField') }}</p>
                <div class="d-flex justify-content-end">
                  <button type="button" class="btn btn-secondary me-2" data-bs-dismiss="modal">
                    {{ $t('generalItems.cancel') }}
                  </button>
                  <button
                    type="submit"
                    class="btn btn-danger"
                    :disabled="!mfaDisableCode || mfaDisableLoading"
                  >
                    <span
                      v-if="mfaDisableLoading"
                      class="spinner-border spinner-border-sm me-2"
                      role="status"
                      aria-hidden="true"
                    ></span>
                    {{ $t('settingsSecurityZone.disableMFAButton') }}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>

      <hr />
      <!-- user sessions list -->
      <h4>{{ $t('settingsSecurityZone.subtitleMySessions') }}</h4>
      <div v-if="isLoading">
        <LoadingComponent />
      </div>
      <div v-else-if="userSessions && userSessions.length > 0">
        <UserSessionsListComponent
          v-for="session in userSessions"
          :key="session.id"
          :session="session"
          @sessionDeleted="updateSessionListDeleted"
        />
      </div>
      <div v-else>
        <NoItemsFoundComponents />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import Modal from 'bootstrap/js/src/modal'
// Importing the services
import { profile } from '@/services/profileService'
// Import Notivue push
import { push } from 'notivue'
// Importing the components
import UsersPasswordRequirementsComponent from '@/components/Settings/SettingsUsersZone/UsersPasswordRequirementsComponent.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import NoItemsFoundComponents from '@/components/GeneralComponents/NoItemsFoundComponents.vue'
import UserSessionsListComponent from '@/components/Settings/SettingsUserSessionsZone/UserSessionsListComponent.vue'

const { t } = useI18n()
const newPassword = ref('')
const newPasswordRepeat = ref('')
const regex =
  /^(?=.*[A-Z])(?=.*\d)(?=.*[ !\"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~])[A-Za-z\d !"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]{8,}$/
const isNewPasswordValid = computed(() => {
  return regex.test(newPassword.value)
})
const isNewPasswordRepeatValid = computed(() => {
  return regex.test(newPasswordRepeat.value)
})
const isPasswordMatch = computed(() => newPassword.value === newPasswordRepeat.value)
const userSessions = ref([])
const isLoading = ref(true)

// MFA related variables
const mfaEnabled = ref(false)
const isMFALoading = ref(false)
const mfaSetupLoading = ref(false)
const mfaEnableLoading = ref(false)
const mfaDisableLoading = ref(false)
const qrCodeData = ref('')
const mfaSecret = ref('')
const mfaVerificationCode = ref('')
const mfaDisableCode = ref('')
const mfaSetupModal = ref(null)
const mfaDisableModal = ref(null)

let mfaSetupModalInstance = null
let mfaDisableModalInstance = null

const showNewPassword = ref(false)
const showNewPasswordRepeat = ref(false)

// Toggle visibility for new password
const toggleNewPasswordVisibility = () => {
  showNewPassword.value = !showNewPassword.value
}

// Toggle visibility for repeated password
const toggleNewPasswordRepeatVisibility = () => {
  showNewPasswordRepeat.value = !showNewPasswordRepeat.value
}

async function submitChangeUserPasswordForm() {
  try {
    if (isNewPasswordValid.value && isNewPasswordRepeatValid.value && isPasswordMatch.value) {
      // Create the data object to send to the service.
      const data = {
        password: newPassword.value
      }

      // Call the service to edit the user password.
      await profile.editProfilePassword(data)

      // Show the success alert.
      push.success(t('settingsSecurityZone.userChangePasswordSuccessMessage'))
      // Clear the form fields.
      newPassword.value = ''
      newPasswordRepeat.value = ''
    }
  } catch (error) {
    // If there is an error, show the error alert.
    push.error(`${t('settingsSecurityZone.userChangePasswordErrorMessage')} - ${error}`)
  }
}

async function updateSessionListDeleted(sessionDeletedId) {
  try {
    // Delete session in the DB
    await profile.deleteProfileSession(sessionDeletedId)

    // Remove the session from the userSessions
    userSessions.value = userSessions.value.filter((session) => session.id !== sessionDeletedId)

    // Show the success alert.
    push.success(t('settingsSecurityZone.successDeleteSession'))
  } catch (error) {
    // If there is an error, show the error alert.
    push.error(`${t('settingsSecurityZone.errorDeleteSession')} - ${error}`)
  }
}

// MFA Functions
async function loadMFAStatus() {
  try {
    isMFALoading.value = true
    const status = await profile.getMFAStatus()
    mfaEnabled.value = status.mfa_enabled
  } catch (error) {
    push.error(`${t('settingsSecurityZone.errorLoadMFAStatus')} - ${error}`)
  } finally {
    isMFALoading.value = false
  }
}

async function setupMFA() {
  try {
    mfaSetupLoading.value = true
    const setupData = await profile.setupMFA()
    qrCodeData.value = setupData.qr_code
    mfaSecret.value = setupData.secret
    mfaSetupModalInstance.show()
  } catch (error) {
    push.error(`${t('settingsSecurityZone.errorSetupMFA')} - ${error}`)
  } finally {
    mfaSetupLoading.value = false
  }
}

async function enableMFA() {
  try {
    mfaEnableLoading.value = true
    await profile.enableMFA({ mfa_code: mfaVerificationCode.value })
    mfaEnabled.value = true
    mfaSetupModalInstance.hide()
    mfaVerificationCode.value = ''
    qrCodeData.value = ''
    mfaSecret.value = ''
    push.success(t('settingsSecurityZone.mfaEnabledSuccess'))
  } catch (error) {
    push.error(`${t('settingsSecurityZone.errorEnableMFA')} - ${error}`)
  } finally {
    mfaEnableLoading.value = false
  }
}

function showDisableMFAModal() {
  mfaDisableModalInstance.show()
}

async function disableMFA() {
  try {
    mfaDisableLoading.value = true
    await profile.disableMFA({ mfa_code: mfaDisableCode.value })
    mfaEnabled.value = false
    mfaDisableModalInstance.hide()
    mfaDisableCode.value = ''
    push.success(t('settingsSecurityZone.mfaDisabledSuccess'))
  } catch (error) {
    push.error(`${t('settingsSecurityZone.errorDisableMFA')} - ${error}`)
  } finally {
    mfaDisableLoading.value = false
  }
}

onMounted(async () => {
  // Initialize modal instances
  if (mfaSetupModal.value) {
    mfaSetupModalInstance = new Modal(mfaSetupModal.value)
  }
  if (mfaDisableModal.value) {
    mfaDisableModalInstance = new Modal(mfaDisableModal.value)
  }

  // Fetch the user sessions
  userSessions.value = await profile.getProfileSessions()

  // Load MFA status
  await loadMFAStatus()

  // Set the isLoading to false
  isLoading.value = false
})
</script>
