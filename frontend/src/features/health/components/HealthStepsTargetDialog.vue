<script setup lang="ts">
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { HealthTargets } from '@/features/health/types'

import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { useForm } from '@/composables/useForm'
import { isStaleWrite } from '@/services/ifMatch'
import { toNumberOrNull } from '@/utils/number'
import { useUpdateStepsTargetMutation } from '@/features/health/composables/useHealth'

const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  /** The current health targets, providing the record id, owner, and steps. */
  targets: HealthTargets
}>()

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const updateTargetMutation = useUpdateStepsTargetMutation()

/** Form shape: the numeric target is kept as a string and parsed at submit. */
interface TargetFormValues {
  steps: string
}

/** Converts the target string to a rounded whole-number count (or `null` to clear). */
function targetToCount(raw: string): number | null {
  const value = toNumberOrNull(raw)
  if (value === null || value <= 0) {
    return null
  }
  return Math.round(value)
}

/**
 * Persists the target, emitting the outcome to the parent and closing on
 * success. An empty field clears the target (sends `null`).
 *
 * @param values - The form values.
 */
async function submitForm(values: TargetFormValues): Promise<void> {
  try {
    await updateTargetMutation.mutateAsync({
      version: props.targets.version,
      steps: targetToCount(values.steps),
    })
    emit('success', t('health.steps.target.saveSuccess'))
    open.value = false
  } catch (error) {
    emit('error', isStaleWrite(error) ? t('app.staleError') : t('health.steps.target.saveError'))
  }
}

const { values, isSubmitting, handleSubmit, reset } = useForm<TargetFormValues>({
  initialValues: { steps: '' },
  onSubmit: submitForm,
})

/** Seeds the field from the current target each time the dialog opens. */
function populate(): void {
  reset()
  values.steps = props.targets.steps !== null ? String(props.targets.steps) : ''
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
    :title="t('health.steps.target.title')"
    :description="t('health.steps.target.description')"
    :submit-label="t('health.steps.target.save')"
    :cancel-label="t('health.steps.target.cancel')"
    :close-label="t('health.steps.target.close')"
    :submitting="isSubmitting"
    @submit="handleSubmit"
  >
    <FormField
      :label="t('health.steps.target.steps')"
      :placeholder="t('health.steps.target.steps')"
      :hint="t('health.steps.target.hint')"
    >
      <template #default="{ fieldId, placeholder }">
        <input
          :id="fieldId"
          v-model="values.steps"
          :class="inputFieldClass"
          :placeholder="placeholder"
          type="number"
          min="0"
          step="1"
          inputmode="numeric"
          :disabled="isSubmitting"
        />
      </template>
    </FormField>
  </FormDialog>
</template>
