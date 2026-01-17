<template>
  <div class="bg-body-tertiary shadow-sm rounded p-3">
    <div class="row justify-content-center align-items-center">
      <div class="col d-none d-lg-block">
        <img
          width="auto"
          height="auto"
          :src="loginPhotoUrl"
          alt="Endurain sign up illustration"
          class="img-fluid rounded"
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
                <option value="sv">{{ $t('generalItems.languageOption13') }}</option>
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
                <option value="male">{{ $t('generalItems.genderMale') }}</option>
                <option value="female">{{ $t('generalItems.genderFemale') }}</option>
                <option value="unspecified">{{ $t('generalItems.genderUnspecified') }}</option>
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
                <option value="sunday">{{ $t('generalItems.firstDayOfWeekOption0') }}</option>
                <option value="monday">{{ $t('generalItems.firstDayOfWeekOption1') }}</option>
                <option value="tuesday">{{ $t('generalItems.firstDayOfWeekOption2') }}</option>
                <option value="wednesday">{{ $t('generalItems.firstDayOfWeekOption3') }}</option>
                <option value="thursday">{{ $t('generalItems.firstDayOfWeekOption4') }}</option>
                <option value="friday">{{ $t('generalItems.firstDayOfWeekOption5') }}</option>
                <option value="saturday">{{ $t('generalItems.firstDayOfWeekOption6') }}</option>
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

<script setup lang="ts">
/**
 * User registration view with form validation and optional profile fields.
 * Handles user signup with required and optional information including personal details,
 * preferences, and physical attributes. Supports both metric and imperial unit systems.
 */

import { ref, computed, onMounted, type Ref, type ComputedRef } from 'vue'
import { useRouter, type Router } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { signUp as signUpService } from '@/services/signUpService'
import { cmToFeetInches, feetAndInchesToCm } from '@/utils/unitsUtils'
import {
  isValidEmail,
  sanitizeInput,
  isValidPassword,
  buildPasswordRequirements
} from '@/utils/validationUtils'
import { HTTP_STATUS, QUERY_PARAM_TRUE, extractStatusCode } from '@/constants/httpConstants'
import type { ErrorWithResponse } from '@/types'
import defaultLoginImage from '@/assets/login.png'

/**
 * User signup request data structure.
 *
 * @property name - User's full name.
 * @property username - Unique username (lowercase).
 * @property email - User's email address (lowercase).
 * @property password - User's password.
 * @property preferred_language - Preferred language code (e.g., 'us', 'pt', 'es').
 * @property city - User's city of residence.
 * @property birthdate - User's birth date in ISO format.
 * @property gender - Gender identifier (male, female, unspecified).
 * @property units - Unit system preference (1=metric, 2=imperial).
 * @property height - User's height in centimeters.
 * @property first_day_of_week - First day of week (sunday, monday, etc.).
 * @property currency - Currency preference (1=Euro, 2=Dollar, 3=Pound).
 */
interface SignUpRequestData {
  name: string
  username: string
  email: string
  password: string
  preferred_language: string
  city: string | null
  birthdate: string | null
  gender: string
  units: number
  height: number | null
  first_day_of_week: string
  currency: number
}

/**
 * Signup API response structure.
 *
 * @property email_verification_required - Whether email verification is required.
 * @property admin_approval_required - Whether admin approval is required.
 */
interface SignUpResponse {
  email_verification_required: boolean
  admin_approval_required: boolean
}

/**
 * Login route query parameters for post-signup redirect.
 *
 * @property emailVerificationSent - Email verification status flag.
 * @property adminApprovalRequired - Admin approval status flag.
 */
interface LoginQueryParams {
  emailVerificationSent?: string
  adminApprovalRequired?: string
  [key: string]: string | undefined
}

const router: Router = useRouter()
const { t } = useI18n()
const serverSettingsStore = useServerSettingsStore()

/** Loading state during form submission. */
const isLoading = ref(false)

/** User's full name. */
const signUpName = ref('')

/** User's username. */
const signUpUsername = ref('')

/** User's email address. */
const signUpEmail = ref('')

/** User's password. */
const signUpPassword = ref('')

/** User's preferred language. */
const signUpPreferredLanguage = ref('us')

/** User's city. */
const signUpCity = ref('')

/** User's birth date. */
const signUpBirthdate = ref('')

/** User's gender (male, female, unspecified). */
const signUpGender = ref('male')

/** User's unit preference (1=metric, 2=imperial). */
const signUpUnits = ref(Number(serverSettingsStore.serverSettings.units))

/** User's height in centimeters. */
const signUpHeightCms = ref<number | null>(null)

/** User's height in feet (imperial). */
const signUpHeightFeet = ref<number | null>(null)

/** User's height in inches (imperial). */
const signUpHeightInches = ref<number | null>(null)

/** First day of week preference (sunday, monday, etc.). */
const signUpFirstDayOfWeek = ref('monday')

/** Currency preference (1=Euro, 2=Dollar, 3=Pound). */
const signUpCurrency = ref(Number(serverSettingsStore.serverSettings.currency))

/** Password visibility toggle state. */
const showPassword = ref(false)

/** Optional fields section visibility state. */
const showOptionalFields = ref(false)

/**
 * Validates feet input for imperial height.
 *
 * @returns `true` if feet value is between 0 and 10, or `null`.
 */
const isFeetValid = computed(() => {
  if (signUpHeightFeet.value === null) return true
  return signUpHeightFeet.value >= 0 && signUpHeightFeet.value <= 10
})

/**
 * Validates inches input for imperial height.
 *
 * @returns `true` if inches value is between 0 and 11, or `null`.
 */
const isInchesValid = computed(() => {
  if (signUpHeightInches.value === null) return true
  return signUpHeightInches.value >= 0 && signUpHeightInches.value <= 11
})

/**
 * Validates email format using RFC 5322 compliant regex.
 *
 * @returns `true` if email is valid or empty.
 */
const isEmailValid = computed(() => {
  if (!signUpEmail.value) return true
  return isValidEmail(signUpEmail.value)
})

/**
 * Validates password strength using centralized validation.
 * Applies password requirements based on server settings and policy type.
 *
 * @returns `true` if password meets server-configured requirements or is empty.
 */
const isPasswordValid = computed(() => {
  if (!signUpPassword.value) return true

  const passwordType = serverSettingsStore.serverSettings.password_type
  const minLength = serverSettingsStore.serverSettings.password_length_regular_users
  const requirements = buildPasswordRequirements(passwordType, minLength)

  return isValidPassword(signUpPassword.value, requirements)
})

/**
 * Computes the login photo URL from server settings.
 *
 * @returns Custom photo URL from server if set, otherwise default image.
 */
const loginPhotoUrl = computed(() => {
  return serverSettingsStore.serverSettings.login_photo_set
    ? `${window.env.ENDURAIN_HOST}/server_images/login.png`
    : defaultLoginImage
})

/**
 * Toggles password visibility between plain text and masked.
 *
 * @returns void
 */
const togglePasswordVisibility = (): void => {
  showPassword.value = !showPassword.value
}

// ============================================================================
// Methods - Form Submission
// ============================================================================

/**
 * Handles form submission for user signup.
 * Converts height units, sanitizes inputs, submits data, and redirects on success.
 *
 * @returns A promise that resolves when signup is complete.
 * @throws {ErrorWithResponse} When signup fails or validation errors occur.
 */
const submitForm = async (): Promise<void> => {
  // Convert height units based on server settings
  if (Number(serverSettingsStore.serverSettings.units) === 1) {
    // Metric system: convert cm to feet/inches for storage
    if (signUpHeightCms.value !== null) {
      const { feet, inches } = cmToFeetInches(signUpHeightCms.value)
      signUpHeightFeet.value = feet
      signUpHeightInches.value = inches
    }
  } else {
    // Imperial system: convert feet/inches to cm for storage
    if (signUpHeightFeet.value !== null && signUpHeightInches.value !== null) {
      const heightInCm = feetAndInchesToCm(signUpHeightFeet.value, signUpHeightInches.value)
      signUpHeightCms.value = Number(heightInCm)
    }
  }

  try {
    isLoading.value = true

    // Sanitize and prepare data for submission
    const data: SignUpRequestData = {
      name: sanitizeInput(signUpName.value),
      username: sanitizeInput(signUpUsername.value.toLowerCase()),
      email: sanitizeInput(signUpEmail.value.toLowerCase()),
      password: signUpPassword.value, // Don't sanitize password
      preferred_language: signUpPreferredLanguage.value,
      city: signUpCity.value ? sanitizeInput(signUpCity.value) : null,
      birthdate: signUpBirthdate.value || null,
      gender: signUpGender.value,
      units: signUpUnits.value,
      height: signUpHeightCms.value,
      first_day_of_week: signUpFirstDayOfWeek.value,
      currency: signUpCurrency.value
    }

    const response: SignUpResponse = await signUpService.signUpRequest(data)

    push.success(t('signupView.success'))

    // Build query parameters for login redirect
    const queryParams: LoginQueryParams = {}
    if (response.email_verification_required) {
      queryParams.emailVerificationSent = QUERY_PARAM_TRUE
    }
    if (response.admin_approval_required) {
      queryParams.adminApprovalRequired = QUERY_PARAM_TRUE
    }

    await router.push({ name: 'login', query: queryParams })
  } catch (error) {
    handleSignUpError(error as ErrorWithResponse)
  } finally {
    isLoading.value = false
  }
}

/**
 * Handles signup errors and displays appropriate error messages.
 *
 * @param error - Error object with response data.
 * @returns void
 */
const handleSignUpError = (error: ErrorWithResponse): void => {
  const statusCode = extractStatusCode(error)

  switch (statusCode) {
    case HTTP_STATUS.CONFLICT:
      push.error(t('signupView.errorUserExists'))
      break
    case HTTP_STATUS.FORBIDDEN:
      push.error(t('signupView.errorSignupDisabled'))
      break
    case HTTP_STATUS.BAD_REQUEST:
      push.error(t('signupView.errorValidation'))
      break
    default:
      push.error(`${t('signupView.errorGeneral')} - ${error}`)
  }
}

// ============================================================================
// Lifecycle Hooks
// ============================================================================

/**
 * Component mounted lifecycle hook.
 * Checks if signup is enabled and redirects to login if disabled.
 *
 * @returns void
 */
onMounted(() => {
  if (!serverSettingsStore.serverSettings.signup_enabled) {
    push.error(t('signupView.signupDisabled'))
    router.push('/login')
  }
})
</script>
