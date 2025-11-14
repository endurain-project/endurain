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
      <div class="col form-signin m-3">
        <form @submit.prevent="submitForm">
          <h1>{{ $t('signupView.title') }}</h1>
          <p>{{ $t('signupView.subtitle') }}</p>
          <br />

          <!-- Name field -->
          <div class="form-floating mb-3">
            <input
              type="text"
              class="form-control"
              id="name"
              :placeholder="$t('signupView.name')"
              v-model="signUpName"
              required
            />
            <label for="name">* {{ $t('signupView.name') }}</label>
          </div>

          <!-- Username field -->
          <div class="form-floating mb-3">
            <input
              type="text"
              class="form-control"
              id="username"
              :placeholder="$t('signupView.username')"
              v-model="signUpUsername"
              required
            />
            <label for="username">* {{ $t('signupView.username') }}</label>
          </div>

          <!-- Email field -->
          <div class="form-floating mb-3">
            <input
              type="email"
              class="form-control"
              id="validationEmail"
              aria-describedby="validationEmailFeedback"
              :class="{ 'is-invalid': !isEmailValid }"
              :placeholder="$t('signupView.email')"
              v-model="signUpEmail"
              required
            />
            <label for="email">* {{ $t('signupView.email') }}</label>
            <div id="validationEmailFeedback" class="invalid-feedback" v-if="!isEmailValid">
              {{ $t('usersAddEditUserModalComponent.addEditUserModalErrorEmailInvalid') }}
            </div>
          </div>

          <!-- Password field -->
          <div class="form-floating mb-3 position-relative">
            <input
              :type="showPassword ? 'text' : 'password'"
              class="form-control"
              :class="{ 'is-invalid': !isPasswordValid }"
              id="validationPassword"
              aria-describedby="validationPasswordFeedback"
              name="signUpPassword"
              :placeholder="$t('signupView.password')"
              v-model="signUpPassword"
              required
            />
            <label for="signUpPassword">* {{ $t('signupView.password') }}</label>
            <button
              type="button"
              class="btn position-absolute top-50 end-0 translate-middle-y"
              :class="{ 'me-4': !isPasswordValid }"
              @click="togglePasswordVisibility"
            >
              <font-awesome-icon :icon="showPassword ? ['fas', 'eye-slash'] : ['fas', 'eye']" />
            </button>
          </div>
          <div
            id="validationPasswordFeedback"
            class="invalid-feedback d-block"
            v-if="!isPasswordValid"
          >
            {{ $t('usersAddEditUserModalComponent.addEditUserModalErrorPasswordInvalid') }}
          </div>

          <!-- Optional fields section -->
          <div class="mb-3">
            <button
              type="button"
              class="btn btn-link"
              @click="showOptionalFields = !showOptionalFields"
            >
              {{ showOptionalFields ? 'Hide' : 'Show' }}{{ $t('signupView.optionalFields') }}
            </button>
          </div>

          <div v-if="showOptionalFields">
            <!-- Preferred language -->
            <div class="form-floating mb-3">
              <select
                class="form-select"
                name="preferredLanguage"
                v-model="signUpPreferredLanguage"
                required
              >
                <option value="ca">{{ $t('generalItems.languageOption2') }}</option>
                <option value="cn">{{ $t('generalItems.languageOption8') }}</option>
                <option value="tw">{{ $t('generalItems.languageOption9') }}</option>
                <option value="de">{{ $t('generalItems.languageOption4') }}</option>
                <option value="fr">{{ $t('generalItems.languageOption5') }}</option>
                <option value="gl">{{ $t('generalItems.languageOption10') }}</option>
                <option value="it">{{ $t('generalItems.languageOption11') }}</option>
                <option value="nl">{{ $t('generalItems.languageOption6') }}</option>
                <option value="pt">{{ $t('generalItems.languageOption3') }}</option>
                <option value="sl">{{ $t('generalItems.languageOption12') }}</option>
                <option value="es">{{ $t('generalItems.languageOption7') }}</option>
                <option value="us">{{ $t('generalItems.languageOption1') }}</option>
              </select>
              <label for="preferredLanguage"> {{ $t('signupView.preferredLanguage') }}</label>
            </div>
            <!-- City field -->
            <div class="form-floating mb-3">
              <input
                type="text"
                class="form-control"
                id="city"
                :placeholder="$t('signupView.city')"
                v-model="signUpCity"
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
                v-model="signUpBirthdate"
              />
              <label for="birthdate">{{ $t('signupView.birthdate') }}</label>
            </div>

            <!-- Gender field -->
            <div class="form-floating mb-3">
              <select class="form-select" id="gender" v-model="signUpGender">
                <option value="1">{{ $t('generalItems.genderMale') }}</option>
                <option value="2">{{ $t('generalItems.genderFemale') }}</option>
                <option value="3">{{ $t('generalItems.genderUnspecified') }}</option>
              </select>
              <label for="gender">{{ $t('signupView.gender') }}</label>
            </div>

            <!-- Units field -->
            <div class="form-floating mb-3">
              <select class="form-select" id="units" v-model="signUpUnits">
                <option value="1">{{ $t('signupView.metric') }}</option>
                <option value="2">{{ $t('signupView.imperial') }}</option>
              </select>
              <label for="units">{{ $t('signupView.units') }}</label>
            </div>

            <!-- Height field -->
            <!-- metric -->
            <div
              class="input-group mb-3"
              v-if="Number(serverSettingsStore.serverSettings.units) === 1"
            >
              <div class="form-floating flex-grow-1">
                <input
                  type="number"
                  class="form-control"
                  name="signUpHeightCms"
                  :placeholder="$t('signupView.height')"
                  v-model="signUpHeightCms"
                />
                <label for="signUpHeightCms">
                  {{ $t('signupView.height') }}
                </label>
              </div>
              <span class="input-group-text">{{ $t('generalItems.unitsCm') }}</span>
            </div>
            <!-- imperial -->
            <div class="input-group mb-3" v-else>
              <div class="form-floating flex-grow-1">
                <input
                  class="form-control"
                  :class="{ 'is-invalid': !isFeetValid }"
                  type="number"
                  aria-describedby="validationFeetFeedback"
                  name="signUpHeightFeet"
                  :placeholder="$t('signupView.height')"
                  v-model="signUpHeightFeet"
                  min="0"
                  max="10"
                  step="1"
                />
                <label for="signUpHeightFeet">
                  {{ $t('signupView.height') }}
                </label>
              </div>
              <span class="input-group-text">{{ $t('generalItems.unitsFeet') }}</span>
              <div class="form-floating flex-grow-1">
                <input
                  class="form-control"
                  :class="{ 'is-invalid': !isInchesValid }"
                  type="number"
                  aria-describedby="validationInchesFeedback"
                  name="signUpHeightInches"
                  :placeholder="$t('signupView.height')"
                  v-model="signUpHeightInches"
                  min="0"
                  max="11"
                  step="1"
                />
                <label for="signUpHeightInches">
                  {{ $t('signupView.height') }}
                </label>
              </div>
              <span class="input-group-text">{{ $t('generalItems.unitsInches') }}</span>
              <div id="validationFeetFeedback" class="invalid-feedback d-block" v-if="!isFeetValid">
                {{ $t('usersAddEditUserModalComponent.addEditUserModalFeetValidationLabel') }}
              </div>
              <div
                id="validationInchesFeedback"
                class="invalid-feedback d-block"
                v-if="!isInchesValid"
              >
                {{ $t('usersAddEditUserModalComponent.addEditUserModalInchesValidationLabel') }}
              </div>
            </div>
            <!-- first day of the week -->
            <div class="form-floating mb-3">
              <select
                class="form-select"
                name="firstDayOfWeek"
                v-model="signUpFirstDayOfWeek"
                required
              >
                <option :value="0">{{ $t('generalItems.firstDayOfWeekOption0') }}</option>
                <option :value="1">{{ $t('generalItems.firstDayOfWeekOption1') }}</option>
                <option :value="2">{{ $t('generalItems.firstDayOfWeekOption2') }}</option>
                <option :value="3">{{ $t('generalItems.firstDayOfWeekOption3') }}</option>
                <option :value="4">{{ $t('generalItems.firstDayOfWeekOption4') }}</option>
                <option :value="5">{{ $t('generalItems.firstDayOfWeekOption5') }}</option>
                <option :value="6">{{ $t('generalItems.firstDayOfWeekOption6') }}</option>
              </select>
              <label for="firstDayOfWeek">{{ $t('signupView.firstDayOfWeek') }}</label>
            </div>
            <!-- currency field -->
            <div class="form-floating mb-3">
              <select class="form-select" name="currency" v-model="signUpCurrency" required>
                <option :value="1">{{ $t('generalItems.currencyEuro') }}</option>
                <option :value="2">{{ $t('generalItems.currencyDollar') }}</option>
                <option :value="3">{{ $t('generalItems.currencyPound') }}</option>
              </select>
              <label for="currency">{{ $t('signupView.currency') }}</label>
            </div>
          </div>

          <p>* {{ $t('generalItems.requiredField') }}</p>

          <button class="w-100 btn btn-lg btn-primary mb-3" type="submit" :disabled="isLoading">
            <span
              v-if="isLoading"
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
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { signUp as signUpService } from '@/services/signUpService'
import { cmToFeetInches, feetAndInchesToCm } from '@/utils/unitsUtils'

// Variables
const router = useRouter()
const { t } = useI18n()
const serverSettingsStore = useServerSettingsStore()
const isLoading = ref(false)
const signUpName = ref(null)
const signUpUsername = ref(null)
const signUpEmail = ref(null)
const signUpPassword = ref(null)
const signUpPreferredLanguage = ref('us')
const signUpCity = ref(null)
const signUpBirthdate = ref(null)
const signUpGender = ref(1)
const signUpUnits = ref(serverSettingsStore.serverSettings.units)
const signUpHeightCms = ref(null)
const signUpHeightFeet = ref(null)
const signUpHeightInches = ref(null)
const signUpFirstDayOfWeek = ref(1)
const signUpCurrency = ref(serverSettingsStore.serverSettings.currency)
const isFeetValid = computed(() => signUpHeightFeet.value >= 0 && signUpHeightFeet.value <= 10)
const isInchesValid = computed(
  () => signUpHeightInches.value >= 0 && signUpHeightInches.value <= 11
)
const isEmailValid = computed(() => {
  if (!signUpEmail.value) return true
  const emailRegex = /^[^\s@]{1,}@[^\s@]{2,}\.[^\s@]{2,}$/
  return emailRegex.test(signUpEmail.value)
})
const showPassword = ref(false)
// Toggle password visibility
const togglePasswordVisibility = () => {
  showPassword.value = !showPassword.value
}
const isPasswordValid = computed(() => {
  if (!signUpPassword.value) return true
  const regex =
    /^(?=.*[A-Z])(?=.*\d)(?=.*[ !\"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~])[A-Za-z\d !"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]{8,}$/
  return regex.test(signUpPassword.value)
})
const showOptionalFields = ref(false)

const loginPhotoUrl = computed(() =>
  serverSettingsStore.serverSettings.login_photo_set
    ? `${window.env.ENDURAIN_HOST}/server_images/login.png`
    : null
)

// Handle form submission
const submitForm = async () => {
  if (Number(serverSettingsStore.serverSettings.units) === 1) {
    const { feet, inches } = cmToFeetInches(signUpHeightCms.value)
    signUpHeightFeet.value = feet
    signUpHeightInches.value = inches
  } else {
    signUpHeightCms.value = feetAndInchesToCm(signUpHeightFeet.value, signUpHeightInches.value)
  }
  try {
    isLoading.value = true

    // Prepare data for submission
    const data = {
      name: signUpName.value,
      username: signUpUsername.value.toLowerCase(),
      email: signUpEmail.value.toLowerCase(),
      password: signUpPassword.value,
      preferred_language: signUpPreferredLanguage.value,
      city: signUpCity.value || null,
      birthdate: signUpBirthdate.value || null,
      gender: signUpGender.value,
      units: signUpUnits.value,
      height: signUpHeightCms.value || null,
      first_day_of_week: signUpFirstDayOfWeek.value,
      currency: signUpCurrency.value
    }

    const response = await signUpService.signUpRequest(data)

    push.success(t('signupView.success'))

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
    isLoading.value = false
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
