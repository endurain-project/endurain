import type { ActivitySortBy } from '@/features/activities/services/activities'

/** A selectable activity-list sort option. */
export interface ActivitySortOption {
  /** Server-recognized field used to order activities. */
  value: ActivitySortBy
  /** i18n key for the option label. */
  labelKey: string
}

/** All sort options offered by the activities list, in display order. */
export const ACTIVITY_SORT_OPTIONS: readonly ActivitySortOption[] = [
  { value: 'start_time', labelKey: 'activities.list.sort.startTime' },
  { value: 'name', labelKey: 'activities.list.sort.name' },
  { value: 'type', labelKey: 'activities.list.sort.type' },
  { value: 'location', labelKey: 'activities.list.sort.location' },
  { value: 'distance', labelKey: 'activities.list.sort.distance' },
  { value: 'duration', labelKey: 'activities.list.sort.duration' },
  { value: 'pace', labelKey: 'activities.list.sort.pace' },
  { value: 'elevation', labelKey: 'activities.list.sort.elevation' },
  { value: 'calories', labelKey: 'activities.list.sort.calories' },
  { value: 'average_hr', labelKey: 'activities.list.sort.avgHr' },
]

/** Sort options available for the period-scoped list in the summary view. */
export const SUMMARY_ACTIVITY_SORT_OPTIONS: readonly ActivitySortOption[] =
  ACTIVITY_SORT_OPTIONS.filter((option) => option.value !== 'location')
