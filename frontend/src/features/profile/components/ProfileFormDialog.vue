<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import type { ProfileDetails, ProfileEditInput } from '@/features/profile/types'
import type { Schemas } from '@/types'

import { FormDialog } from '@/components/ui/form-dialog'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { Select } from '@/components/ui/select'
import { useForm } from '@/composables/useForm'
import { applyServerFieldErrors } from '@/services/fieldErrors'
import { isStaleWrite } from '@/services/ifMatch'
import { toNumberOrNull } from '@/utils/number'
import { cmToFeetInches } from '@/utils/units'
import { compose, maxLength, required } from '@/utils/validators'
import {
  CURRENCY_OPTIONS,
  GENDER_OPTIONS,
  heightCmValidator,
  maxHeartRateValidator,
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
  city: string
  birthdate: string
  gender: Schemas['Gender']
  units: Schemas['Units']
  weightUnits: 'default' | Schemas['Units']
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

/** The viewer's own timezone, offered as a choice for the field. */
function detectBrowserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
}

/** The read-only identity fields, each with the hint that points to where it is changed. */
const managedFields = computed(() => [
  {
    name: 'username',
    value: props.profile.username,
    hintKey: 'settings.profile.usernameManagedIn',
  },
  { name: 'email', value: props.profile.email, hintKey: 'settings.profile.emailManagedIn' },
])

/**
 * Persists the profile, emitting the outcome to the parent and closing on
 * success. A stale write closes the dialog; other failures show a generic
 * message and keep it open.
 *
 * @param values - The validated form values.
 */
async function submitForm(values: ProfileFormValues): Promise<void> {
  // Nothing changed: skip the request and just close.
  if (!isDirty.value) {
    open.value = false
    return
  }
  const input: ProfileEditInput = {
    name: values.name.trim(),
    city: values.city.trim() ? values.city.trim() : null,
    birthdate: values.birthdate || null,
    gender: values.gender,
    units: values.units,
    weightUnits: values.weightUnits === 'default' ? null : values.weightUnits,
    currency: values.currency,
    height: resolveHeightCm(values, props.profile.height),
    // `v-model.number` leaves a stale '' in place instead of `null` when a
    // cleared field can't parse as a finite number.
    maxHeartRate: toNumberOrNull(values.maxHeartRate ?? ''),
    preferredLanguage: values.preferredLanguage,
    firstDayOfWeek: values.firstDayOfWeek,
    timezone: values.timezone || null,
  }
  try {
    await updateMutation.mutateAsync({ input, version: props.profile.version })
    emit('success', t('settings.profile.edit.success'))
    open.value = false
  } catch (error) {
    if (
      applyServerFieldErrors(error, setErrors, t, FORM_KEYS, {
        height: values.units === 'metric' ? 'heightCm' : 'heightFeet',
      })
    ) {
      return
    }
    if (isStaleWrite(error)) {
      open.value = false
      emit('error', t('app.staleError'))
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

const FORM_KEYS = [
  'name',
  'city',
  'birthdate',
  'heightCm',
  'heightFeet',
  'maxHeartRate',
  'timezone',
] as const

const {
  values,
  errors,
  isValid,
  isSubmitting,
  handleSubmit,
  handleBlur,
  reset,
  isDirty,
  markPristine,
  setErrors,
} = useForm<ProfileFormValues>({
  initialValues: {
    name: '',
    city: '',
    birthdate: '',
    gender: 'unspecified',
    units: 'metric',
    weightUnits: 'default',
    currency: 'euro',
    heightCm: null,
    heightFeet: null,
    heightInches: null,
    maxHeartRate: null,
    preferredLanguage: 'en',
    firstDayOfWeek: 'monday',
    timezone: '',
  },
  validators: {
    name: compose(
      required(t('settings.users.form.nameRequired')),
      maxLength(TEXT_MAX, t('settings.users.form.nameTooLong')),
    ),
    heightCm: heightCmValidator(t('settings.users.form.heightInvalid')),
    maxHeartRate: maxHeartRateValidator(t('settings.users.form.maxHeartRateInvalid')),
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

/** The viewer's browser timezone, offered by the "use my browser's timezone" action. */
const browserTimezone = detectBrowserTimezone()

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
  values.city = profile.city ?? ''
  values.birthdate = profile.birthdate ?? ''
  values.gender = profile.gender
  values.units = profile.units
  values.weightUnits = profile.weightUnits ?? 'default'
  values.currency = profile.currency
  values.heightCm = profile.height
  values.maxHeartRate = profile.maxHeartRate
  values.preferredLanguage = profile.preferredLanguage
  values.firstDayOfWeek = profile.firstDayOfWeek
  // An unset timezone stays empty so saving the form keeps it unset.
  values.timezone = profile.timezone ?? ''
  if (profile.height !== null) {
    const { feet, inches } = cmToFeetInches(profile.height)
    values.heightFeet = feet
    values.heightInches = inches
  }
  markPristine()
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

      <FormField
        v-for="field in managedFields"
        :key="field.name"
        :label="t(`settings.users.form.${field.name}`)"
      >
        <template #default="{ fieldId }">
          <Input
            :id="fieldId"
            :model-value="field.value"
            :name="field.name"
            :type="field.name === 'email' ? 'email' : 'text'"
            disabled
          />
          <p class="text-hint">
            {{ t(field.hintKey) }}
            <RouterLink :to="{ name: 'settings-security' }" class="underline" @click="open = false">
              {{ t('settings.profile.securitySettingsLink') }}
            </RouterLink>
          </p>
        </template>
      </FormField>

      <FormField :label="t('settings.users.form.city')" :error="errors.city">
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

      <FormField :label="t('settings.users.form.birthdate')" :error="errors.birthdate">
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
        :error="errors.timezone"
        :hint="t('settings.users.form.timezoneHint')"
      >
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.timezone" :disabled="isSubmitting">
            <option value="">{{ t('settings.users.form.timezoneNotSet') }}</option>
            <option v-for="zone in TIMEZONE_OPTIONS" :key="zone" :value="zone">
              {{ zone }}
            </option>
          </Select>
          <Button
            v-if="values.timezone !== browserTimezone"
            type="button"
            variant="link"
            size="sm"
            class="h-auto max-w-full self-start text-left whitespace-normal"
            :disabled="isSubmitting"
            @click="values.timezone = browserTimezone"
          >
            {{ t('settings.users.form.timezoneUseBrowser', { timezone: browserTimezone }) }}
          </Button>
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

      <FormField :label="t('settings.users.form.weightUnits')">
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.weightUnits" :disabled="isSubmitting">
            <option value="default">{{ t('settings.users.form.weightUnitsDefault') }}</option>
            <option value="metric">{{ t('settings.users.form.weightUnitsMetric') }}</option>
            <option value="imperial">{{ t('settings.users.form.weightUnitsImperial') }}</option>
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

      <FormField v-if="isMetric" :label="t('settings.users.form.height')" :error="errors.heightCm">
        <template #default="{ fieldId, describedBy, invalid }">
          <input
            :id="fieldId"
            v-model.number="values.heightCm"
            :class="inputFieldClass"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            name="heightCm"
            type="number"
            min="50"
            max="272"
            :placeholder="t('units.cm')"
            :disabled="isSubmitting"
            @blur="handleBlur('heightCm')"
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
              :placeholder="t('units.ft')"
              :disabled="isSubmitting"
              @blur="handleBlur('heightFeet')"
            />
          </template>
        </FormField>
        <FormField :label="t('units.in')" :error="errors.heightInches">
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
              :placeholder="t('units.in')"
              :disabled="isSubmitting"
              @blur="handleBlur('heightInches')"
            />
          </template>
        </FormField>
      </div>

      <FormField :label="t('settings.users.form.maxHeartRate')" :error="errors.maxHeartRate">
        <template #default="{ fieldId, describedBy, invalid }">
          <input
            :id="fieldId"
            v-model.number="values.maxHeartRate"
            :class="inputFieldClass"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            name="maxHeartRate"
            type="number"
            min="30"
            max="250"
            :placeholder="t('units.bpm')"
            :disabled="isSubmitting"
            @blur="handleBlur('maxHeartRate')"
          />
        </template>
      </FormField>
    </div>
  </FormDialog>
</template>
