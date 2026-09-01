<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ManagedUser, UserAccessType } from '@/features/users/types'
import type { Schemas } from '@/types'

import PasswordInput from '@/features/security/components/PasswordInput.vue'
import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useForm } from '@/composables/useForm'
import { usePublicServerSettings } from '@/features/config/composables/usePublicServerSettings'
import { HttpError } from '@/services/http'
import { toNumberOrNull } from '@/utils/number'
import { cmToFeetInches } from '@/utils/units'
import {
  buildPasswordRequirements,
  isValidPassword,
  resolvePasswordMinLength,
} from '@/utils/validation'
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
import { useCreateUserMutation, useUpdateUserMutation } from '@/features/users/composables/useUsers'

const open = defineModel<boolean>('open', { required: true })

const props = withDefaults(
  defineProps<{
    /** The user being edited, or `null`/absent when adding a new one. */
    user?: ManagedUser | null
  }>(),
  { user: null },
)

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t, locale } = useI18n()

const languageCodes = computed(() =>
  sortLanguageCodes((code) => t(`settings.users.form.languages.${code}`), locale.value),
)

const createMutation = useCreateUserMutation()
const updateMutation = useUpdateUserMutation()

const { serverSettings } = usePublicServerSettings()

/**
 * Form shape — the full set of admin-editable user fields. `password` is only
 * used (and required) when adding. Height is captured per unit system (`cm`
 * when metric, `feet`/`inches` when imperial) and reconciled on submit.
 */
interface UserFormValues {
  name: string
  username: string
  email: string
  password: string
  confirmPassword: string
  accessType: UserAccessType
  active: boolean
  emailVerified: boolean
  pendingAdminApproval: boolean
  preferredLanguage: Schemas['Language']
  gender: Schemas['Gender']
  units: Schemas['Units']
  currency: Schemas['Currency']
  firstDayOfWeek: Schemas['WeekDay']
  city: string
  birthdate: string
  heightCm: number | null
  heightFeet: number | null
  heightInches: number | null
  maxHeartRate: number | null
}

/** The pristine values used for "add" and as the reset baseline. */
function defaultValues(): UserFormValues {
  return {
    name: '',
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
    accessType: 'regular',
    active: true,
    emailVerified: true,
    pendingAdminApproval: false,
    preferredLanguage: 'en',
    gender: 'unspecified',
    units: 'metric',
    currency: 'euro',
    firstDayOfWeek: 'monday',
    city: '',
    birthdate: '',
    heightCm: null,
    heightFeet: null,
    heightInches: null,
    maxHeartRate: null,
  }
}

/**
 * Persists the user, emitting the outcome to the parent and closing on success.
 * A duplicate username/email (`409`) is surfaced as a specific message; other
 * failures fall back to a generic one so the dialog stays open for correction.
 *
 * @param formValues - The validated form values.
 */
async function submitForm(formValues: UserFormValues): Promise<void> {
  const city = formValues.city.trim() ? formValues.city.trim() : null
  const birthdate = formValues.birthdate || null
  const height = resolveHeightCm(formValues)
  // `v-model.number` leaves a stale '' in place instead of `null` when a
  // cleared field can't parse as a finite number.
  const maxHeartRate = toNumberOrNull(formValues.maxHeartRate ?? '')
  try {
    if (props.user) {
      await updateMutation.mutateAsync({
        user: props.user,
        edits: {
          name: formValues.name.trim(),
          username: formValues.username.trim(),
          email: formValues.email.trim(),
          accessType: formValues.accessType,
          active: formValues.active,
          emailVerified: formValues.emailVerified,
          pendingAdminApproval: formValues.pendingAdminApproval,
          preferredLanguage: formValues.preferredLanguage,
          gender: formValues.gender,
          units: formValues.units,
          currency: formValues.currency,
          firstDayOfWeek: formValues.firstDayOfWeek,
          city,
          birthdate,
          height,
          maxHeartRate,
        },
      })
      emit('success', t('settings.users.form.updateSuccess'))
    } else {
      await createMutation.mutateAsync({
        name: formValues.name.trim(),
        username: formValues.username.trim(),
        email: formValues.email.trim(),
        password: formValues.password,
        accessType: formValues.accessType,
        active: formValues.active,
        emailVerified: formValues.emailVerified,
        pendingAdminApproval: formValues.pendingAdminApproval,
        preferredLanguage: formValues.preferredLanguage,
        gender: formValues.gender,
        units: formValues.units,
        currency: formValues.currency,
        firstDayOfWeek: formValues.firstDayOfWeek,
        city,
        birthdate,
        height,
        maxHeartRate,
      })
      emit('success', t('settings.users.form.createSuccess'))
    }
    open.value = false
  } catch (error) {
    if (error instanceof HttpError && error.status === 409) {
      emit('error', t('settings.users.form.conflict'))
    } else if (!props.user && error instanceof HttpError && error.status === 400) {
      // Create-only: the backend's own password-policy check is the only
      // documented 400 this endpoint raises, so it's safe to surface a
      // password-specific message here (edits never send a password).
      emit('error', t('settings.users.form.passwordInvalid'))
    } else {
      emit('error', t('settings.users.form.saveError'))
    }
  }
}

// Mirror the active unit system into its own ref so the height validators can
// branch on it. They can't read `values.units`: `values` comes from this same
// `useForm(...)` call, so referencing it inside that call's validators would be
// a circular reference TypeScript rejects.
const activeUnits = ref<Schemas['Units']>('metric')

// Same circular-reference constraint as `activeUnits` above: the password
// validator can't read `values.accessType` from the same `useForm(...)` call,
// so the selected access type (which determines the length policy) is
// mirrored into its own ref, kept in sync via the watch below.
const activeAccessType = ref<UserAccessType>('regular')

/** Password policy mirrored from the server, scoped to the selected access type. */
const passwordRequirements = computed(() =>
  buildPasswordRequirements(
    serverSettings.value.password_type,
    resolvePasswordMinLength(
      serverSettings.value.password_length_regular_users,
      serverSettings.value.password_length_admin_users,
      activeAccessType.value,
    ),
  ),
)
/** Human-readable hint describing the active password policy. */
const passwordHint = computed(() =>
  serverSettings.value.password_type === 'length_only'
    ? t('settings.users.form.passwordHintLength', { min: passwordRequirements.value.minLength })
    : t('settings.users.form.passwordHintStrict', { min: passwordRequirements.value.minLength }),
)

const { values, errors, isValid, isSubmitting, handleSubmit, handleBlur, reset } =
  useForm<UserFormValues>({
    initialValues: defaultValues(),
    validators: {
      name: compose(
        required<string>(t('settings.users.form.nameRequired')),
        maxLength(TEXT_MAX, t('settings.users.form.nameTooLong')),
      ),
      username: compose(
        required<string>(t('settings.users.form.usernameRequired')),
        maxLength(TEXT_MAX, t('settings.users.form.usernameTooLong')),
        pattern(/^[a-zA-Z0-9._-]+$/, t('settings.users.form.usernameInvalid')),
      ),
      email: compose(
        required<string>(t('settings.users.form.emailRequired')),
        email(t('settings.users.form.emailInvalid')),
      ),
      // Password is required only when creating; edits never change it here, so
      // the validator passes (returns null) in edit mode where the field is hidden.
      password: (value: string) =>
        props.user
          ? null
          : compose(
              required<string>(t('settings.users.form.passwordRequired')),
              (candidate: string) =>
                isValidPassword(candidate, passwordRequirements.value)
                  ? null
                  : t('settings.users.form.passwordInvalid'),
            )(value),
      // Required only when creating; the mismatch itself is surfaced via the
      // `passwordsMatch`/`confirmPasswordError` computeds below (a validator here
      // can't safely read the sibling `password` field — see `values` note above).
      confirmPassword: (value: string) =>
        props.user
          ? null
          : required<string>(t('settings.users.form.confirmPasswordRequired'))(value),
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

const isEditing = computed(() => props.user !== null)
const isMetric = computed(() => values.units === 'metric')

// Only relevant when creating (the password fields are hidden on edit); a
// blank confirm field isn't yet a mismatch, it just hasn't been filled in.
const passwordsMatch = computed(
  () =>
    isEditing.value ||
    (values.confirmPassword.length > 0 && values.confirmPassword === values.password),
)
const confirmPasswordError = computed(() =>
  values.confirmPassword.length > 0 && values.confirmPassword !== values.password
    ? t('settings.users.form.passwordMismatch')
    : undefined,
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
// Keep `activeAccessType` in step with the access-type selector so the
// password validator re-runs against the correct length policy whenever the
// admin toggles Regular/Admin.
watch(
  () => values.accessType,
  (accessType) => {
    activeAccessType.value = accessType
  },
  { immediate: true },
)
const dialogTitle = computed(() =>
  isEditing.value ? t('settings.users.form.editTitle') : t('settings.users.form.addTitle'),
)

/** Seeds the form from the user being edited, or pristine defaults for "add". */
function populate(): void {
  reset()
  const user = props.user
  if (!user) {
    return
  }
  values.name = user.name
  values.username = user.username
  values.email = user.email
  values.accessType = user.accessType
  values.active = user.active
  values.emailVerified = user.emailVerified
  values.pendingAdminApproval = user.pendingAdminApproval
  values.preferredLanguage = user.preferredLanguage
  values.gender = user.gender
  values.units = user.units
  values.currency = user.currency
  values.firstDayOfWeek = user.firstDayOfWeek
  values.city = user.city ?? ''
  values.birthdate = user.birthdate ?? ''
  values.heightCm = user.height
  values.maxHeartRate = user.maxHeartRate
  if (user.height !== null) {
    const { feet, inches } = cmToFeetInches(user.height)
    values.heightFeet = feet
    values.heightInches = inches
  }
}

// Re-seed each time the dialog opens; the parent sets `user` before opening.
watch(open, (isOpen) => {
  if (isOpen) {
    populate()
  }
})
</script>

<template>
  <FormDialog
    v-model:open="open"
    :title="dialogTitle"
    :description="t('settings.users.form.description')"
    :submit-label="isEditing ? t('settings.users.form.save') : t('settings.users.form.create')"
    :cancel-label="t('settings.users.form.cancel')"
    :close-label="t('settings.users.form.close')"
    :submitting="isSubmitting"
    :can-submit="isValid && passwordsMatch"
    content-class="max-w-2xl"
    @submit="handleSubmit"
  >
    <div class="grid grid-cols-1 gap-1 sm:grid-cols-2">
      <FormField
        class="sm:col-span-2"
        :label="t('settings.users.form.name')"
        :placeholder="t('settings.users.form.name')"
        :error="errors.name"
        required
      >
        <template #default="{ fieldId, describedBy, invalid, placeholder }">
          <Input
            :id="fieldId"
            v-model="values.name"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            name="name"
            :placeholder="placeholder"
            maxlength="250"
            :disabled="isSubmitting"
            @blur="handleBlur('name')"
          />
        </template>
      </FormField>

      <FormField
        :label="t('settings.users.form.username')"
        :error="errors.username"
        :placeholder="t('settings.users.form.username')"
        required
      >
        <template #default="{ fieldId, describedBy, invalid, placeholder }">
          <Input
            :id="fieldId"
            v-model="values.username"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            name="username"
            :placeholder="placeholder"
            maxlength="250"
            autocapitalize="none"
            :disabled="isSubmitting"
            @blur="handleBlur('username')"
          />
        </template>
      </FormField>

      <FormField
        :label="t('settings.users.form.email')"
        :error="errors.email"
        :placeholder="t('settings.users.form.email')"
        required
      >
        <template #default="{ fieldId, describedBy, invalid, placeholder }">
          <Input
            :id="fieldId"
            v-model="values.email"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            type="email"
            name="email"
            :placeholder="placeholder"
            :disabled="isSubmitting"
            @blur="handleBlur('email')"
          />
        </template>
      </FormField>

      <FormField
        v-if="!isEditing"
        class="sm:col-span-2"
        :label="t('settings.users.form.password')"
        :error="errors.password"
        :placeholder="t('settings.users.form.password')"
        :hint="passwordHint"
        required
      >
        <template #default="{ fieldId, describedBy, invalid, placeholder }">
          <PasswordInput
            :id="fieldId"
            v-model="values.password"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            name="new-password"
            autocomplete="new-password"
            :placeholder="placeholder"
            :disabled="isSubmitting"
            @blur="handleBlur('password')"
          />
        </template>
      </FormField>

      <FormField
        v-if="!isEditing"
        class="sm:col-span-2"
        :label="t('settings.users.form.confirmPassword')"
        :placeholder="t('settings.users.form.confirmPassword')"
        :error="confirmPasswordError"
        required
      >
        <template #default="{ fieldId, describedBy, invalid, placeholder }">
          <PasswordInput
            :id="fieldId"
            v-model="values.confirmPassword"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            name="confirm-password"
            autocomplete="new-password"
            :placeholder="placeholder"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>

      <FormField
        :label="t('settings.users.form.city')"
        :placeholder="t('settings.users.form.city')"
      >
        <template #default="{ fieldId, placeholder }">
          <Input
            :id="fieldId"
            v-model="values.city"
            :placeholder="placeholder"
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

      <FormField :label="t('settings.users.form.units')">
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.units" :disabled="isSubmitting">
            <option value="metric">{{ t('settings.users.form.unitsMetric') }}</option>
            <option value="imperial">{{ t('settings.users.form.unitsImperial') }}</option>
          </Select>
        </template>
      </FormField>

      <FormField
        v-if="isMetric"
        :label="`${t('settings.users.form.height')} (${t('settings.users.form.unitCm')})`"
        :placeholder="`${t('settings.users.form.height')} (${t('settings.users.form.unitCm')})`"
      >
        <template #default="{ fieldId, placeholder }">
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
            :placeholder="placeholder"
          />
        </template>
      </FormField>

      <div v-else class="flex flex-col gap-1.5">
        <span class="text-meta font-medium text-foreground">{{
          t('settings.users.form.height')
        }}</span>
        <div class="flex gap-3">
          <FormField
            class="flex-1"
            :error="errors.heightFeet"
            :placeholder="t('settings.users.form.unitFeet')"
          >
            <template #default="{ fieldId, describedBy, invalid, placeholder }">
              <input
                :id="fieldId"
                v-model.number="values.heightFeet"
                :class="inputFieldClass"
                :aria-describedby="describedBy"
                :aria-invalid="invalid"
                :aria-label="`${t('settings.users.form.height')} (${t('settings.users.form.unitFeet')})`"
                name="heightFeet"
                type="number"
                min="0"
                max="10"
                step="1"
                :placeholder="placeholder"
                :disabled="isSubmitting"
                @blur="handleBlur('heightFeet')"
              />
            </template>
          </FormField>
          <FormField
            class="flex-1"
            :error="errors.heightInches"
            :placeholder="t('settings.users.form.unitInches')"
          >
            <template #default="{ fieldId, describedBy, invalid, placeholder }">
              <input
                :id="fieldId"
                v-model.number="values.heightInches"
                :class="inputFieldClass"
                :aria-describedby="describedBy"
                :aria-invalid="invalid"
                :aria-label="`${t('settings.users.form.height')} (${t('settings.users.form.unitInches')})`"
                name="heightInches"
                type="number"
                min="0"
                max="11"
                step="1"
                :placeholder="placeholder"
                :disabled="isSubmitting"
                @blur="handleBlur('heightInches')"
              />
            </template>
          </FormField>
        </div>
      </div>

      <FormField
        :label="`${t('settings.users.form.maxHeartRate')} (${t('settings.users.form.unitBpm')})`"
        :placeholder="`${t('settings.users.form.maxHeartRate')} (${t('settings.users.form.unitBpm')})`"
      >
        <template #default="{ fieldId, placeholder }">
          <input
            :id="fieldId"
            v-model.number="values.maxHeartRate"
            :class="inputFieldClass"
            name="maxHeartRate"
            type="number"
            min="0"
            max="250"
            step="1"
            :placeholder="placeholder"
            :disabled="isSubmitting"
          />
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

      <FormField :label="t('settings.users.form.firstDayOfWeek')">
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.firstDayOfWeek" :disabled="isSubmitting">
            <option v-for="value in WEEKDAY_OPTIONS" :key="value" :value="value">
              {{ t(`settings.users.form.weekdays.${value}`) }}
            </option>
          </Select>
        </template>
      </FormField>

      <FormField :label="t('settings.users.form.accessType')">
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.accessType" :disabled="isSubmitting">
            <option value="regular">{{ t('settings.users.form.accessTypeRegular') }}</option>
            <option value="admin">{{ t('settings.users.form.accessTypeAdmin') }}</option>
          </Select>
        </template>
      </FormField>

      <fieldset class="flex flex-col gap-3 sm:col-span-2">
        <legend class="mb-1 text-meta font-medium text-foreground">
          {{ t('settings.users.form.statusLegend') }}
        </legend>
        <Switch v-model="values.active" :disabled="isSubmitting">
          {{ t('settings.users.form.active') }}
        </Switch>
        <Switch v-model="values.emailVerified" :disabled="isSubmitting">
          {{ t('settings.users.form.emailVerified') }}
        </Switch>
        <Switch v-model="values.pendingAdminApproval" :disabled="isSubmitting">
          {{ t('settings.users.form.pendingAdminApproval') }}
        </Switch>
      </fieldset>

      <p class="text-hint sm:col-span-2">* {{ t('settings.users.form.requiredField') }}</p>
    </div>
  </FormDialog>
</template>
