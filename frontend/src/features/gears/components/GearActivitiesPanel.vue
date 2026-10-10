<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, type RouteLocationRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'

import type { GearActivity } from '@/features/gears/types'

import { ListPanel } from '@/components/ui/list-panel'
import { Skeleton } from '@/components/ui/skeleton'
import { useRecordsPerPage } from '@/features/config/composables/useRecordsPerPage'
import { useListPagination } from '@/composables/useListPagination'
import { useGearActivitiesQuery } from '@/features/gears/composables/useGearActivities'
import { formatZonedDateTime } from '@/utils/datetime'

/**
 * The activities section of the gear detail page: a read-only, paginated list
 * of the activities recorded on the gear, each row deep-linking to the activity
 * detail page. Self-contained — it owns its query and paging state, so the
 * detail view only has to place it in the layout.
 */
const props = defineProps<{
  /** The parent gear id whose activities are listed. */
  gearId: number
}>()

const { t, locale } = useI18n()

// Records-per-page is the server-enforced setting shared across paged lists.
const { recordsPerPage } = useRecordsPerPage()

const activitiesPage = ref(1)
const activitiesQuery = useGearActivitiesQuery(() => props.gearId, activitiesPage, recordsPerPage)
const activities = computed(() => activitiesQuery.data.value?.records ?? [])
// Each row deep-links to the activity detail page (`/activity/:id`).
const activityRows = computed<{ activity: GearActivity; to: RouteLocationRaw }[]>(() =>
  activities.value.map((activity) => ({
    activity,
    to: { name: 'activity', params: { id: String(activity.id) } },
  })),
)
const activitiesTotal = computed(() => activitiesQuery.data.value?.total ?? 0)
const { totalPages: activitiesTotalPages } = useListPagination(
  activitiesPage,
  activitiesTotal,
  recordsPerPage,
)

/** Formats an activity start time as a localized medium date. */
function formatActivityDate(activity: GearActivity): string {
  return formatZonedDateTime(activity.startTime, activity.timezone, locale.value, {
    dateStyle: 'medium',
  })
}
</script>

<template>
  <ListPanel
    v-model:page="activitiesPage"
    :is-loading="activitiesQuery.isPending.value"
    :is-error="activitiesQuery.isError.value"
    :is-empty="activities.length === 0"
    :error-title="t('gears.activities.error.title')"
    :error-description="t('gears.activities.error.description')"
    :retry-label="t('gears.error.retry')"
    paginated
    :total-pages="activitiesTotalPages"
    @retry="() => activitiesQuery.refetch()"
  >
    <template #header>
      <div class="px-4 py-3">
        <h2 class="text-card-heading">{{ t('gears.activities.title') }}</h2>
      </div>
    </template>

    <template #loading>
      <div class="divide-y divide-border" aria-busy="true">
        <div v-for="n in 5" :key="n" class="flex items-center justify-between gap-3 px-4 py-3">
          <Skeleton class="h-4 w-1/3" />
          <Skeleton class="h-3 w-20" />
        </div>
      </div>
    </template>

    <template #empty>
      <p class="px-4 py-8 text-center text-hint">{{ t('gears.activities.empty') }}</p>
    </template>

    <ul class="divide-y divide-border">
      <li v-for="row in activityRows" :key="row.activity.id">
        <RouterLink
          :to="row.to"
          class="flex cursor-pointer items-center justify-between gap-3 px-4 py-3 transition-colors hover:bg-accent"
        >
          <span class="min-w-0 flex-1 truncate text-body">{{ row.activity.name }}</span>
          <span class="shrink-0 text-hint tabular-nums">{{
            formatActivityDate(row.activity)
          }}</span>
        </RouterLink>
      </li>
    </ul>
  </ListPanel>
</template>
