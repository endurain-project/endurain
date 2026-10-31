<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import type { StreakSettings } from '@/features/streaks/types'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { FormField } from '@/components/ui/form-field'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { Switch } from '@/components/ui/switch'
import { useForm } from '@/composables/useForm'
import { useToasts } from '@/composables/useToasts'
import { ACTIVITY_TYPE_LABEL_KEYS } from '@/features/activities/utils/activityType'
import { MAX_ACTIVITIES_PER_WEEK } from '@/features/streaks/types'
import { useUpdateStreakSettingsMutation } from '@/features/streaks/composables/useStreaks'

const props = defineProps<{
  /** The loaded settings; seeds the form and refreshes its unedited fields. */
  settings: StreakSettings
}>()

const { t } = useI18n()
const toasts = useToasts()
const updateMutation = useUpdateStreakSettingsMutation()

/** Form shape: the type list is edited as a Set-backed array plus an "all" flag. */
interface StreakForm {
  minActivitiesPerWeek: number
  countAllTypes: boolean
  activityTypes: number[]
  showOnProfile: boolean
}

/** Every known activity type, sorted by its translated label. */
const typeOptions = computed(() =>
  Object.entries(ACTIVITY_TYPE_LABEL_KEYS)
    .map(([code, labelKey]) => ({ code: Number(code), label: t(labelKey) }))
    .sort((a, b) => a.label.localeCompare(b.label)),
)

/**
 * Maps stored settings to the form shape.
 *
 * @param settings - The stored settings.
 * @returns Fresh form values (the type list is copied).
 */
function toForm(settings: StreakSettings): StreakForm {
  return {
    minActivitiesPerWeek: settings.minActivitiesPerWeek,
    countAllTypes: settings.activityTypes === null,
    activityTypes: [...(settings.activityTypes ?? [])],
    showOnProfile: settings.showOnProfile,
  }
}

/** Compares two form values; type lists by content. */
function sameValue(a: unknown, b: unknown): boolean {
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, index) => item === b[index])
  }
  return a === b
}

const { values, errors, isSubmitting, handleSubmit } = useForm<StreakForm>({
  initialValues: toForm(props.settings),
  validators: {
    minActivitiesPerWeek: (value) =>
      Number.isInteger(value) && value >= 1 && value <= MAX_ACTIVITIES_PER_WEEK
        ? null
        : t('settings.goals.streak.minActivitiesInvalid', { max: MAX_ACTIVITIES_PER_WEEK }),
  },
  onSubmit: submit,
})

// The card stays mounted while the settings query refreshes (e.g. after a save
// in another tab). Adopt the new stored values for every field the user has not
// edited, so a later save cannot write back a stale value such as an old
// `showOnProfile`.
watch(
  () => props.settings,
  (next, previous) => {
    const nextForm = toForm(next)
    const previousForm = toForm(previous)
    for (const key of Object.keys(nextForm) as (keyof StreakForm)[]) {
      if (sameValue(values[key], previousForm[key])) {
        Object.assign(values, { [key]: nextForm[key] })
      }
    }
  },
)

/** Shown when "all types" is off but no type is ticked. */
const typesError = ref<string | null>(null)

/** Toggles one activity type in the selection. */
function toggleType(code: number, checked: boolean): void {
  const selected = new Set(values.activityTypes)
  if (checked) {
    selected.add(code)
  } else {
    selected.delete(code)
  }
  values.activityTypes = [...selected].sort((a, b) => a - b)
  typesError.value = null
}

/**
 * Persists the settings, surfacing the outcome as a toast.
 *
 * @param form - The current form values.
 */
async function submit(form: StreakForm): Promise<void> {
  if (!form.countAllTypes && form.activityTypes.length === 0) {
    typesError.value = t('settings.goals.streak.typesRequired')
    return
  }
  try {
    await updateMutation.mutateAsync({
      minActivitiesPerWeek: Number(form.minActivitiesPerWeek),
      activityTypes: form.countAllTypes ? null : form.activityTypes,
      showOnProfile: form.showOnProfile,
    })
    toasts.success(t('settings.goals.streak.saveSuccess'))
  } catch {
    toasts.error(t('settings.goals.streak.saveError'))
  }
}
</script>

<template>
  <Card class="flex flex-col gap-3" as="form" @submit.prevent="handleSubmit">
    <div class="flex flex-col gap-1">
      <h2 class="text-card-heading">{{ t('settings.goals.streak.title') }}</h2>
      <p class="text-body">{{ t('settings.goals.streak.subtitle') }}</p>
    </div>

    <FormField
      class="sm:max-w-xs"
      :label="t('settings.goals.streak.minActivities')"
      :hint="t('settings.goals.streak.minActivitiesHint')"
      :error="errors.minActivitiesPerWeek"
    >
      <template #default="{ fieldId }">
        <input
          :id="fieldId"
          v-model.number="values.minActivitiesPerWeek"
          :class="inputFieldClass"
          name="minActivitiesPerWeek"
          type="number"
          inputmode="numeric"
          min="1"
          :max="MAX_ACTIVITIES_PER_WEEK"
          step="1"
          :disabled="isSubmitting"
        />
      </template>
    </FormField>

    <div class="flex flex-col gap-2">
      <Switch v-model="values.countAllTypes" :disabled="isSubmitting">
        {{ t('settings.goals.streak.allTypes') }}
      </Switch>

      <fieldset
        v-if="!values.countAllTypes"
        class="flex flex-col gap-2 rounded-input border border-border p-3"
      >
        <legend class="px-1 text-caption">
          {{ t('settings.goals.streak.typesLegend', { count: values.activityTypes.length }) }}
        </legend>
        <div
          class="grid max-h-64 grid-cols-1 gap-x-4 gap-y-1 overflow-y-auto sm:grid-cols-2 lg:grid-cols-3"
        >
          <label
            v-for="option in typeOptions"
            :key="option.code"
            class="flex cursor-pointer items-center gap-2 py-0.5 text-body"
          >
            <input
              type="checkbox"
              class="size-4 accent-brand"
              :checked="values.activityTypes.includes(option.code)"
              :disabled="isSubmitting"
              @change="toggleType(option.code, ($event.target as HTMLInputElement).checked)"
            />
            {{ option.label }}
          </label>
        </div>
        <p v-if="typesError" class="text-field-error" role="alert">{{ typesError }}</p>
      </fieldset>
    </div>

    <Switch v-model="values.showOnProfile" :disabled="isSubmitting">
      {{ t('settings.goals.streak.showOnProfile') }}
    </Switch>

    <div class="flex justify-begin">
      <Button type="submit" class="w-full sm:w-auto" :disabled="isSubmitting">
        <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
        {{ isSubmitting ? t('settings.goals.streak.saving') : t('settings.goals.streak.save') }}
      </Button>
    </div>
  </Card>
</template>
