<template>
  <div class="container mt-4">
    <h2>{{ $t('activitiesView.title') }}</h2>
    <div v-if="loading" class="text-center">
      <div class="spinner-border" role="status">
        <span class="visually-hidden">{{ $t('activitiesView.loading') }}</span>
      </div>
    </div>
    <div v-else-if="error" class="alert alert-danger">
      {{ error }}
    </div>
    <div v-else>
      <!-- Filter Section -->
      <div class="card mb-4">
        <div class="card-body">
          <form @submit.prevent="applyFilters" class="row g-3 align-items-end">
            <!-- Activity Type -->
            <div class="col-md-3">
              <label for="activityTypeFilter" class="form-label">{{ $t('activitiesView.filterLabelType') }}</label>
              <select
                id="activityTypeFilter"
                class="form-select"
                v-model="selectedType"
                @change="applyFilters"
              >
                <option value="">{{ $t('activitiesView.filterOptionAllTypes') }}</option>
                <option v-for="type in activityTypes" :key="type" :value="type">{{ type }}</option>
              </select>
            </div>
            <!-- Start Date -->
            <div class="col-md-3">
              <label for="startDateFilter" class="form-label">{{ $t('activitiesView.filterLabelFromDate') }}</label>
              <input type="date" id="startDateFilter" class="form-control" v-model="startDate" />
            </div>
            <!-- End Date -->
            <div class="col-md-3">
              <label for="endDateFilter" class="form-label">{{ $t('activitiesView.filterLabelToDate') }}</label>
              <input type="date" id="endDateFilter" class="form-control" v-model="endDate" />
            </div>
            <!-- Name Search -->
            <div class="col-md-3">
              <label for="nameSearchFilter" class="form-label">{{ $t('activitiesView.filterLabelNameLocation') }}</label>
              <input
                type="text"
                id="nameSearchFilter"
                class="form-control"
                v-model="nameSearch"
                :placeholder="$t('activitiesView.filterPlaceholderNameLocation')"
              />
            </div>
            <!-- Buttons -->
            <div class="col-12 mt-3 d-flex justify-content-end gap-2">
              <button type="button" class="btn btn-secondary" @click="clearFilters">{{ $t('activitiesView.buttonClear') }}</button>
              <button type="submit" class="btn btn-primary">{{ $t('activitiesView.buttonApply') }}</button>
            </div>
          </form>
        </div>
      </div>
      <!-- End Filter Section -->

      <ActivitiesTable
        :activities="activities"
        :sort-by="sortBy"
        :sort-order="sortOrder"
        @sort-changed="handleSort"
      />

      <!-- Note removed as total count is now available -->
      <PaginationComponent
        v-if="activities.length > 0 || currentPage > 1"
        :current-page="currentPage"
        :total-pages="calculatedTotalPages"
        @page-changed="handlePageChange"
      />
      <!-- Note removed as total count is now available -->
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue' // Added watch
import { useI18n } from 'vue-i18n' // Import useI18n
import { useAuthStore } from '@/stores/authStore'
import ActivitiesTable from '@/components/Activities/ActivitiesTable.vue'
import PaginationComponent from '@/components/Common/PaginationComponent.vue'
import { activities as activitiesService } from '@/services/activitiesService' // Import the service

const { t } = useI18n() // Setup useI18n

const authStore = useAuthStore()
const activities = ref([])
const currentPage = ref(1)
const totalActivities = ref(0) // We might need another endpoint or header for total count
const activitiesPerPage = ref(20) // Default page size
const loading = ref(true)
const error = ref(null)

// Filter state
const activityTypes = ref([])
const selectedType = ref('')
const startDate = ref('')
const endDate = ref('')
const nameSearch = ref('')

// Sorting state
const sortBy = ref('start_time') // Default sort column
const sortOrder = ref('desc') // Default sort order

// Fetch available activity types for the filter dropdown
async function fetchActivityTypes() {
  try {
    activityTypes.value = await activitiesService.getActivityTypes() // Assuming a new service function
  } catch (err) {
    console.error('Failed to fetch activity types:', err)
    // Handle error appropriately, maybe show a message
  }
}

// Fetch activities with pagination, filters, and sorting
async function fetchActivities(
  page = 1,
  currentFilters = {},
  currentSortBy = sortBy.value,
  currentSortOrder = sortOrder.value
) {
  loading.value = true
  error.value = null
  activities.value = [] // Clear previous activities

  const userId = authStore.user?.id
  if (!userId) {
    error.value = t('activitiesView.errorUserNotAuthenticated')
    loading.value = false
    return
  }

  // Adjust page number if needed (API might be 0-indexed or 1-indexed)
  const apiPageNumber = page // Assuming API is 1-indexed based on path param name
  const numRecords = activitiesPerPage.value

  try {
    // Prepare filters, removing empty values
    const activeFilters = {}
    if (currentFilters.type) activeFilters.type = currentFilters.type
    if (currentFilters.start_date) activeFilters.start_date = currentFilters.start_date
    if (currentFilters.end_date) activeFilters.end_date = currentFilters.end_date
    if (currentFilters.name_search) activeFilters.name_search = currentFilters.name_search

    // Use the activities service with filters and sorting
    const response = await activitiesService.getUserActivitiesWithPagination(
      userId,
      apiPageNumber,
      numRecords,
      activeFilters,
      currentSortBy, // Pass sort column
      currentSortOrder // Pass sort order
    )
    activities.value = response.activities || [] // Extract activities array
    totalActivities.value = response.total_count || 0 // Extract total count

    currentPage.value = page
  } catch (err) {
    console.error('Failed to fetch activities:', err)
    error.value = t('activitiesView.errorFailedLoad')
  } finally {
    loading.value = false
  }
}

// Function to handle page changes from pagination component
function handlePageChange(newPage) {
  // Pass current filters and sorting when changing page
  fetchActivities(
    newPage,
    {
      type: selectedType.value,
      start_date: startDate.value,
      end_date: endDate.value,
      name_search: nameSearch.value
    },
    sortBy.value,
    sortOrder.value
  )
}

// Calculate total pages based on the total count from the API
const calculatedTotalPages = computed(() => {
  if (totalActivities.value > 0) {
    return Math.ceil(totalActivities.value / activitiesPerPage.value)
  }
  // Default to 1 if totalActivities is 0 or not yet loaded
  return 1
})

onMounted(() => {
  fetchActivityTypes() // Fetch types on mount
  // Initial fetch with default page, filters (empty), and sorting
  fetchActivities(currentPage.value, {}, sortBy.value, sortOrder.value)
})

// Function to apply filters and fetch data
function applyFilters() {
  // Reset to page 1 when filters change, keep current sort order
  fetchActivities(
    1,
    {
      type: selectedType.value,
      start_date: startDate.value,
      end_date: endDate.value,
      name_search: nameSearch.value
    },
    sortBy.value,
    sortOrder.value
  )
}

// Function to clear filters
function clearFilters() {
  selectedType.value = ''
  startDate.value = ''
  endDate.value = ''
  nameSearch.value = ''
  // applyFilters will re-fetch with cleared filters and current sort order
  applyFilters()
}

// Function to handle sorting changes from table component
function handleSort(columnName) {
  if (sortBy.value === columnName) {
    // Toggle sort order if same column is clicked
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    // Set new column and default to descending order
    sortBy.value = columnName
    sortOrder.value = 'desc' // Or 'asc' if preferred as default
  }
  // Fetch data with new sorting, reset to page 1
  fetchActivities(
    1,
    {
      type: selectedType.value,
      start_date: startDate.value,
      end_date: endDate.value,
      name_search: nameSearch.value
    },
    sortBy.value,
    sortOrder.value
  )
}
</script>
