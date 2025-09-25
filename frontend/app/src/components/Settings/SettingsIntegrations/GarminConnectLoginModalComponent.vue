<template>
  <!-- Modal Garmin Connect authentication -->
  <div
    class="modal fade"
    id="garminConnectAuthModal"
    ref="garminConnectAuthModal"
    tabindex="-1"
    aria-labelledby="garminConnectAuthModal"
    aria-hidden="true"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h1 class="modal-title fs-5" id="garminConnectAuthModal">
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
            <!-- username fields -->
            <label for="garminConnectUsername"
              ><b
                >*
                {{ $t('garminConnectLoginModalComponent.garminConnectAuthModalUsernameLabel') }}</b
              ></label
            >
            <input
              class="form-control"
              type="text"
              name="garminConnectUsername"
              :placeholder="
                $t('garminConnectLoginModalComponent.garminConnectAuthModalUsernamePlaceholder')
              "
              v-model="garminConnectUsername"
              required
            />
            <!-- password fields -->
            <label for="garminConnectPassword"
              ><b
                >*
                {{ $t('garminConnectLoginModalComponent.garminConnectAuthModalPasswordLabel') }}</b
              ></label
            >
            <input
              class="form-control"
              type="password"
              name="garminConnectPassword"
              :placeholder="
                $t('garminConnectLoginModalComponent.garminConnectAuthModalPasswordPlaceholder')
              "
              v-model="garminConnectPassword"
              required
            />

            <!-- MFA code field -->
            <div class="row g-3 align-items-end" v-if="mfaRequired">
              <div class="col">
                <label for="garminConnectMfaCode"
                  ><b
                    >*
                    {{
                      $t('garminConnectLoginModalComponent.garminConnectAuthModalMfaCodeLabel')
                    }}</b
                  ></label
                >
                <input
                  class="form-control"
                  type="text"
                  name="garminConnectMfaCode"
                  :placeholder="
                    $t('garminConnectLoginModalComponent.garminConnectAuthModalMfaCodePlaceholder')
                  "
                  v-model="mfaCode"
                />
              </div>
              <div class="col">
                <a
                  href="#"
                  class="btn btn-success w-100"
                  :class="{ disabled: loadingLoginWithMfa }"
                  @click="submitMfaCode"
                >
                  <span
                    class="spinner-border spinner-border-sm me-1"
                    aria-hidden="true"
                    v-if="loadingLoginWithMfa"
                  ></span>
                  <span role="status">{{
                    $t('garminConnectLoginModalComponent.buttonSubmitMfaCode')
                  }}</span>
                </a>
              </div>
            </div>

            <p>* {{ $t('generalItems.requiredField') }}</p>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
              {{ $t('generalItems.buttonClose') }}
            </button>
            <button type="submit" class="btn btn-success" :disabled="loadingLogin">
              <span
                class="spinner-border spinner-border-sm me-1"
                aria-hidden="true"
                v-if="loadingLogin"
              ></span>
              <span role="status">{{
                $t('garminConnectLoginModalComponent.garminConnectAuthModalLoginButton')
              }}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
// Importing the stores
import { useAuthStore } from '@/stores/authStore'
// Import Notivue push
import { push } from 'notivue'
// Importing the services
import { garminConnect } from '@/services/garminConnectService'
// Importing the utils
import { removeActiveModal, resetBodyStylesIfNoActiveModals } from '@/utils/modalUtils'
// Importing the bootstrap modal
import Modal from 'bootstrap/js/src/modal'

const authStore = useAuthStore()
const { locale, t } = useI18n()
const garminConnectUsername = ref('')
const garminConnectPassword = ref('')
const mfaRequired = ref(false)
const mfaCode = ref('')
const garminConnectAuthModal = ref(null) // Ref for the modal element
const loadingLogin = ref(false)
const loadingLoginWithMfa = ref(false)

let modalInstance = null // Holds the modal instance

// Set up websocket message handler
authStore.user_websocket.onmessage = (event) => {
  const data = JSON.parse(event.data)
  if (data && data.message === 'MFA_REQUIRED') {
    mfaRequired.value = true
  }
}

// Initialize the modal instance on mount
onMounted(() => {
  if (garminConnectAuthModal.value) {
    modalInstance = new Modal(garminConnectAuthModal.value)
  }
})

async function submitConnectGarminConnect() {
  loadingLogin.value = true
  // Set the loading message
  const notification = push.promise(
    t('garminConnectLoginModalComponent.processingMessageLinkGarminConnect')
  )
  try {
    const data = {
      username: garminConnectUsername.value,
      password: garminConnectPassword.value
    }
    await garminConnect.linkGarminConnect(data)

    // Set the user object with the is_garminconnect_linked property set to 1.
    const user = authStore.user
    user.is_garminconnect_linked = 1
    authStore.setUser(user, locale)

    // Show success message
    notification.resolve(t('garminConnectLoginModalComponent.successMessageLinkGarminConnect'))
  } catch (error) {
    // If there is an error, show the error alert.
    notification.reject(
      `${t('garminConnectLoginModalComponent.errorMessageUnableToLinkGarminConnect')} - ${error}`
    )
  } finally {
    // Remove any remaining modal backdrops
    removeActiveModal(modalInstance)

    // Reset body overflow to restore scrolling
    resetBodyStylesIfNoActiveModals()

    // reset variables
    mfaRequired.value = false
    mfaCode.value = ''
    loadingLogin.value = false
    loadingLoginWithMfa.value = false
  }
}

async function submitMfaCode() {
  const data = {
    mfa_code: mfaCode.value
  }
  await garminConnect.mfaGarminConnect(data)
  loadingLoginWithMfa.value = true
}
</script>
