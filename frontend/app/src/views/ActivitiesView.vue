<template>
	<h1>{{ $t('activitiesView.title') }}</h1>
	<!-- Filter Section -->
	<div class="card mb-4 bg-body-tertiary border-0 rounded">
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
						<option v-for="(value, key) in activityTypes" :key="key" :value="key">{{ value }}</option>
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
					<button type="submit" class="btn btn-primary" disabled v-if="isLoading">
						<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>
						<span role="status">{{ $t('activitiesView.buttonApply') }}</span>
					</button>
					<button type="submit" class="btn btn-primary" v-else>{{ $t('activitiesView.buttonApply') }}</button>
				</div>
			</form>
		</div>
	</div>
	<!-- End Filter Section -->

<LoadingComponent v-if="isLoading" />

<div class="p-3 bg-body-tertiary rounded shadow-sm" v-else-if="activities && activities.length" ref="activitiesListRef">
<!-- Activities Table -->
<ActivitiesTableComponent
			:activities="activities"
			:sort-by="sortBy"
			:sort-order="sortOrder"
			@sortChanged="handleSort"
			v-if="activities && activities.length"
		/>

		<PaginationComponent class="d-none d-lg-block" :totalPages="totalPages" :pageNumber="pageNumber" @pageNumberChanged="setPageNumber" v-if="activities && activities.length"/>
		<PaginationMobileComponent class="d-lg-none d-block" :totalPages="totalPages" :pageNumber="pageNumber" @pageNumberChanged="setPageNumber" v-if="activities && activities.length"/>
	</div>
		
	<NoItemsFoundComponents v-else />
</template>

<script>
import { ref, onMounted, watch, nextTick } from "vue";
import { useI18n } from "vue-i18n";
// import lodash
import { debounce } from "lodash";
// Import Notivue push
import { push } from "notivue";
// Import stores
import { useAuthStore } from "@/stores/authStore";
// Import services
import { activities as activitiesService } from "@/services/activitiesService";
// Import components
import ActivitiesTableComponent from "@/components/Activities/ActivitiesTableComponent.vue";
import PaginationComponent from "@/components/GeneralComponents/PaginationComponent.vue";
import PaginationMobileComponent from "@/components/GeneralComponents/PaginationMobileComponent.vue";
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import NoItemsFoundComponents from "@/components/GeneralComponents/NoItemsFoundComponents.vue";

export default {
	components: {
		ActivitiesTableComponent,
		PaginationComponent,
		PaginationMobileComponent,
		LoadingComponent,
		NoItemsFoundComponents,
	},
	setup() {
		const { t } = useI18n();
		const authStore = useAuthStore();
		const activityTypes = ref([]);
		const activities = ref([]);
		const userNumberActivities = ref(0);
		const pageNumber = ref(1);
		const numRecords = 20;
		const totalPages = ref(1);
const isLoading = ref(true);

// Scroll position preservation
const activitiesListRef = ref(null);
let storedScrollPositionActivities = null;

// Filter state
const selectedType = ref("");
		const startDate = ref("");
		const endDate = ref("");
		const nameSearch = ref("");

		// Sorting state
		const sortBy = ref("start_time"); // Default sort column
		const sortOrder = ref("desc"); // Default sort order

		const performNameSearch = debounce(async () => {
			// If the search nickname is empty, reset the list to initial state.
			if (!nameSearch.value) {
				// Reset the list to the initial state when search text is cleared
				pageNumber.value = 1;
				// Apply filters
				await applyFilters();
				// Exit the function
				return;
			}
			try {
				// Fetch the activities based on the search name.
				await applyFilters();
			} catch (error) {
				push.error(`${t("activitiesView.errorUpdatingActivities")} - ${error}`);
			}
		}, 500);

// Fetch available activity types for the filter dropdown
async function fetchActivityTypes() {
try {
activityTypes.value = await activitiesService.getActivityTypes();
} catch (error) {
push.error(
`${t("activitiesView.errorFailedFetchActivityTypes")} - ${error}`,
);
}
}

function setPageNumber(page) {
  if (activitiesListRef.value) {
    storedScrollPositionActivities = activitiesListRef.value.getBoundingClientRect().top;
  }
// Set the page number.
pageNumber.value = page;
}

async function updateActivities() {
			try {
				// Set the loading variable to true.
				isLoading.value = true;

				// Fetch the gears with pagination.
				await fetchActivities();
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
push.error(`${t("activitiesView.errorUpdatingActivities")} - ${error}`);
} finally {
// Set the loading variable to false.
isLoading.value = false;
      nextTick(() => {
        if (storedScrollPositionActivities !== null && activitiesListRef.value) {
          const newTop = activitiesListRef.value.getBoundingClientRect().top;
          const scrollDifference = newTop - storedScrollPositionActivities;
          window.scrollBy(0, scrollDifference);
          storedScrollPositionActivities = null; // Reset after use
        }
      });
}
}

		// Fetch activities with pagination, filters, and sorting
		async function fetchActivities() {
			activities.value = [];
			const filters = {
				type: selectedType.value,
				start_date: startDate.value,
				end_date: endDate.value,
				name_search: nameSearch.value,
			};

			try {
				// Use the activities service with filters and sorting
				activities.value =
					await activitiesService.getUserActivitiesWithPagination(
						authStore.user.id,
						pageNumber.value,
						numRecords,
						filters,
						sortBy.value,
						sortOrder.value,
					);
				userNumberActivities.value =
					await activitiesService.getUserNumberOfActivities(filters);

				totalPages.value = Math.ceil(userNumberActivities.value / numRecords);
			} catch (error) {
				push.error(`${t("activitiesView.errorFetchingActivities")} - ${error}`);
			}
		}

		onMounted(async () => {
			// fetch initial data
			await fetchActivityTypes();
			await updateActivities();
		});

		// Function to apply filters and fetch data
		async function applyFilters() {
			// Reset to page 1 when filters change
			pageNumber.value = 1;
			// keep current sort order
			await updateActivities();
		}

		// Function to clear filters
		async function clearFilters() {
			selectedType.value = "";
			startDate.value = "";
			endDate.value = "";
			nameSearch.value = "";
			sortBy.value = "start_time";
			sortOrder.value = "desc";
			// applyFilters will re-fetch with cleared filters and current sort order
			await applyFilters();
		}

// Function to handle sorting changes from table component
async function handleSort(columnName) {
  if (activitiesListRef.value) {
    storedScrollPositionActivities = activitiesListRef.value.getBoundingClientRect().top;
  }
if (sortBy.value === columnName) {
// Toggle sort order if same column is clicked
sortOrder.value = sortOrder.value === "asc" ? "desc" : "asc";
} else {
// Set new column and default to descending order
sortBy.value = columnName;
sortOrder.value = "desc"; // Or 'asc' if preferred as default
}
// Fetch data with new sorting, reset to page 1
await updateActivities();
}

		// Watch the search name variable.
		watch(nameSearch, performNameSearch, { immediate: false });

		// Watch the page number variable.
		watch(pageNumber, updateActivities, { immediate: false });

		return {
			activities,
			pageNumber,
			totalPages,
			isLoading,
			activityTypes,
			selectedType,
			startDate,
endDate,
nameSearch,
sortBy,
sortOrder,
activitiesListRef,
setPageNumber,
applyFilters,
clearFilters,
handleSort,
};
},
};
</script>
