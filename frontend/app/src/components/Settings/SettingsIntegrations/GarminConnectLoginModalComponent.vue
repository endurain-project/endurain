<template>
  <div
    ref="modalRef"
    class="modal fade"
    id="garminConnectAuthModal"
    tabindex="-1"
    aria-labelledby="garminConnectAuthModalTitle"
    aria-hidden="true"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h1 class="modal-title fs-5" id="garminConnectAuthModalTitle">
            {{ $t('garminConnectLoginModalComponent.garminConnectAuthModalTitle') }}
          </h1>
          <button
            type="button"
            class="btn-close"
            data-bs-dismiss="modal"
            aria-label="Close"
          ></button>
        </div>
        <form @submit.prevent="submitConnectGarminConnect">
          <div class="modal-body">
            <!-- Username field -->
            <div class="mb-3">
              <label for="garminConnectUsername" class="form-label">
                <b
                  >*
                  {{
                    $t('garminConnectLoginModalComponent.garminConnectAuthModalUsernameLabel')
                  }}</b
                >
              </label>
              <input
                id="garminConnectUsername"
                v-model="garminConnectUsername"
                class="form-control"
                type="text"
                name="garminConnectUsername"
                :placeholder="
                  $t('garminConnectLoginModalComponent.garminConnectAuthModalUsernamePlaceholder')
                "
                :aria-label="
                  $t('garminConnectLoginModalComponent.garminConnectAuthModalUsernameLabel')
                "
                required
              />
            </div>

            <!-- Password field -->
            <div class="mb-3">
              <label for="garminConnectPassword" class="form-label">
                <b
                  >*
                  {{
                    $t('garminConnectLoginModalComponent.garminConnectAuthModalPasswordLabel')
                  }}</b
                >
              </label>
              <input
                id="garminConnectPassword"
                v-model="garminConnectPassword"
                class="form-control"
                type="password"
                name="garminConnectPassword"
                :placeholder="
                  $t('garminConnectLoginModalComponent.garminConnectAuthModalPasswordPlaceholder')
                "
                :aria-label="
                  $t('garminConnectLoginModalComponent.garminConnectAuthModalPasswordLabel')
                "
                required
              />
            </div>

            <!-- MFA code field -->
            <div v-if="mfaRequired" class="row g-3 align-items-end">
              <div class="col">
                <label for="garminConnectMfaCode" class="form-label">
                  <b
                    >*
                    {{
                      $t('garminConnectLoginModalComponent.garminConnectAuthModalMfaCodeLabel')
                    }}</b
                  >
                </label>
                <input
                  id="garminConnectMfaCode"
                  v-model="mfaCode"
                  class="form-control"
                  type="text"
                  name="garminConnectMfaCode"
                  :placeholder="
                    $t('garminConnectLoginModalComponent.garminConnectAuthModalMfaCodePlaceholder')
                  "
                  :aria-label="
                    $t('garminConnectLoginModalComponent.garminConnectAuthModalMfaCodeLabel')
                  "
                />
              </div>
              <div class="col">
                <button
                  type="button"
                  class="btn btn-success w-100"
                  :disabled="loadingLoginWithMfa"
                  :aria-label="$t('garminConnectLoginModalComponent.buttonSubmitMfaCode')"
                  @click="submitMfaCode"
                >
                  <span
                    v-if="loadingLoginWithMfa"
                    class="spinner-border spinner-border-sm me-1"
                    role="status"
                    aria-hidden="true"
                  ></span>
                  {{ $t('garminConnectLoginModalComponent.buttonSubmitMfaCode') }}
                </button>
              </div>
            </div>

            <p class="mt-2">* {{ $t('generalItems.requiredField') }}</p>
          </div>
          <div class="modal-footer">
            <button
              type="button"
              class="btn btn-secondary"
              data-bs-dismiss="modal"
              aria-label="Close modal"
            >
              {{ $t('generalItems.buttonClose') }}
            </button>
            <button
              type="submit"
              class="btn btn-success"
              :disabled="loadingLogin"
              :aria-label="$t('garminConnectLoginModalComponent.garminConnectAuthModalLoginButton')"
            >
              <span
                v-if="loadingLogin"
                class="spinner-border spinner-border-sm me-1"
                role="status"
                aria-hidden="true"
              ></span>
              {{ $t('garminConnectLoginModalComponent.garminConnectAuthModalLoginButton') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * GarminConnectLoginModalComponent
 *
 * Modal component for authenticating and linking a Garmin Connect account.
 * Supports MFA authentication via WebSocket for 2FA verification.
 * Follows the same structure and patterns as other modal components.
 *
 * @component
 */

// ============================================================================
// Section 1: Imports
// ============================================================================

// Vue composition API
import { ref, onMounted, onUnmounted } from 'vue'
// i18n
import { useI18n } from 'vue-i18n'
// Stores
import { useAuthStore } from '@/stores/authStore'
// Composables
import { useBootstrapModal } from '@/composables/useBootstrapModal'
// Services
import { garminConnect } from '@/services/garminConnectService'
// Notifications
import { push } from 'notivue'

// ============================================================================
// Section 3: Composables & Stores
// ============================================================================

const authStore = useAuthStore()
const { locale, t } = useI18n()
const { initializeModal, hideModal, disposeModal } = useBootstrapModal()

// ============================================================================
// Section 4: Reactive State
// ============================================================================

const modalRef = ref<HTMLDivElement | null>(null)
const garminConnectUsername = ref('')
const garminConnectPassword = ref('')
const mfaRequired = ref(false)
const mfaCode = ref('')
const loadingLogin = ref(false)
const loadingLoginWithMfa = ref(false)

// ============================================================================
// Section 6: UI Interaction Handlers
// ============================================================================

/**
 * WebSocket message handler for MFA requirement
 */
const handleWebSocketMessage = (event: MessageEvent): void => {
  try {
    const data = JSON.parse(event.data)
    if (data?.message === 'MFA_REQUIRED') {
      mfaRequired.value = true
    }
  } catch (error) {
    console.error('Error parsing WebSocket message:', error)
  }
}

// ============================================================================
// Section 8: Main Logic
// ============================================================================

/**
 * Submit Garmin Connect credentials to link account
 * Handles success, error states, and modal cleanup
 */
const submitConnectGarminConnect = async (): Promise<void> => {
  loadingLogin.value = true

  const notification = push.promise(
    t('garminConnectLoginModalComponent.processingMessageLinkGarminConnect')
  )

  try {
    const data = {
      username: garminConnectUsername.value,
      password: garminConnectPassword.value
    }

    await garminConnect.linkGarminConnect(data)

    // Update user object with linked status
    const user = { ...authStore.user } as any
    user.is_garminconnect_linked = 1
    authStore.setUser(user, authStore.session_id, locale)

    // Show success message
    notification.resolve(t('garminConnectLoginModalComponent.successMessageLinkGarminConnect'))

    // Hide modal and reset form
    hideModal()
    resetForm()
  } catch (error) {
    notification.reject(
      `${t('garminConnectLoginModalComponent.errorMessageUnableToLinkGarminConnect')} - ${error}`
    )
  } finally {
    loadingLogin.value = false
  }
}

/**
 * Submit MFA code for two-factor authentication
 */
const submitMfaCode = async (): Promise<void> => {
  if (!mfaCode.value) return

  loadingLoginWithMfa.value = true

  try {
    const data = {
      mfa_code: mfaCode.value
    }
    await garminConnect.mfaGarminConnect(data)
  } catch (error) {
    push.error(
      `${t('garminConnectLoginModalComponent.errorMessageUnableToLinkGarminConnect')} - ${error}`
    )
    loadingLoginWithMfa.value = false
  }
}

/**
 * Reset form fields and state
 */
const resetForm = (): void => {
  garminConnectUsername.value = ''
  garminConnectPassword.value = ''
  mfaRequired.value = false
  mfaCode.value = ''
  loadingLogin.value = false
  loadingLoginWithMfa.value = false
}

// ============================================================================
// Section 9: Lifecycle Hooks
// ============================================================================

/**
 * Initialize modal and WebSocket handler on mount
 */
onMounted(async () => {
  await initializeModal(modalRef)

  // Set up WebSocket message handler for MFA
  const websocket = authStore.user_websocket as WebSocket | null
  if (websocket) {
    websocket.onmessage = handleWebSocketMessage
  }
})

/**
 * Clean up modal and WebSocket handler on unmount
 */
onUnmounted(() => {
  // Remove WebSocket message handler
  const websocket = authStore.user_websocket as WebSocket | null
  if (websocket) {
    websocket.onmessage = null
  }

  disposeModal()
})
</script>
