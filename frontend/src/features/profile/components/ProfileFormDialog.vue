<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ProfileDetails, ProfileEditInput } from '@/features/profile/types'
import type { Schemas } from '@/types'

import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { Select } from '@/components/ui/select'
import { useForm } from '@/composables/useForm'
import { HttpError } from '@/services/http'
import { toNumberOrNull } from '@/utils/number'
import { cmToFeetInches } from '@/utils/units'
import { compose, email, maxLength, pattern, required } from '@/utils/validators'
import {
  CURRENCY_OPTIONS,
  GENDER_OPTIONS,
  numberRange,
  resolveHeightCm,
  sortLanguageCodes,
  TEXT_MAX,
  WEEKDAY_OPTIONS,
} from '@/features/users/utils/userFieldOptions'
import { useUpdateProfileMutation } from '@/features/profile/composables/useProfile'

const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  /** The profile being edited; seeds the form when the dialog opens. */
  profile: ProfileDetails
}>()

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t, locale } = useI18n()

const languageCodes = computed(() =>
  sortLanguageCodes((code) => t(`settings.users.form.languages.${code}`), locale.value),
)

const updateMutation = useUpdateProfileMutation()

/** Form shape — the user's editable identity fields. Height is captured per unit. */
interface ProfileFormValues {
  name: string
  username: string
  email: string
  city: string
  birthdate: string
  gender: Schemas['Gender']
  units: Schemas['Units']
  currency: Schemas['Currency']
  heightCm: number | null
  heightFeet: number | null
  heightInches: number | null
  maxHeartRate: number | null
  preferredLanguage: Schemas['Language']
  firstDayOfWeek: Schemas['WeekDay']
  timezone: string
}

/**
 * IANA timezone names the browser knows about, for the profile picker.
 *
 * `Intl.supportedValuesOf` is available in every browser this app targets but is
 * not in the configured TypeScript lib, hence the narrow cast. Fall back to the
 * detected zone alone rather than rendering an empty select if it is missing.
 */
const TIMEZONE_OPTIONS: readonly string[] = (() => {
  const supportedValuesOf = (Intl as { supportedValuesOf?: (key: string) => string[] })
    .supportedValuesOf
  try {
    return supportedValuesOf?.('timeZone') ?? [detectBrowserTimezone()]
  } catch {
    return [detectBrowserTimezone()]
  }
})()

/** The viewer's own timezone, used to seed the field when the profile has none. */
function detectBrowserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
}

/**
 * Persists the profile, emitting the outcome to the parent and closing on
 * success. A duplicate username/email (`409`) is surfaced specifically; other
 * failures fall back to a generic message so the dialog stays open.
 *
 * @param values - The validated form values.
 */
async function submitForm(values: ProfileFormValues): Promise<void> {
  const input: ProfileEditInput = {
    name: values.name.trim(),
    username: values.username.trim(),
    email: values.email.trim(),
    city: values.city.trim() ? values.city.trim() : null,
    birthdate: values.birthdate || null,
    gender: values.gender,
    units: values.units,
    currency: values.currency,
    height: resolveHeightCm(values),
    // `v-model.number` leaves a stale '' in place instead of `null` when a
    // cleared field can't parse as a finite number.
    maxHeartRate: toNumberOrNull(values.maxHeartRate ?? ''),
    preferredLanguage: values.preferredLanguage,
    firstDayOfWeek: values.firstDayOfWeek,
    timezone: values.timezone || null,
  }
  try {
    await updateMutation.mutateAsync(input)
    emit('success', t('settings.profile.edit.success'))
    open.value = false
  } catch (error) {
    if (error instanceof HttpError && error.status === 409) {
      emit('error', t('settings.profile.edit.conflict'))
    } else {
      emit('error', t('settings.profile.edit.error'))
    }
  }
}

// Mirror the active unit system into its own ref so the height validators can
// branch on it. They can't read `values.units`: `values` comes from this same
// `useForm(...)` call, so referencing it inside that call's validators would be
// a circular reference TypeScript rejects.
const activeUnits = ref<Schemas['Units']>('metric')

const { values, errors, isValid, isSubmitting, handleSubmit, handleBlur, reset } =
  useForm<ProfileFormValues>({
    initialValues: {
      name: '',
      username: '',
      email: '',
      city: '',
      birthdate: '',
      gender: 'unspecified',
      units: 'metric',
      currency: 'euro',
      heightCm: null,
      heightFeet: null,
      heightInches: null,
      maxHeartRate: null,
      preferredLanguage: 'en',
      firstDayOfWeek: 'monday',
      timezone: detectBrowserTimezone(),
    },
    validators: {
      name: compose(
        required(t('settings.users.form.nameRequired')),
        maxLength(TEXT_MAX, t('settings.users.form.nameTooLong')),
      ),
      username: compose(
        required(t('settings.users.form.usernameRequired')),
        maxLength(TEXT_MAX, t('settings.users.form.usernameTooLong')),
        pattern(/^[a-zA-Z0-9._-]+$/, t('settings.users.form.usernameInvalid')),
      ),
      email: compose(
        required(t('settings.users.form.emailRequired')),
        email(t('settings.users.form.emailInvalid')),
      ),
      // Height is captured per unit system and only the active system's inputs
      // are rendered. Skip the imperial validators in metric mode (and vice
      // versa) so a hidden field's seed value can't silently fail validation and
      // disable submit with no visible error.
      heightFeet: (value: number | null) =>
        activeUnits.value === 'metric'
          ? null
          : numberRange(10, t('settings.users.form.feetInvalid'))(value),
      heightInches: (value: number | null) =>
        activeUnits.value === 'metric'
          ? null
          : numberRange(11, t('settings.users.form.inchesInvalid'))(value),
    },
    onSubmit: submitForm,
  })

const isMetric = computed(() => values.units === 'metric')

// Keep `activeUnits` in step with the unit selector so the height validators
// re-run against the correct system whenever the user toggles units.
watch(
  () => values.units,
  (units) => {
    activeUnits.value = units
  },
  { immediate: true },
)

/** Seeds the form from the current profile each time the dialog opens. */
function populate(): void {
  reset()
  const profile = props.profile
  values.name = profile.name
  values.username = profile.username
  values.email = profile.email
  values.city = profile.city ?? ''
  values.birthdate = profile.birthdate ?? ''
  values.gender = profile.gender
  values.units = profile.units
  values.currency = profile.currency
  values.heightCm = profile.height
  values.maxHeartRate = profile.maxHeartRate
  values.preferredLanguage = profile.preferredLanguage
  values.firstDayOfWeek = profile.firstDayOfWeek
  // Seed from the browser when the account predates this setting, so saving the
  // form once stops GPS-less activities inheriting the server's timezone.
  values.timezone = profile.timezone ?? detectBrowserTimezone()
  if (profile.height !== null) {
    const { feet, inches } = cmToFeetInches(profile.height)
    values.heightFeet = feet
    values.heightInches = inches
  }
}

watch(open, (isOpen) => {
  if (isOpen) {
    populate()
  }
})
</script>

<template>
  <FormDialog
    v-model:open="open"
    :title="t('settings.profile.edit.title')"
    :description="t('settings.profile.edit.description')"
    :submit-label="t('settings.users.form.save')"
    :cancel-label="t('settings.users.form.cancel')"
    :close-label="t('settings.users.form.close')"
    :submitting="isSubmitting"
    :can-submit="isValid"
    content-class="max-w-2xl"
    @submit="handleSubmit"
  >
    <div class="grid grid-cols-1 gap-1 sm:grid-cols-2">
      <FormField
        class="sm:col-span-2"
        :label="t('settings.users.form.name')"
        :error="errors.name"
        required
      >
        <template #default="{ fieldId, describedBy, invalid }">
          <Input
            :id="fieldId"
            v-model="values.name"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            name="name"
            maxlength="250"
            :disabled="isSubmitting"
            @blur="handleBlur('name')"
          />
        </template>
      </FormField>

      <FormField :label="t('settings.users.form.username')" :error="errors.username" required>
        <template #default="{ fieldId, describedBy, invalid }">
          <Input
            :id="fieldId"
            v-model="values.username"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            name="username"
            maxlength="250"
            :disabled="isSubmitting"
            @blur="handleBlur('username')"
          />
        </template>
      </FormField>

      <FormField :label="t('settings.users.form.email')" :error="errors.email" required>
        <template #default="{ fieldId, describedBy, invalid }">
          <Input
            :id="fieldId"
            v-model="values.email"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            name="email"
            type="email"
            maxlength="250"
            autocomplete="email"
            :disabled="isSubmitting"
            @blur="handleBlur('email')"
          />
        </template>
      </FormField>

      <FormField :label="t('settings.users.form.city')">
        <template #default="{ fieldId }">
          <Input
            :id="fieldId"
            v-model="values.city"
            name="city"
            type="text"
            maxlength="45"
            autocomplete="address-level2"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>

      <FormField :label="t('settings.users.form.birthdate')">
        <template #default="{ fieldId }">
          <input
            :id="fieldId"
            v-model="values.birthdate"
            :class="inputFieldClass"
            name="birthdate"
            type="date"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>

      <FormField :label="t('settings.users.form.gender')">
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.gender" :disabled="isSubmitting">
            <option v-for="value in GENDER_OPTIONS" :key="value" :value="value">
              {{ t(`settings.users.form.genders.${value}`) }}
            </option>
          </Select>
        </template>
      </FormField>

      <FormField :label="t('settings.users.form.preferredLanguage')">
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.preferredLanguage" :disabled="isSubmitting">
            <option v-for="code in languageCodes" :key="code" :value="code">
              {{ t(`settings.users.form.languages.${code}`) }}
            </option>
          </Select>
        </template>
      </FormField>

      <FormField :label="t('settings.users.form.firstDayOfWeek')">
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.firstDayOfWeek" :disabled="isSubmitting">
            <option v-for="day in WEEKDAY_OPTIONS" :key="day" :value="day">
              {{ t(`settings.users.form.weekdays.${day}`) }}
            </option>
          </Select>
        </template>
      </FormField>

      <FormField
        :label="t('settings.users.form.timezone')"
        :hint="t('settings.users.form.timezoneHint')"
      >
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.timezone" :disabled="isSubmitting">
            <option v-for="zone in TIMEZONE_OPTIONS" :key="zone" :value="zone">
              {{ zone }}
            </option>
          </Select>
        </template>
      </FormField>

      <FormField :label="t('settings.users.form.units')">
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.units" :disabled="isSubmitting">
            <option value="metric">{{ t('settings.users.form.unitsMetric') }}</option>
            <option value="imperial">{{ t('settings.users.form.unitsImperial') }}</option>
          </Select>
        </template>
      </FormField>

      <FormField :label="t('settings.users.form.currency')">
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.currency" :disabled="isSubmitting">
            <option v-for="value in CURRENCY_OPTIONS" :key="value" :value="value">
              {{ t(`settings.users.form.currencies.${value}`) }}
            </option>
          </Select>
        </template>
      </FormField>

      <FormField v-if="isMetric" :label="t('settings.users.form.height')">
        <template #default="{ fieldId }">
          <input
            :id="fieldId"
            v-model.number="values.heightCm"
            :class="inputFieldClass"
            name="heightCm"
            type="number"
            min="0"
            :placeholder="t('settings.users.form.unitCm')"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>

      <div v-else class="grid grid-cols-2 gap-1">
        <FormField :label="t('settings.users.form.height')" :error="errors.heightFeet">
          <template #default="{ fieldId, describedBy, invalid }">
            <input
              :id="fieldId"
              v-model.number="values.heightFeet"
              :class="inputFieldClass"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              name="heightFeet"
              type="number"
              min="0"
              max="10"
              step="1"
              :placeholder="t('settings.users.form.unitFeet')"
              :disabled="isSubmitting"
              @blur="handleBlur('heightFeet')"
            />
          </template>
        </FormField>
        <FormField :label="t('settings.users.form.unitInches')" :error="errors.heightInches">
          <template #default="{ fieldId, describedBy, invalid }">
            <input
              :id="fieldId"
              v-model.number="values.heightInches"
              :class="inputFieldClass"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              name="heightInches"
              type="number"
              min="0"
              max="11"
              step="1"
              :placeholder="t('settings.users.form.unitInches')"
              :disabled="isSubmitting"
              @blur="handleBlur('heightInches')"
            />
          </template>
        </FormField>
      </div>

      <FormField :label="t('settings.users.form.maxHeartRate')">
        <template #default="{ fieldId }">
          <input
            :id="fieldId"
            v-model.number="values.maxHeartRate"
            :class="inputFieldClass"
            name="maxHeartRate"
            type="number"
            min="0"
            :placeholder="t('settings.users.form.unitBpm')"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>
    </div>
  </FormDialog>
</template>
