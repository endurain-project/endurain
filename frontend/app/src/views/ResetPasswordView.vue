<template>
  <div class="px-3">
    <div class="row justify-content-center">
      <div class="col-md-6 p-3 rounded bg-body-tertiary shadow-sm">
        <h1>{{ $t('resetPassword.title') }}</h1>
        <form @submit.prevent="submitResetForm">
          <div class="mb-3">
            <label for="newPassword" class="form-label">{{
              $t('resetPassword.newPasswordLabel')
            }}</label>
            <div class="position-relative">
              <input
                :type="showNewPassword ? 'text' : 'password'"
                class="form-control"
                :class="{ 'is-invalid': !isNewPasswordValid && newPassword }"
                id="newPassword"
                v-model="newPassword"
                required
              />
              <button
                type="button"
                class="btn position-absolute top-50 end-0 translate-middle-y me-2"
                @click="toggleNewPasswordVisibility"
              >
                <font-awesome-icon
                  :icon="showNewPassword ? ['fas', 'eye-slash'] : ['fas', 'eye']"
                />
              </button>
            </div>
            <div v-if="!isNewPasswordValid && newPassword" class="invalid-feedback d-block">
              {{ $t('resetPassword.passwordComplexityError') }}
            </div>
          </div>
          <div class="mb-3">
            <label for="confirmPassword" class="form-label">{{
              $t('resetPassword.confirmPasswordLabel')
            }}</label>
            <div class="position-relative">
              <input
                :type="showConfirmPassword ? 'text' : 'password'"
                class="form-control"
                :class="{ 'is-invalid': !isPasswordMatch && confirmPassword }"
                id="confirmPassword"
                v-model="confirmPassword"
                required
              />
              <button
                type="button"
                class="btn position-absolute top-50 end-0 translate-middle-y me-2"
                @click="toggleConfirmPasswordVisibility"
              >
                <font-awesome-icon
                  :icon="showConfirmPassword ? ['fas', 'eye-slash'] : ['fas', 'eye']"
                />
              </button>
            </div>
            <div v-if="!isPasswordMatch && confirmPassword" class="invalid-feedback d-block">
              {{ $t('resetPassword.passwordMismatchError') }}
            </div>
          </div>
          <div class="d-grid gap-2">
            <button
              type="submit"
              class="btn btn-primary"
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
            <router-link to="/login" class="btn btn-secondary">
              {{ $t('resetPassword.backToLogin') }}
            </router-link>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'
import { passwordReset } from '@/services/passwordResetService'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

// Form data
const newPassword = ref('')
const confirmPassword = ref('')
const showNewPassword = ref(false)
const showConfirmPassword = ref(false)
const resetLoading = ref(false)

// Get token from query params
const token = route.query.token

// Password validation regex (same as backend)
const passwordRegex =
  /^(?=.*[A-Z])(?=.*\d)(?=.*[ !"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~])[A-Za-z\d !"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]{8,}$/

// Computed properties
const isNewPasswordValid = computed(() => {
  if (!newPassword.value) return true
  return passwordRegex.test(newPassword.value)
})

const isPasswordMatch = computed(() => {
  if (!confirmPassword.value) return true
  return newPassword.value === confirmPassword.value
})

// Methods
const toggleNewPasswordVisibility = () => {
  showNewPassword.value = !showNewPassword.value
}

const toggleConfirmPasswordVisibility = () => {
  showConfirmPassword.value = !showConfirmPassword.value
}

const submitResetForm = async () => {
  if (!isNewPasswordValid.value || !isPasswordMatch.value) {
    return
  }

  resetLoading.value = true

  try {
    await passwordReset.confirmPasswordReset({
      token: token,
      new_password: newPassword.value
    })

    // Redirect to login with success message
    router.push('/login?passwordResetSuccess=true')
  } catch (error) {
    if (error.toString().includes('400')) {
      push.error(t('resetPassword.invalidOrExpiredToken'))
    } else {
      push.error(`${t('resetPassword.resetError')} - ${error}`)
    }
  } finally {
    resetLoading.value = false
  }
}

onMounted(() => {
  // Check if token is provided
  if (!token) {
    router.push('/login?passwordResetInvalidLink=true')
  }
})
</script>
