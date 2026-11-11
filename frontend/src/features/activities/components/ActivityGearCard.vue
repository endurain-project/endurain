<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { Pencil, Plus, Trash2 } from '@lucide/vue'

import type { Activity } from '@/features/activities/types'

import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { useToasts } from '@/composables/useToasts'
import {
  useActivityGearOptionsQuery,
  useSetActivityGearMutation,
} from '@/features/activities/composables/useActivityDetail'
import { activityTypeToGearType } from '@/features/activities/utils/activityType'
import { useGearQuery } from '@/features/gears/composables/useGears'
import { presentGearType } from '@/features/gears/utils/gearType'

const props = defineProps<{
  /** The activity whose gear association is shown and (owner-only) edited. */
  activity: Activity
}>()

const { t } = useI18n()
const toasts = useToasts()

/** The gear type compatible with this activity, or `null` when none applies. */
const gearType = computed(() => activityTypeToGearType(props.activity.activityType))
const gearId = computed(() => props.activity.gearId)

// The currently associated gear, for its nickname + deep link. Gated by
// useGearQuery on a valid id, so it stays idle when no gear is set.
const { data: currentGear } = useGearQuery(gearId)
const optionsQuery = useActivityGearOptionsQuery(gearType)
const options = computed(() => optionsQuery.data.value ?? [])

const setGearMutation = useSetActivityGearMutation()
const isSaving = computed(() => setGearMutation.isPending.value)

const isPickerOpen = ref(false)
const isRemoveOpen = ref(false)
const selectedGearId = ref<number | null>(props.activity.gearId)

// Hidden when this activity family has no gear and none is already set.
const showCard = computed(() => gearType.value !== null || gearId.value !== null)

/** Icon for the activity's gear family: shoes for a walk or run, a bike for a ride. */
const gearIcon = computed(() => {
  const type = gearType.value ?? currentGear.value?.gearType
  return type == null ? null : presentGearType(type).icon
})
const canSubmit = computed(() => selectedGearId.value !== null)

// Re-seed the picker with the activity's current gear each time it opens.
watch(isPickerOpen, (open) => {
  if (open) {
    selectedGearId.value = props.activity.gearId
  }
})

/** Assigns or changes the activity's gear, then closes the picker. */
async function submitGear(): Promise<void> {
  if (selectedGearId.value === null) {
    return
  }
  try {
    await setGearMutation.mutateAsync({ activity: props.activity, gearId: selectedGearId.value })
    isPickerOpen.value = false
    toasts.success(t('activities.gear.saveSuccess'))
  } catch {
    toasts.error(t('activities.gear.saveError'))
  }
}

/** Removes the gear association from the activity, then closes the dialog. */
async function removeGear(): Promise<void> {
  try {
    await setGearMutation.mutateAsync({ activity: props.activity, gearId: null })
    isRemoveOpen.value = false
    toasts.success(t('activities.gear.removeSuccess'))
  } catch {
    toasts.error(t('activities.gear.removeError'))
  }
}
</script>

<template>
  <div v-if="showCard" class="min-w-0">
    <div v-if="activity.gearId" class="flex min-w-0 items-center gap-1">
      <component
        v-if="gearIcon"
        :is="gearIcon"
        class="size-4 shrink-0 text-muted-foreground"
        aria-hidden="true"
      />
      <RouterLink
        :to="{ name: 'gear', params: { id: String(activity.gearId) } }"
        class="max-w-48 truncate text-sm text-brand hover:underline"
      >
        {{ currentGear?.nickname ?? t('activities.gear.loading') }}
      </RouterLink>
      <Button
        v-if="gearType !== null"
        variant="ghost"
        size="icon-sm"
        :aria-label="t('activities.gear.change')"
        @click="isPickerOpen = true"
      >
        <Pencil class="size-3.5" />
      </Button>
      <Button
        variant="ghostDestructive"
        size="icon-sm"
        :aria-label="t('activities.gear.remove')"
        @click="isRemoveOpen = true"
      >
        <Trash2 class="size-3.5" />
      </Button>
    </div>

    <Button v-else-if="gearType !== null" variant="outline" size="sm" @click="isPickerOpen = true">
      <Plus class="size-3.5" />
      {{ t('activities.gear.add') }}
    </Button>

    <!-- Add / change gear -->
    <FormDialog
      v-model:open="isPickerOpen"
      :title="activity.gearId ? t('activities.gear.changeTitle') : t('activities.gear.addTitle')"
      :submit-label="t('activities.gear.save')"
      :cancel-label="t('activities.gear.cancel')"
      :close-label="t('activities.gear.close')"
      :submitting="isSaving"
      :can-submit="canSubmit"
      @submit="submitGear"
    >
      <FormField :label="t('activities.gear.selectLabel')">
        <template #default="{ fieldId }">
          <select
            :id="fieldId"
            v-model="selectedGearId"
            :class="inputFieldClass"
            :disabled="isSaving"
          >
            <option :value="null" disabled>{{ t('activities.gear.selectPlaceholder') }}</option>
            <option v-for="gear in options" :key="gear.id" :value="gear.id">
              {{ gear.nickname }}
            </option>
          </select>
        </template>
      </FormField>
      <p v-if="options.length === 0" class="text-hint">{{ t('activities.gear.noGears') }}</p>
    </FormDialog>

    <!-- Remove gear -->
    <ConfirmDialog
      v-model:open="isRemoveOpen"
      :title="t('activities.gear.removeTitle')"
      :description="t('activities.gear.removeBody')"
      :confirm-label="t('activities.gear.remove')"
      :cancel-label="t('activities.gear.cancel')"
      :close-label="t('activities.gear.close')"
      :pending="isSaving"
      @confirm="removeGear"
    />
  </div>
</template>
