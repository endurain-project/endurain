<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'
import { ArrowLeft } from '@lucide/vue'

import type { ActivityOwner, HrZoneBucket } from '@/features/activities/types'
import type { StreamChart, XAxisBasis } from '@/features/activities/utils/streams'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import ActivityDetailHeader from '@/features/activities/components/ActivityDetailHeader.vue'
import ActivityGallery from '@/features/activities/components/ActivityGallery.vue'
import ActivityGearCard from '@/features/activities/components/ActivityGearCard.vue'
import ActivityHrZones from '@/features/activities/components/ActivityHrZones.vue'
import ActivityLapsTable from '@/features/activities/components/ActivityLapsTable.vue'
import ActivityMetricsGrid from '@/features/activities/components/ActivityMetricsGrid.vue'
import ActivityPrivacyAlerts from '@/features/activities/components/ActivityPrivacyAlerts.vue'
import ActivityStreamChart from '@/features/activities/components/ActivityStreamChart.vue'
import ActivityWorkoutSets from '@/features/activities/components/ActivityWorkoutSets.vue'
import {
  useActivityExerciseTitlesQuery,
  useActivityLapsQuery,
  useActivityOwnerQuery,
  useActivityQuery,
  useActivitySetsQuery,
  useActivityStreamsQuery,
  useActivityWorkoutStepsQuery,
  useDisplayUnits,
} from '@/features/activities/composables/useActivityDetail'
import {
  buildMetricVisibility,
  canViewField,
  isActivityOwner,
  streamMetricVisibility,
} from '@/features/activities/utils/privacy'
import { extractHrZones } from '@/features/activities/utils/hrZones'
import {
  availableXAxisBases,
  buildStreamCharts,
  defaultXAxisBasis,
  extractTrackPoints,
} from '@/features/activities/utils/streams'
import { getStorageItem, setStorageItem } from '@/lib/storage'

const route = useRoute()
const { t } = useI18n()
const { data: currentUser } = useCurrentUser()
const units = useDisplayUnits()

const activityId = computed(() => {
  const raw = Number(route.params.id)
  return Number.isFinite(raw) && raw > 0 ? raw : null
})

const { data: activity, isPending, isError, refetch } = useActivityQuery(activityId)

const activityLoaded = computed(() => !!activity.value)
const { data: streams } = useActivityStreamsQuery(activityId, activityLoaded)
const { data: laps } = useActivityLapsQuery(activityId, activityLoaded)

const currentUserId = computed(() => currentUser.value?.id ?? null)

// Only the owner manages gear; non-owners (incl. public viewers) never see the
// gear card.
const isOwner = computed(
  () => !!activity.value && isActivityOwner(activity.value, currentUserId.value),
)

const ownerQuery = useActivityOwnerQuery(activity)
const owner = computed<ActivityOwner | null>(() => {
  if (!activity.value) {
    return null
  }
  // Self: build the identity from the cached current user.
  if (currentUser.value && isActivityOwner(activity.value, currentUserId.value)) {
    return {
      name: currentUser.value.name,
      username: currentUser.value.username,
      avatarUrl: currentUser.value.avatarUrl,
    }
  }
  // Other viewers (authenticated or public): the fetched owner, or null when
  // the "show user info on public links" setting withholds it.
  return ownerQuery.data.value ?? null
})

const metricVisibility = computed(() =>
  activity.value ? buildMetricVisibility(activity.value, currentUserId.value) : null,
)

const trackPoints = computed(() => extractTrackPoints(streams.value ?? []))
const showMap = computed(
  () =>
    !!activity.value &&
    canViewField(activity.value, 'hideMap', currentUserId.value) &&
    trackPoints.value.length > 0,
)

// X-axis basis (distance ↔ time), shared by every stream chart. The user's
// choice is remembered on this device; it applies only when that basis is
// available for the activity, otherwise the smart default wins (distance when
// GPS makes it real, else time).
const X_AXIS_STORAGE_KEY = 'activityXAxisBasis'
const xAxisChoice = ref<XAxisBasis | null>(getStorageItem<XAxisBasis>(X_AXIS_STORAGE_KEY))

const xAxisBases = computed<XAxisBasis[]>(() =>
  activity.value ? availableXAxisBases(streams.value ?? [], activity.value) : [],
)
const showXAxisToggle = computed(() => xAxisBases.value.length > 1)

const xAxisBasis = computed<XAxisBasis>(() => {
  if (!activity.value) {
    return 'time'
  }
  if (xAxisChoice.value && xAxisBases.value.includes(xAxisChoice.value)) {
    return xAxisChoice.value
  }
  return defaultXAxisBasis(streams.value ?? [], activity.value)
})

function setXAxisBasis(basis: XAxisBasis): void {
  xAxisChoice.value = basis
  setStorageItem(X_AXIS_STORAGE_KEY, basis)
}

const streamCharts = computed(() => {
  if (!activity.value) {
    return []
  }
  return buildStreamCharts(
    streams.value ?? [],
    activity.value,
    units.value,
    streamMetricVisibility(activity.value, currentUserId.value),
    {
      basis: xAxisBasis.value,
      text: {
        distance: t('activities.streams.xAxis.distance'),
        time: t('activities.streams.xAxis.time'),
      },
    },
  )
})

const showLaps = computed(
  () =>
    !!activity.value &&
    canViewField(activity.value, 'hideLaps', currentUserId.value) &&
    (laps.value?.length ?? 0) > 0,
)

// Workout steps/sets. Fetched for every activity (like laps/streams); the
// section self-hides when there is no data, mirroring v1 which fetches these
// regardless of activity type and lets data presence drive display.
const { data: workoutSteps } = useActivityWorkoutStepsQuery(activityId, activityLoaded)
const { data: workoutSets } = useActivitySetsQuery(activityId, activityLoaded)
const hasWorkoutData = computed(
  () => (workoutSteps.value?.length ?? 0) > 0 || (workoutSets.value?.length ?? 0) > 0,
)
// The exercise-name catalogue is only needed once we know workout data exists.
const { data: exerciseTitles } = useActivityExerciseTitlesQuery(hasWorkoutData)

const showWorkout = computed(
  () =>
    !!activity.value &&
    canViewField(activity.value, 'hideWorkoutSetsSteps', currentUserId.value) &&
    hasWorkoutData.value,
)

// Active tab when both laps and workout sets are available (v1's pill switch).
const splitsTab = ref('laps')

// HR zones live on the HR stream; gate them by the same HR visibility as the
// HR chart so a privacy-restricted viewer never sees them.
const hrZones = computed(() => extractHrZones(streams.value ?? []))
const showHrZones = computed(
  () =>
    !!activity.value &&
    canViewField(activity.value, 'hideHr', currentUserId.value) &&
    (hrZones.value?.length ?? 0) > 0,
)

// One chart-grid panel: either a metric chart or the HR-zones card. The HR
// zones are inserted immediately after the HR chart so they sit side by side
// in the two-column grid.
type ChartGridPanel =
  | { kind: 'chart'; key: string; chart: StreamChart }
  | { kind: 'hr-zones'; key: string; zones: HrZoneBucket[] }

const chartPanels = computed<ChartGridPanel[]>(() => {
  const panels: ChartGridPanel[] = []
  const zones = showHrZones.value ? hrZones.value : null
  let zonesInserted = false
  for (const chart of streamCharts.value) {
    panels.push({ kind: 'chart', key: chart.metric, chart })
    if (chart.metric === 'hr' && zones) {
      panels.push({ kind: 'hr-zones', key: 'hr-zones', zones })
      zonesInserted = true
    }
  }
  // HR zones present but no HR chart (unlikely) — still surface them.
  if (zones && !zonesInserted) {
    panels.push({ kind: 'hr-zones', key: 'hr-zones', zones })
  }
  return panels
})

// `data` is `null` (not `undefined`) once a fetch resolves to a missing or
// non-shareable activity; distinguish that from the still-loading state.
const notFound = computed(() => !isPending.value && !isError.value && activity.value === null)
</script>

<template>
  <div class="flex flex-col gap-3">
    <Button variant="ghost" size="sm" class="self-start" @click="$router.back()">
      <ArrowLeft class="size-4" />
      {{ t('activities.back') }}
    </Button>

    <!-- Loading: mirror the summary (athlete header + metrics), the map, the
         charts grid, and the splits table so the placeholder matches the load. -->
    <template v-if="isPending">
      <!-- Summary: athlete header + at-a-glance metrics (one card, as loaded). -->
      <Card class="flex flex-col gap-3" aria-busy="true">
        <div class="flex items-start justify-between gap-3">
          <div class="flex min-w-0 items-center gap-3">
            <Skeleton class="size-14 shrink-0 rounded-full" />
            <div class="space-y-2">
              <Skeleton class="h-4 w-32" />
              <Skeleton class="h-5 w-40 rounded-full" />
              <Skeleton class="h-3 w-48" />
            </div>
          </div>
          <Skeleton class="size-8 shrink-0 rounded-input" />
        </div>
        <Skeleton class="h-7 w-2/3" />
        <div class="border-t border-border pt-4">
          <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Skeleton v-for="n in 6" :key="n" class="h-16 rounded-input" />
          </div>
        </div>
      </Card>

      <!-- Map zone: matches the gallery's height. -->
      <Skeleton class="h-72 w-full rounded-card lg:h-150" />

      <!-- Charts grid: two-column stream-chart placeholders. -->
      <div class="grid gap-3 lg:grid-cols-2" aria-busy="true">
        <Card v-for="n in 4" :key="n" class="flex min-w-0 flex-col gap-3">
          <div class="flex items-center gap-2">
            <Skeleton class="size-2.5 rounded-full" />
            <Skeleton class="h-5 w-32" />
          </div>
          <Skeleton class="h-56 w-full rounded-input" />
          <div class="flex flex-wrap gap-x-6 gap-y-2">
            <div class="space-y-1">
              <Skeleton class="h-3 w-12" />
              <Skeleton class="h-4 w-16" />
            </div>
            <div class="space-y-1">
              <Skeleton class="h-3 w-12" />
              <Skeleton class="h-4 w-16" />
            </div>
          </div>
        </Card>
      </div>

      <!-- Splits/laps table. -->
      <Card class="flex flex-col gap-3" aria-busy="true">
        <Skeleton class="h-5 w-24" />
        <div class="space-y-2">
          <Skeleton v-for="n in 4" :key="n" class="h-8 w-full" />
        </div>
      </Card>
    </template>

    <!-- Network error -->
    <ErrorState
      v-else-if="isError"
      :title="t('activities.error.title')"
      :description="t('activities.error.description')"
    >
      <template #action="{ retry }">
        <Button
          variant="outline"
          size="sm"
          @click="
            () => {
              retry()
              refetch()
            }
          "
        >
          {{ t('activities.error.retry') }}
        </Button>
      </template>
    </ErrorState>

    <!-- Not found / not shareable -->
    <Card v-else-if="notFound" class="flex flex-col items-center gap-3 py-12 text-center">
      <p class="text-item-title">{{ t('activities.notFound.title') }}</p>
      <p class="max-w-sm text-body">
        {{ t('activities.notFound.description') }}
      </p>
      <Button as-child variant="outline" size="sm">
        <RouterLink :to="{ name: 'home' }">{{ t('activities.notFound.action') }}</RouterLink>
      </Button>
    </Card>

    <!-- Content -->
    <template v-else-if="activity && metricVisibility">
      <!-- Summary: title/user + at-a-glance metrics, before the map (v1 order). -->
      <Card class="flex flex-col gap-3">
        <ActivityDetailHeader
          :activity="activity"
          :units="units"
          :current-user-id="currentUserId"
          :owner="owner"
        />
        <div class="border-t border-border pt-4">
          <ActivityMetricsGrid :activity="activity" :units="units" :visibility="metricVisibility" />
        </div>
      </Card>

      <ActivityPrivacyAlerts :activity="activity" :current-user-id="currentUserId" />

      <ActivityGallery
        :points="showMap ? trackPoints : []"
        :activity-id="activity.id"
        :is-owner="isOwner"
      />

      <ActivityGearCard v-if="isOwner" :activity="activity" />

      <div v-if="chartPanels.length > 0" class="flex flex-col gap-3">
        <div v-if="showXAxisToggle" class="flex justify-end">
          <Tabs
            :model-value="xAxisBasis"
            @update:model-value="(value) => setXAxisBasis(value as XAxisBasis)"
          >
            <TabsList>
              <TabsTrigger v-if="xAxisBases.includes('distance')" value="distance">
                {{ t('activities.streams.xAxis.distance') }}
              </TabsTrigger>
              <TabsTrigger v-if="xAxisBases.includes('time')" value="time">
                {{ t('activities.streams.xAxis.time') }}
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
        <div class="grid gap-3 lg:grid-cols-2">
          <template v-for="panel in chartPanels" :key="panel.key">
            <ActivityStreamChart
              v-if="panel.kind === 'chart'"
              :title="t(panel.chart.titleKey)"
              :render="panel.chart.render"
              :stats="panel.chart.stats"
            />
            <Card v-else class="flex min-w-0 flex-col gap-3">
              <div class="flex items-center gap-2">
                <span class="bg-hr size-2.5 rounded-full" aria-hidden="true" />
                <h3 class="text-card-heading">{{ t('activities.hrZones.title') }}</h3>
              </div>
              <div class="flex flex-1 items-center">
                <ActivityHrZones :zones="panel.zones" class="w-full" />
              </div>
            </Card>
          </template>
        </div>
      </div>

      <Card v-if="showLaps || showWorkout" class="flex flex-col gap-3">
        <!-- Both available → switch between Laps and Sets (mirrors v1's pills). -->
        <Tabs v-if="showLaps && showWorkout" v-model="splitsTab">
          <TabsList>
            <TabsTrigger value="laps">{{ t('activities.laps.title') }}</TabsTrigger>
            <TabsTrigger value="sets">{{ t('activities.workout.title') }}</TabsTrigger>
          </TabsList>
          <TabsContent value="laps">
            <ActivityLapsTable :laps="laps ?? []" :activity="activity" :units="units" />
          </TabsContent>
          <TabsContent value="sets">
            <ActivityWorkoutSets
              :workout-steps="workoutSteps ?? []"
              :workout-sets="workoutSets ?? []"
              :exercise-titles="exerciseTitles ?? []"
            />
          </TabsContent>
        </Tabs>

        <!-- Only one available → a plain titled table. -->
        <template v-else-if="showLaps">
          <h2 class="text-card-heading">{{ t('activities.laps.title') }}</h2>
          <ActivityLapsTable :laps="laps ?? []" :activity="activity" :units="units" />
        </template>
        <template v-else>
          <h2 class="text-card-heading">{{ t('activities.workout.title') }}</h2>
          <ActivityWorkoutSets
            :workout-steps="workoutSteps ?? []"
            :workout-sets="workoutSets ?? []"
            :exercise-titles="exerciseTitles ?? []"
          />
        </template>
      </Card>
    </template>
  </div>
</template>
