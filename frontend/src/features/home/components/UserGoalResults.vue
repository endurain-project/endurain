<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Target, type LucideIcon } from '@lucide/vue'

import type { GoalActivityType, GoalMetric, GoalProgress } from '@/features/goals/types'
import type { Units } from '@/features/activities/utils/format'

import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { Skeleton } from '@/components/ui/skeleton'
import { activityTypeIcon } from '@/features/activities/utils/activityType'
import {
  formatDistance,
  formatElevation,
  formatHmsDuration,
} from '@/features/activities/utils/format'

const props = defineProps<{
  /** The viewer's per-goal progress for the current interval. */
  goals: GoalProgress[]
  /** The viewer's unit system. */
  units: Units
  /** Whether the goal-results query is still loading. */
  isLoading?: boolean
}>()

const { t } = useI18n()

/** Maps a goal's sport-level activity type to a representative numeric type. */
const GOAL_ACTIVITY_TYPE: Record<GoalActivityType, number> = {
  run: 1,
  bike: 4,
  swim: 8,
  walk: 11,
  strength: 19,
  cardio: 41,
}

/** A goal prepared for display: localized labels, formatted values, and an icon. */
interface GoalRow {
  goalId: number
  icon: LucideIcon
  label: string
  metricLabel: string
  total: string
  target: string
  unit: string
  percentage: number
  reached: boolean
}

/** Formats one numeric value for the goal's metric (value only, no unit). */
function formatByMetric(value: number, goalType: GoalMetric, activityType: number): string {
  if (goalType === 'distance') {
    return formatDistance(value, activityType, props.units).value
  }
  if (goalType === 'elevation') {
    return formatElevation(value, props.units).value
  }
  if (goalType === 'duration') {
    return formatHmsDuration(value)
  }
  return String(Math.round(value))
}

/** Resolves the unit suffix shown after the total/target values. */
function unitFor(goalType: GoalMetric, activityType: number): string {
  if (goalType === 'distance') {
    return t(formatDistance(0, activityType, props.units).unit)
  }
  if (goalType === 'elevation') {
    return t(formatElevation(0, props.units).unit)
  }
  if (goalType === 'calories') {
    return t('settings.goals.unit.calories')
  }
  return ''
}

const rows = computed<GoalRow[]>(() =>
  props.goals.map((goal) => {
    const activityType = GOAL_ACTIVITY_TYPE[goal.activityType]
    return {
      goalId: goal.goalId,
      icon: activityTypeIcon(activityType),
      label: `${t(`settings.goals.activityType.${goal.activityType}`)} · ${t(`settings.goals.interval.${goal.interval}`)}`,
      metricLabel: t(`settings.goals.metric.${goal.goalType}`),
      total: formatByMetric(goal.total, goal.goalType, activityType),
      target: goal.target === null ? '—' : formatByMetric(goal.target, goal.goalType, activityType),
      unit: unitFor(goal.goalType, activityType),
      percentage: Math.round(goal.percentageCompleted),
      reached: goal.percentageCompleted >= 100,
    }
  }),
)

/** Clamps a completion percentage to the 0–100 bar range. */
function barWidth(percentage: number): string {
  return `${Math.min(100, Math.max(0, percentage))}%`
}
</script>

<template>
  <Card class="flex flex-col gap-3">
    <h2 class="text-card-heading">{{ t('home.goals.title') }}</h2>

    <!-- Loading -->
    <div v-if="isLoading" class="space-y-4" aria-busy="true">
      <div v-for="n in 3" :key="n" class="space-y-2">
        <Skeleton class="h-4 w-1/2" />
        <Skeleton class="h-2 w-full" />
      </div>
    </div>

    <!-- Empty -->
    <EmptyState
      v-else-if="rows.length === 0"
      :title="t('home.goals.empty.title')"
      :description="t('home.goals.empty.description')"
    >
      <template #icon>
        <Target class="size-8" aria-hidden="true" />
      </template>
    </EmptyState>

    <!-- Goal list -->
    <ul v-else class="space-y-4">
      <li v-for="row in rows" :key="row.goalId" class="space-y-1.5">
        <div class="flex items-center gap-2">
          <component
            :is="row.icon"
            class="size-4 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
          <span class="min-w-0 flex-1 truncate text-item-title">{{ row.label }}</span>
          <span class="text-caption">{{ row.percentage }}%</span>
        </div>

        <div class="h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            class="h-full rounded-full transition-all"
            :class="row.reached ? 'bg-goal' : 'bg-brand'"
            :style="{ width: barWidth(row.percentage) }"
          />
        </div>

        <p class="text-hint">
          {{ row.metricLabel }}: {{ row.total }} / {{ row.target
          }}<span v-if="row.unit"> {{ row.unit }}</span>
        </p>
      </li>
    </ul>
  </Card>
</template>
