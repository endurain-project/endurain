<template>
  <h1>{{ t('summaryView.title') }}</h1>
  <!-- Controls Section -->
  <div class="p-3 mb-3 bg-body-tertiary border-0 rounded">
    <div class="row align-items-end">
      <!-- Activity Type Filter -->
      <div class="col-md-3">
        <label for="activityTypeFilter" class="form-label">{{
          t('summaryView.filterLabelActivityType')
        }}</label>
        <select
          id="activityTypeFilter"
          class="form-select"
          v-model="selectedActivityType"
          :disabled="isAnyLoading"
        >
          <option value="">{{ t('summaryView.filterOptionAllTypes') }}</option>
          <option v-for="(name, id) in activityTypes" :key="id" :value="id">{{ name }}</option>
        </select>
      </div>
      <!-- View Type Filter -->
      <div class="col-md-3">
        <label for="viewType" class="form-label">{{ t('summaryView.labelViewType') }}</label>
        <select id="viewType" class="form-select" v-model="selectedViewType">
          <option value="week">{{ t('summaryView.optionWeekly') }}</option>
          <option value="month">{{ t('summaryView.optionMonthly') }}</option>
          <option value="year">{{ t('summaryView.optionYearly') }}</option>
          <option value="lifetime">{{ t('summaryView.optionLifetime') }}</option>
        </select>
      </div>
      <!-- Week/month/year select -->
      <div class="col-md-3" v-if="selectedViewType !== 'lifetime'">
        <label :for="periodInputId" class="form-label">{{ periodLabel }}</label>
        <input
          type="date"
          :id="periodInputId"
          class="form-control"
          v-if="selectedViewType === 'week'"
          v-model="selectedDate"
        />
        <input
          type="month"
          :id="periodInputId"
          class="form-control"
          v-else-if="selectedViewType === 'month'"
          v-model="selectedMonth"
        />
        <input
          type="number"
          :id="periodInputId"
          class="form-control"
          v-else-if="selectedViewType === 'year'"
          v-model="selectedYear"
          placeholder="YYYY"
          min="1900"
          :max="todayYear"
          @input="validateYear"
        />
      </div>
      <!-- Buttons -->
      <div
        class="col-12 mt-3 d-flex justify-content-end gap-3"
        v-if="selectedViewType !== 'lifetime'"
      >
        <button
          class="btn btn-primary me-1"
          :disabled="
            isAnyLoading ||
            (selectedViewType === 'year' && selectedYear === 1900) ||
            (selectedViewType === 'month' && selectedMonth === '1900-01') ||
            (selectedViewType === 'week' && selectedDate === '1900-01-01')
          "
          @click="navigatePeriod(-1)"
        >
          <span
            v-if="isAnyLoading"
            class="spinner-border spinner-border-sm me-1"
            aria-hidden="true"
          ></span>
          <span role="status">{{ t('summaryView.buttonPreviousPeriod') }}</span>
        </button>
        <button
          class="btn btn-primary"
          :disabled="
            isAnyLoading ||
            (selectedViewType === 'year' && selectedYear === todayYear) ||
            (selectedViewType === 'month' && selectedMonth === todayMonth) ||
            (selectedViewType === 'week' && selectedDate === todayWeek)
          "
          @click="navigatePeriod(1)"
        >
          <span
            v-if="isAnyLoading"
            class="spinner-border spinner-border-sm me-1"
            aria-hidden="true"
          ></span>
          <span role="status">{{ t('summaryView.buttonNextPeriod') }}</span>
        </button>
      </div>
    </div>
  </div>

  <!-- Summary Display Section -->
  <div class="bg-body-tertiary border-0 rounded p-3">
    <h5>{{ t('summaryView.headerSummaryFor', { period: summaryPeriodText }) }}</h5>
    <hr />
    <LoadingComponent v-if="isLoading" />
    <!-- New Highlighted Summary Totals Section -->
    <div class="row row-gap-3 gap-0 justify-content-around" v-else-if="summaryData">
      <div class="col-lg col-md-4 col-sm-6">
        <ActivitiesSummaryTotalsSectionComponent
          :title="t('summaryView.metricTotalDistance')"
          :subTitle="formatRawDistance(t, summaryData.total_distance, authStore.user.units)"
        />
      </div>
      <div class="col-lg col-md-4 col-sm-6">
        <ActivitiesSummaryTotalsSectionComponent
          :title="t('summaryView.metricTotalDuration')"
          :subTitle="formatDuration(t, summaryData.total_duration)"
        />
      </div>
      <div class="col-lg col-md-4 col-sm-6">
        <ActivitiesSummaryTotalsSectionComponent
          :title="t('summaryView.metricTotalElevation')"
          :subTitle="formatElevation(t, summaryData.total_elevation_gain, authStore.user.units)"
        />
      </div>
      <div class="col-lg col-md-6 col-sm-6">
        <ActivitiesSummaryTotalsSectionComponent
          :title="t('summaryView.metricTotalCalories')"
          :subTitle="formatCalories(t, summaryData.total_calories)"
        />
      </div>
      <div class="col-lg col-md-6 col-sm-6">
        <ActivitiesSummaryTotalsSectionComponent
          :title="t('summaryView.metricTotalActivities')"
          :subTitle="String(summaryData.activity_count)"
        />
      </div>
    </div>
    <NoItemsFoundComponents :showShadow="false" v-else />

    <h5 class="mt-3">{{ t('summaryView.headerBreakdown') }}</h5>
    <hr />
    <LoadingComponent v-if="isLoading" />
    <ActivitiesSummaryBreakdownTableComponent
      :selectedViewType="selectedViewType"
      :summaryData="summaryData"
      :authStore="authStore"
      :selectedYear="selectedYear"
      v-else-if="summaryData['activity_count'] > 0"
    />
    <NoItemsFoundComponents :showShadow="false" v-else />

    <h5>{{ t('summaryView.headerTypeBreakdown') }}</h5>
    <hr />
    <LoadingComponent v-if="isLoading" />
    <ActivitiesTypeBreakdownTableComponent
      :typeBreakdownData="typeBreakdownData"
      :authStore="authStore"
      v-else-if="typeBreakdownData && !selectedActivityType"
    />
    <NoItemsFoundComponents :showShadow="false" v-else />
  </div>

  <!-- Activities in Period Section -->
  <div class="mt-3" v-if="selectedViewType !== 'lifetime'">
    <LoadingComponent v-if="isLoadingActivities" />
    <div v-else class="p-3 bg-body-tertiary rounded shadow-sm">
      <h5>{{ t('summaryView.headerActivitiesInPeriod') }}</h5>
      <hr />
      <div v-if="activities && activities.length">
        <LoadingComponent v-if="isLoading" />
        <ActivitiesTableComponent
          :activities="activities"
          :sortBy="sortBy"
          :sortOrder="sortOrder"
          @sortChanged="handleSort"
          v-else
        />
        <PaginationComponent
          v-if="userNumberActivities > 0"
          :pageNumber="pageNumber"
          :totalPages="totalPages"
          @pageNumberChanged="setPageNumber"
        />
      </div>
      <NoItemsFoundComponents :showShadow="false" v-else />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
// import lodash
import { debounce } from 'lodash'
import { useAuthStore } from '@/stores/authStore'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { summaryService } from '@/services/summaryService'
import { activities as activitiesService } from '@/services/activitiesService'
// Import Notivue push
import { push } from 'notivue'

// Lazy load heavy components that are conditionally rendered
const ActivitiesTableComponent = defineAsyncComponent(
  () => import('@/components/Activities/ActivitiesTableComponent.vue')
)
const ActivitiesSummaryBreakdownTableComponent = defineAsyncComponent(
  () => import('@/components/Activities/ActivitiesSummaryBreakdownTableComponent.vue')
)
const ActivitiesTypeBreakdownTableComponent = defineAsyncComponent(
  () => import('@/components/Activities/ActivitiesTypeBreakdownTableComponent.vue')
)

// Eagerly load lightweight components
import ActivitiesSummaryTotalsSectionComponent from '@/components/Activities/ActivitiesSummaryTotalsSectionComponent.vue'
import PaginationComponent from '@/components/GeneralComponents/PaginationComponent.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import NoItemsFoundComponents from '@/components/GeneralComponents/NoItemsFoundComponents.vue'

// Import utility functions for formatting and date handling
import {
  formatRawDistance,
  formatDuration,
  formatElevation,
  formatCalories
} from '@/utils/activityUtils'
import { getWeekStartDate, formatDateISO, formatDateToMonthString } from '@/utils/dateTimeUtils'
import { buildSummaryParams, buildActivityFilters } from '@/utils/summaryUtils'

const { t } = useI18n()
const authStore = useAuthStore()
const serverSettingsStore = useServerSettingsStore()

// Filter and View State
const selectedViewType = ref('week')
const selectedActivityType = ref('')
const activityTypes = ref([])
const initialDate = new Date()
const selectedDate = ref(
  formatDateISO(getWeekStartDate(initialDate, authStore.user.first_day_of_week))
)
const todayWeek = computed(() =>
  formatDateISO(getWeekStartDate(new Date(), authStore.user.first_day_of_week))
)
const todayMonth = formatDateToMonthString(initialDate)
const todayYear = initialDate.getFullYear()
const selectedYear = ref(todayYear)
const selectedMonth = ref(todayMonth)

// Data State
const summaryData = ref(null)
const typeBreakdownData = ref(null)
const activities = ref([])
const timezone = ref('')
const userNumberActivities = ref(0)
const pageNumber = ref(1)
const totalPages = ref(1)
const numRecords = serverSettingsStore.serverSettings.num_records_per_page || 25

// Loading State
const isLoading = ref(true)
const isLoadingActivities = ref(true)

// Sorting State
const sortBy = ref('start_time')
const sortOrder = ref('desc')

// Period configuration maps
const periodInputIdMap = {
  week: 'periodPickerWeek',
  month: 'periodPickerMonth',
  year: 'periodPickerYear'
}

const periodLabelKeyMap = {
  week: 'summaryView.labelSelectWeek',
  month: 'summaryView.labelSelectMonth',
  year: 'summaryView.labelSelectYear',
  lifetime: ''
}

// Computed property for dynamic input ID
const periodInputId = computed(() => {
  return periodInputIdMap[selectedViewType.value] || 'periodPicker'
})

const periodLabel = computed(() => {
  const labelKey = periodLabelKeyMap[selectedViewType.value]
  return labelKey ? t(labelKey) : t('summaryView.labelSelectPeriod')
})

// Computed properties for loading state management
const isAnyLoading = computed(() => {
  return isLoading.value || isLoadingActivities.value
})

// Centralized data clearing function
const clearData = (options = {}) => {
  const {
    clearSummary = true,
    clearTypeBreakdown = true,
    clearActivities = true,
    clearTotals = true,
    resetPage = true
  } = options

  if (clearSummary) {
    summaryData.value = null
  }
  if (clearTypeBreakdown) {
    typeBreakdownData.value = null
  }
  if (clearActivities) {
    activities.value = []
  }
  if (clearTotals) {
    userNumberActivities.value = 0
  }
  if (resetPage) {
    pageNumber.value = 1
  }
}

// Fetch available activity types for the filter dropdown
async function fetchActivityTypes() {
  try {
    activityTypes.value = await activitiesService.getActivityTypes()
  } catch (error) {
    push.error(`${t('summaryView.errorLoadingActivityTypes')} - ${error}`)
  }
}

function setPageNumber(page) {
  // Set the page number.
  pageNumber.value = page
}

function updateViewType() {
  if (selectedViewType.value !== 'lifetime') {
    if (selectedViewType.value === 'month') {
      selectedMonth.value = formatDateToMonthString(new Date(selectedDate.value))
    } else if (selectedViewType.value === 'year') {
      selectedYear.value = new Date(selectedDate.value).getUTCFullYear()
    }
  } else {
    // Switching to lifetime - clear activities immediately
    clearData({
      clearSummary: false,
      clearTypeBreakdown: false,
      clearActivities: true,
      clearTotals: true,
      resetPage: true
    })
  }
  try {
    triggerDataFetch()
  } catch (error) {
    push.error(`${t('summaryView.errorLoadingSummary')} - ${error}`)
  }
}

async function updateActivities() {
  // If the selected view type is "lifetime", do not fetch activities.
  if (selectedViewType.value === 'lifetime') {
    isLoadingActivities.value = false
    return
  }

  try {
    // Set the loading variable to true.
    isLoadingActivities.value = true

    // Fetch the activities with pagination.
    await fetchActivities()
  } catch (error) {
    // If there is an error, set the error message and show the error alert.
    push.error(`${t('summaryView.errorFetchingActivities')} - ${error}`)
  } finally {
    // Set the loading variable to false.
    isLoadingActivities.value = false
  }
}

// Fetch activities with pagination, filters, and sorting
async function fetchActivities() {
  //Get timezone
  timezone.value = await activitiesService.getTimezone()

  clearData({
    clearSummary: false,
    clearTypeBreakdown: false,
    clearActivities: true,
    clearTotals: false,
    resetPage: false
  })
  const filters = buildActivityFilters(
    selectedViewType.value,
    selectedDate.value,
    selectedYear.value,
    selectedActivityType.value,
    timezone.value
  )

  try {
    // Use the activities service with filters and sorting
    activities.value = await activitiesService.getUserActivitiesWithPagination(
      authStore.user.id,
      pageNumber.value,
      numRecords,
      filters,
      sortBy.value,
      sortOrder.value
    )
    userNumberActivities.value = await activitiesService.getUserNumberOfActivities(filters)

    totalPages.value = Math.ceil(userNumberActivities.value / numRecords)
  } catch (error) {
    push.error(`${t('summaryView.errorFetchingActivities')} - ${error}`)
  }
}

async function fetchSummaryData() {
  isLoading.value = true

  clearData({
    clearSummary: true,
    clearTypeBreakdown: true,
    clearActivities: true,
    clearTotals: true,
    resetPage: true
  })

  try {
    const params = buildSummaryParams(
      selectedViewType.value,
      selectedDate.value,
      selectedYear.value
    )

    const activityTypeName = selectedActivityType.value
      ? activityTypes.value[selectedActivityType.value]
      : null

    const response = await summaryService.getSummary(
      authStore.user.id,
      selectedViewType.value,
      params,
      activityTypeName
    )
    summaryData.value = response
    typeBreakdownData.value = response.type_breakdown
  } catch (error) {
    push.error(`${t('summaryView.errorLoadingSummary')} - ${error}`)
  } finally {
    isLoading.value = false
  }
}

const performYearTriggerDataFetch = debounce(async () => {
  if (selectedYear.value >= 1900 && selectedYear.value <= todayYear) {
    try {
      await triggerDataFetch()
    } catch (error) {
      push.error(`${t('summaryView.errorLoadingSummary')} - ${error}`)
    }
  } else {
    push.error(`${t('summaryView.invalidYearSelected')}: ${selectedYear.value} - 1900-${todayYear}`)
  }
}, 500)

async function performMonthTriggerDataFetch() {
  if (selectedViewType.value === 'month') {
    triggerDataFetch()
  }
}

async function triggerDataFetch() {
  try {
    // Reset to page 1 when date input changes
    pageNumber.value = 1
    await fetchSummaryData()
    await updateActivities()
  } catch (error) {
    clearData({
      clearSummary: true,
      clearTypeBreakdown: true,
      clearActivities: true,
      clearTotals: true,
      resetPage: true
    })
  }
}

onMounted(async () => {
  try {
    await fetchActivityTypes()
    await triggerDataFetch()
  } catch (error) {
    push.error(`${t('summaryView.errorLoadingSummaryLoad')} - ${error}`)
  }
})

const summaryPeriodText = computed(() => {
  // Early return for lifetime view
  if (selectedViewType.value === 'lifetime') {
    return t('summaryView.optionLifetime')
  }

  // Early return for loading state
  if (isLoading.value) {
    return t('generalItems.labelNotApplicable')
  }

  // Early return when no data and not loading
  if (!summaryData.value) {
    return t('summaryView.labelSelectPeriod')
  }

  // Handle year view type
  if (selectedViewType.value === 'year') {
    return t('summaryView.headerYear', { year: selectedYear.value })
  }

  let date = new Date(selectedDate.value)
  // Handle month view type
  if (selectedViewType.value === 'month') {
    return date.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'long',
      timeZone: 'UTC'
    })
  }

  // Handle week view type
  if (selectedViewType.value === 'week') {
    const weekStart = getWeekStartDate(date)
    return t('summaryView.headerWeekStarting', {
      date: formatDateISO(weekStart)
    })
  }

  // Fallback
  return t('summaryView.labelSelectPeriod')
})

function handleSort(columnName) {
  if (sortBy.value === columnName) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = columnName
    sortOrder.value = 'desc'
  }
  updateActivities()
}

function navigatePeriod(direction) {
  if (selectedViewType.value === 'lifetime' || isAnyLoading.value) return

  try {
    if (selectedViewType.value === 'year') {
      selectedYear.value = selectedYear.value + direction
    } else {
      let date = new Date(selectedDate.value)
      if (selectedViewType.value === 'week') {
        date.setUTCDate(date.getUTCDate() + 7 * direction)
      } else {
        // 'month'
        date.setUTCMonth(date.getUTCMonth() + direction, 1)
      }
      selectedDate.value = formatDateISO(date)
    }
    if (selectedViewType.value === 'month') {
      selectedMonth.value = formatDateToMonthString(new Date(selectedDate.value))
    }
  } catch (error) {
    push.error(`${t('summaryView.labelError')} - ${error}`)
  }
}

function validateYear() {
  if (selectedYear.value < 1900) {
    selectedYear.value = 1900
  } else if (selectedYear.value > todayYear) {
    selectedYear.value = todayYear
  }
}

// Watch the pageNumber variable.
watch(pageNumber, updateActivities, { immediate: false })
// Watch the selectedViewType variable.
watch(selectedViewType, updateViewType, { immediate: false })
// Watch the selectedActivityType variable.
watch(selectedActivityType, triggerDataFetch, { immediate: false })
// Watch the selectedDate variable.
watch(selectedDate, triggerDataFetch, { immediate: false })
// Watch the selectedYear variable.
watch(selectedYear, performYearTriggerDataFetch, { immediate: false })
// Watch the selectedMonth variable.
watch(selectedMonth, performMonthTriggerDataFetch, { immediate: false })
</script>
