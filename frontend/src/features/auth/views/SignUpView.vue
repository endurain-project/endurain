<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronDown, ChevronUp, LoaderCircle } from '@lucide/vue'

import type { SignUpRequest } from '@/features/auth/types'

import AppLogo from '@/components/AppLogo.vue'
import AuthScreenLayout from '@/components/layout/AuthScreenLayout.vue'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { Select } from '@/components/ui/select'
import { useForm } from '@/composables/useForm'
import { usePublicServerSettings } from '@/features/config/composables/usePublicServerSettings'
import { useToasts } from '@/composables/useToasts'
import { HttpError } from '@/services/http'
import { requestSignUp } from '@/features/auth/services/signUp'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import {
  usePasswordConfirmation,
  usePasswordPolicy,
} from '@/features/security/composables/usePasswordPolicy'
import {
  CURRENCY_OPTIONS,
  GENDER_OPTIONS,
  numberRange,
  resolveHeightCm,
  sortLanguageCodes,
  WEEKDAY_OPTIONS,
} from '@/features/users/utils/userFieldOptions'
import { compose, email, required } from '@/utils/validators'

/** Form field shape backing the sign-up form. */
interface SignUpFormValues {
  name: string
  username: string
  email: string
  password: string
  confirmPassword: string
  preferredLanguage: SignUpRequest['preferred_language']
  city: string
  birthdate: string
  gender: SignUpRequest['gender']
  units: SignUpRequest['units']
  currency: SignUpRequest['currency']
  firstDayOfWeek: SignUpRequest['first_day_of_week']
  heightCm: number | null
  heightFeet: number | null
  heightInches: number | null
}

const router = useRouter()
const { t, locale } = useI18n()

const languageCodes = computed(() =>
  sortLanguageCodes((code) => t(`signup.languages.${code}`), locale.value),
)
const { serverSettings, loginImageUrl, load } = usePublicServerSettings()
const toasts = useToasts()

const showOptionalFields = ref(false)

// Sign-up creates a regular account, so the regular policy applies.
const { hint: passwordHint, validate: validatePassword } = usePasswordPolicy('regular')

/**
 * Maps a backend HTTP error to a non-enumerating user-facing message.
 *
 * @param error - Caught sign-up error.
 * @returns Translated error message.
 */
function getSignUpErrorMessage(error: unknown): string {
  if (!(error instanceof HttpError)) {
    return t('signup.errorGeneral')
  }
  switch (error.status) {
    case 409:
      return t('signup.errorUserExists')
    case 403:
      return t('signup.errorSignupDisabled')
    case 400:
    case 422:
      return t('signup.errorValidation')
    case 429:
      return t('signup.errorTooManyAttempts')
    default:
      return t('signup.errorGeneral')
  }
}

/**
 * Builds the payload, requests sign-up, and redirects to login with the
 * appropriate verification/approval flags. Throws a translated message on
 * failure so `useForm` surfaces it via `submitError`.
 *
 * @param formValues - Validated form values.
 */
async function submitForm(formValues: SignUpFormValues): Promise<void> {
  const payload: SignUpRequest = {
    name: formValues.name.trim(),
    username: formValues.username.trim().toLowerCase(),
    email: formValues.email.trim().toLowerCase(),
    password: formValues.password,
    preferred_language: formValues.preferredLanguage,
    city: formValues.city.trim() ? formValues.city.trim() : null,
    birthdate: formValues.birthdate || null,
    gender: formValues.gender,
    units: formValues.units,
    height: resolveHeightCm(formValues),
    first_day_of_week: formValues.firstDayOfWeek,
    currency: formValues.currency,
  }

  try {
    const response = await requestSignUp(payload)

    const query: Record<string, string> = {}
    if (response.email_verification_required) {
      query.emailVerificationSent = 'true'
    }
    if (response.admin_approval_required) {
      query.adminApprovalRequired = 'true'
    }

    toasts.success(t('signup.success'))
    await router.push({ name: 'login', query })
  } catch (error) {
    throw new Error(getSignUpErrorMessage(error))
  }
}

// Validators can't read `values.units` directly: `values` is destructured from
// this same `useForm(...)` call, so referencing it here is a circular reference.
// Mirror the active unit system into a standalone ref the validators can read,
// kept in sync with `values.units` via the watch below.
const activeUnits = ref<SignUpFormValues['units']>('metric')

const { values, errors, isValid, isSubmitting, submitError, handleSubmit, handleBlur } =
  useForm<SignUpFormValues>({
    initialValues: {
      name: '',
      username: '',
      email: '',
      password: '',
      confirmPassword: '',
      preferredLanguage: 'en',
      city: '',
      birthdate: '',
      gender: 'unspecified',
      units: 'metric',
      currency: 'euro',
      firstDayOfWeek: 'monday',
      heightCm: null,
      heightFeet: null,
      heightInches: null,
    },
    validators: {
      name: required(t('signup.requiredField')),
      username: required(t('signup.requiredField')),
      email: compose(required<string>(t('signup.requiredField')), email(t('signup.emailInvalid'))),
      password: compose(required<string>(t('signup.requiredField')), validatePassword),
      // Height is captured per unit system and only the active system's inputs
      // are rendered. Skip the imperial validators in metric mode (and vice
      // versa) so a hidden field's stale value can't silently fail validation
      // and disable submit with no visible error.
      heightFeet: (value: number | null) =>
        activeUnits.value === 'metric' ? null : numberRange(10, t('signup.feetInvalid'))(value),
      heightInches: (value: number | null) =>
        activeUnits.value === 'metric' ? null : numberRange(11, t('signup.inchesInvalid'))(value),
    },
    onSubmit: submitForm,
  })

const isMetric = computed(() => values.units === 'metric')

// A validator can't safely read the sibling `password` field (`values` is
// destructured from this same `useForm(...)` call, so referencing it inside a
// validator here would be a circular reference) — the mismatch is surfaced via
// this computed + the `confirmPasswordError` below instead.
const { matches: passwordsMatch, error: confirmPasswordError } = usePasswordConfirmation(
  () => values.password,
  () => values.confirmPassword,
)

// Keep `activeUnits` in step with the unit selector so the height validators
// re-run against the correct system whenever the user toggles units.
watch(
  () => values.units,
  (units) => {
    activeUnits.value = units
  },
  { immediate: true },
)

onMounted(async () => {
  await load()

  if (!serverSettings.value.signup_enabled) {
    toasts.error(t('signup.signupDisabled'))
    await router.replace({ name: 'login' })
    return
  }

  // Seed unit-dependent defaults from the instance configuration.
  values.units = serverSettings.value.units
  values.currency = serverSettings.value.currency
})
</script>

<template>
  <AuthScreenLayout :image-url="loginImageUrl" :image-alt="t('signup.imageAlt')">
    <form class="mx-auto flex w-full max-w-sm flex-col" novalidate @submit.prevent="handleSubmit">
      <AppLogo width="40" height="40" class="mx-auto mb-3 size-10" />
      <h1 class="text-center text-page-title">
        {{ t('signup.title') }}
      </h1>
      <p class="mt-2 text-center text-body">
        {{ t('signup.subtitle') }}
      </p>

      <Alert v-if="submitError" kind="error" class="mt-5">
        {{ submitError }}
      </Alert>

      <div class="mt-5 flex flex-col gap-3">
        <FormField :label="t('signup.name')" required :error="errors.name">
          <template #default="{ fieldId, describedBy, invalid }">
            <Input
              :id="fieldId"
              v-model="values.name"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              name="name"
              type="text"
              autocomplete="name"
              required
              :disabled="isSubmitting"
              @blur="handleBlur('name')"
            />
          </template>
        </FormField>

        <FormField :label="t('signup.username')" required :error="errors.username">
          <template #default="{ fieldId, describedBy, invalid }">
            <Input
              :id="fieldId"
              v-model="values.username"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              name="username"
              type="text"
              autocomplete="username"
              required
              :disabled="isSubmitting"
              @blur="handleBlur('username')"
            />
          </template>
        </FormField>

        <FormField :label="t('signup.email')" required :error="errors.email">
          <template #default="{ fieldId, describedBy, invalid }">
            <Input
              :id="fieldId"
              v-model="values.email"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              name="email"
              type="email"
              autocomplete="email"
              required
              :disabled="isSubmitting"
              @blur="handleBlur('email')"
            />
          </template>
        </FormField>

        <FormField
          :label="t('signup.password')"
          :placeholder="t('signup.password')"
          required
          :error="errors.password"
        >
          <template #default="{ fieldId, describedBy, invalid, placeholder }">
            <PasswordInput
              :id="fieldId"
              v-model="values.password"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              :placeholder="placeholder"
              name="new-password"
              autocomplete="new-password"
              :disabled="isSubmitting"
              @blur="handleBlur('password')"
            />
            <p class="text-hint">{{ passwordHint }}</p>
          </template>
        </FormField>

        <FormField
          :label="t('signup.confirmPassword')"
          :placeholder="t('signup.confirmPassword')"
          required
          :error="confirmPasswordError"
        >
          <template #default="{ fieldId, describedBy, invalid, placeholder }">
            <PasswordInput
              :id="fieldId"
              v-model="values.confirmPassword"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              :placeholder="placeholder"
              name="confirm-password"
              autocomplete="new-password"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>

        <button
          type="button"
          class="flex items-center gap-1.5 self-start text-meta text-muted-foreground hover:text-foreground"
          :aria-expanded="showOptionalFields"
          @click="showOptionalFields = !showOptionalFields"
        >
          <ChevronUp v-if="showOptionalFields" class="size-4" />
          <ChevronDown v-else class="size-4" />
          <span>{{
            showOptionalFields ? t('signup.hideOptionalFields') : t('signup.showOptionalFields')
          }}</span>
        </button>

        <div v-if="showOptionalFields" class="flex flex-col gap-3">
          <FormField :label="t('signup.preferredLanguage')">
            <template #default="{ fieldId }">
              <Select
                :id="fieldId"
                v-model="values.preferredLanguage"
                name="preferredLanguage"
                :disabled="isSubmitting"
              >
                <option v-for="code in languageCodes" :key="code" :value="code">
                  {{ t(`signup.languages.${code}`) }}
                </option>
              </Select>
            </template>
          </FormField>

          <FormField :label="t('signup.city')">
            <template #default="{ fieldId }">
              <Input
                :id="fieldId"
                v-model="values.city"
                name="city"
                type="text"
                autocomplete="address-level2"
                :disabled="isSubmitting"
              />
            </template>
          </FormField>

          <FormField :label="t('signup.birthdate')">
            <template #default="{ fieldId }">
              <Input
                :id="fieldId"
                v-model="values.birthdate"
                name="birthdate"
                type="date"
                :disabled="isSubmitting"
              />
            </template>
          </FormField>

          <FormField :label="t('signup.gender')">
            <template #default="{ fieldId }">
              <Select :id="fieldId" v-model="values.gender" name="gender" :disabled="isSubmitting">
                <option v-for="value in GENDER_OPTIONS" :key="value" :value="value">
                  {{ t(`signup.genders.${value}`) }}
                </option>
              </Select>
            </template>
          </FormField>

          <FormField :label="t('signup.units')">
            <template #default="{ fieldId }">
              <Select :id="fieldId" v-model="values.units" name="units" :disabled="isSubmitting">
                <option value="metric">{{ t('signup.metric') }}</option>
                <option value="imperial">{{ t('signup.imperial') }}</option>
              </Select>
            </template>
          </FormField>

          <FormField v-if="isMetric" :label="`${t('signup.height')} (${t('signup.unitCm')})`">
            <template #default="{ fieldId }">
              <input
                :id="fieldId"
                v-model.number="values.heightCm"
                :class="inputFieldClass"
                name="heightCm"
                type="number"
                min="0"
                max="300"
                step="1"
                :disabled="isSubmitting"
              />
            </template>
          </FormField>

          <div v-else class="flex flex-col gap-1.5">
            <span class="text-meta font-medium text-foreground">
              {{ t('signup.height') }}
            </span>
            <div class="flex gap-3">
              <FormField class="flex-1" :error="errors.heightFeet">
                <template #default="{ fieldId, describedBy, invalid }">
                  <input
                    :id="fieldId"
                    v-model.number="values.heightFeet"
                    :class="inputFieldClass"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                    :aria-label="`${t('signup.height')} (${t('signup.unitFeet')})`"
                    name="heightFeet"
                    type="number"
                    min="0"
                    max="10"
                    step="1"
                    :placeholder="t('signup.unitFeet')"
                    :disabled="isSubmitting"
                    @blur="handleBlur('heightFeet')"
                  />
                </template>
              </FormField>
              <FormField class="flex-1" :error="errors.heightInches">
                <template #default="{ fieldId, describedBy, invalid }">
                  <input
                    :id="fieldId"
                    v-model.number="values.heightInches"
                    :class="inputFieldClass"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                    :aria-label="`${t('signup.height')} (${t('signup.unitInches')})`"
                    name="heightInches"
                    type="number"
                    min="0"
                    max="11"
                    step="1"
                    :placeholder="t('signup.unitInches')"
                    :disabled="isSubmitting"
                    @blur="handleBlur('heightInches')"
                  />
                </template>
              </FormField>
            </div>
          </div>

          <FormField :label="t('signup.firstDayOfWeek')">
            <template #default="{ fieldId }">
              <Select
                :id="fieldId"
                v-model="values.firstDayOfWeek"
                name="firstDayOfWeek"
                :disabled="isSubmitting"
              >
                <option v-for="value in WEEKDAY_OPTIONS" :key="value" :value="value">
                  {{ t(`signup.weekdays.${value}`) }}
                </option>
              </Select>
            </template>
          </FormField>

          <FormField :label="t('signup.currency')">
            <template #default="{ fieldId }">
              <Select
                :id="fieldId"
                v-model="values.currency"
                name="currency"
                :disabled="isSubmitting"
              >
                <option v-for="value in CURRENCY_OPTIONS" :key="value" :value="value">
                  {{ t(`signup.currencies.${value}`) }}
                </option>
              </Select>
            </template>
          </FormField>
        </div>

        <p class="text-hint">* {{ t('signup.requiredField') }}</p>

        <Button
          class="w-full"
          type="submit"
          :disabled="!isValid || !passwordsMatch || isSubmitting"
        >
          <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
          <span>{{ isSubmitting ? t('signup.signingUp') : t('signup.signUpButton') }}</span>
        </Button>

        <RouterLink
          :to="{ name: 'login' }"
          class="self-center text-meta text-muted-foreground hover:text-foreground"
        >
          {{ t('signup.alreadyHaveAccount') }}
        </RouterLink>
      </div>
    </form>
  </AuthScreenLayout>
</template>
