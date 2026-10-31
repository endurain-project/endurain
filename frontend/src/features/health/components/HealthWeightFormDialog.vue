<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Schemas } from '@/types'
import type { WeightEntry, WeightEntryInput } from '@/features/health/types'
import type { Validator } from '@/utils/validators'

import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { useForm } from '@/composables/useForm'
import { isStaleWrite } from '@/services/ifMatch'
import { todayIsoDate } from '@/utils/datetime'
import { toNumberOrNull } from '@/utils/number'
import { kgToLbs, lbsToKg } from '@/utils/units'
import { compose, required } from '@/utils/validators'
import {
  useCreateWeightEntryMutation,
  useUpdateWeightEntryMutation,
} from '@/features/health/composables/useHealth'

const open = defineModel<boolean>('open', { required: true })

const props = withDefaults(
  defineProps<{
    /** The weight entry being edited, or `null`/absent when logging a new one. */
    entry?: WeightEntry | null
    /** The measurement system used to present body mass (kg or lbs). */
    weightUnits: Schemas['Units']
  }>(),
  { entry: null },
)

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const createMutation = useCreateWeightEntryMutation()
const updateMutation = useUpdateWeightEntryMutation()

/** Form shape: numeric fields are kept as strings and parsed at submit. */
interface WeightFormValues {
  date: string
  weight: string
  bmi: string
  bodyFat: string
  bodyWater: string
  boneMass: string
  muscleMass: string
}

/** Rejects non-numeric or non-positive input (runs after `required`). */
function positiveNumber(message: string): Validator<string> {
  return (value) => {
    const parsed = toNumberOrNull(value)
    return parsed === null || parsed <= 0 ? message : null
  }
}

/** The pristine values used for "add" and as the reset baseline. */
function defaultValues(): WeightFormValues {
  return {
    date: todayIsoDate(),
    weight: '',
    bmi: '',
    bodyFat: '',
    bodyWater: '',
    boneMass: '',
    muscleMass: '',
  }
}

/** Renders a stored kg mass in the viewer's units for the form input. */
function displayMassFromKg(kg: number | null): string {
  if (kg === null) {
    return ''
  }
  const value = props.weightUnits === 'imperial' ? kgToLbs(kg) : kg
  return String(Math.round(value * 100) / 100)
}

/** Converts a validated display-unit mass string back to kilograms for the wire. */
function massToKg(raw: string): number {
  const value = Number(raw.trim())
  const kg = props.weightUnits === 'imperial' ? lbsToKg(value) : value
  return Math.round(kg * 1000) / 1000
}

/** Converts the string-based form values into the clean {@link WeightEntryInput}. */
function buildInput(values: WeightFormValues): WeightEntryInput {
  return {
    date: values.date || null,
    weightKg: massToKg(values.weight),
    bmi: toNumberOrNull(values.bmi),
    bodyFatPct: toNumberOrNull(values.bodyFat),
    bodyWaterPct: toNumberOrNull(values.bodyWater),
    boneMassKg: massToKg(values.boneMass),
    muscleMassKg: massToKg(values.muscleMass),
  }
}

/**
 * Persists the entry, emitting the outcome to the parent and closing on success.
 * Backend failures are mapped to a toast message rather than thrown, so the
 * dialog stays open for correction.
 *
 * @param values - The validated form values.
 */
async function submitForm(values: WeightFormValues): Promise<void> {
  const input = buildInput(values)
  try {
    if (props.entry) {
      await updateMutation.mutateAsync({
        id: props.entry.id,
        version: props.entry.version,
        input,
      })
      emit('success', t('health.weight.form.updateSuccess'))
    } else {
      await createMutation.mutateAsync(input)
      emit('success', t('health.weight.form.createSuccess'))
    }
    open.value = false
  } catch (error) {
    emit('error', isStaleWrite(error) ? t('app.staleError') : t('health.weight.form.saveError'))
  }
}

const { values, errors, isValid, isSubmitting, handleSubmit, handleBlur, reset } =
  useForm<WeightFormValues>({
    initialValues: defaultValues(),
    validators: {
      date: required<string>(t('health.weight.form.dateRequired')),
      weight: compose(
        required<string>(t('health.weight.form.weightRequired')),
        positiveNumber(t('health.weight.form.weightInvalid')),
      ),
    },
    onSubmit: submitForm,
  })

const isEditing = computed(() => props.entry !== null)
const dialogTitle = computed(() =>
  isEditing.value ? t('health.weight.form.editTitle') : t('health.weight.form.addTitle'),
)
const massUnitLabel = computed(() => (props.weightUnits === 'imperial' ? 'lbs' : 'kg'))
const weightLabel = computed(() => `${t('health.weight.form.weight')} (${massUnitLabel.value})`)
const boneMassLabel = computed(() => `${t('health.weight.form.boneMass')} (${massUnitLabel.value})`)
const muscleMassLabel = computed(
  () => `${t('health.weight.form.muscleMass')} (${massUnitLabel.value})`,
)

/** Seeds the form from the entry being edited, or pristine defaults for "add". */
function populate(): void {
  reset()
  const entry = props.entry
  if (!entry) {
    values.date = todayIsoDate()
    return
  }
  values.date = entry.date ?? todayIsoDate()
  values.weight = displayMassFromKg(entry.weightKg)
  values.bmi = entry.bmi !== null ? String(entry.bmi) : ''
  values.bodyFat = entry.bodyFatPct !== null ? String(entry.bodyFatPct) : ''
  values.bodyWater = entry.bodyWaterPct !== null ? String(entry.bodyWaterPct) : ''
  values.boneMass = displayMassFromKg(entry.boneMassKg)
  values.muscleMass = displayMassFromKg(entry.muscleMassKg)
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
    :description="t('health.weight.form.description')"
    :submit-label="isEditing ? t('health.weight.form.save') : t('health.weight.form.create')"
    :cancel-label="t('health.weight.form.cancel')"
    :close-label="t('health.weight.form.close')"
    :submitting="isSubmitting"
    :can-submit="isValid"
    @submit="handleSubmit"
  >
    <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
      <FormField :label="t('health.weight.form.date')" :error="errors.date" required>
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

      <FormField :label="weightLabel" :error="errors.weight" :placeholder="weightLabel" required>
        <template #default="{ fieldId, describedBy, invalid, placeholder }">
          <input
            :id="fieldId"
            v-model="values.weight"
            :class="inputFieldClass"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            :placeholder="placeholder"
            type="number"
            min="0"
            step="0.1"
            inputmode="decimal"
            :disabled="isSubmitting"
            @blur="handleBlur('weight')"
          />
        </template>
      </FormField>
    </div>

    <details class="mt-2 rounded-input border border-border px-3 py-2">
      <summary class="cursor-pointer text-caption select-none">
        {{ t('health.weight.form.bodyComposition') }}
      </summary>
      <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <FormField :label="t('health.weight.form.bmi')" :placeholder="t('health.weight.form.bmi')">
          <template #default="{ fieldId, placeholder }">
            <input
              :id="fieldId"
              v-model="values.bmi"
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

        <FormField
          :label="t('health.weight.form.bodyFat')"
          :placeholder="t('health.weight.form.bodyFat')"
        >
          <template #default="{ fieldId, placeholder }">
            <input
              :id="fieldId"
              v-model="values.bodyFat"
              :class="inputFieldClass"
              :placeholder="placeholder"
              type="number"
              min="0"
              max="100"
              step="0.1"
              inputmode="decimal"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>

        <FormField
          :label="t('health.weight.form.bodyWater')"
          :placeholder="t('health.weight.form.bodyWater')"
        >
          <template #default="{ fieldId, placeholder }">
            <input
              :id="fieldId"
              v-model="values.bodyWater"
              :class="inputFieldClass"
              :placeholder="placeholder"
              type="number"
              min="0"
              max="100"
              step="0.1"
              inputmode="decimal"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>

        <FormField :label="boneMassLabel" :placeholder="boneMassLabel">
          <template #default="{ fieldId, placeholder }">
            <input
              :id="fieldId"
              v-model="values.boneMass"
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

        <FormField :label="muscleMassLabel" :placeholder="muscleMassLabel">
          <template #default="{ fieldId, placeholder }">
            <input
              :id="fieldId"
              v-model="values.muscleMass"
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
      </div>
    </details>
  </FormDialog>
</template>
