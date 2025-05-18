<template>
  <div class="container mt-4">
    <h2>{{ t('summaryView.title') }}</h2>

    <!-- Controls Section -->
    <div class="row mb-3 align-items-end">
      <!-- Activity Type Filter -->
      <div class="col-md-3">
        <label for="activityTypeFilter" class="form-label">{{ t('summaryView.filterLabelActivityType') }}</label>
        <select id="activityTypeFilter" class="form-select" v-model="selectedActivityType" :disabled="loadingTypes">
          <option value="">{{ t('summaryView.filterOptionAllTypes') }}</option>
          <option v-for="(name, id) in activityTypes" :key="id" :value="id">{{ name }}</option>
        </select>
         <div v-if="loadingTypes" class="form-text">{{ t('generalItems.labelLoading') }}...</div>
         <div v-if="errorTypes" class="form-text text-danger">{{ errorTypes }}</div>
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
      <div class="col-md-3" v-if="selectedViewType !== 'lifetime'">
         <label :for="periodInputId" class="form-label">{{ periodLabel }}</label>
         <input type="date" :id="periodInputId" class="form-control" v-if="selectedViewType === 'week'" v-model="selectedDate" @change="handleDateInputChange">
         <input type="month" :id="periodInputId" class="form-control" v-else-if="selectedViewType === 'month'" v-model="selectedPeriodString">
         <input type="number" :id="periodInputId" class="form-control" v-else-if="selectedViewType === 'year'" v-model.number="selectedYear" placeholder="YYYY" min="1900" max="2100">
      </div>
       <div class="col-md-3 d-flex align-items-end" v-if="selectedViewType !== 'lifetime'">
         <button class="btn btn-outline-secondary me-1" @click="navigatePeriod(-1)" :disabled="loadingSummary || loadingActivities"><</button>
         <button class="btn btn-outline-secondary" @click="navigatePeriod(1)" :disabled="loadingSummary || loadingActivities">></button>
      </div>
    </div>

    <!-- Summary Display Section -->
    <div v-if="loadingSummary" class="text-center">
      <div class="spinner-border" role="status">
        <span class="visually-hidden">{{ t('summaryView.loadingSummary') }}</span>
      </div>
    </div>
    <div v-else-if="summaryData" class="card mb-4">
      <div class="card-header">
        {{ t('summaryView.headerSummaryFor', { period: summaryPeriodText }) }}
      </div>
      <div class="card-body">
        <!-- New Highlighted Summary Totals Section -->
        <div class="row text-center justify-content-around mb-3">
            <div class="col-lg col-md-4 col-sm-6 mb-3">
                <div class="card shadow-sm h-100 bg-primary text-white">
                    <div class="card-body d-flex flex-column justify-content-center">
                        <h6 class="card-subtitle mb-2 text-white-50">{{ t('summaryView.metricTotalDistance') }}</h6>
                        <p class="card-text h4 mb-0">{{ formatRawDistance(summaryData.total_distance, authStore.user.units) }}</p>
                    </div>
                </div>
            </div>
            <div class="col-lg col-md-4 col-sm-6 mb-3">
                <div class="card shadow-sm h-100 bg-primary text-white">
                    <div class="card-body d-flex flex-column justify-content-center">
                        <h6 class="card-subtitle mb-2 text-white-50">{{ t('summaryView.metricTotalDuration') }}</h6>
                        <p class="card-text h4 mb-0">{{ formatDuration(summaryData.total_duration) }}</p>
                    </div>
                </div>
            </div>
            <div class="col-lg col-md-4 col-sm-6 mb-3">
                <div class="card shadow-sm h-100 bg-primary text-white">
                    <div class="card-body d-flex flex-column justify-content-center">
                        <h6 class="card-subtitle mb-2 text-white-50">{{ t('summaryView.metricTotalElevation') }}</h6>
                        <p class="card-text h4 mb-0">{{ formatElevation(summaryData.total_elevation_gain, authStore.user.units) }}</p>
                    </div>
                </div>
            </div>
            <div class="col-lg col-md-6 col-sm-6 mb-3"> <!-- Adjusted col-md for potentially wider content -->
                <div class="card shadow-sm h-100 bg-primary text-white">
                    <div class="card-body d-flex flex-column justify-content-center">
                        <h6 class="card-subtitle mb-2 text-white-50">{{ t('summaryView.metricTotalCalories') }}</h6>
                        <p class="card-text h4 mb-0">{{ formatCalories(summaryData.total_calories) }}</p>
                    </div>
                </div>
            </div>
            <div class="col-lg col-md-6 col-sm-12 mb-3"> <!-- Adjusted col-md and col-sm for last item -->
                <div class="card shadow-sm h-100 bg-primary text-white">
                    <div class="card-body d-flex flex-column justify-content-center">
                        <h6 class="card-subtitle mb-2 text-white-50">{{ t('summaryView.metricTotalActivities') }}</h6>
                        <p class="card-text h4 mb-0">{{ summaryData.activity_count }}</p>
                    </div>
                </div>
            </div>
        </div>
        <hr>
        <h5>{{ t('summaryView.headerBreakdown') }}</h5>
        <div class="table-responsive">
          <table class="table table-sm table-striped responsive-summary-table">
            <thead>
              <tr>
                <th class="col-main-header">{{ breakdownHeader }}</th>
                <th>{{ t('summaryView.colDistance') }}</th>
                <th>{{ t('summaryView.colDuration') }}</th>
                <th v-if="showElevation">{{ t('summaryView.colElevation') }}</th>
                <th v-if="showCalories">{{ t('summaryView.colCalories') }}</th>
                <th v-if="showActivityCount">{{ t('summaryView.colActivities') }}</th>
              </tr>
            </thead>
            <tbody>
               <tr v-for="item in summaryData.breakdown" :key="getBreakdownKey(item)">
                  <td class="col-main-header">{{ getBreakdownLabel(item) }}</td>
                  <td>{{ formatRawDistance(item.total_distance, authStore.user.units) }}</td>
                  <td>{{ formatDuration(item.total_duration) }}</td>
                  <td v-if="showElevation">{{ formatElevation(item.total_elevation_gain, authStore.user.units) }}</td>
                  <td v-if="showCalories">{{ formatCalories(item.total_calories) }}</td>
                  <td v-if="showActivityCount">{{ item.activity_count }}</td>
               </tr>
               <tr v-if="!summaryData.breakdown || summaryData.breakdown.length === 0">
                  <td :colspan="mainBreakdownVisibleCols" class="text-center">{{ t('summaryView.noDataForPeriod') }}</td>
               </tr>
            </tbody>
          </table>
        </div>

        <div v-if="typeBreakdownData && !selectedActivityType" class="mt-4">
           <hr>
           <h5>{{ t('summaryView.headerTypeBreakdown') }}</h5>
           <div class="table-responsive">
             <table class="table table-sm table-striped responsive-summary-table">
               <thead>
                 <tr>
                   <th class="col-activity-type">{{ t('summaryView.colActivityType') }}</th>
                   <th>{{ t('summaryView.colDistance') }}</th>
                   <th>{{ t('summaryView.colDuration') }}</th>
                   <th v-if="showElevation">{{ t('summaryView.colElevation') }}</th>
                   <th v-if="showCalories">{{ t('summaryView.colCalories') }}</th>
                   <th v-if="showActivityCount">{{ t('summaryView.colActivities') }}</th>
                 </tr>
               </thead>
               <tbody>
                  <tr v-for="item in typeBreakdownData" :key="item.activity_type_id">
                     <td class="col-activity-type text-center"><font-awesome-icon :icon="getIcon(item.activity_type_id)" /></td>
                     <td>{{ formatRawDistance(item.total_distance, authStore.user.units) }}</td>
                     <td>{{ formatDuration(item.total_duration) }}</td>
                     <td v-if="showElevation">{{ formatElevation(item.total_elevation_gain, authStore.user.units) }}</td>
                     <td v-if="showCalories">{{ formatCalories(item.total_calories) }}</td>
                     <td v-if="showActivityCount">{{ item.activity_count }}</td>
                  </tr>
                  <tr v-if="!typeBreakdownData || typeBreakdownData.length === 0">
                    <td :colspan="typeBreakdownVisibleCols" class="text-center">{{ t('summaryView.noDataForPeriod') }}</td>
                  </tr>
               </tbody>
             </table>
           </div>
        </div>
      </div>
    </div>
     <div v-else-if="errorSummary" class="alert alert-danger">
      {{ t('summaryView.errorLoadingSummary', { error: errorSummary }) }}
    </div>

    <!-- Activities in Period Section - Conditionally rendered -->
    <div v-if="selectedViewType !== 'lifetime'">
      <h3 class="mt-4">{{ t('summaryView.headerActivitiesInPeriod') }}</h3>
      <div v-if="loadingActivities" class="text-center">
        <div class="spinner-border" role="status">
          <span class="visually-hidden">{{ t('summaryView.loadingActivities') }}</span>
        </div>
      </div>
      <div v-else-if="errorActivities" class="alert alert-danger">
        {{ t('summaryView.errorLoadingActivities', { error: errorActivities }) }}
      </div>
      <div v-else ref="activitiesSectionRef">
        <ActivitiesTableComponent
          :activities="activities"
          :sort-by="sortBy"
          :sort-order="sortOrder"
          @sort-changed="handleSort"
        />
        <PaginationComponent
          v-if="totalActivities > 0"
          :pageNumber="currentPage"
          :total-pages="calculatedTotalPages"
          @pageNumberChanged="handlePageChange"
        />
        <p v-if="activities.length === 0 && !loadingActivities">{{ t('summaryView.noActivitiesFound') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick, onBeforeUnmount } from 'vue';
import { useI18n } from 'vue-i18n';
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome';
import { useAuthStore } from '@/stores/authStore';
import { summaryService } from '@/services/summaryService';
import { activities as activitiesService } from '@/services/activitiesService';
import ActivitiesTableComponent from '@/components/Activities/ActivitiesTableComponent.vue';
import PaginationComponent from '@/components/GeneralComponents/PaginationComponent.vue';
import { getIcon, formatRawDistance, formatDuration, formatElevation, formatCalories } from '@/utils/activityUtils';
import {
  getWeekStartDate, getWeekEndDate, getMonthStartDate, getMonthEndDate, formatDateISO,
  parseMonthString, formatDateToMonthString
} from '@/utils/dateTimeUtils';

const { t } = useI18n();
const authStore = useAuthStore();

// Filter and View State
const selectedViewType = ref('week');
const selectedActivityType = ref('');
const activityTypes = ref({});
const initialDate = new Date();
const selectedDate = ref(formatDateISO(initialDate));
const selectedYear = ref(initialDate.getFullYear());
const selectedPeriodString = ref(formatDateToMonthString(initialDate));

// Data State
const summaryData = ref(null);
const typeBreakdownData = ref(null);
const activities = ref([]);
const totalActivities = ref(0);
const currentPage = ref(1);
const activitiesPerPage = ref(10);

// Loading and Error State
const loadingSummary = ref(false);
const errorSummary = ref(null);
const loadingActivities = ref(false);
const errorActivities = ref(null);
const loadingTypes = ref(false);
const errorTypes = ref(null);

// Scroll position preservation
const activitiesSectionRef = ref(null);
let storedScrollPosition = null;

// Sorting State
const sortBy = ref('start_time');
const sortOrder = ref('desc');

// Responsive column visibility
const showElevation = ref(true);
const showCalories = ref(true);
const showActivityCount = ref(true);

const updateColumnVisibility = () => {
  const width = window.innerWidth;
  const screenMd = 768; // Bootstrap 'md' breakpoint
  const screenSm = 576; // Bootstrap 'sm' breakpoint
  const screenXs = 480; // Custom extra-small, or a bit less than sm

  // Start by assuming all are visible
  showElevation.value = true;
  showCalories.value = true;
  showActivityCount.value = true;

  // Then, hide them progressively as the screen gets narrower
  if (width < screenMd) { // Below 768px
    showActivityCount.value = false;
  }
  if (width < screenSm) { // Below 576px
    showCalories.value = false;
  }
  if (width < screenXs) { // Below 480px (or your chosen smallest breakpoint)
    showElevation.value = false;
  }
};

// Computed property for dynamic input ID
const periodInputId = computed(() => {
  switch (selectedViewType.value) {
    case 'week': return 'periodPickerWeek';
    case 'month': return 'periodPickerMonth';
    case 'year': return 'periodPickerYear';
    default: return 'periodPicker';
  }
});

const periodLabel = computed(() => {
  switch (selectedViewType.value) {
    case 'week': return t('summaryView.labelSelectWeek');
    case 'month': return t('summaryView.labelSelectMonth');
    case 'year': return t('summaryView.labelSelectYear');
    case 'lifetime': return '';
    default: return t('summaryView.labelSelectPeriod');
  }
});

const summaryPeriodText = computed(() => {
  if (selectedViewType.value === 'lifetime') {
    return t('summaryView.optionLifetime');
  }
  if (!summaryData.value && !loadingSummary.value) return t('summaryView.labelSelectPeriod');
  if (loadingSummary.value) return t('generalItems.labelLoading');

  try {
    if (selectedViewType.value === 'year') {
      return t('summaryView.headerYear', { year: selectedYear.value });
    }
    const date = new Date(selectedDate.value + 'T00:00:00Z');
    if (isNaN(date.getTime())) return t('summaryView.invalidDateSelected');

    if (selectedViewType.value === 'month') {
      return date.toLocaleDateString(undefined, { year: 'numeric', month: 'long', timeZone: 'UTC' });
    }
    if (selectedViewType.value === 'week') {
      const weekStart = getWeekStartDate(date);
      return t('summaryView.headerWeekStarting', { date: formatDateISO(weekStart) });
    }
  } catch (e) {
    console.error("Error formatting summary period text:", e);
    return t('summaryView.labelSelectPeriod');
  }
  return '';
});

const breakdownHeader = computed(() => {
  switch (selectedViewType.value) {
    case 'week': return t('summaryView.colDay');
    case 'month': return t('summaryView.colWeekNum');
    case 'year': return t('summaryView.colMonth');
    case 'lifetime': return t('summaryView.colYear');
    default: return 'Period';
  }
});

const getBreakdownKey = (item) => {
  switch (selectedViewType.value) {
    case 'week': return item.day_of_week;
    case 'month': return item.week_number;
    case 'year': return item.month_number;
    case 'lifetime': return item.year_number;
    default: return '';
  }
};

const getBreakdownLabel = (item) => {
   switch (selectedViewType.value) {
    case 'week':
        const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
        return days[item.day_of_week] || 'Unknown Day';
    case 'month':
        return `${t('summaryView.colWeekNum')} ${item.week_number}`;
    case 'year':
        const monthDate = new Date(Date.UTC(selectedYear.value, item.month_number - 1, 1));
        return monthDate.toLocaleDateString(undefined, { month: 'long', timeZone: 'UTC' });
    case 'lifetime':
        return item.year_number;
    default: return '';
  }
};

const fetchActivityTypes = async () => {
  if (!authStore.user?.id) return;
  loadingTypes.value = true;
  errorTypes.value = null;
  try {
    activityTypes.value = await activitiesService.getActivityTypes();
  } catch (err) {
    console.error('Failed to fetch activity types:', err);
    errorTypes.value = t('generalItems.labelError');
  } finally {
    loadingTypes.value = false;
  }
};

const fetchSummaryData = async () => {
  if (!authStore.user?.id) return;

  loadingSummary.value = true;
  errorSummary.value = null;
  summaryData.value = null;
  typeBreakdownData.value = null;
  
  // Reset activities only if they are supposed to be fetched for the current view
  if (selectedViewType.value !== 'lifetime') {
    activities.value = [];
    totalActivities.value = 0;
    currentPage.value = 1;
  }


  try {
    const params = {};
    if (selectedViewType.value === 'year') {
      if (!selectedYear.value || selectedYear.value < 1900 || selectedYear.value > 2100) {
        throw new Error(t('summaryView.invalidYearSelected'));
      }
      params.year = selectedYear.value;
    } else if (selectedViewType.value === 'week' || selectedViewType.value === 'month') {
      if (!selectedDate.value) {
        throw new Error(t('summaryView.noDateSelected'));
      }
      params.date = selectedDate.value;
    }
    // For 'lifetime', params remains empty.

    const activityTypeName = selectedActivityType.value ? activityTypes.value[selectedActivityType.value] : null;

    const response = await summaryService.getSummary(
        authStore.user.id,
        selectedViewType.value,
        params,
        activityTypeName
    );
    summaryData.value = response;
    typeBreakdownData.value = response.type_breakdown;
    
    if (selectedViewType.value !== 'lifetime') {
      fetchActivitiesForPeriod(); 
    } else {
      // For lifetime view, ensure activities list is and stays empty
      activities.value = [];
      totalActivities.value = 0;
      currentPage.value = 1;
      loadingActivities.value = false; // Ensure loading state is false
      errorActivities.value = null; // Clear any previous activity errors
    }
  } catch (err) {
    console.error('Error fetching summary:', err);
    errorSummary.value = err.message || (err.response?.data?.detail || t('generalItems.labelError'));
  } finally {
    loadingSummary.value = false;
  }
};

const fetchActivitiesForPeriod = async (page = currentPage.value) => {
  if (!authStore.user?.id || selectedViewType.value === 'lifetime') { // Do not fetch for lifetime
    activities.value = [];
    totalActivities.value = 0;
    loadingActivities.value = false;
    return;
  }

  loadingActivities.value = true;
  errorActivities.value = null;
  if (page === 1) {
      activities.value = [];
      totalActivities.value = 0;
  }

  try {
    const filters = {
      type: selectedActivityType.value || null
    };

    if (selectedViewType.value === 'year') {
      if (!selectedYear.value || selectedYear.value < 1900 || selectedYear.value > 2100) {
        throw new Error(t('summaryView.invalidYearSelected'));
      }
      filters.start_date = `${selectedYear.value}-01-01`;
      filters.end_date = `${selectedYear.value + 1}-01-01`;
    } else if (selectedViewType.value === 'week' || selectedViewType.value === 'month') {
      if (!selectedDate.value) {
         throw new Error(t('summaryView.noDateSelected'));
      }
      const date = new Date(selectedDate.value + 'T00:00:00Z');
      if (isNaN(date.getTime())) throw new Error(t('summaryView.invalidDateSelected'));

      if (selectedViewType.value === 'week') {
          const weekStart = getWeekStartDate(date);
          const weekEnd = getWeekEndDate(date);
          filters.start_date = formatDateISO(weekStart);
          filters.end_date = formatDateISO(weekEnd); 
      } else { // month
          const monthStart = getMonthStartDate(date);
          const monthEnd = getMonthEndDate(date);
          filters.start_date = formatDateISO(monthStart);
          filters.end_date = formatDateISO(monthEnd);
      }
    }
    // For 'lifetime', no date filters are added (already handled by the guard clause at the start)
    
    Object.keys(filters).forEach(key => (filters[key] == null || filters[key] === '') && delete filters[key]);

    const response = await activitiesService.getUserActivitiesWithPagination(
        authStore.user.id,
        page,
        activitiesPerPage.value,
        filters,
        sortBy.value,
        sortOrder.value
    );
    activities.value = Array.isArray(response) ? response : [];
    currentPage.value = page;

    if (authStore.user?.id) {
      try {
        const countResponse = await activitiesService.getUserNumberOfActivities(filters);
        totalActivities.value = countResponse || 0;
      } catch (countErr) {
        console.error('Error fetching total activities count:', countErr);
        totalActivities.value = 0;
      }
    } else {
       totalActivities.value = 0;
    }

  } catch (err) {
    console.error('Error fetching activities:', err);
    errorActivities.value = err.message || (err.response?.data?.detail || t('generalItems.labelError'));
    activities.value = []; // Clear activities on error
    totalActivities.value = 0; // Reset count on error
  } finally {
    loadingActivities.value = false;
    nextTick(() => {
      if (storedScrollPosition !== null && activitiesSectionRef.value) {
        const newTop = activitiesSectionRef.value.getBoundingClientRect().top;
        const scrollDifference = newTop - storedScrollPosition;
        window.scrollBy(0, scrollDifference);
        storedScrollPosition = null;
      }
    });
  }
};

function handlePageChange(newPage) {
  if (activitiesSectionRef.value) {
    storedScrollPosition = activitiesSectionRef.value.getBoundingClientRect().top;
  }
  fetchActivitiesForPeriod(newPage);
}

function handleSort(columnName) {
  if (activitiesSectionRef.value) {
    storedScrollPosition = activitiesSectionRef.value.getBoundingClientRect().top;
  }
  if (sortBy.value === columnName) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc';
  } else {
    sortBy.value = columnName;
    sortOrder.value = 'desc';
  }
  fetchActivitiesForPeriod(1);
}

function triggerDataFetch() {
    currentPage.value = 1;
    let shouldFetchSummary = false;
    errorSummary.value = null; 

    if (selectedViewType.value === 'lifetime') {
        shouldFetchSummary = true;
    } else if (selectedViewType.value === 'year') {
        if (selectedYear.value && selectedYear.value >= 1900 && selectedYear.value <= 2100) {
            shouldFetchSummary = true;
        } else {
            if (selectedYear.value) { 
                errorSummary.value = t('summaryView.invalidYearSelected');
            } else {
                 console.warn("Year is not selected or invalid, not fetching summary.");
            }
        }
    } else { // 'week' or 'month'
        if (selectedDate.value) {
            if (/^\d{4}-\d{2}-\d{2}$/.test(selectedDate.value)) { 
                 shouldFetchSummary = true;
            } else {
                 errorSummary.value = t('summaryView.invalidDateSelected');
            }
        } else {
            errorSummary.value = t('summaryView.noDateSelected');
        }
    }

    if (shouldFetchSummary) {
        fetchSummaryData(); // This will conditionally call fetchActivitiesForPeriod
    } else {
        console.warn("Skipping summary fetch due to invalid period selection for view type:", selectedViewType.value);
        summaryData.value = null;
        typeBreakdownData.value = null;
        activities.value = [];
        totalActivities.value = 0;
    }
}

function handleDateInputChange() {
    triggerDataFetch();
}

watch(selectedPeriodString, (newString) => {
  if (selectedViewType.value !== 'month' || !newString) return;
  try {
    const newDate = parseMonthString(newString);
    if (newDate && !isNaN(newDate.getTime())) {
      const newDateISO = formatDateISO(newDate);
      if (newDateISO !== selectedDate.value) {
        selectedDate.value = newDateISO;
        triggerDataFetch();
      }
    } else if (newString) { 
      errorSummary.value = t('summaryView.invalidInputFormat');
    }
  } catch (e) {
    console.error('Error parsing month string ${newString}:', e);
    errorSummary.value = t('summaryView.invalidInputFormat');
  }
});

watch(selectedYear, (newYear, oldYear) => {
    if (selectedViewType.value !== 'year') return;
    
    if (newYear && newYear >= 1900 && newYear <= 2100) {
         errorSummary.value = null; 
         triggerDataFetch();
    } else if (newYear) { 
        errorSummary.value = t('summaryView.invalidYearSelected');
        summaryData.value = null;
        typeBreakdownData.value = null;
        activities.value = [];
        totalActivities.value = 0;
    } else if (!newYear && oldYear) { 
        errorSummary.value = t('summaryView.invalidYearSelected'); 
        summaryData.value = null;
        typeBreakdownData.value = null;
        activities.value = [];
        totalActivities.value = 0;
    }
});

watch(selectedActivityType, () => {
  triggerDataFetch();
});

watch(selectedViewType, (newType, oldType) => {
  if (newType === oldType) return;

  try {
    errorSummary.value = null;
    errorActivities.value = null;

    if (newType !== 'lifetime') {
        let baseDate;
        try {
            baseDate = new Date(selectedDate.value + 'T00:00:00Z');
            if (isNaN(baseDate.getTime())) throw new Error("Current selectedDate is invalid, defaulting to today.");
        } catch(e) {
            console.warn(e.message);
            baseDate = new Date(); 
            selectedDate.value = formatDateISO(baseDate); 
        }

        if (newType === 'month') {
          selectedPeriodString.value = formatDateToMonthString(baseDate);
        } else if (newType === 'year') {
          selectedYear.value = baseDate.getUTCFullYear();
        }
    } else { // Switching to lifetime
        activities.value = []; // Clear activities immediately
        totalActivities.value = 0;
        currentPage.value = 1;
        loadingActivities.value = false;
        errorActivities.value = null;
    }
    triggerDataFetch();

  } catch (e) {
      console.error("Error handling view type change:", e);
      errorSummary.value = t('generalItems.labelError');
      const today = new Date();
      selectedViewType.value = 'week'; 
      selectedDate.value = formatDateISO(today);
      selectedPeriodString.value = formatDateToMonthString(today);
      selectedYear.value = today.getUTCFullYear();
      triggerDataFetch(); 
  }
});

function navigatePeriod(direction) {
    if (selectedViewType.value === 'lifetime') return;

    try {
        errorSummary.value = null; 

        if (selectedViewType.value === 'year') {
            const currentYear = selectedYear.value || new Date().getUTCFullYear();
            selectedYear.value = currentYear + direction;
            // triggerDataFetch() is called by the watcher on selectedYear
        } else { 
            let currentDate;
            try {
                currentDate = new Date(selectedDate.value + 'T00:00:00Z');
                if (isNaN(currentDate.getTime())) throw new Error("Invalid date for navigation");
            } catch {
                currentDate = new Date(); 
            }
            
            if (selectedViewType.value === 'week') {
                currentDate.setUTCDate(currentDate.getUTCDate() + (7 * direction));
            } else { // 'month'
                currentDate.setUTCMonth(currentDate.getUTCMonth() + direction, 1); 
            }
            selectedDate.value = formatDateISO(currentDate); 
            
            if (selectedViewType.value === 'month') {
                 selectedPeriodString.value = formatDateToMonthString(currentDate); // This will trigger its watcher
                 triggerDataFetch(); 
            } else { // week
                 triggerDataFetch(); // For week, date change needs to trigger fetch directly
            }
        }
    } catch (e) {
        console.error("Error navigating period:", e);
        errorSummary.value = t('generalItems.labelError');
    }
}

const calculatedTotalPages = computed(() => {
  return totalActivities.value > 0 ? Math.ceil(totalActivities.value / activitiesPerPage.value) : 1;
});

const mainBreakdownVisibleCols = computed(() => {
  let count = 3; // Base: Header, Distance, Duration
  if (showElevation.value) count++;
  if (showCalories.value) count++;
  if (showActivityCount.value) count++;
  return count;
});

const typeBreakdownVisibleCols = computed(() => {
  let count = 3; // Base: Activity Type, Distance, Duration
  if (showElevation.value) count++;
  if (showCalories.value) count++;
  if (showActivityCount.value) count++;
  return count;
});

onMounted(() => {
  fetchActivityTypes();
  updateColumnVisibility();
  window.addEventListener('resize', updateColumnVisibility);
  triggerDataFetch(); 
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateColumnVisibility);
});

</script>

<style scoped>
.table-responsive {
    max-height: 400px;
}
.card .row.text-center p {
    margin-bottom: 0;
}
.align-items-end {
    align-items: flex-end;
}

.responsive-summary-table th,
.responsive-summary-table td {
  min-width: 75px; 
  white-space: nowrap; 
}
.responsive-summary-table .col-main-header {
    min-width: 100px;
}
.responsive-summary-table .col-activity-type {
    min-width: 60px;
    text-align: center;
}
</style>
