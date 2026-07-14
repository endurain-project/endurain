<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { Activity as ActivityIcon, ArrowDown, ArrowUp, Search, X } from '@lucide/vue'

import type {
  ActivityListFilters,
  ActivitySortBy,
  ActivitySortOrder,
} from '@/features/activities/services/activities'

import ActivityListItem from '@/features/activities/components/ActivityListItem.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ListPanel } from '@/components/ui/list-panel'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
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
  useUserActivityTypesQuery,
} from '@/features/activities/composables/useActivities'
import {
  ACTIVITY_METRIC_COLUMNS,
  sortByToExtraColumn,
} from '@/features/activities/utils/activityListColumns'
import { ACTIVITY_SORT_OPTIONS } from '@/features/activities/utils/activitySortOptions'
import { presentActivityType } from '@/features/activities/utils/activityType'

const { t } = useI18n()
const { data: currentUser } = useCurrentUser()
const route = useRoute()

const units = computed(() => currentUser.value?.units ?? 'metric')
const userId = computed(() => currentUser.value?.id ?? null)

/** Parses the `sortBy` query param, falling back to `'start_time'` for unknown/missing values. */
function parseSortByParam(value: unknown): ActivitySortBy {
  const match = ACTIVITY_SORT_OPTIONS.find((option) => option.value === getScalarQueryString(value))
  return match ? match.value : 'start_time'
}

/** Parses the `sortOrder` query param, falling back to `'desc'` for unknown/missing values. */
function parseSortOrderParam(value: unknown): ActivitySortOrder {
  const raw = getScalarQueryString(value)
  return raw === 'asc' || raw === 'desc' ? raw : 'desc'
}

/** Parses the `page` query param, falling back to `1` for unknown/missing/invalid values. */
function parsePageParam(value: unknown): number {
  const raw = getScalarQueryString(value)
  const parsed = raw ? Number(raw) : NaN
  return Number.isInteger(parsed) && parsed >= 1 ? parsed : 1
}

const page = ref(parsePageParam(route.query.page))

// Filter state. `typeFilter` uses 0 as the "all types" sentinel (codes start at
// 1); the dates are ISO `YYYY-MM-DD` strings straight from the native pickers.
// Initial values are read from the URL query so that navigating to an activity
// and back doesn't reset the list back to its defaults.
const typeFilter = ref(parseActivityTypeFilterQuery(route.query.type))
const startDate = ref(parseIsoDateQuery(route.query.startDate))
const endDate = ref(parseIsoDateQuery(route.query.endDate))
const searchTerm = ref(getScalarQueryString(route.query.q))
const debouncedSearch = ref(searchTerm.value)

// Sort state, defaulting to newest first (mirrors v1).
const sortBy = ref<ActivitySortBy>(parseSortByParam(route.query.sortBy))
const sortOrder = ref<ActivitySortOrder>(parseSortOrderParam(route.query.sortOrder))

// Calories/avg HR aren't part of the default headline columns, so sorting by
// either added no visible column (issue #778); append the matching one so its
// values are visible while that sort is active.
const visibleColumns = computed(() => {
  const extraColumn = sortByToExtraColumn(sortBy.value)
  return extraColumn ? [...ACTIVITY_METRIC_COLUMNS, extraColumn] : ACTIVITY_METRIC_COLUMNS
})

// Page size follows the server's enforced `num_records_per_page` setting.
const { recordsPerPage } = useRecordsPerPage()

// Debounce the name/location search so typing doesn't fire a request per
// keystroke (mirrors GearsView and v1's 500ms debounce, tuned to 400ms).
let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(searchTerm, (value) => {
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
  searchTimer = setTimeout(() => {
    debouncedSearch.value = value
  }, 400)
})
onBeforeUnmount(() => {
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
})

/** Clears the search field and immediately drops the active term. */
function clearSearch(): void {
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
  searchTerm.value = ''
  debouncedSearch.value = ''
}

/** The active server-side filters, recomputed whenever any input changes. */
const filters = computed<ActivityListFilters>(() => ({
  type: typeFilter.value > 0 ? typeFilter.value : null,
  startDate: startDate.value || null,
  endDate: endDate.value || null,
  nameSearch: debouncedSearch.value.trim() || null,
}))

const hasActiveFilters = computed(
  () =>
    typeFilter.value > 0 ||
    startDate.value !== '' ||
    endDate.value !== '' ||
    debouncedSearch.value.trim() !== '',
)

/** Resets every filter and the search back to their defaults. */
function clearFilters(): void {
  typeFilter.value = 0
  startDate.value = ''
  endDate.value = ''
  clearSearch()
}

const typesQuery = useUserActivityTypesQuery()
/** Distinct activity-type codes the user owns, for the type filter. */
const typeOptions = computed(() => typesQuery.data.value ?? [])

const listQuery = useUserActivitiesQuery(userId, page, recordsPerPage, filters, sortBy, sortOrder)

/** Activities on the current page. */
const activities = computed(() => listQuery.data.value?.records ?? [])
/** Server-reported total across all pages for the active filters. */
const totalCount = computed(() => listQuery.data.value?.total ?? 0)

// Numbered pagination: derives the page count and clamps the page when the
// total shrinks (e.g. after a filter narrows the result set).
const { totalPages, reset: resetPage } = useListPagination(page, totalCount, recordsPerPage)

const isPending = computed(() => listQuery.isPending.value)
const isError = computed(() => listQuery.isError.value)
const isEmpty = computed(() => !isPending.value && !isError.value && activities.value.length === 0)

// Any change to the filters or sort changes the result set, so restart at page 1.
watch([filters, sortBy, sortOrder], resetPage)

/** Flips the sort direction between ascending and descending. */
function toggleSortOrder(): void {
  sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
}

function refetch(): void {
  void listQuery.refetch()
}

// Mirror the active filter/sort/page state into the URL query so it survives
// navigating to an activity and back (and page refreshes); browser
// back/forward then also works as expected.
const activitiesQueryState = computed<Record<string, string>>(() => {
  const params: Record<string, string> = {
    sortBy: sortBy.value,
    sortOrder: sortOrder.value,
  }
  if (typeFilter.value > 0) {
    params.type = String(typeFilter.value)
  }
  if (startDate.value) {
    params.startDate = startDate.value
  }
  if (endDate.value) {
    params.endDate = endDate.value
  }
  if (debouncedSearch.value.trim()) {
    params.q = debouncedSearch.value.trim()
  }
  if (page.value > 1) {
    params.page = String(page.value)
  }
  return params
})

useRouteQueryReplacement(activitiesQueryState)
</script>

<template>
  <section class="flex flex-col gap-3">
    <header class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('activities.list.title') }}</h1>
      <p class="text-body">{{ t('activities.list.subtitle') }}</p>
    </header>

    <!--
      Two-column shell on lg+: a filter rail beside the list. Below lg the rail
      collapses to the top of the normal flow, so the same controls appear at
      every breakpoint.
    -->
    <div class="grid gap-3 lg:grid-cols-[18rem_minmax(0,1fr)] lg:items-start">
      <!-- Controls rail: name search + type + date range filters. -->
      <aside class="lg:sticky lg:top-6">
        <Card class="flex flex-col gap-3">
          <div class="relative">
            <Search
              class="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              v-model="searchTerm"
              type="search"
              :placeholder="t('activities.list.searchPlaceholder')"
              :aria-label="t('activities.list.searchPlaceholder')"
              class="w-full pl-9 pr-9"
            />
            <button
              v-if="searchTerm"
              type="button"
              class="absolute right-1 top-1/2 inline-flex size-7 -translate-y-1/2 items-center justify-center rounded-input text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
              :aria-label="t('activities.list.clearSearch')"
              @click="clearSearch"
            >
              <X class="size-4" aria-hidden="true" />
            </button>
          </div>

          <div class="flex flex-col gap-1.5">
            <Label for="activity-type-filter">{{ t('activities.list.filters.type') }}</Label>
            <Select
              id="activity-type-filter"
              v-model="typeFilter"
              class="w-full"
              :aria-label="t('activities.list.filters.type')"
            >
              <option :value="0">{{ t('activities.list.filters.allTypes') }}</option>
              <option v-for="code in typeOptions" :key="code" :value="code">
                {{ t(presentActivityType(code).labelKey) }}
              </option>
            </Select>
          </div>

          <div class="grid grid-cols-2 gap-2">
            <div class="flex flex-col gap-1.5">
              <Label for="activity-from-date">{{ t('activities.list.filters.fromDate') }}</Label>
              <Input id="activity-from-date" v-model="startDate" type="date" class="w-full" />
            </div>
            <div class="flex flex-col gap-1.5">
              <Label for="activity-to-date">{{ t('activities.list.filters.toDate') }}</Label>
              <Input id="activity-to-date" v-model="endDate" type="date" class="w-full" />
            </div>
          </div>

          <Button v-if="hasActiveFilters" variant="outline" size="sm" @click="clearFilters">
            <X class="size-4" aria-hidden="true" />
            {{ t('activities.list.filters.clear') }}
          </Button>
        </Card>
      </aside>

      <!-- Main panel: result count + sort header, then the list and pager. -->
      <ListPanel
        v-model:page="page"
        :is-loading="isPending"
        :is-error="isError"
        :is-empty="isEmpty"
        :error-title="t('activities.list.error.title')"
        :error-description="t('activities.list.error.description')"
        :retry-label="t('activities.list.error.retry')"
        paginated
        :total-pages="totalPages"
        @retry="refetch"
      >
        <template #header>
          <div class="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <p class="text-hint">{{ t('activities.list.resultCount', { count: totalCount }) }}</p>
            <div class="flex items-center gap-2">
              <Label for="activity-sort" class="sr-only">{{
                t('activities.list.sort.label')
              }}</Label>
              <Select
                id="activity-sort"
                v-model="sortBy"
                class="w-auto"
                :aria-label="t('activities.list.sort.label')"
              >
                <option
                  v-for="option in ACTIVITY_SORT_OPTIONS"
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
          <EmptyState
            :title="
              hasActiveFilters
                ? t('activities.list.empty.filteredTitle')
                : t('activities.list.empty.title')
            "
            :description="hasActiveFilters ? undefined : t('activities.list.empty.description')"
            :variant="hasActiveFilters ? 'filtered' : 'first-time'"
          >
            <template #icon>
              <ActivityIcon class="size-8" aria-hidden="true" />
            </template>
          </EmptyState>
        </template>

        <div>
          <!-- Aligned column headers (desktop); cell classes match ActivityListItem. -->
          <div class="hidden border-b border-border px-4 py-2 sm:flex sm:items-center sm:gap-3">
            <span class="flex-1 ps-13 text-caption">{{
              t('activities.list.columns.activity')
            }}</span>
            <div class="flex shrink-0 items-baseline gap-6">
              <span
                v-for="col in visibleColumns"
                :key="col.key"
                :class="['text-caption', col.cellClass]"
              >
                {{ t(col.labelKey) }}
              </span>
            </div>
          </div>
          <ul class="divide-y divide-border">
            <li v-for="activity in activities" :key="activity.id">
              <ActivityListItem :activity="activity" :units="units" :columns="visibleColumns" />
            </li>
          </ul>
        </div>
      </ListPanel>
    </div>
  </section>
</template>
