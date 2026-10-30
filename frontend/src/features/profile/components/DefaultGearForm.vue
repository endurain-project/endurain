<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import type { DefaultGear, DefaultGearValues } from '@/features/profile/types'
import type { GearOptionsByType } from '@/features/profile/composables/useDefaultGear'
import type { Gear } from '@/features/gears/types'

import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { useForm } from '@/composables/useForm'
import { isStaleWrite } from '@/services/ifMatch'
import { useToasts } from '@/composables/useToasts'
import { useUpdateDefaultGearMutation } from '@/features/profile/composables/useDefaultGear'
import { DEFAULT_GEAR_GROUPS } from '@/features/profile/utils/defaultGearFields'

const props = defineProps<{
  /** The loaded default-gear record; seeds the form (mounted only after load). */
  defaultGear: DefaultGear
  /** Gears keyed by type, populating each activity's selector. */
  options: GearOptionsByType
}>()

const { t } = useI18n()
const toasts = useToasts()
const updateMutation = useUpdateDefaultGearMutation()

/** Projects the loaded record onto the editable assignments (drops id/userId). */
function toFormValues(gear: DefaultGear): DefaultGearValues {
  return {
    runGearId: gear.runGearId,
    trailRunGearId: gear.trailRunGearId,
    virtualRunGearId: gear.virtualRunGearId,
    walkGearId: gear.walkGearId,
    hikeGearId: gear.hikeGearId,
    rideGearId: gear.rideGearId,
    mtbRideGearId: gear.mtbRideGearId,
    gravelRideGearId: gear.gravelRideGearId,
    virtualRideGearId: gear.virtualRideGearId,
    owsGearId: gear.owsGearId,
    tennisGearId: gear.tennisGearId,
    alpineSkiGearId: gear.alpineSkiGearId,
    nordicSkiGearId: gear.nordicSkiGearId,
    snowboardGearId: gear.snowboardGearId,
    windsurfGearId: gear.windsurfGearId,
  }
}

/** The gears offered for a given gear type (empty when none exist). */
function gearsForType(gearType: number): Gear[] {
  return props.options[gearType] ?? []
}

/**
 * Persists the assignments, merging them over the loaded record. The outcome is surfaced as a toast.
 *
 * @param values - The current assignments.
 */
async function submitForm(values: DefaultGearValues): Promise<void> {
  try {
    await updateMutation.mutateAsync({ ...props.defaultGear, ...values })
    toasts.success(t('settings.profile.defaultGear.saveSuccess'))
  } catch (error) {
    toasts.error(
      isStaleWrite(error) ? t('app.staleError') : t('settings.profile.defaultGear.saveError'),
    )
  }
}

const { values, isSubmitting, handleSubmit } = useForm<DefaultGearValues>({
  initialValues: toFormValues(props.defaultGear),
  onSubmit: submitForm,
})
</script>

<template>
  <form class="flex flex-col gap-3" novalidate @submit.prevent="handleSubmit">
    <div class="grid gap-x-6 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
      <div v-for="group in DEFAULT_GEAR_GROUPS" :key="group.titleKey" class="flex flex-col gap-2">
        <p class="text-caption">{{ t(group.titleKey) }}</p>
        <FormField v-for="field in group.fields" :key="field.key" :label="t(field.labelKey)">
          <template #default="{ fieldId }">
            <select
              :id="fieldId"
              v-model="values[field.key]"
              :class="inputFieldClass"
              :disabled="isSubmitting"
            >
              <option :value="null">{{ t('settings.profile.defaultGear.notDefined') }}</option>
              <option v-for="gear in gearsForType(field.gearType)" :key="gear.id" :value="gear.id">
                {{ gear.nickname }}
              </option>
            </select>
          </template>
        </FormField>
      </div>
    </div>

    <div class="flex justify-begin">
      <Button type="submit" class="w-full sm:w-auto" :disabled="isSubmitting">
        <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
        {{
          isSubmitting
            ? t('settings.profile.defaultGear.saving')
            : t('settings.profile.defaultGear.save')
        }}
      </Button>
    </div>
  </form>
</template>
