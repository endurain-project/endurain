<template>
  <!-- change user password Modal -->
  <div
    class="modal fade"
    :id="`editUserPasswordModal${user.id}`"
    tabindex="-1"
    :aria-labelledby="`editUserPasswordModal${user.id}`"
    aria-hidden="true"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h1 class="modal-title fs-5" :id="`editUserPasswordModal${user.id}`">
            {{ $t('usersChangeUserPasswordModalComponent.modalChangeUserPasswordTitle') }}
          </h1>
          <button
            type="button"
            class="btn-close"
            data-bs-dismiss="modal"
            aria-label="Close"
          ></button>
        </div>
        <form @submit.prevent="submitChangeUserPasswordForm">
          <div class="modal-body">
            <UsersPasswordRequirementsComponent />

            <p>
              {{ $t('usersChangeUserPasswordModalComponent.modalChangeUserPasswordBodyLabel')
              }}<b>{{ user.username }}</b>
            </p>

            <!-- password fields -->
            <label :for="`validationNewPassword${user.id}`"
              ><b
                >*
                {{
                  $t('usersChangeUserPasswordModalComponent.modalChangeUserPasswordPasswordLabel')
                }}</b
              ></label
            >
            <div class="position-relative">
              <input
                :type="showNewPassword ? 'text' : 'password'"
                class="form-control"
                :class="{ 'is-invalid': !isNewPasswordValid || !isPasswordMatch }"
                :id="`validationNewPassword${user.id}`"
                :aria-describedby="`validationNewPasswordFeedback${user.id}`"
                :placeholder="
                  $t('usersChangeUserPasswordModalComponent.modalChangeUserPasswordPasswordLabel')
                "
                v-model="newPassword"
                required
              />
              <button
                type="button"
                class="btn position-absolute top-50 end-0 translate-middle-y"
                :class="{ 'me-4': !isNewPasswordValid || !isPasswordMatch }"
                @click="toggleNewPasswordVisibility"
              >
                <font-awesome-icon
                  :icon="showNewPassword ? ['fas', 'eye-slash'] : ['fas', 'eye']"
                />
              </button>
            </div>
            <div
              :id="`validationNewPasswordFeedback${user.id}`"
              class="invalid-feedback d-block"
              v-if="!isNewPasswordValid"
            >
              {{ $t('usersChangeUserPasswordModalComponent.modalChangeUserPasswordFeedbackLabel') }}
            </div>
            <div
              :id="`validationNewPasswordFeedback${user.id}`"
              class="invalid-feedback d-block"
              v-if="!isPasswordMatch"
            >
              {{
                $t(
                  'usersChangeUserPasswordModalComponent.modalChangeUserPasswordPasswordsDoNotMatchFeedbackLabel'
                )
              }}
            </div>
            <!-- repeat password fields -->

            <label class="mt-1" :for="`validationNewPasswordRepeat${user.id}`"
              ><b
                >*
                {{
                  $t(
                    'usersChangeUserPasswordModalComponent.modalChangeUserPasswordPasswordConfirmationLabel'
                  )
                }}</b
              ></label
            >
            <div class="position-relative">
              <input
                :type="showNewPasswordRepeat ? 'text' : 'password'"
                class="form-control"
                :class="{ 'is-invalid': !isNewPasswordRepeatValid || !isPasswordMatch }"
                :id="`validationNewPasswordRepeat${user.id}`"
                :aria-describedby="`validationNewPasswordRepeatFeedback${user.id}`"
                :placeholder="
                  $t(
                    'usersChangeUserPasswordModalComponent.modalChangeUserPasswordPasswordConfirmationLabel'
                  )
                "
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
              :id="`validationNewPasswordRepeatFeedback${user.id}`"
              class="invalid-feedback d-block"
              v-if="!isNewPasswordRepeatValid"
            >
              {{ $t('usersChangeUserPasswordModalComponent.modalChangeUserPasswordFeedbackLabel') }}
            </div>
            <div
              :id="`validationNewPasswordRepeatFeedback${user.id}`"
              class="invalid-feedback d-block"
              v-if="!isPasswordMatch"
            >
              {{
                $t(
                  'usersChangeUserPasswordModalComponent.modalChangeUserPasswordPasswordsDoNotMatchFeedbackLabel'
                )
              }}
            </div>

            <p>* {{ $t('generalItems.requiredField') }}</p>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
              {{ $t('generalItems.buttonClose') }}
            </button>
            <button
              type="submit"
              class="btn btn-success"
              :disabled="!isNewPasswordValid || !isNewPasswordRepeatValid || !isPasswordMatch"
              name="editUserPasswordAdmin"
              data-bs-dismiss="modal"
            >
              {{ $t('usersChangeUserPasswordModalComponent.modalChangeUserPasswordTitle') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
// Import Notivue push
import { push } from 'notivue'
// Importing stores
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
// Importing the services
import { users } from '@/services/usersService'
// Importing the components
import UsersPasswordRequirementsComponent from '@/components/Settings/SettingsUsersZone/UsersPasswordRequirementsComponent.vue'
// Importing validation utilities
import { isValidPassword, passwordsMatch, buildPasswordRequirements } from '@/utils/validationUtils'

// Define props
const props = defineProps({
  user: {
    type: Object,
    required: true
  }
})

// Composition API setup
const { t } = useI18n()
const serverSettingsStore = useServerSettingsStore()
const newPassword = ref('')
const newPasswordRepeat = ref('')
const passwordType = serverSettingsStore.serverSettings.password_type
const passMinLength =
  props.user.access_type === 'admin'
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
      const data = {
        password: newPassword.value
      }
      await users.editUserPassword(props.user.id, data)
      // Set the success message and show the success alert.
      push.success(t('usersChangeUserPasswordModalComponent.userChangePasswordSuccessMessage'))
    }
  } catch (error) {
    // If there is an error, set the error message and show the error alert.
    push.error(
      `${t('usersChangeUserPasswordModalComponent.userChangePasswordErrorMessage')} - ${error}`
    )
  }
}
</script>
