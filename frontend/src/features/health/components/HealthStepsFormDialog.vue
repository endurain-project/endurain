<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { StepsEntry, StepsEntryInput } from '@/features/health/types'
import type { Validator } from '@/utils/validators'

import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { useForm } from '@/composables/useForm'
import { isStaleWrite } from '@/services/ifMatch'
import { todayIsoDate } from '@/utils/datetime'
import { toNumberOrNull } from '@/utils/number'
import { compose, required } from '@/utils/validators'
import {
  useCreateStepsEntryMutation,
  useUpdateStepsEntryMutation,
} from '@/features/health/composables/useHealth'

const open = defineModel<boolean>('open', { required: true })

const props = withDefaults(
  defineProps<{
    /** The steps entry being edited, or `null`/absent when logging a new one. */
    entry?: StepsEntry | null
  }>(),
  { entry: null },
)

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const createMutation = useCreateStepsEntryMutation()
const updateMutation = useUpdateStepsEntryMutation()

/** Form shape: the numeric steps field is kept as a string and parsed at submit. */
interface StepsFormValues {
  date: string
  steps: string
}

/** Rejects non-numeric or non-positive input (runs after `required`). */
function positiveNumber(message: string): Validator<string> {
  return (value) => {
    const parsed = toNumberOrNull(value)
    return parsed === null || parsed <= 0 ? message : null
  }
}

/** The pristine values used for "add" and as the reset baseline. */
function defaultValues(): StepsFormValues {
  return {
    date: todayIsoDate(),
    steps: '',
  }
}

/** Converts a validated steps string to a rounded whole-number count. */
function stepsToCount(raw: string): number {
  return Math.round(Number(raw.trim()))
}

/** Converts the string-based form values into the clean {@link StepsEntryInput}. */
function buildInput(values: StepsFormValues): StepsEntryInput {
  return {
    date: values.date || null,
    steps: stepsToCount(values.steps),
  }
}

/**
 * Persists the entry, emitting the outcome to the parent and closing on success.
 * Backend failures are mapped to a toast message rather than thrown, so the
 * dialog stays open for correction.
 *
 * @param values - The validated form values.
 */
async function submitForm(values: StepsFormValues): Promise<void> {
  const input = buildInput(values)
  try {
    if (props.entry) {
      await updateMutation.mutateAsync({
        id: props.entry.id,
        version: props.entry.version,
        input,
      })
      emit('success', t('health.steps.form.updateSuccess'))
    } else {
      await createMutation.mutateAsync(input)
      emit('success', t('health.steps.form.createSuccess'))
    }
    open.value = false
  } catch (error) {
    emit('error', isStaleWrite(error) ? t('app.staleError') : t('health.steps.form.saveError'))
  }
}

const { values, errors, isValid, isSubmitting, handleSubmit, handleBlur, reset } =
  useForm<StepsFormValues>({
    initialValues: defaultValues(),
    validators: {
      date: required<string>(t('health.steps.form.dateRequired')),
      steps: compose(
        required<string>(t('health.steps.form.stepsRequired')),
        positiveNumber(t('health.steps.form.stepsInvalid')),
      ),
    },
    onSubmit: submitForm,
  })

const isEditing = computed(() => props.entry !== null)
const dialogTitle = computed(() =>
  isEditing.value ? t('health.steps.form.editTitle') : t('health.steps.form.addTitle'),
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
  values.steps = entry.steps !== null ? String(entry.steps) : ''
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
    :description="t('health.steps.form.description')"
    :submit-label="isEditing ? t('health.steps.form.save') : t('health.steps.form.create')"
    :cancel-label="t('health.steps.form.cancel')"
    :close-label="t('health.steps.form.close')"
    :submitting="isSubmitting"
    :can-submit="isValid"
    @submit="handleSubmit"
  >
    <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
      <FormField :label="t('health.steps.form.date')" :error="errors.date" required>
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

      <FormField
        :label="t('health.steps.form.steps')"
        :error="errors.steps"
        :placeholder="t('health.steps.form.steps')"
        required
      >
        <template #default="{ fieldId, describedBy, invalid, placeholder }">
          <input
            :id="fieldId"
            v-model="values.steps"
            :class="inputFieldClass"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            :placeholder="placeholder"
            type="number"
            min="0"
            step="1"
            inputmode="numeric"
            :disabled="isSubmitting"
            @blur="handleBlur('steps')"
          />
        </template>
      </FormField>
    </div>
  </FormDialog>
</template>
