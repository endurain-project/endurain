<template>
  <div class="bg-body-tertiary shadow-sm rounded p-3">
    <div class="row justify-content-center align-items-center">
      <div class="col d-none d-lg-block">
        <img
          width="auto"
          height="auto"
          :src="loginPhotoUrl"
          alt="Square signup image"
          class="img-fluid rounded"
          v-if="serverSettingsStore.serverSettings.login_photo_set"
        />
        <img
          width="auto"
          height="auto"
          src="/src/assets/login.png"
          alt="Square signup image"
          class="img-fluid rounded"
          v-else
        />
      </div>
      <div class="col form-signin text-center m-3">
        <form @submit.prevent="submitForm">
          <h1>Create Account</h1>
          <p>{{ $t('signupView.subtitle') }}</p>
          <br />

          <!-- Name field -->
          <div class="form-floating mb-3">
            <input
              type="text"
              class="form-control"
              id="name"
              :class="{ 'is-invalid': errors.name }"
              :placeholder="$t('signupView.name')"
              v-model="formData.name"
              required
            />
            <label for="name">{{ $t('signupView.name') }}</label>
            <div class="invalid-feedback" v-if="errors.name">{{ errors.name }}</div>
          </div>

          <!-- Username field -->
          <div class="form-floating mb-3">
            <input
              type="text"
              class="form-control"
              id="username"
              :class="{ 'is-invalid': errors.username }"
              :placeholder="$t('signupView.username')"
              v-model="formData.username"
              required
            />
            <label for="username">{{ $t('signupView.username') }}</label>
            <div class="invalid-feedback" v-if="errors.username">{{ errors.username }}</div>
          </div>

          <!-- Email field -->
          <div class="form-floating mb-3">
            <input
              type="email"
              class="form-control"
              id="email"
              :class="{ 'is-invalid': errors.email }"
              :placeholder="$t('signupView.email')"
              v-model="formData.email"
              required
            />
            <label for="email">{{ $t('signupView.email') }}</label>
            <div class="invalid-feedback" v-if="errors.email">{{ errors.email }}</div>
          </div>

          <!-- Password field -->
          <div class="form-floating position-relative mb-3">
            <input
              :type="showPassword ? 'text' : 'password'"
              class="form-control"
              id="password"
              :class="{ 'is-invalid': errors.password }"
              :placeholder="$t('signupView.password')"
              v-model="formData.password"
              required
            />
            <label for="password">{{ $t('signupView.password') }}</label>
            <button
              type="button"
              class="btn position-absolute top-50 end-0 translate-middle-y me-2"
              @click="togglePasswordVisibility"
            >
              <font-awesome-icon :icon="showPassword ? ['fas', 'eye-slash'] : ['fas', 'eye']" />
            </button>
            <div class="invalid-feedback" v-if="errors.password">{{ errors.password }}</div>
          </div>

          <!-- Optional fields section -->
          <div class="mb-3">
            <button
              type="button"
              class="btn btn-link"
              @click="showOptionalFields = !showOptionalFields"
            >
              {{ showOptionalFields ? 'Hide' : 'Show' }} Optional Fields
            </button>
          </div>

          <div v-if="showOptionalFields">
            <!-- City field -->
            <div class="form-floating mb-3">
              <input
                type="text"
                class="form-control"
                id="city"
                :placeholder="$t('signupView.city')"
                v-model="formData.city"
              />
              <label for="city">{{ $t('signupView.city') }}</label>
            </div>

            <!-- Birth date field -->
            <div class="form-floating mb-3">
              <input
                type="date"
                class="form-control"
                id="birthdate"
                :placeholder="$t('signupView.birthdate')"
                v-model="formData.birthdate"
              />
              <label for="birthdate">{{ $t('signupView.birthdate') }}</label>
            </div>

            <!-- Gender field -->
            <div class="form-floating mb-3">
              <select class="form-select" id="gender" v-model="formData.gender">
                <option value="1">{{ $t('signupView.male') }}</option>
                <option value="2">{{ $t('signupView.female') }}</option>
                <option value="3">{{ $t('signupView.unspecified') }}</option>
              </select>
              <label for="gender">{{ $t('signupView.gender') }}</label>
            </div>

            <!-- Units field -->
            <div class="form-floating mb-3">
              <select class="form-select" id="units" v-model="formData.units">
                <option value="1">{{ $t('signupView.metric') }}</option>
                <option value="2">{{ $t('signupView.imperial') }}</option>
              </select>
              <label for="units">{{ $t('signupView.units') }}</label>
            </div>

            <!-- Height field -->
            <div class="form-floating mb-3">
              <input
                type="number"
                class="form-control"
                id="height"
                :placeholder="$t('signupView.height')"
                v-model="formData.height"
                min="0"
              />
              <label for="height">{{ $t('signupView.height') }}</label>
            </div>
          </div>

          <button class="w-100 btn btn-lg btn-primary mb-3" type="submit" :disabled="loading">
            <span
              v-if="loading"
              class="spinner-border spinner-border-sm me-2"
              role="status"
              aria-hidden="true"
            ></span>
            {{ $t('signupView.signUpButton') }}
          </button>

          <div class="text-center">
            <router-link
              to="/login"
              class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
            >
              {{ $t('signupView.alreadyHaveAccount') }}
            </router-link>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { session } from '@/services/sessionService'

// Variables
const router = useRouter()
const { t } = useI18n()
const serverSettingsStore = useServerSettingsStore()
const loading = ref(false)
const showPassword = ref(false)
const showOptionalFields = ref(false)

const loginPhotoUrl = computed(() =>
  serverSettingsStore.serverSettings.login_photo_set
    ? `${window.env.ENDURAIN_HOST}/server_images/login.png`
    : null
)

// Form data
const formData = reactive({
  name: '',
  username: '',
  email: '',
  password: '',
  city: '',
  birthdate: '',
  gender: 1,
  units: 1,
  height: null,
  preferred_language: 'en',
  first_day_of_week: 1,
  currency: 1
})

// Form errors
const errors = ref({})

// Toggle password visibility
const togglePasswordVisibility = () => {
  showPassword.value = !showPassword.value
}

// Validate form
const validateForm = () => {
  const newErrors = {}

  if (!formData.name.trim()) {
    newErrors.name = t('signupView.errorNameRequired')
  }

  if (!formData.username.trim()) {
    newErrors.username = t('signupView.errorUsernameRequired')
  }

  if (!formData.email.trim()) {
    newErrors.email = t('signupView.errorEmailRequired')
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
    newErrors.email = t('signupView.errorEmailInvalid')
  }

  if (!formData.password) {
    newErrors.password = t('signupView.errorPasswordRequired')
  } else if (formData.password.length < 8) {
    newErrors.password = t('signupView.errorPasswordTooShort')
  }

  errors.value = newErrors
  return Object.keys(newErrors).length === 0
}

// Handle form submission
const submitForm = async () => {
  if (!validateForm()) {
    return
  }

  try {
    loading.value = true

    // Prepare data for submission
    const signupData = { ...formData }
    
    // Convert numeric fields to integers
    signupData.gender = parseInt(signupData.gender)
    signupData.units = parseInt(signupData.units)
    signupData.height = signupData.height ? parseInt(signupData.height) : null

    const response = await session.signUp(signupData)

    push.success(response.message)

    // Redirect to login with appropriate query parameters
    const queryParams = {}
    if (response.email_verification_required) {
      queryParams.emailVerificationSent = 'true'
    }
    if (response.admin_approval_required) {
      queryParams.adminApprovalRequired = 'true'
    }

    router.push({ name: 'login', query: queryParams })
  } catch (error) {
    if (error.toString().includes('409')) {
      push.error(t('signupView.errorUserExists'))
    } else if (error.toString().includes('403')) {
      push.error(t('signupView.errorSignupDisabled'))
    } else if (error.toString().includes('400')) {
      push.error(t('signupView.errorValidation'))
    } else {
      push.error(`${t('signupView.errorGeneral')} - ${error}`)
    }
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  // Check if signup is enabled
  if (!serverSettingsStore.serverSettings.signup_enabled) {
    push.error(t('signupView.signupDisabled'))
    router.push('/login')
  }
})
</script>