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
      <h4>{{ $t('settingsSecurityZone.subtitleMFA') }}</h4>
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

          <!-- Backup Codes Status -->
          <div v-if="backupCodeStatusLoading" class="mb-3">
            <LoadingComponent />
          </div>
          <div v-else-if="backupCodeStatus" class="alert alert-info mb-3" role="alert">
            <font-awesome-icon :icon="['fas', 'key']" class="me-2" />
            {{
              $t('settingsSecurityZone.backupCodesRemaining', {
                remaining: backupCodeStatus.unused,
                total: backupCodeStatus.total
              })
            }}
          </div>

          <div class="d-flex flex-wrap gap-2">
            <button
              type="button"
              class="btn btn-primary"
              @click="regenerateBackupCodes"
              :disabled="regenerateBackupCodesLoading"
            >
              <span
                v-if="regenerateBackupCodesLoading"
                class="spinner-border spinner-border-sm me-2"
                role="status"
                aria-hidden="true"
              ></span>
              <font-awesome-icon v-else :icon="['fas', 'rotate']" class="me-1" />
              {{ $t('settingsSecurityZone.regenerateBackupCodesButton') }}
            </button>
            <button
              type="button"
              class="btn btn-danger"
              data-bs-toggle="modal"
              data-bs-target="#mfaDisableModal"
              :disabled="mfaDisableLoading"
            >
              {{ $t('settingsSecurityZone.disableMFAButton') }}
            </button>
          </div>
        </div>
      </div>

      <!-- MFA Setup Modal -->
      <ModalComponentMFASetup
        ref="mfaSetupModalRef"
        modalId="mfaSetupModal"
        :title="t('settingsSecurityZone.mfaSetupModalTitle')"
        :instructions="t('settingsSecurityZone.mfaSetupInstructions')"
        :qrCodeData="qrCodeData"
        :mfaSecret="mfaSecret"
        :secretLabel="t('settingsSecurityZone.mfaSecretLabel')"
        :verificationCodeLabel="t('settingsSecurityZone.mfaVerificationCodeLabel')"
        :verificationCodePlaceholder="t('settingsSecurityZone.mfaVerificationCodePlaceholder')"
        :requiredFieldText="t('generalItems.requiredField')"
        :cancelButtonText="t('generalItems.cancel')"
        actionButtonType="success"
        :actionButtonText="t('settingsSecurityZone.enableMFAButton')"
        :isLoading="mfaEnableLoading"
        @submitAction="enableMFA"
      />

      <!-- MFA Disable Modal -->
      <ModalComponentNumberInput
        modalId="mfaDisableModal"
        :title="t('settingsSecurityZone.mfaDisableModalTitle')"
        :numberFieldLabel="t('settingsSecurityZone.mfaVerificationCodeLabel')"
        :numberDefaultValue="null"
        :actionButtonType="`danger`"
        :actionButtonText="t('settingsSecurityZone.disableMFAButton')"
        @numberToEmitAction="disableMFA"
      />

      <!-- MFA Backup Codes Modal -->
      <ModalComponentMFABackupCodes
        ref="mfaBackupCodesModalRef"
        modalId="mfaBackupCodesModal"
        :title="t('settingsSecurityZone.backupCodesModalTitle')"
        :description="t('settingsSecurityZone.backupCodesModalDescription')"
        :warningTitle="t('settingsSecurityZone.backupCodesWarningTitle')"
        :warningMessage="t('settingsSecurityZone.backupCodesWarningMessage')"
        :codes="backupCodes"
        :copyButtonText="t('settingsSecurityZone.backupCodesCopyAll')"
        :downloadButtonText="t('settingsSecurityZone.backupCodesDownload')"
        :copySuccessMessage="t('settingsSecurityZone.backupCodesCopySuccess')"
        :confirmationText="t('settingsSecurityZone.backupCodesSaveConfirmation')"
        :closeButtonText="t('settingsSecurityZone.backupCodesClose')"
        @closed="onBackupCodesModalClosed"
      />

      <hr />
      <!-- Linked Accounts (Identity Providers) -->
      <h4>{{ $t('settingsSecurityZone.subtitleLinkedAccounts') }}</h4>
      <p>{{ $t('settingsSecurityZone.linkedAccountsDescription') }}</p>

      <div v-if="isLoadingLinkedAccounts">
        <LoadingComponent />
      </div>
      <div v-else>
        <!-- Linked Accounts List -->
        <ul class="list-group" v-if="linkedAccounts && linkedAccounts.length > 0">
          <UserIdentityProviderListComponent
            v-for="account in linkedAccounts"
            :key="account.id"
            :idp="account"
            :userId="authStore.user.id"
            actionIcon="unlink"
            :showProviderType="false"
            @idpDeleted="unlinkAccount"
          />
        </ul>

        <!-- Available Providers to Link -->
        <div v-if="availableProviders && availableProviders.length > 0" class="mt-3">
          <h5>{{ $t('settingsSecurityZone.availableProvidersLabel') }}</h5>
          <div class="d-flex flex-wrap gap-2">
            <button
              v-for="provider in availableProviders"
              :key="provider.id"
              type="button"
              class="btn btn-secondary"
              @click="linkAccount(provider.id)"
              :disabled="linkingProviderId !== null"
              :aria-label="`${provider.name}`"
            >
              <span
                v-if="linkingProviderId === provider.id"
                class="spinner-border spinner-border-sm me-2"
                role="status"
                aria-hidden="true"
              ></span>
              <img
                v-else
                :src="getProviderCustomLogo(provider.icon)"
                :alt="`${provider.name} logo`"
                style="height: 20px; width: 20px; object-fit: contain"
              />
              {{ provider.name }}
            </button>
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
        <NoItemsFoundComponents :show-shadow="false" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
// Importing the services
import { profile } from '@/services/profileService'
import { identityProviders } from '@/services/identityProvidersService'
// Import Notivue push
import { push } from 'notivue'
// Importing the components
import UsersPasswordRequirementsComponent from '@/components/Settings/SettingsUsersZone/UsersPasswordRequirementsComponent.vue'
import ModalComponentNumberInput from '@/components/Modals/ModalComponentNumberInput.vue'
import ModalComponentMFASetup from '@/components/Modals/ModalComponentMFASetup.vue'
import ModalComponentMFABackupCodes from '@/components/Modals/ModalComponentMFABackupCodes.vue'
import UserIdentityProviderListComponent from '@/components/Settings/SettingsUsersZone/UserIdentityProviderListComponent.vue'
// Importing validation utilities
import { isValidPassword, passwordsMatch, buildPasswordRequirements } from '@/utils/validationUtils'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import NoItemsFoundComponents from '@/components/GeneralComponents/NoItemsFoundComponents.vue'
import UserSessionsListComponent from '@/components/Settings/SettingsUserSessionsZone/UserSessionsListComponent.vue'
// Importing stores
import { useAuthStore } from '@/stores/authStore'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { PROVIDER_CUSTOM_LOGO_MAP } from '@/constants/ssoConstants'

const { t } = useI18n()
const route = useRoute()
const authStore = useAuthStore()
const serverSettingsStore = useServerSettingsStore()
const newPassword = ref('')
const newPasswordRepeat = ref('')
const passwordType = serverSettingsStore.serverSettings.password_type
const passMinLength =
  authStore.user.access_type === 'admin'
    ? serverSettingsStore.serverSettings.password_length_admin_users
    : serverSettingsStore.serverSettings.password_length_regular_users
const passRequirements = buildPasswordRequirements(passwordType, passMinLength)
const isNewPasswordValid = computed(() => {
  if (!newPassword.value) return true
  return isValidPassword(newPassword.value, passRequirements)
})
const isNewPasswordRepeatValid = computed(() => {
  if (!newPasswordRepeat.value) return true
  return isValidPassword(newPasswordRepeat.value, passRequirements)
})
const isPasswordMatch = computed(() => passwordsMatch(newPassword.value, newPasswordRepeat.value))
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
const mfaSetupModalRef = ref(null)
const mfaBackupCodesModalRef = ref(null)
const backupCodes = ref([])
const backupCodeStatus = ref(null)
const backupCodeStatusLoading = ref(false)
const regenerateBackupCodesLoading = ref(false)

const showNewPassword = ref(false)
const showNewPasswordRepeat = ref(false)

// Linked Accounts (Identity Providers) variables
const linkedAccounts = ref([])
const availableProviders = ref([])
const allProviders = ref([])
const isLoadingLinkedAccounts = ref(false)
const linkingProviderId = ref(null)

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
    mfaSetupModalRef.value?.show()
  } catch (error) {
    push.error(`${t('settingsSecurityZone.errorSetupMFA')} - ${error}`)
  } finally {
    mfaSetupLoading.value = false
  }
}

async function enableMFA(verificationCode) {
  try {
    mfaEnableLoading.value = true
    const response = await profile.enableMFA({ mfa_code: verificationCode })
    mfaEnabled.value = true
    mfaSetupModalRef.value?.hide()
    qrCodeData.value = ''
    mfaSecret.value = ''
    push.success(t('settingsSecurityZone.mfaEnabledSuccess'))

    // Show backup codes modal if codes are returned
    if (response.backup_codes && response.backup_codes.length > 0) {
      backupCodes.value = response.backup_codes
      mfaBackupCodesModalRef.value?.show()
    }
  } catch (error) {
    push.error(`${t('settingsSecurityZone.errorEnableMFA')} - ${error}`)
  } finally {
    mfaEnableLoading.value = false
  }
}

async function disableMFA(mfaCode) {
  if (!mfaCode) return

  try {
    mfaDisableLoading.value = true
    await profile.disableMFA({ mfa_code: mfaCode.toString() })
    mfaEnabled.value = false
    backupCodeStatus.value = null
    push.success(t('settingsSecurityZone.mfaDisabledSuccess'))
  } catch (error) {
    push.error(`${t('settingsSecurityZone.errorDisableMFA')} - ${error}`)
  } finally {
    mfaDisableLoading.value = false
  }
}

async function loadBackupCodeStatus() {
  if (!mfaEnabled.value) return

  try {
    backupCodeStatusLoading.value = true
    backupCodeStatus.value = await profile.getBackupCodeStatus()
  } catch (error) {
    push.error(`${t('settingsSecurityZone.errorLoadBackupCodeStatus')} - ${error}`)
  } finally {
    backupCodeStatusLoading.value = false
  }
}

async function regenerateBackupCodes() {
  try {
    regenerateBackupCodesLoading.value = true
    const response = await profile.regenerateBackupCodes()

    if (response.codes && response.codes.length > 0) {
      backupCodes.value = response.codes
      mfaBackupCodesModalRef.value?.show()
      push.success(t('settingsSecurityZone.successRegenerateBackupCodes'))
    }
  } catch (error) {
    push.error(`${t('settingsSecurityZone.errorRegenerateBackupCodes')} - ${error}`)
  } finally {
    regenerateBackupCodesLoading.value = false
  }
}

function onBackupCodesModalClosed() {
  backupCodes.value = []
  // Refresh backup code status after modal is closed
  loadBackupCodeStatus()
}

const getProviderCustomLogo = (iconName) => {
  if (!iconName) return null
  const logoPath = PROVIDER_CUSTOM_LOGO_MAP[iconName.toLowerCase()]
  return logoPath || null
}

// Linked Accounts Functions
async function loadLinkedAccounts() {
  try {
    isLoadingLinkedAccounts.value = true

    // Fetch linked accounts and available providers in parallel
    linkedAccounts.value = await profile.getMyIdentityProviders()
    allProviders.value = await identityProviders.getAllProviders()

    // Filter out already linked providers
    const linkedProviderIds = new Set(linkedAccounts.value.map((account) => account.idp_id))
    availableProviders.value = allProviders.value.filter(
      (provider) => !linkedProviderIds.has(provider.id)
    )
  } catch (error) {
    push.error(`${t('settingsSecurityZone.errorLoadingLinkedAccounts')} - ${error}`)
  } finally {
    isLoadingLinkedAccounts.value = false
  }
}

async function unlinkAccount(idpId) {
  if (!idpId) return

  try {
    await profile.unlinkIdentityProvider(idpId)

    // Find the account being unlinked
    const unlinkedAccount = linkedAccounts.value.find((account) => account.idp_id === idpId)

    // Remove from linked accounts list
    linkedAccounts.value = linkedAccounts.value.filter((account) => account.idp_id !== idpId)

    // Add back to available providers
    const unlinkedProvider = allProviders.value.find((p) => p.id === idpId)
    if (unlinkedProvider) {
      availableProviders.value.push(unlinkedProvider)
    }

    push.success(t('settingsSecurityZone.unlinkAccountSuccess'))
  } catch (error) {
    const errorMessage = error.message || error.toString()

    // Check for specific error scenarios
    if (errorMessage.includes('last authentication method') || errorMessage.includes('400')) {
      push.error(t('settingsSecurityZone.unlinkAccountLastMethodError'))
    } else {
      push.error(`${t('settingsSecurityZone.unlinkAccountError')} - ${errorMessage}`)
    }
  }
}

async function linkAccount(providerId) {
  try {
    linkingProviderId.value = providerId
    // Generate token and redirect to OAuth flow
    await profile.linkIdentityProvider(providerId)
  } catch (error) {
    linkingProviderId.value = null
    const errorMessage = error.message || error.toString()

    // Check for rate limiting
    if (errorMessage.includes('429') || errorMessage.toLowerCase().includes('rate limit')) {
      push.error(t('settingsSecurityZone.linkAccountRateLimitError'))
    } else {
      push.error(`${t('settingsSecurityZone.linkAccountError')} - ${errorMessage}`)
    }
  }
}

// Check for OAuth link success/error in URL params
function checkOAuthLinkStatus() {
  const idpLink = route.query.idp_link
  const idpName = route.query.idp_name

  if (idpLink === 'success' && idpName) {
    push.success(t('settingsSecurityZone.linkAccountSuccess', { providerName: idpName }))
    // Reload linked accounts to show the new one
    loadLinkedAccounts()
  } else if (idpLink === 'error') {
    push.error(t('settingsSecurityZone.linkAccountError'))
  }
}

onMounted(async () => {
  // Check for OAuth callback status
  checkOAuthLinkStatus()

  // Fetch the user sessions
  userSessions.value = await profile.getProfileSessions()

  // Load MFA status
  await loadMFAStatus()

  // Load backup code status if MFA is enabled
  await loadBackupCodeStatus()

  // Load linked accounts
  await loadLinkedAccounts()

  // Set the isLoading to false
  isLoading.value = false
})
</script>
