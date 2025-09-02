<template>
  <h1>{{ $t('activitiesView.title') }}</h1>
  <!-- Filter Section -->
  <div class="p-3 mb-3 bg-body-tertiary border-0 rounded">
    <div class="row align-items-end">
      <!-- Activity Type -->
      <div class="col-md-3">
        <label for="activityTypeFilter" class="form-label">{{
          $t('activitiesView.filterLabelType')
        }}</label>
        <select
          id="activityTypeFilter"
          class="form-select"
          v-model="selectedType"
          @change="applyFilters"
        >
          <option value="">{{ $t('activitiesView.filterOptionAllTypes') }}</option>
          <option v-for="(value, key) in activityTypes" :key="key" :value="key">{{ value }}</option>
        </select>
      </div>
      <!-- Start Date -->
      <div class="col-md-3">
        <label for="startDateFilter" class="form-label">{{
          $t('activitiesView.filterLabelFromDate')
        }}</label>
        <input type="date" id="startDateFilter" class="form-control" v-model="startDate" />
      </div>
      <!-- End Date -->
      <div class="col-md-3">
        <label for="endDateFilter" class="form-label">{{
          $t('activitiesView.filterLabelToDate')
        }}</label>
        <input type="date" id="endDateFilter" class="form-control" v-model="endDate" />
      </div>
      <!-- Name Search -->
      <div class="col-md-3">
        <label for="nameSearchFilter" class="form-label">{{
          $t('activitiesView.filterLabelNameLocation')
        }}</label>
        <input
          type="text"
          id="nameSearchFilter"
          class="form-control"
          v-model="nameSearch"
          :placeholder="$t('activitiesView.filterPlaceholderNameLocation')"
        />
      </div>
      <!-- Buttons -->
      <div class="col-12 mt-3 d-flex justify-content-end gap-3">
        <button type="button" class="btn btn-secondary" @click="clearFilters">
          {{ $t('activitiesView.buttonClear') }}
        </button>
        <button type="submit" class="btn btn-primary" disabled v-if="isLoading">
          <span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>
          <span role="status">{{ $t('activitiesView.buttonApply') }}</span>
        </button>
        <button type="submit" class="btn btn-primary" v-else>
          {{ $t('activitiesView.buttonApply') }}
        </button>
      </div>
    </div>
  </div>
  <!-- End Filter Section -->

  <LoadingComponent v-if="isLoading" />
  <div class="p-3 bg-body-tertiary rounded shadow-sm" v-else-if="activities && activities.length">
    <!-- Activities Table -->
    <ActivitiesTableComponent
      :activities="activities"
      :sort-by="sortBy"
      :sort-order="sortOrder"
      @sortChanged="handleSort"
      v-if="activities && activities.length"
    />

    <PaginationComponent
      :totalPages="totalPages"
      :pageNumber="pageNumber"
      @pageNumberChanged="setPageNumber"
      v-if="activities && activities.length"
    />
  </div>

  <NoItemsFoundComponents v-else />
</template>

<script setup>
// Switch to <script setup> composition API
import { ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { debounce } from 'lodash'
import { push } from 'notivue'
import { useAuthStore } from '@/stores/authStore'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { activities as activitiesService } from '@/services/activitiesService'
import ActivitiesTableComponent from '@/components/Activities/ActivitiesTableComponent.vue'
import PaginationComponent from '@/components/GeneralComponents/PaginationComponent.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import NoItemsFoundComponents from '@/components/GeneralComponents/NoItemsFoundComponents.vue'

const { t } = useI18n()
const serverSettingsStore = useServerSettingsStore()
const authStore = useAuthStore()
const activityTypes = ref([])
const activities = ref([])
const userNumberActivities = ref(0)
const pageNumber = ref(1)
const numRecords = serverSettingsStore.serverSettings.num_records_per_page || 25
const totalPages = ref(1)
const isLoading = ref(true)

// Filter state
const selectedType = ref('')
const startDate = ref('')
const endDate = ref('')
const nameSearch = ref('')

// Sorting state
const sortBy = ref('start_time') // Default sort column
const sortOrder = ref('desc') // Default sort order

const performNameSearch = debounce(async () => {
  if (!nameSearch.value) {
    pageNumber.value = 1
    await applyFilters()
    return
  }
  try {
    await applyFilters()
  } catch (error) {
    push.error(`${t('activitiesView.errorUpdatingActivities')} - ${error}`)
  }
}, 500)

async function fetchActivityTypes() {
  try {
    activityTypes.value = await activitiesService.getActivityTypes()
  } catch (error) {
    push.error(`${t('activitiesView.errorFailedFetchActivityTypes')} - ${error}`)
  }
}

function setPageNumber(page) {
  pageNumber.value = page
}

async function updateActivities() {
  try {
    isLoading.value = true
    await fetchActivities()
  } catch (error) {
    push.error(`${t('activitiesView.errorUpdatingActivities')} - ${error}`)
  } finally {
    isLoading.value = false
  }
}

async function fetchActivities() {
  activities.value = []
  const filters = {
    type: selectedType.value,
    start_date: startDate.value,
    end_date: endDate.value,
    name_search: nameSearch.value
  }
  try {
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
    push.error(`${t('activitiesView.errorFetchingActivities')} - ${error}`)
  }
}

onMounted(async () => {
  await fetchActivityTypes()
  await updateActivities()
})

async function applyFilters() {
  pageNumber.value = 1
  await updateActivities()
}

async function clearFilters() {
  selectedType.value = ''
  startDate.value = ''
  endDate.value = ''
  nameSearch.value = ''
  sortBy.value = 'start_time'
  sortOrder.value = 'desc'
  await applyFilters()
}

async function handleSort(columnName) {
  if (sortBy.value === columnName) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = columnName
    sortOrder.value = 'desc'
  }
  await updateActivities()
}

watch(nameSearch, performNameSearch, { immediate: false })
watch(pageNumber, updateActivities, { immediate: false })
</script>
