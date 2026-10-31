<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { GearComponent, GearComponentInput } from '@/features/gears/types'
import type { Schemas } from '@/types'

import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { useForm } from '@/composables/useForm'
import { HttpError } from '@/services/http'
import { isStaleWrite } from '@/services/ifMatch'
import { todayIsoDate } from '@/utils/datetime'
import { toNumberOrNull } from '@/utils/number'
import { kmToMiles, milesToKm } from '@/utils/units'
import { compose, maxLength, required } from '@/utils/validators'
import { currencySymbol } from '@/features/gears/utils/format'
import { humanizeComponentType, isTimeBasedGear } from '@/features/gears/utils/gearComponentType'
import {
  useCreateGearComponentMutation,
  useUpdateGearComponentMutation,
} from '@/features/gears/composables/useGearComponents'

const open = defineModel<boolean>('open', { required: true })

const props = withDefaults(
  defineProps<{
    /** The component being edited, or `null`/absent when adding a new one. */
    component?: GearComponent | null
    /** The parent gear id (used when creating a component). */
    gearId: number
    /** The parent gear's numeric type, selecting distance- vs time-based wear. */
    gearType: number
    /** The component-type ids valid for the parent gear family. */
    availableTypes: string[]
    /** The viewer's measurement system, used for the expected-distance unit. */
    units: Schemas['Units']
    /** The viewer's currency, used for the purchase-value symbol. */
    currency: Schemas['Currency']
  }>(),
  { component: null },
)

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const createMutation = useCreateGearComponentMutation()
const updateMutation = useUpdateGearComponentMutation()

/** Form shape: numeric/date fields are kept as strings and parsed at submit. */
interface ComponentFormValues {
  type: string
  brand: string
  model: string
  purchaseDate: string
  expected: string
  purchaseValue: string
  retiredDate: string
  active: boolean
}

const TEXT_MAX = 250

/**
 * Converts the "expected" form field (shown in km/mi for distance gears or
 * hours for the racquet family) into the backend's base units — metres or
 * seconds — matching how accumulated usage is reported.
 */
function expectedToBaseUnits(value: string): number | null {
  const parsed = toNumberOrNull(value)
  if (parsed === null) {
    return null
  }
  if (isTimeBasedGear(props.gearType)) {
    return Math.round(parsed * 3600)
  }
  const km = props.units === 'imperial' ? milesToKm(parsed) : parsed
  return Math.round(km * 1000)
}

/** Renders a stored base-units threshold back into the form's display unit. */
function expectedFromBaseUnits(base: number | null): string {
  if (base === null) {
    return ''
  }
  if (isTimeBasedGear(props.gearType)) {
    return String(Math.round((base / 3600) * 100) / 100)
  }
  const km = base / 1000
  const value = props.units === 'imperial' ? kmToMiles(km) : km
  return String(Math.round(value * 100) / 100)
}

/** The pristine values used for "add" and as the reset baseline. */
function defaultValues(): ComponentFormValues {
  return {
    type: '',
    brand: '',
    model: '',
    purchaseDate: todayIsoDate(),
    expected: '',
    purchaseValue: '',
    retiredDate: '',
    active: true,
  }
}

/** Converts the string-based form values into the clean {@link GearComponentInput}. */
function buildInput(values: ComponentFormValues): GearComponentInput {
  return {
    gearId: props.gearId,
    type: values.type,
    brand: values.brand.trim(),
    model: values.model.trim(),
    purchaseDate: values.purchaseDate || null,
    retiredDate: values.retiredDate || null,
    active: values.active,
    expectedBaseUnits: expectedToBaseUnits(values.expected),
    purchaseValue: toNumberOrNull(values.purchaseValue),
  }
}

/**
 * Persists the component, emitting the outcome to the parent and closing on
 * success. The retired-after-purchase rule is checked client-side first (and
 * the backend's 400 mapped as a fallback) so the dialog stays open with a clear
 * message rather than a generic error.
 *
 * @param values - The validated form values.
 */
async function submitForm(values: ComponentFormValues): Promise<void> {
  const input = buildInput(values)
  if (input.retiredDate && input.purchaseDate && input.retiredDate <= input.purchaseDate) {
    emit('error', t('gears.components.form.retiredBeforePurchase'))
    return
  }
  try {
    if (props.component) {
      await updateMutation.mutateAsync({
        id: props.component.id,
        input,
        version: props.component.version,
      })
      emit('success', t('gears.components.form.updateSuccess'))
    } else {
      await createMutation.mutateAsync(input)
      emit('success', t('gears.components.form.createSuccess'))
    }
    open.value = false
  } catch (error) {
    if (isStaleWrite(error)) {
      emit('error', t('app.staleError'))
    } else if (error instanceof HttpError && error.status === 400) {
      emit('error', t('gears.components.form.retiredBeforePurchase'))
    } else {
      emit('error', t('gears.components.form.saveError'))
    }
  }
}

const { values, errors, isValid, isSubmitting, handleSubmit, handleBlur, reset } =
  useForm<ComponentFormValues>({
    initialValues: defaultValues(),
    validators: {
      type: required<string>(t('gears.components.form.typeRequired')),
      brand: compose(
        required<string>(t('gears.components.form.brandRequired')),
        maxLength(TEXT_MAX, t('gears.components.form.brandTooLong')),
      ),
      model: compose(
        required<string>(t('gears.components.form.modelRequired')),
        maxLength(TEXT_MAX, t('gears.components.form.modelTooLong')),
      ),
      purchaseDate: required<string>(t('gears.components.form.purchaseDateRequired')),
    },
    onSubmit: submitForm,
  })

const isEditing = computed(() => props.component !== null)
const dialogTitle = computed(() =>
  isEditing.value ? t('gears.components.form.editTitle') : t('gears.components.form.addTitle'),
)
// Component types are sorted by their human label for an easier-to-scan select.
const sortedTypes = computed(() =>
  [...props.availableTypes].sort((a, b) =>
    humanizeComponentType(a).localeCompare(humanizeComponentType(b)),
  ),
)
const distanceUnitLabel = computed(() =>
  props.units === 'imperial' ? t('gears.unitMi') : t('gears.unitKm'),
)
const expectedLabel = computed(() =>
  isTimeBasedGear(props.gearType)
    ? `${t('gears.components.form.expectedTime')} (${t('gears.components.unitHours')})`
    : `${t('gears.components.form.expectedDistance')} (${distanceUnitLabel.value})`,
)
const purchaseValueLabel = computed(
  () => `${t('gears.components.form.purchaseValue')} (${currencySymbol(props.currency)})`,
)

/** A component with a retired date is necessarily inactive (server invariant). */
const isRetired = computed(() => values.retiredDate !== '')

/**
 * Mirrors the retirement state into the active flag on direct user edits:
 * entering a retired date deactivates the component, clearing it reactivates.
 * Bound to the native `change` event so programmatic seeding via {@link populate}
 * never clobbers the stored `active` value.
 */
function syncActiveWithRetiredDate(): void {
  values.active = !isRetired.value
}

/** Seeds the form from the component being edited, or pristine defaults. */
function populate(): void {
  reset()
  values.purchaseDate = todayIsoDate()
  const component = props.component
  if (!component) {
    return
  }
  values.type = component.type
  values.brand = component.brand
  values.model = component.model
  values.purchaseDate = component.purchaseDate
    ? component.purchaseDate.slice(0, 10)
    : todayIsoDate()
  values.retiredDate = component.retiredDate ? component.retiredDate.slice(0, 10) : ''
  values.active = component.active
  values.expected = expectedFromBaseUnits(component.expectedBaseUnits)
  values.purchaseValue = component.purchaseValue !== null ? String(component.purchaseValue) : ''
}

// Re-seed each time the dialog opens; the parent sets `component` before opening.
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
    :description="t('gears.components.form.description')"
    :submit-label="isEditing ? t('gears.components.form.save') : t('gears.components.form.create')"
    :cancel-label="t('gears.components.form.cancel')"
    :close-label="t('gears.components.form.close')"
    :submitting="isSubmitting"
    :can-submit="isValid"
    @submit="handleSubmit"
  >
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <FormField
        class="sm:col-span-2"
        :label="t('gears.components.form.type')"
        :error="errors.type"
        required
      >
        <template #default="{ fieldId, describedBy, invalid }">
          <Select
            :id="fieldId"
            v-model="values.type"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            :disabled="isSubmitting"
            @blur="handleBlur('type')"
          >
            <option value="" disabled>{{ t('gears.components.form.typePlaceholder') }}</option>
            <option v-for="type in sortedTypes" :key="type" :value="type">
              {{ humanizeComponentType(type) }}
            </option>
          </Select>
        </template>
      </FormField>

      <FormField
        :label="t('gears.components.form.brand')"
        :placeholder="t('gears.components.form.brand')"
        :error="errors.brand"
        required
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
        :label="t('gears.components.form.model')"
        :placeholder="t('gears.components.form.model')"
        :error="errors.model"
        required
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

      <FormField
        :label="t('gears.components.form.purchaseDate')"
        :error="errors.purchaseDate"
        required
      >
        <template #default="{ fieldId, describedBy, invalid }">
          <input
            :id="fieldId"
            v-model="values.purchaseDate"
            :class="inputFieldClass"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            type="date"
            :disabled="isSubmitting"
            @blur="handleBlur('purchaseDate')"
          />
        </template>
      </FormField>

      <FormField v-if="isEditing" :label="t('gears.components.form.retiredDate')">
        <template #default="{ fieldId }">
          <input
            :id="fieldId"
            v-model="values.retiredDate"
            :class="inputFieldClass"
            type="date"
            :disabled="isSubmitting"
            @change="syncActiveWithRetiredDate"
          />
        </template>
      </FormField>

      <FormField :label="expectedLabel" :placeholder="expectedLabel">
        <template #default="{ fieldId, placeholder }">
          <input
            :id="fieldId"
            v-model="values.expected"
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

      <Switch
        v-if="isEditing"
        v-model="values.active"
        :disabled="isSubmitting || isRetired"
        class="sm:col-span-2"
      >
        {{ t('gears.components.form.active') }}
      </Switch>
    </div>
  </FormDialog>
</template>
