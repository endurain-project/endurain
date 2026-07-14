<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import {
  Activity as ActivityIcon,
  ArrowDown,
  ArrowUp,
  Calendar,
  CalendarDays,
  CalendarRange,
  ChevronLeft,
  ChevronRight,
  Infinity as InfinityIcon,
} from '@lucide/vue'
import type { LucideIcon } from '@lucide/vue'

import type {
  ActivityListFilters,
  ActivitySortBy,
  ActivitySortOrder,
} from '@/features/activities/services/activities'
import type { ActivitySummaryParams } from '@/features/summary/services/summary'
import type { SummaryViewType } from '@/features/summary/types'

import ActivityListItem from '@/features/activities/components/ActivityListItem.vue'
import {
  ACTIVITY_METRIC_COLUMNS,
  sortByToExtraColumn,
} from '@/features/activities/utils/activityListColumns'
import SummaryBreakdownTable from '@/features/summary/components/SummaryBreakdownTable.vue'
import SummaryTotals from '@/features/summary/components/SummaryTotals.vue'
import SummaryTypeBreakdownTable from '@/features/summary/components/SummaryTypeBreakdownTable.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ListPanel } from '@/components/ui/list-panel'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { useRecordsPerPage } from '@/features/config/composables/useRecordsPerPage'
import { useListPagination } from '@/composables/useListPagination'
import {
  getScalarQueryString,
  parseActivityTypeFilterQuery,
  parseIsoDateQuery,
  useRouteQueryReplacement,
} from '@/composables/useRouteQuery'
import {
  useUserActivitiesQuery,
  useUserActivityTypeMapQuery,
} from '@/features/activities/composables/useActivities'
import { useActivitySummaryQuery } from '@/features/summary/composables/useSummary'
import { SUMMARY_ACTIVITY_SORT_OPTIONS } from '@/features/activities/utils/activitySortOptions'
import { presentActivityType } from '@/features/activities/utils/activityType'
import {
  currentMonth,
  currentWeekAnchor,
  currentYear,
  formatPeriodDate,
  monthEnd,
  monthLabel,
  monthStart,
  shiftMonths,
  shiftWeeks,
  weekEnd,
  weekStart,
  yearRange,
} from '@/features/summary/utils/period'

const { t, locale } = useI18n()
const { data: currentUser } = useCurrentUser()
const route = useRoute()

const units = computed(() => currentUser.value?.units ?? 'metric')
const userId = computed(() => currentUser.value?.id ?? null)

// View type (period granularity) and its tab options.
const VIEW_TYPE_OPTIONS: ReadonlyArray<{
  value: SummaryViewType
  labelKey: string
  icon: LucideIcon
}> = [
  { value: 'week', labelKey: 'summary.viewType.week', icon: CalendarDays },
  { value: 'month', labelKey: 'summary.viewType.month', icon: Calendar },
  { value: 'year', labelKey: 'summary.viewType.year', icon: CalendarRange },
  { value: 'lifetime', labelKey: 'summary.viewType.lifetime', icon: InfinityIcon },
]

/** Parses the `viewType` query param, falling back to `'week'` for unknown/missing values. */
function parseViewTypeParam(value: unknown): SummaryViewType {
  const match = VIEW_TYPE_OPTIONS.find((option) => option.value === getScalarQueryString(value))
  return match ? match.value : 'week'
}

/** Parses a `YYYY-MM` query param, falling back when missing or malformed. */
function parseMonthParam(value: unknown, fallback: string): string {
  const raw = getScalarQueryString(value)
  return raw && /^\d{4}-\d{2}$/.test(raw) ? raw : fallback
}

/** Parses the `year` query param, clamped to `[1900, maxYear]`. */
function parseYearParam(value: unknown, maxYear: number): number {
  const raw = getScalarQueryString(value)
  const parsed = raw ? Number(raw) : NaN
  return Number.isFinite(parsed) && parsed >= 1900 && parsed <= maxYear ? parsed : maxYear
}

const viewType = ref<SummaryViewType>(parseViewTypeParam(route.query.viewType))

/**
 * String proxy for the Tabs primitive, whose model is a plain `string`. Reads
 * and writes flow through the typed `viewType` ref so the rest of the view keeps
 * full `SummaryViewType` narrowing; unknown values are ignored.
 */
const viewTypeModel = computed<string>({
  get: () => viewType.value,
  set: (value) => {
    const match = VIEW_TYPE_OPTIONS.find((option) => option.value === value)
    if (match) {
      viewType.value = match.value
    }
  },
})

// Period anchors per view type. Native pickers can be cleared, so each value is
// run through a guard before use to fall back to the current period. Initial
// values are read from the URL query so a refresh doesn't reset the period
// back to the defaults.
const weekAnchor = ref(parseIsoDateQuery(route.query.weekAnchor, currentWeekAnchor()))
const month = ref(parseMonthParam(route.query.month, currentMonth()))
const thisYear = currentYear()
const year = ref(parseYearParam(route.query.year, thisYear))

// Upper bounds for the native pickers and the next-period guard: a period that
// has not started yet can't be summarized.
const maxWeekAnchor = currentWeekAnchor()
const maxMonth = currentMonth()

const safeWeekAnchor = computed(() => weekAnchor.value || currentWeekAnchor())
const safeMonth = computed(() => (/^\d{4}-\d{2}$/.test(month.value) ? month.value : currentMonth()))

/** String proxy for the numeric year input, clamped to a sane range. */
const yearModel = computed<string>({
  get: () => String(year.value),
  set: (value) => {
    const parsed = Number(value)
    if (Number.isFinite(parsed) && parsed >= 1900 && parsed <= thisYear) {
      year.value = parsed
    }
  },
})

// Type filter (code; 0 = all). The summary endpoint filters by type *name*, so
// the selected code is resolved to its backend name via the owned-types map.
const typeFilter = ref(parseActivityTypeFilterQuery(route.query.type))
const typeMapQuery = useUserActivityTypeMapQuery()
const typeOptions = computed(() =>
  [...(typeMapQuery.data.value?.keys() ?? [])].sort((a, b) => a - b),
)
const selectedTypeName = computed(() =>
  typeFilter.value > 0 ? (typeMapQuery.data.value?.get(typeFilter.value) ?? null) : null,
)

// Summary query: the date/year anchor + optional type name, by view type.
const summaryParams = computed<ActivitySummaryParams>(() => {
  switch (viewType.value) {
    case 'week':
      return { date: weekStart(safeWeekAnchor.value), typeName: selectedTypeName.value }
    case 'month':
      return { date: monthStart(safeMonth.value), typeName: selectedTypeName.value }
    case 'year':
      return { year: year.value, typeName: selectedTypeName.value }
    default:
      return { typeName: selectedTypeName.value }
  }
})

const summaryQuery = useActivitySummaryQuery(viewType, summaryParams)
const summary = computed(() => summaryQuery.data.value ?? null)
const isSummaryPending = computed(() => summaryQuery.isPending.value)
const isSummaryError = computed(() => summaryQuery.isError.value)

// Mirror the active filter state into the URL query so it survives page
// refreshes and can be bookmarked/shared; browser back/forward then also works.
const summaryQueryState = computed<Record<string, string>>(() => {
  const params: Record<string, string> = { viewType: viewType.value }
  if (viewType.value === 'week') {
    params.weekAnchor = safeWeekAnchor.value
  } else if (viewType.value === 'month') {
    params.month = safeMonth.value
  } else if (viewType.value === 'year') {
    params.year = String(year.value)
  }
  if (typeFilter.value > 0) {
    params.type = String(typeFilter.value)
  }
  return params
})

useRouteQueryReplacement(summaryQueryState)

const showPeriodNav = computed(() => viewType.value !== 'lifetime')
const showTypeBreakdown = computed(() => typeFilter.value === 0)
const showActivities = computed(() => viewType.value !== 'lifetime')

/** Human-readable label for the selected period, shown under the controls. */
const periodLabel = computed(() => {
  switch (viewType.value) {
    case 'week':
      return `${formatPeriodDate(weekStart(safeWeekAnchor.value), locale.value)} – ${formatPeriodDate(
        weekEnd(safeWeekAnchor.value),
        locale.value,
      )}`
    case 'month':
      return monthLabel(monthStart(safeMonth.value), locale.value)
    case 'year':
      return String(year.value)
    default:
      return t('summary.period.allTime')
  }
})

/**
 * Whether the active period already reaches the present, so stepping forward
 * would enter the future. Drives the next button's disabled state.
 */
const isAtLatestPeriod = computed(() => {
  switch (viewType.value) {
    case 'week':
      return weekStart(safeWeekAnchor.value) >= weekStart(maxWeekAnchor)
    case 'month':
      return safeMonth.value >= maxMonth
    case 'year':
      return year.value >= thisYear
    default:
      return true
  }
})

/** Steps the active anchor back one period. */
function goPrevious(): void {
  if (viewType.value === 'week') {
    weekAnchor.value = shiftWeeks(safeWeekAnchor.value, -1)
  } else if (viewType.value === 'month') {
    month.value = shiftMonths(safeMonth.value, -1)
  } else if (viewType.value === 'year') {
    year.value -= 1
  }
}

/** Steps the active anchor forward one period, unless already at the present. */
function goNext(): void {
  if (isAtLatestPeriod.value) {
    return
  }
  if (viewType.value === 'week') {
    weekAnchor.value = shiftWeeks(safeWeekAnchor.value, 1)
  } else if (viewType.value === 'month') {
    month.value = shiftMonths(safeMonth.value, 1)
  } else if (viewType.value === 'year') {
    year.value += 1
  }
}

// Activities-in-period list, reusing the activities list query. The user id is
// nulled for the lifetime view (the section is hidden) so no needless fetch runs.
const page = ref(1)
const { recordsPerPage } = useRecordsPerPage()
const sortBy = ref<ActivitySortBy>('start_time')
const sortOrder = ref<ActivitySortOrder>('desc')

// Calories/avg HR aren't part of the default headline columns, so sorting by
// either added no visible column (issue #778); append the matching one so its
// values are visible while that sort is active.
const visibleColumns = computed(() => {
  const extraColumn = sortByToExtraColumn(sortBy.value)
  return extraColumn ? [...ACTIVITY_METRIC_COLUMNS, extraColumn] : ACTIVITY_METRIC_COLUMNS
})

/** Inclusive period bounds for the activities list (matches the summary period). */
const activityRange = computed<{ startDate: string | null; endDate: string | null }>(() => {
  switch (viewType.value) {
    case 'week':
      return { startDate: weekStart(safeWeekAnchor.value), endDate: weekEnd(safeWeekAnchor.value) }
    case 'month':
      return { startDate: monthStart(safeMonth.value), endDate: monthEnd(safeMonth.value) }
    case 'year':
      return yearRange(year.value)
    default:
      return { startDate: null, endDate: null }
  }
})

const activityFilters = computed<ActivityListFilters>(() => ({
  type: typeFilter.value > 0 ? typeFilter.value : null,
  startDate: activityRange.value.startDate,
  endDate: activityRange.value.endDate,
  nameSearch: null,
}))

const listUserId = computed(() => (viewType.value === 'lifetime' ? null : userId.value))
const listQuery = useUserActivitiesQuery(
  listUserId,
  page,
  recordsPerPage,
  activityFilters,
  sortBy,
  sortOrder,
)

const activities = computed(() => listQuery.data.value?.records ?? [])
const totalCount = computed(() => listQuery.data.value?.total ?? 0)
const { totalPages: listTotalPages, reset: resetPage } = useListPagination(
  page,
  totalCount,
  recordsPerPage,
)

const isListPending = computed(() => listQuery.isPending.value)
const isListError = computed(() => listQuery.isError.value)
const isListEmpty = computed(
  () => !isListPending.value && !isListError.value && activities.value.length === 0,
)

// Any change to the period, type, or sort changes the result set: restart at page 1.
watch([activityFilters, sortBy, sortOrder], resetPage)

/** Flips the activities sort direction. */
function toggleSortOrder(): void {
  sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
}

function refetchSummary(): void {
  void summaryQuery.refetch()
}

function refetchList(): void {
  void listQuery.refetch()
}
</script>

<template>
  <section class="flex flex-col gap-3">
    <header class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('summary.title') }}</h1>
      <p class="text-body">{{ t('summary.subtitle') }}</p>
    </header>

    <!-- Controls: view-type switch, type filter, and period navigation. -->
    <Card class="flex flex-col gap-3">
      <Tabs v-model="viewTypeModel">
        <TabsList class="grid w-full grid-cols-4" :aria-label="t('summary.viewType.label')">
          <TabsTrigger
            v-for="option in VIEW_TYPE_OPTIONS"
            :key="option.value"
            :value="option.value"
            class="gap-1.5"
          >
            <component :is="option.icon" class="size-4" aria-hidden="true" />
            {{ t(option.labelKey) }}
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div class="flex flex-col gap-1.5">
          <Label for="summary-type-filter">{{ t('summary.filters.type') }}</Label>
          <Select
            id="summary-type-filter"
            v-model="typeFilter"
            class="w-full sm:w-56"
            :aria-label="t('summary.filters.type')"
          >
            <option :value="0">{{ t('summary.filters.allTypes') }}</option>
            <option v-for="code in typeOptions" :key="code" :value="code">
              {{ t(presentActivityType(code).labelKey) }}
            </option>
          </Select>
        </div>

        <div v-if="showPeriodNav" class="flex items-end gap-2">
          <Button
            variant="outline"
            size="icon"
            :aria-label="t('summary.period.previous')"
            @click="goPrevious"
          >
            <ChevronLeft class="size-4" aria-hidden="true" />
          </Button>

          <div class="flex flex-col gap-1.5">
            <Label for="summary-period-picker" class="sr-only">{{
              t('summary.period.picker')
            }}</Label>
            <Input
              v-if="viewType === 'week'"
              id="summary-period-picker"
              v-model="weekAnchor"
              type="date"
              :max="maxWeekAnchor"
              class="h-9 w-44"
              :aria-label="t('summary.period.picker')"
            />
            <Input
              v-else-if="viewType === 'month'"
              id="summary-period-picker"
              v-model="month"
              type="month"
              :max="maxMonth"
              class="h-9 w-44"
              :aria-label="t('summary.period.picker')"
            />
            <Input
              v-else
              id="summary-period-picker"
              v-model="yearModel"
              type="number"
              min="1900"
              :max="thisYear"
              class="h-9 w-28"
              :aria-label="t('summary.period.picker')"
            />
          </div>

          <Button
            variant="outline"
            size="icon"
            :disabled="isAtLatestPeriod"
            :aria-label="t('summary.period.next')"
            @click="goNext"
          >
            <ChevronRight class="size-4" aria-hidden="true" />
          </Button>
        </div>
      </div>

      <p class="text-hint">{{ periodLabel }}</p>
    </Card>

    <!-- Summary error / loading / content. -->
    <Card v-if="isSummaryError">
      <ErrorState
        :title="t('summary.error.title')"
        :description="t('summary.error.description')"
        @retry="refetchSummary"
      >
        <template #action="{ retry }">
          <Button variant="outline" size="sm" @click="retry">{{ t('summary.error.retry') }}</Button>
        </template>
      </ErrorState>
    </Card>

    <div v-else-if="isSummaryPending" class="flex flex-col gap-3" aria-busy="true">
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Card v-for="n in 5" :key="n" class="flex flex-col gap-2">
          <Skeleton class="h-3 w-16" />
          <Skeleton class="h-6 w-20" />
        </Card>
      </div>
      <Card class="flex flex-col gap-3">
        <Skeleton class="h-4 w-28" />
        <Skeleton v-for="n in 4" :key="n" class="h-5 w-full" />
      </Card>
    </div>

    <template v-else-if="summary">
      <SummaryTotals :totals="summary.totals" :units="units" />
      <SummaryBreakdownTable :view-type="viewType" :rows="summary.breakdown" :units="units" />
      <SummaryTypeBreakdownTable
        v-if="showTypeBreakdown"
        :rows="summary.typeBreakdown"
        :units="units"
      />
    </template>

    <!-- Activities recorded in the selected period (hidden for lifetime). -->
    <section v-if="showActivities" class="flex flex-col gap-3">
      <h2 class="text-item-title">{{ t('summary.activities.title') }}</h2>

      <ListPanel
        v-model:page="page"
        :is-loading="isListPending"
        :is-error="isListError"
        :is-empty="isListEmpty"
        :error-title="t('activities.list.error.title')"
        :error-description="t('activities.list.error.description')"
        :retry-label="t('activities.list.error.retry')"
        paginated
        :total-pages="listTotalPages"
        @retry="refetchList"
      >
        <template #header>
          <div class="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <p class="text-hint">{{ t('activities.list.resultCount', { count: totalCount }) }}</p>
            <div class="flex items-center gap-2">
              <Label for="summary-activity-sort" class="sr-only">{{
                t('activities.list.sort.label')
              }}</Label>
              <Select
                id="summary-activity-sort"
                v-model="sortBy"
                class="h-9 w-auto"
                :aria-label="t('activities.list.sort.label')"
              >
                <option
                  v-for="option in SUMMARY_ACTIVITY_SORT_OPTIONS"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ t(option.labelKey) }}
                </option>
              </Select>
              <Button
                variant="outline"
                size="icon"
                :aria-label="
                  sortOrder === 'desc'
                    ? t('activities.list.sort.descending')
                    : t('activities.list.sort.ascending')
                "
                @click="toggleSortOrder"
              >
                <ArrowDown v-if="sortOrder === 'desc'" class="size-4" aria-hidden="true" />
                <ArrowUp v-else class="size-4" aria-hidden="true" />
              </Button>
            </div>
          </div>
        </template>

        <template #loading>
          <div class="divide-y divide-border" aria-busy="true">
            <div v-for="n in 6" :key="n" class="flex items-center gap-3 px-4 py-3">
              <Skeleton class="size-10 shrink-0 rounded-full" />
              <div class="flex-1 space-y-2">
                <Skeleton class="h-4 w-1/3" />
                <Skeleton class="h-3 w-1/5" />
              </div>
              <Skeleton class="hidden h-8 w-40 sm:block" />
            </div>
          </div>
        </template>

        <template #empty>
          <EmptyState :title="t('activities.list.empty.filteredTitle')" variant="filtered">
            <template #icon>
              <ActivityIcon class="size-8" aria-hidden="true" />
            </template>
          </EmptyState>
        </template>

        <ul class="divide-y divide-border">
          <li v-for="activity in activities" :key="activity.id">
            <ActivityListItem :activity="activity" :units="units" :columns="visibleColumns" />
          </li>
        </ul>
      </ListPanel>
    </section>
  </section>
</template>
