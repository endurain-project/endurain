<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Pencil, Trash2 } from '@lucide/vue'

import type { Goal } from '@/features/goals/types'
import type { UnitKey } from '@/i18n'
import type { Schemas } from '@/types'

import { useUnitFormat } from '@/composables/useUnitFormat'
import {
  ACTIVITY_TYPE_ICONS,
  ACTIVITY_TYPE_LABEL_KEYS,
  GOAL_METRIC_LABEL_KEYS,
  INTERVAL_LABEL_KEYS,
  metersToDistanceValue,
  metersToElevationValue,
  secondsToHoursMinutes,
} from '@/features/goals/utils/goalFormat'

const props = defineProps<{
  /** The goal to render. */
  goal: Goal
  /** The viewer's measurement system, used for distance/elevation display. */
  units: Schemas['Units']
}>()

const emit = defineEmits<{
  edit: [goal: Goal]
  delete: [goal: Goal]
}>()

const { t } = useI18n()
const { withUnit, duration } = useUnitFormat()

/** The activity icon for the goal's activity type. */
const activityIcon = computed(() => ACTIVITY_TYPE_ICONS[props.goal.activityType])

/** The translated activity-type name shown as the row title. */
const activityLabel = computed(() => t(ACTIVITY_TYPE_LABEL_KEYS[props.goal.activityType]))

/** The unit of a distance target. */
const distanceUnit = computed<UnitKey>(() => (props.units === 'imperial' ? 'mi' : 'km'))

/** The unit of an elevation target. */
const elevationUnit = computed<UnitKey>(() => (props.units === 'imperial' ? 'ft' : 'm'))

/** The formatted target value, expressed in the viewer's units. */
const targetText = computed<string>(() => {
  const goal = props.goal
  switch (goal.goalType) {
    case 'calories':
      return withUnit(`${goal.calories ?? 0}`, 'kcal')
    case 'activities':
      return `${goal.activitiesNumber ?? 0}`
    case 'distance':
      return withUnit(
        `${metersToDistanceValue(goal.distanceMeters ?? 0, props.units)}`,
        distanceUnit.value,
      )
    case 'elevation':
      return withUnit(
        `${metersToElevationValue(goal.elevationMeters ?? 0, props.units)}`,
        elevationUnit.value,
      )
    case 'duration': {
      const { hours, minutes } = secondsToHoursMinutes(goal.durationSeconds ?? 0)
      return duration(hours, minutes)
    }
  }
  return ''
})

/** The interval · metric · target summary shown beneath the activity name. */
const summary = computed(
  () =>
    `${t(INTERVAL_LABEL_KEYS[props.goal.interval])} · ${t(GOAL_METRIC_LABEL_KEYS[props.goal.goalType])} · ${targetText.value}`,
)
</script>

<template>
  <div class="flex items-center gap-3 px-4 py-3">
    <div
      class="flex size-10 shrink-0 items-center justify-center rounded-input bg-muted-foreground/15 text-muted-foreground"
    >
      <component :is="activityIcon" class="size-5" aria-hidden="true" />
    </div>

    <div class="min-w-0 flex-1">
      <p class="truncate font-medium text-foreground">{{ activityLabel }}</p>
      <p class="truncate text-hint">{{ summary }}</p>
    </div>

    <div class="flex shrink-0 items-center gap-1">
      <button
        type="button"
        class="inline-flex size-8 items-center justify-center rounded-input text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
        :aria-label="t('settings.goals.list.edit', { name: activityLabel })"
        @click="emit('edit', goal)"
      >
        <Pencil class="size-4" aria-hidden="true" />
      </button>
      <button
        type="button"
        class="inline-flex size-8 items-center justify-center rounded-input text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-destructive/30"
        :aria-label="t('settings.goals.list.delete', { name: activityLabel })"
        @click="emit('delete', goal)"
      >
        <Trash2 class="size-4" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>
