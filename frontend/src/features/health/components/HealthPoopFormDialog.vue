<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { BristolType, PoopColor, PoopEntry, PoopEntryInput } from '@/features/health/types'

import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { useForm } from '@/composables/useForm'
import { required } from '@/utils/validators'
import {
  useCreatePoopEntryMutation,
  useUpdatePoopEntryMutation,
} from '@/features/health/composables/useHealth'
import {
  dateTimeLocalToIso,
  nowDateTimeLocalInput,
  toDateTimeLocalInput,
} from '@/features/health/utils/healthFormat'

const open = defineModel<boolean>('open', { required: true })

const props = withDefaults(
  defineProps<{
    /** The poop entry being edited, or `null`/absent when logging a new one. */
    entry?: PoopEntry | null
  }>(),
  { entry: null },
)

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const createMutation = useCreatePoopEntryMutation()
const updateMutation = useUpdatePoopEntryMutation()

/** The Bristol Stool Scale types offered in the select, in order. */
const BRISTOL_TYPES: BristolType[] = [1, 2, 3, 4, 5, 6, 7]

/** The stool colours offered in the select, in display order. */
const COLORS: PoopColor[] = [
  'brown',
  'dark_brown',
  'light_brown',
  'yellow',
  'green',
  'black',
  'red',
  'white',
]

/** Maximum length of the free-text notes field. */
const NOTES_MAX_LENGTH = 500

/** Form shape: every field is kept as a string and parsed at submit. */
interface PoopFormValues {
  dateTime: string
  bristolType: string
  color: string
  notes: string
}

/** The pristine values used for "add" and as the reset baseline. */
function defaultValues(): PoopFormValues {
  return {
    dateTime: nowDateTimeLocalInput(),
    bristolType: '',
    color: '',
    notes: '',
  }
}

/** Converts the string-based form values into the clean {@link PoopEntryInput}. */
function buildInput(values: PoopFormValues): PoopEntryInput {
  const notes = values.notes.trim()
  return {
    // The input yields an offset-less local wall clock; convert it to a real
    // UTC instant so the backend stores the moment the user meant rather than
    // reading their wall clock as if it were UTC.
    dateTime: dateTimeLocalToIso(values.dateTime),
    bristolType: values.bristolType ? (Number(values.bristolType) as BristolType) : null,
    color: values.color ? (values.color as PoopColor) : null,
    notes: notes ? notes : null,
  }
}

/**
 * Persists the entry, emitting the outcome to the parent and closing on success.
 * Backend failures are mapped to a toast message rather than thrown, so the
 * dialog stays open for correction.
 *
 * @param values - The validated form values.
 */
async function submitForm(values: PoopFormValues): Promise<void> {
  const input = buildInput(values)
  try {
    if (props.entry) {
      await updateMutation.mutateAsync({
        id: props.entry.id,
        userId: props.entry.userId,
        input,
      })
      emit('success', t('health.poop.form.updateSuccess'))
    } else {
      await createMutation.mutateAsync(input)
      emit('success', t('health.poop.form.createSuccess'))
    }
    open.value = false
  } catch {
    emit('error', t('health.poop.form.saveError'))
  }
}

const { values, errors, isValid, isSubmitting, handleSubmit, handleBlur, reset } =
  useForm<PoopFormValues>({
    initialValues: defaultValues(),
    validators: {
      dateTime: required<string>(t('health.poop.form.dateTimeRequired')),
    },
    onSubmit: submitForm,
  })

const isEditing = computed(() => props.entry !== null)
const dialogTitle = computed(() =>
  isEditing.value ? t('health.poop.form.editTitle') : t('health.poop.form.addTitle'),
)

/** Seeds the form from the entry being edited, or pristine defaults for "add". */
function populate(): void {
  reset()
  const entry = props.entry
  if (!entry) {
    values.dateTime = nowDateTimeLocalInput()
    return
  }
  // Render the stored instant as the viewer's wall clock; string-slicing the
  // ISO showed the UTC time, which disagreed with the list row.
  values.dateTime = toDateTimeLocalInput(entry.dateTime) || nowDateTimeLocalInput()
  values.bristolType = entry.bristolType !== null ? String(entry.bristolType) : ''
  values.color = entry.color ?? ''
  values.notes = entry.notes ?? ''
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
    :description="t('health.poop.form.description')"
    :submit-label="isEditing ? t('health.poop.form.save') : t('health.poop.form.create')"
    :cancel-label="t('health.poop.form.cancel')"
    :close-label="t('health.poop.form.close')"
    :submitting="isSubmitting"
    :can-submit="isValid"
    @submit="handleSubmit"
  >
    <div class="flex flex-col gap-2">
      <FormField :label="t('health.poop.form.dateTime')" :error="errors.dateTime" required>
        <template #default="{ fieldId, describedBy, invalid }">
          <input
            :id="fieldId"
            v-model="values.dateTime"
            :class="inputFieldClass"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            type="datetime-local"
            :disabled="isSubmitting"
            @blur="handleBlur('dateTime')"
          />
        </template>
      </FormField>

      <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <FormField :label="t('health.poop.form.bristolType')">
          <template #default="{ fieldId }">
            <select
              :id="fieldId"
              v-model="values.bristolType"
              :class="inputFieldClass"
              :disabled="isSubmitting"
            >
              <option value="">{{ t('health.poop.form.none') }}</option>
              <option v-for="type in BRISTOL_TYPES" :key="type" :value="String(type)">
                {{ t('health.poop.list.bristolBadge', { type }) }}
              </option>
            </select>
          </template>
        </FormField>

        <FormField :label="t('health.poop.form.color')">
          <template #default="{ fieldId }">
            <select
              :id="fieldId"
              v-model="values.color"
              :class="inputFieldClass"
              :disabled="isSubmitting"
            >
              <option value="">{{ t('health.poop.form.none') }}</option>
              <option v-for="color in COLORS" :key="color" :value="color">
                {{ t(`health.poop.form.colors.${color}`) }}
              </option>
            </select>
          </template>
        </FormField>
      </div>

      <FormField :label="t('health.poop.form.notes')">
        <template #default="{ fieldId }">
          <textarea
            :id="fieldId"
            v-model="values.notes"
            :class="inputFieldClass"
            :maxlength="NOTES_MAX_LENGTH"
            rows="3"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>
    </div>
  </FormDialog>
</template>
