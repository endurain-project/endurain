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
import { useUpdateSleepTargetMutation } from '@/features/health/composables/useHealth'

const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  /** The current health targets, providing the record id, owner, and sleep goal. */
  targets: HealthTargets
}>()

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const updateTargetMutation = useUpdateSleepTargetMutation()

/** Form shape: hours and minutes are kept as strings and combined at submit. */
interface TargetFormValues {
  hours: string
  minutes: string
}

/** Combines the hours/minutes fields into total seconds (or `null` to clear). */
function targetToSeconds(formValues: TargetFormValues): number | null {
  const hours = toNumberOrNull(formValues.hours) ?? 0
  const minutes = toNumberOrNull(formValues.minutes) ?? 0
  const total = Math.round(hours * 3600 + minutes * 60)
  return total > 0 ? total : null
}

/**
 * Persists the target, emitting the outcome to the parent and closing on
 * success. Empty fields clear the target (sends `null`).
 *
 * @param formValues - The form values.
 */
async function submitForm(formValues: TargetFormValues): Promise<void> {
  try {
    await updateTargetMutation.mutateAsync({
      version: props.targets.version,
      sleepSeconds: targetToSeconds(formValues),
    })
    emit('success', t('health.sleep.target.saveSuccess'))
    open.value = false
  } catch (error) {
    emit('error', isStaleWrite(error) ? t('app.staleError') : t('health.sleep.target.saveError'))
  }
}

const { values, isSubmitting, handleSubmit, reset } = useForm<TargetFormValues>({
  initialValues: { hours: '', minutes: '' },
  onSubmit: submitForm,
})

/** Seeds the fields from the current target each time the dialog opens. */
function populate(): void {
  reset()
  const seconds = props.targets.sleepSeconds
  if (seconds != null && seconds > 0) {
    values.hours = String(Math.floor(seconds / 3600))
    values.minutes = String(Math.round((seconds % 3600) / 60))
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
    :title="t('health.sleep.target.title')"
    :description="t('health.sleep.target.description')"
    :submit-label="t('health.sleep.target.save')"
    :cancel-label="t('health.sleep.target.cancel')"
    :close-label="t('health.sleep.target.close')"
    :submitting="isSubmitting"
    @submit="handleSubmit"
  >
    <div class="grid grid-cols-2 gap-2">
      <FormField :label="t('health.sleep.target.hours')">
        <template #default="{ fieldId }">
          <input
            :id="fieldId"
            v-model="values.hours"
            :class="inputFieldClass"
            type="number"
            min="0"
            step="1"
            inputmode="numeric"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>

      <FormField :label="t('health.sleep.target.minutes')" :hint="t('health.sleep.target.hint')">
        <template #default="{ fieldId }">
          <input
            :id="fieldId"
            v-model="values.minutes"
            :class="inputFieldClass"
            type="number"
            min="0"
            max="59"
            step="1"
            inputmode="numeric"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>
    </div>
  </FormDialog>
</template>
