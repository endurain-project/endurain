<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Schemas } from '@/types'
import type { WaterEntry, WaterEntryInput } from '@/features/health/types'
import type { Validator } from '@/utils/validators'

import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { useForm } from '@/composables/useForm'
import { isStaleWrite } from '@/services/ifMatch'
import { todayIsoDate } from '@/utils/datetime'
import { toNumberOrNull } from '@/utils/number'
import { flOzToMl, mlToFlOz } from '@/utils/units'
import { compose, required } from '@/utils/validators'
import {
  useCreateWaterEntryMutation,
  useUpdateWaterEntryMutation,
} from '@/features/health/composables/useHealth'

const open = defineModel<boolean>('open', { required: true })

const props = withDefaults(
  defineProps<{
    /** The water entry being edited, or `null`/absent when logging a new one. */
    entry?: WaterEntry | null
    /** The viewer's measurement system, used for the amount field units. */
    units: Schemas['Units']
  }>(),
  { entry: null },
)

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const createMutation = useCreateWaterEntryMutation()
const updateMutation = useUpdateWaterEntryMutation()

/** Form shape: the numeric amount is kept as a string and parsed at submit. */
interface WaterFormValues {
  date: string
  amount: string
}

/** Whether the viewer enters volumes in US fluid ounces rather than millilitres. */
const isImperial = computed(() => props.units === 'imperial')

/** Rejects non-numeric or non-positive input (runs after `required`). */
function positiveNumber(message: string): Validator<string> {
  return (value) => {
    const parsed = toNumberOrNull(value)
    return parsed === null || parsed <= 0 ? message : null
  }
}

/** The pristine values used for "add" and as the reset baseline. */
function defaultValues(): WaterFormValues {
  return {
    date: todayIsoDate(),
    amount: '',
  }
}

/** Renders a stored millilitre amount in the viewer's units for the form input. */
function displayAmountFromMl(ml: number | null): string {
  if (ml === null) {
    return ''
  }
  const value = isImperial.value ? Math.round(mlToFlOz(ml) * 10) / 10 : Math.round(ml)
  return String(value)
}

/** Converts a validated display-unit amount string back to whole millilitres for the wire. */
function amountToMl(raw: string): number {
  const value = Number(raw.trim())
  return Math.round(isImperial.value ? flOzToMl(value) : value)
}

/** Converts the string-based form values into the clean {@link WaterEntryInput}. */
function buildInput(values: WaterFormValues): WaterEntryInput {
  return {
    date: values.date || null,
    amountMl: amountToMl(values.amount),
  }
}

/**
 * Persists the entry, emitting the outcome to the parent and closing on success.
 * Backend failures are mapped to a toast message rather than thrown, so the
 * dialog stays open for correction.
 *
 * @param values - The validated form values.
 */
async function submitForm(values: WaterFormValues): Promise<void> {
  const input = buildInput(values)
  try {
    if (props.entry) {
      await updateMutation.mutateAsync({
        id: props.entry.id,
        version: props.entry.version,
        input,
      })
      emit('success', t('health.water.form.updateSuccess'))
    } else {
      await createMutation.mutateAsync(input)
      emit('success', t('health.water.form.createSuccess'))
    }
    open.value = false
  } catch (error) {
    emit('error', isStaleWrite(error) ? t('app.staleError') : t('health.water.form.saveError'))
  }
}

const { values, errors, isValid, isSubmitting, handleSubmit, handleBlur, reset } =
  useForm<WaterFormValues>({
    initialValues: defaultValues(),
    validators: {
      date: required<string>(t('health.water.form.dateRequired')),
      amount: compose(
        required<string>(t('health.water.form.amountRequired')),
        positiveNumber(t('health.water.form.amountInvalid')),
      ),
    },
    onSubmit: submitForm,
  })

const isEditing = computed(() => props.entry !== null)
const dialogTitle = computed(() =>
  isEditing.value ? t('health.water.form.editTitle') : t('health.water.form.addTitle'),
)
const amountUnitLabel = computed(() => (isImperial.value ? 'fl oz' : 'ml'))
const amountLabel = computed(() => `${t('health.water.form.amount')} (${amountUnitLabel.value})`)

/** Seeds the form from the entry being edited, or pristine defaults for "add". */
function populate(): void {
  reset()
  const entry = props.entry
  if (!entry) {
    values.date = todayIsoDate()
    return
  }
  values.date = entry.date ?? todayIsoDate()
  values.amount = displayAmountFromMl(entry.amountMl)
}

// Re-seed each time the dialog opens; the parent sets `entry` before opening.
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
    :description="t('health.water.form.description')"
    :submit-label="isEditing ? t('health.water.form.save') : t('health.water.form.create')"
    :cancel-label="t('health.water.form.cancel')"
    :close-label="t('health.water.form.close')"
    :submitting="isSubmitting"
    :can-submit="isValid"
    @submit="handleSubmit"
  >
    <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
      <FormField :label="t('health.water.form.date')" :error="errors.date" required>
        <template #default="{ fieldId, describedBy, invalid }">
          <input
            :id="fieldId"
            v-model="values.date"
            :class="inputFieldClass"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            type="date"
            :disabled="isSubmitting"
            @blur="handleBlur('date')"
          />
        </template>
      </FormField>

      <FormField :label="amountLabel" :error="errors.amount" :placeholder="amountLabel" required>
        <template #default="{ fieldId, describedBy, invalid, placeholder }">
          <input
            :id="fieldId"
            v-model="values.amount"
            :class="inputFieldClass"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            :placeholder="placeholder"
            type="number"
            min="0"
            step="any"
            inputmode="decimal"
            :disabled="isSubmitting"
            @blur="handleBlur('amount')"
          />
        </template>
      </FormField>
    </div>
  </FormDialog>
</template>
