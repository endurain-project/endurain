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
import { useUpdatePoopTargetMutation } from '@/features/health/composables/useHealth'

const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  /** The current health targets, providing the record id, owner, and poop count. */
  targets: HealthTargets
}>()

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const updateTargetMutation = useUpdatePoopTargetMutation()

/** Form shape: the numeric target is kept as a string and parsed at submit. */
interface TargetFormValues {
  count: string
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
      poopCount: targetToCount(values.count),
    })
    emit('success', t('health.poop.target.saveSuccess'))
    open.value = false
  } catch (error) {
    emit('error', isStaleWrite(error) ? t('app.staleError') : t('health.poop.target.saveError'))
  }
}

const { values, isSubmitting, handleSubmit, reset } = useForm<TargetFormValues>({
  initialValues: { count: '' },
  onSubmit: submitForm,
})

/** Seeds the field from the current target each time the dialog opens. */
function populate(): void {
  reset()
  values.count = props.targets.poopCount !== null ? String(props.targets.poopCount) : ''
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
    :title="t('health.poop.target.title')"
    :description="t('health.poop.target.description')"
    :submit-label="t('health.poop.target.save')"
    :cancel-label="t('health.poop.target.cancel')"
    :close-label="t('health.poop.target.close')"
    :submitting="isSubmitting"
    @submit="handleSubmit"
  >
    <FormField
      :label="t('health.poop.target.count')"
      :placeholder="t('health.poop.target.count')"
      :hint="t('health.poop.target.hint')"
    >
      <template #default="{ fieldId, placeholder }">
        <input
          :id="fieldId"
          v-model="values.count"
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
