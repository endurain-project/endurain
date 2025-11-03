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

<script setup lang="ts">
/**
 * @fileoverview SignUpView Component
 *
 * User registration view with comprehensive form validation and optional profile fields.
 * Handles user signup with required and optional information including personal details,
 * preferences, and physical attributes. Supports both metric and imperial unit systems.
 *
 * @component
 * @example
 * <SignUpView />
 */

// ============================================================================
// Imports
// ============================================================================
import { ref, computed, onMounted, type Ref, type ComputedRef } from 'vue'
import { useRouter, type Router } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { signUp as signUpService } from '@/services/signUpService'
import { cmToFeetInches, feetAndInchesToCm } from '@/utils/unitsUtils'
import { isValidEmail, sanitizeInput, isValidPassword } from '@/utils/validationUtils'
import { HTTP_STATUS, QUERY_PARAM_TRUE, extractStatusCode } from '@/constants/httpConstants'
import type { ErrorWithResponse } from '@/types'
import defaultLoginImage from '@/assets/login.png'

// ============================================================================
// Interfaces
// ============================================================================

/**
 * User signup request data structure
 * @interface SignUpRequestData
 */
interface SignUpRequestData {
  /** User's full name */
  name: string
  /** Unique username (lowercase) */
  username: string
  /** User's email address (lowercase) */
  email: string
  /** User's password */
  password: string
  /** Preferred language code (e.g., 'us', 'pt', 'es') */
  preferred_language: string
  /** User's city of residence */
  city: string | null
  /** User's birth date in ISO format */
  birthdate: string | null
  /** Gender identifier (1=male, 2=female, 3=unspecified) */
  gender: number
  /** Unit system preference (1=metric, 2=imperial) */
  units: number
  /** User's height in centimeters */
  height: number | null
  /** First day of week (0=Sunday, 1=Monday, etc.) */
  first_day_of_week: number
  /** Currency preference (1=Euro, 2=Dollar, 3=Pound) */
  currency: number
}

/**
 * Signup API response structure
 * @interface SignUpResponse
 */
interface SignUpResponse {
  /** Whether email verification is required */
  email_verification_required: boolean
  /** Whether admin approval is required */
  admin_approval_required: boolean
}

/**
 * Login route query parameters for post-signup redirect
 * @interface LoginQueryParams
 */
interface LoginQueryParams {
  /** Email verification status flag */
  emailVerificationSent?: string
  /** Admin approval status flag */
  adminApprovalRequired?: string
  /** Index signature for Vue Router compatibility */
  [key: string]: string | undefined
}

// ============================================================================
// Composables & Stores
// ============================================================================
const router: Router = useRouter()
const { t } = useI18n()
const serverSettingsStore = useServerSettingsStore()

// ============================================================================
// Reactive State - Form Data
// ============================================================================

/** Loading state during form submission */
const isLoading: Ref<boolean> = ref(false)

/** User's full name */
const signUpName: Ref<string> = ref('')

/** User's username */
const signUpUsername: Ref<string> = ref('')

/** User's email address */
const signUpEmail: Ref<string> = ref('')

/** User's password */
const signUpPassword: Ref<string> = ref('')

/** User's preferred language */
const signUpPreferredLanguage: Ref<string> = ref('us')

/** User's city */
const signUpCity: Ref<string> = ref('')

/** User's birth date */
const signUpBirthdate: Ref<string> = ref('')

/** User's gender (1=male, 2=female, 3=unspecified) */
const signUpGender: Ref<number> = ref(1)

/** User's unit preference (1=metric, 2=imperial) */
const signUpUnits: Ref<number> = ref(Number(serverSettingsStore.serverSettings.units))

/** User's height in centimeters */
const signUpHeightCms: Ref<number | null> = ref(null)

/** User's height in feet (imperial) */
const signUpHeightFeet: Ref<number | null> = ref(null)

/** User's height in inches (imperial) */
const signUpHeightInches: Ref<number | null> = ref(null)

/** First day of week preference (0=Sunday, 1=Monday, etc.) */
const signUpFirstDayOfWeek: Ref<number> = ref(1)

/** Currency preference (1=Euro, 2=Dollar, 3=Pound) */
const signUpCurrency: Ref<number> = ref(Number(serverSettingsStore.serverSettings.currency))

// ============================================================================
// Reactive State - UI State
// ============================================================================

/** Password visibility toggle state */
const showPassword: Ref<boolean> = ref(false)

/** Optional fields section visibility state */
const showOptionalFields: Ref<boolean> = ref(false)

// ============================================================================
// Computed Properties - Validation
// ============================================================================

/**
 * Validates feet input for imperial height
 * Range: 0-10 feet
 */
const isFeetValid: ComputedRef<boolean> = computed(() => {
  if (signUpHeightFeet.value === null) return true
  return signUpHeightFeet.value >= 0 && signUpHeightFeet.value <= 10
})

/**
 * Validates inches input for imperial height
 * Range: 0-11 inches
 */
const isInchesValid: ComputedRef<boolean> = computed(() => {
  if (signUpHeightInches.value === null) return true
  return signUpHeightInches.value >= 0 && signUpHeightInches.value <= 11
})

/**
 * Validates email format using RFC 5322 compliant regex
 */
const isEmailValid: ComputedRef<boolean> = computed(() => {
  if (!signUpEmail.value) return true
  return isValidEmail(signUpEmail.value)
})

/**
 * Validates password strength using centralized validation
 * Requirements: min 8 chars, 1 uppercase, 1 digit, 1 special character
 */
const isPasswordValid: ComputedRef<boolean> = computed(() => {
  if (!signUpPassword.value) return true
  return isValidPassword(signUpPassword.value)
})

/**
 * Compute the login photo URL from server settings
 * Returns custom photo from server if set, otherwise default image
 */
const loginPhotoUrl: ComputedRef<string> = computed(() => {
  return serverSettingsStore.serverSettings.login_photo_set
    ? `${window.env.ENDURAIN_HOST}/server_images/login.png`
    : defaultLoginImage
})

// ============================================================================
// Methods - UI Interactions
// ============================================================================

/**
 * Toggles password visibility between plain text and masked
 */
const togglePasswordVisibility = (): void => {
  showPassword.value = !showPassword.value
}

// ============================================================================
// Methods - Form Submission
// ============================================================================

/**
 * Handles form submission for user signup
 * Converts height units, sanitizes inputs, submits data, and redirects on success
 *
 * @async
 * @throws {Error} When signup fails or validation errors occur
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
 * Handles signup errors and displays appropriate error messages
 *
 * @param {ErrorWithResponse} error - Error object with response data
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
 * Component mounted lifecycle hook
 * Checks if signup is enabled and redirects to login if disabled
 */
onMounted(() => {
  if (!serverSettingsStore.serverSettings.signup_enabled) {
    push.error(t('signupView.signupDisabled'))
    router.push('/login')
  }
})
</script>
