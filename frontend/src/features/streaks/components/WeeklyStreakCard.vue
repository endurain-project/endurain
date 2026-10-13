<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Flame, Trophy } from '@lucide/vue'

import type { StreakWeek, WeeklyStreak } from '@/features/streaks/types'

import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { formatMediumDate } from '@/utils/datetime'

const props = defineProps<{
  /** The streak to show; `null`/`undefined` while loading or when unavailable. */
  streak: WeeklyStreak | null | undefined
  /** Whether the streak query is still loading. */
  isLoading?: boolean
  /** Hides the "keep it going" nudge (e.g. when viewing someone else's profile). */
  isOtherUser?: boolean
}>()

const { t, locale } = useI18n()

/**
 * Formats an ISO `YYYY-MM-DD` week start as a short localized date. Anchored at
 * local noon so the calendar day never shifts with the viewer's UTC offset.
 */
function formatWeek(iso: string): string {
  return formatMediumDate(`${iso}T12:00:00`, locale.value)
}

/** The flame's state drives its color: lit, at risk, or cold. */
const flameState = computed<'lit' | 'risk' | 'cold'>(() => {
  const streak = props.streak
  if (!streak || streak.currentStreak === 0) {
    return 'cold'
  }
  return streak.atRisk ? 'risk' : 'lit'
})

/** This week's progress toward the target, clamped to 0–100%. */
const weekProgress = computed(() => {
  const streak = props.streak
  if (!streak) {
    return 0
  }
  return Math.min(100, Math.round((streak.currentWeekCount / streak.minActivitiesPerWeek) * 100))
})

/** The status line under the big number. */
const statusText = computed(() => {
  const streak = props.streak
  if (!streak) {
    return ''
  }
  const progress = {
    count: streak.currentWeekCount,
    target: streak.minActivitiesPerWeek,
  }
  if (streak.currentWeekMet) {
    return t('home.streak.status.met', progress)
  }
  if (streak.atRisk && !props.isOtherUser) {
    const remaining = streak.minActivitiesPerWeek - streak.currentWeekCount
    return t('home.streak.status.atRisk', { remaining }, remaining)
  }
  return t('home.streak.status.progress', progress)
})

/** Accessible description for one history dot. */
function weekLabel(week: StreakWeek): string {
  return t(
    week.met ? 'home.streak.history.weekMet' : 'home.streak.history.weekMissed',
    { date: formatWeek(week.weekStart), count: week.activityCount },
    week.activityCount,
  )
}

/** Fill class for one history dot. */
function dotClass(week: StreakWeek): string {
  if (week.met) {
    return 'bg-goal'
  }
  return week.activityCount > 0 ? 'bg-brand/40' : 'bg-muted-foreground/15'
}

/** The longest-streak caption, including its date range when known. */
const longestText = computed(() => {
  const streak = props.streak
  if (!streak || streak.longestStreak === 0) {
    return t('home.streak.longest.none')
  }
  const weeks = t('home.streak.weeks', { count: streak.longestStreak }, streak.longestStreak)
  if (!streak.longestStreakStart || !streak.longestStreakEnd) {
    return t('home.streak.longest.label', { weeks })
  }
  return t('home.streak.longest.range', {
    weeks,
    start: formatWeek(streak.longestStreakStart),
    end: formatWeek(streak.longestStreakEnd),
  })
})

const isPersonalBest = computed(
  () =>
    !!props.streak &&
    props.streak.currentStreak > 0 &&
    props.streak.currentStreak >= props.streak.longestStreak,
)
</script>

<template>
  <Card class="@container flex flex-col gap-3">
    <h2 class="text-card-heading">{{ t('home.streak.title') }}</h2>

    <!-- Loading -->
    <div v-if="isLoading" class="space-y-3" aria-busy="true">
      <Skeleton class="h-10 w-32" />
      <Skeleton class="h-2 w-full" />
      <Skeleton class="h-4 w-full" />
    </div>

    <p v-else-if="!streak" class="text-hint">{{ t('home.streak.unavailable') }}</p>

    <template v-else>
      <div class="flex flex-col gap-3 @lg:flex-row @lg:items-center @lg:gap-6">
        <!-- Current streak -->
        <div class="flex items-center gap-3">
          <div
            :class="
              cn(
                'flex size-12 shrink-0 items-center justify-center rounded-full',
                flameState === 'lit' && 'bg-brand/15 text-brand',
                flameState === 'risk' && 'bg-warning/15 text-warning',
                flameState === 'cold' && 'bg-muted text-muted-foreground',
              )
            "
          >
            <Flame class="size-6" aria-hidden="true" />
          </div>
          <div class="min-w-0">
            <p class="text-metric" data-testid="streak-current">
              {{ t('home.streak.weeks', { count: streak.currentStreak }, streak.currentStreak) }}
            </p>
            <p class="text-caption">
              {{ t('home.streak.current') }}
              <span v-if="isPersonalBest" class="inline-flex items-center gap-1 text-goal">
                · <Trophy class="size-3.5" aria-hidden="true" />{{ t('home.streak.personalBest') }}
              </span>
            </p>
          </div>
        </div>

        <!-- This week -->
        <div class="flex min-w-0 flex-1 flex-col gap-1.5">
          <div
            class="h-2 w-full overflow-hidden rounded-full bg-muted-foreground/15"
            role="progressbar"
            :aria-valuenow="streak.currentWeekCount"
            aria-valuemin="0"
            :aria-valuemax="streak.minActivitiesPerWeek"
            :aria-label="t('home.streak.thisWeek')"
          >
            <div
              class="h-full rounded-full transition-all"
              :class="streak.currentWeekMet ? 'bg-goal' : 'bg-brand'"
              :style="{ width: `${weekProgress}%` }"
            />
          </div>
          <p
            :class="cn('text-hint', streak.atRisk && !isOtherUser && 'text-warning')"
            data-testid="streak-status"
          >
            {{ statusText }}
          </p>
        </div>
      </div>

      <!-- History strip: oldest → current week -->
      <div class="flex flex-col gap-1.5">
        <ol class="flex gap-1" :aria-label="t('home.streak.history.label')">
          <li
            v-for="(week, index) in streak.recentWeeks"
            :key="week.weekStart"
            :class="
              cn(
                'h-3 flex-1 rounded-sm',
                dotClass(week),
                index === streak.recentWeeks.length - 1 &&
                  'ring-1 ring-foreground/40 ring-offset-1 ring-offset-card',
              )
            "
            :title="weekLabel(week)"
          >
            <span class="sr-only">{{ weekLabel(week) }}</span>
          </li>
        </ol>
        <div class="flex justify-between text-micro text-muted-foreground">
          <span>{{
            t('home.streak.history.weeksAgo', { count: streak.recentWeeks.length - 1 })
          }}</span>
          <span>{{ t('home.streak.thisWeek') }}</span>
        </div>
      </div>

      <p class="border-t border-border pt-3 text-hint">{{ longestText }}</p>
    </template>
  </Card>
</template>
