<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Gear, GearInput, GearType } from '@/features/gears/types'
import type { Schemas } from '@/types'

import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { useForm } from '@/composables/useForm'
import { HttpError } from '@/services/http'
import { todayIsoDate } from '@/utils/datetime'
import { toNumberOrNull } from '@/utils/number'
import { kmToMiles, milesToKm } from '@/utils/units'
import { compose, maxLength, required } from '@/utils/validators'
import { currencySymbol } from '@/features/gears/utils/format'
import { GEAR_TYPE, GEAR_TYPE_VALUES, presentGearType } from '@/features/gears/utils/gearType'
import { useCreateGearMutation, useUpdateGearMutation } from '@/features/gears/composables/useGears'

const open = defineModel<boolean>('open', { required: true })

const props = withDefaults(
  defineProps<{
    /** The gear being edited, or `null`/absent when adding a new one. */
    gear?: Gear | null
    /** The viewer's measurement system, used for the distance field unit. */
    units: Schemas['Units']
    /** The viewer's currency, used for the purchase-value symbol. */
    currency: Schemas['Currency']
  }>(),
  { gear: null },
)

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const createMutation = useCreateGearMutation()
const updateMutation = useUpdateGearMutation()

/** Form shape: numeric fields are kept as strings and parsed at submit. */
interface GearFormValues {
  nickname: string
  gearType: GearType
  brand: string
  model: string
  active: boolean
  createdAt: string
  initialDistance: string
  purchaseValue: string
}

const NICKNAME_MAX = 250

/** Renders a stored km distance in the viewer's units for the form input. */
function displayDistanceFromKm(km: number | null): string {
  if (km === null) {
    return ''
  }
  const value = props.units === 'imperial' ? kmToMiles(km) : km
  return String(Math.round(value * 100) / 100)
}

/** The pristine values used for "add" and as the reset baseline. */
function defaultValues(): GearFormValues {
  return {
    nickname: '',
    gearType: GEAR_TYPE.BICYCLE,
    brand: '',
    model: '',
    active: true,
    createdAt: todayIsoDate(),
    initialDistance: '',
    purchaseValue: '',
  }
}

/** Converts the string-based form values into the clean {@link GearInput}. */
function buildInput(values: GearFormValues): GearInput {
  const isRacquet = values.gearType === GEAR_TYPE.RACQUET
  const distanceValue = toNumberOrNull(values.initialDistance)
  let initialKms: number | null = null
  if (!isRacquet && distanceValue !== null) {
    const km = props.units === 'imperial' ? milesToKm(distanceValue) : distanceValue
    initialKms = Math.round(km * 1000) / 1000
  }
  const brand = values.brand.trim()
  const model = values.model.trim()
  return {
    nickname: values.nickname.trim(),
    gearType: values.gearType,
    brand: brand.length > 0 ? brand : null,
    model: model.length > 0 ? model : null,
    active: values.active,
    createdAt: values.createdAt || null,
    initialKms,
    purchaseValue: toNumberOrNull(values.purchaseValue),
  }
}

/**
 * Persists the gear, emitting the outcome to the parent and closing on success.
 * Backend failures (incl. the 409 duplicate-nickname guard the form can't check
 * synchronously) are mapped to a toast message rather than thrown, so the
 * dialog stays open for correction.
 *
 * @param values - The validated form values.
 */
async function submitForm(values: GearFormValues): Promise<void> {
  const input = buildInput(values)
  try {
    if (props.gear) {
      await updateMutation.mutateAsync({ id: props.gear.id, input, version: props.gear.version })
      emit('success', t('gears.form.updateSuccess'))
    } else {
      await createMutation.mutateAsync(input)
      emit('success', t('gears.form.createSuccess'))
    }
    open.value = false
  } catch (error) {
    if (error instanceof HttpError && error.status === 409) {
      emit('error', t('gears.form.nicknameTaken'))
    } else {
      emit('error', t('gears.form.saveError'))
    }
  }
}

const { values, errors, isValid, isSubmitting, handleSubmit, handleBlur, reset } =
  useForm<GearFormValues>({
    initialValues: defaultValues(),
    validators: {
      nickname: compose(
        required<string>(t('gears.form.nicknameRequired')),
        maxLength(NICKNAME_MAX, t('gears.form.nicknameTooLong')),
      ),
      brand: maxLength(NICKNAME_MAX, t('gears.form.brandTooLong')),
      model: maxLength(NICKNAME_MAX, t('gears.form.modelTooLong')),
      createdAt: required<string>(t('gears.form.createdAtRequired')),
    },
    onSubmit: submitForm,
  })

const isEditing = computed(() => props.gear !== null)
const dialogTitle = computed(() =>
  isEditing.value ? t('gears.form.editTitle') : t('gears.form.addTitle'),
)
// Racquets have no odometer, so the distance field is hidden for that type.
const showDistance = computed(() => values.gearType !== GEAR_TYPE.RACQUET)
const distanceUnitLabel = computed(() =>
  props.units === 'imperial' ? t('gears.unitMi') : t('gears.unitKm'),
)
const distanceLabel = computed(
  () => `${t('gears.form.initialDistance')} (${distanceUnitLabel.value})`,
)
const purchaseValueLabel = computed(
  () => `${t('gears.form.purchaseValue')} (${currencySymbol(props.currency)})`,
)

/** Seeds the form from the gear being edited, or pristine defaults for "add". */
function populate(): void {
  reset()
  values.createdAt = todayIsoDate()
  const gear = props.gear
  if (!gear) {
    return
  }
  values.nickname = gear.nickname
  values.gearType = gear.gearType
  values.brand = gear.brand ?? ''
  values.model = gear.model ?? ''
  values.active = gear.active
  values.createdAt = gear.createdAt ? gear.createdAt.slice(0, 10) : todayIsoDate()
  values.initialDistance = displayDistanceFromKm(gear.initialKms)
  values.purchaseValue = gear.purchaseValue !== null ? String(gear.purchaseValue) : ''
}

// Re-seed each time the dialog opens; the parent sets `gear` before opening.
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
    :description="t('gears.form.description')"
    :submit-label="isEditing ? t('gears.form.save') : t('gears.form.create')"
    :cancel-label="t('gears.form.cancel')"
    :close-label="t('gears.form.close')"
    :submitting="isSubmitting"
    :can-submit="isValid"
    @submit="handleSubmit"
  >
    <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
      <FormField
        class="sm:col-span-2"
        :label="t('gears.form.nickname')"
        :error="errors.nickname"
        :placeholder="t('gears.form.nickname')"
        required
      >
        <template #default="{ fieldId, describedBy, invalid, placeholder }">
          <Input
            :id="fieldId"
            v-model="values.nickname"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            :placeholder="placeholder"
            name="nickname"
            maxlength="250"
            :disabled="isSubmitting"
            @blur="handleBlur('nickname')"
          />
        </template>
      </FormField>

      <FormField :label="t('gears.form.gearType')">
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.gearType" :disabled="isSubmitting">
            <option v-for="type in GEAR_TYPE_VALUES" :key="type" :value="type">
              {{ t(presentGearType(type).labelKey) }}
            </option>
          </Select>
        </template>
      </FormField>

      <FormField :label="t('gears.form.createdAt')" :error="errors.createdAt" required>
        <template #default="{ fieldId, describedBy, invalid }">
          <input
            :id="fieldId"
            v-model="values.createdAt"
            :class="inputFieldClass"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            type="date"
            :disabled="isSubmitting"
            @blur="handleBlur('createdAt')"
          />
        </template>
      </FormField>

      <FormField
        :label="t('gears.form.brand')"
        :error="errors.brand"
        :placeholder="t('gears.form.brand')"
      >
        <template #default="{ fieldId, describedBy, invalid, placeholder }">
          <Input
            :id="fieldId"
            v-model="values.brand"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            :placeholder="placeholder"
            name="brand"
            maxlength="250"
            :disabled="isSubmitting"
            @blur="handleBlur('brand')"
          />
        </template>
      </FormField>

      <FormField
        :label="t('gears.form.model')"
        :error="errors.model"
        :placeholder="t('gears.form.model')"
      >
        <template #default="{ fieldId, describedBy, invalid, placeholder }">
          <Input
            :id="fieldId"
            v-model="values.model"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            :placeholder="placeholder"
            name="model"
            maxlength="250"
            :disabled="isSubmitting"
            @blur="handleBlur('model')"
          />
        </template>
      </FormField>

      <FormField v-if="showDistance" :label="distanceLabel" :placeholder="distanceLabel">
        <template #default="{ fieldId, placeholder }">
          <input
            :id="fieldId"
            v-model="values.initialDistance"
            :class="inputFieldClass"
            :placeholder="placeholder"
            type="number"
            min="0"
            step="0.1"
            inputmode="decimal"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>

      <FormField :label="purchaseValueLabel" :placeholder="purchaseValueLabel">
        <template #default="{ fieldId, placeholder }">
          <input
            :id="fieldId"
            v-model="values.purchaseValue"
            :class="inputFieldClass"
            :placeholder="placeholder"
            type="number"
            min="0"
            step="0.01"
            inputmode="decimal"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>

      <Switch v-model="values.active" :disabled="isSubmitting" class="sm:col-span-2">
        {{ t('gears.form.active') }}
      </Switch>
    </div>
  </FormDialog>
</template>
