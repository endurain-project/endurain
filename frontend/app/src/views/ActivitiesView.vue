<template>
	<h1>{{ $t('activitiesView.title') }}</h1>
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
					<button type="submit" class="btn btn-primary">{{ $t('activitiesView.buttonApply') }}</button>
				</div>
			</form>
		</div>
	</div>
	<!-- End Filter Section -->

	<LoadingComponent v-if="isLoading" />

	<div v-else>
		<!-- Activities Table -->
		<ActivitiesTableComponent
			:activities="activities"
			:sort-by="sortBy"
			:sort-order="sortOrder"
			@sort-changed="handleSort"
			v-if="activities && activities.length"
		/>

		<PaginationComponent :totalPages="totalPages" :pageNumber="pageNumber" @pageNumberChanged="setPageNumber" v-if="activities && activities.length"/>
		
		<NoItemsFoundComponents v-else />
	</div>
</template>

<script>
import { ref, onMounted, watch } from "vue";
import { useI18n } from "vue-i18n";
// Import Notivue push
import { push } from "notivue";
// Import stores
import { useAuthStore } from "@/stores/authStore";
// Import services
import { activities as activitiesService } from "@/services/activitiesService";
// Import components
import ActivitiesTableComponent from "@/components/Activities/ActivitiesTableComponent.vue";
import PaginationComponent from "@/components/GeneralComponents/PaginationComponent.vue";
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import NoItemsFoundComponents from "@/components/GeneralComponents/NoItemsFoundComponents.vue";

export default {
	components: {
		ActivitiesTableComponent,
		PaginationComponent,
		LoadingComponent,
		NoItemsFoundComponents,
	},
	setup() {
		const { t } = useI18n();

		const authStore = useAuthStore();
		const activities = ref([]);
		const userNumberActivities = ref(0);
		const pageNumber = ref(1);
		const numRecords = 5;
		const totalPages = ref(1);
		const isLoading = ref(true);
		const error = ref(null);

		// Filter state
		const activityTypes = ref([]);
		const selectedType = ref("");
		const startDate = ref("");
		const endDate = ref("");
		const nameSearch = ref("");

		// Sorting state
		const sortBy = ref("start_time"); // Default sort column
		const sortOrder = ref("desc"); // Default sort order

		// Fetch available activity types for the filter dropdown
		async function fetchActivityTypes() {
			try {
				activityTypes.value = await activitiesService.getActivityTypes(); // Assuming a new service function
			} catch (error) {
				push.error(`${t("activitiesView.errorFailedFetchActivityTypes")} - ${error}`);
			}
		}

		function setPageNumber(page) {
			// Set the page number.
			pageNumber.value = page;
		}

		async function updateActivities() {
			try {
				// Set the loading variable to true.
				isLoading.value = true;

				// Fetch the gears with pagination.
				fetchActivities({}, sortBy.value, sortOrder.value);
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(`${t("activitiesView.errorUpdatingActivities")} - ${error}`);
			} finally {
				// Set the loading variable to false.
				isLoading.value = false;
			}
		}

		// Fetch activities with pagination, filters, and sorting
		async function fetchActivities(
			currentFilters = {},
			currentSortBy = sortBy.value,
			currentSortOrder = sortOrder.value,
		) {
			isLoading.value = true;
			error.value = null;
			activities.value = [];

			try {
				// Prepare filters, removing empty values
				const activeFilters = {};
				if (currentFilters.type) activeFilters.type = currentFilters.type;
				if (currentFilters.start_date)
					activeFilters.start_date = currentFilters.start_date;
				if (currentFilters.end_date)
					activeFilters.end_date = currentFilters.end_date;
				if (currentFilters.name_search)
					activeFilters.name_search = currentFilters.name_search;

				// Use the activities service with filters and sorting
				activities.value =
					await activitiesService.getUserActivitiesWithPagination(
						authStore.user.id,
						pageNumber.value,
						numRecords,
						activeFilters,
						currentSortBy, // Pass sort column
						currentSortOrder, // Pass sort order
					);
				userNumberActivities.value =
					await activitiesService.getUserNumberOfActivities();

				totalPages.value = Math.ceil(userNumberActivities.value / numRecords);
			} catch (error) {
				push.error(`${t("activitiesView.errorFetchingActivities")} - ${error}`);
			} finally {
				isLoading.value = false;
			}
		}

		onMounted(() => {
			fetchActivityTypes(); // Fetch types on mount
			// Initial fetch with default page, filters (empty), and sorting
			fetchActivities({}, sortBy.value, sortOrder.value);
		});

		// Function to apply filters and fetch data
		function applyFilters() {
			// Reset to page 1 when filters change
			pageNumber.value = 1;
			// keep current sort order
			fetchActivities(
				{
					type: selectedType.value,
					start_date: startDate.value,
					end_date: endDate.value,
					name_search: nameSearch.value,
				},
				sortBy.value,
				sortOrder.value,
			);
		}

		// Function to clear filters
		function clearFilters() {
			selectedType.value = "";
			startDate.value = "";
			endDate.value = "";
			nameSearch.value = "";
			// applyFilters will re-fetch with cleared filters and current sort order
			applyFilters();
		}

		// Function to handle sorting changes from table component
		function handleSort(columnName) {
			if (sortBy.value === columnName) {
				// Toggle sort order if same column is clicked
				sortOrder.value = sortOrder.value === "asc" ? "desc" : "asc";
			} else {
				// Set new column and default to descending order
				sortBy.value = columnName;
				sortOrder.value = "desc"; // Or 'asc' if preferred as default
			}
			// Fetch data with new sorting, reset to page 1
			fetchActivities(
				{
					type: selectedType.value,
					start_date: startDate.value,
					end_date: endDate.value,
					name_search: nameSearch.value,
				},
				sortBy.value,
				sortOrder.value,
			);
		}

		// Watch the page number variable.
		watch(pageNumber, updateActivities, { immediate: false });

		return {
			activities,
			pageNumber,
			numRecords,
			totalPages,
			isLoading,
			error,
			activityTypes,
			selectedType,
			startDate,
			endDate,
			nameSearch,
			sortBy,
			sortOrder,
			fetchActivities,
			setPageNumber,
			applyFilters,
			clearFilters,
			handleSort,
		};
	},
};
</script>
