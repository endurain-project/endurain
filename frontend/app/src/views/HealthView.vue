<template>
    <div class="row row-gap-3">
        <h1>{{ $t("healthView.title") }}</h1>

        <!-- Include the HealthSideBarComponent -->
        <HealthSideBarComponent :activeSection="activeSection" @update-active-section="updateActiveSection" />

        <LoadingComponent v-if="isLoading" />

        <!-- Include the HealthDashboardZone -->
        <HealthDashboardZone :userHealthData="userHealthData" :userHealthTargets="userHealthTargets" v-if="activeSection === 'dashboard' && !isLoading"/>

        <!-- Include the SettingsUserProfileZone -->
        <HealthWeightZone :userHealthData="userHealthData" :userHealthDataPagination="userHealthDataPagination" :userHealthTargets="userHealthTargets" :isLoading="isLoading" :totalPages="totalPages" :pageNumber="pageNumber" @createdWeight="updateWeightListAdded" @deletedWeight="updateWeightListDeleted" @editedWeight="updateWeightListEdited" @pageNumberChanged="setPageNumber" v-if="activeSection === 'weight' && !isLoading" />
    </div>
    <!-- back button -->
    <BackButtonComponent />
</template>

<script>
import { ref, onMounted, watch } from "vue";
import { useI18n } from "vue-i18n";
// Import Notivue push
import { push } from "notivue";
// Importing the components
import HealthSideBarComponent from "../components/Health/HealthSideBarComponent.vue";
import HealthDashboardZone from "../components/Health/HealthDashboardZoneComponent.vue";
import HealthWeightZone from "../components/Health/HealthWeightZone.vue";
import BackButtonComponent from "@/components/GeneralComponents/BackButtonComponent.vue";
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
// Importing the services
import { health_data } from "@/services/health_dataService";
import { health_targets } from "@/services/health_targetsService";

export default {
	components: {
		HealthSideBarComponent,
		HealthDashboardZone,
		HealthWeightZone,
		BackButtonComponent,
		LoadingComponent,
	},
	setup() {
		const { t } = useI18n();
		const activeSection = ref("dashboard");
		const isLoading = ref(true);
		const isHealthDataUpdatingLoading = ref(true);
		const userHealthDataNumber = ref(0);
		const userHealthData = ref([]);
		const userHealthDataPagination = ref([]);
		const userHealthTargets = ref(null);
		const pageNumber = ref(1);
		const totalPages = ref(1);
		const numRecords = 5;

		function updateActiveSection(section) {
			// Update the active section.
			activeSection.value = section;

			if (pageNumber.value !== 1) {
				pageNumber.value = 1;
				updateHealthData();
			}
		}

		async function updateHealthData() {
			try {
				// Set the loading variable to true.
				isHealthDataUpdatingLoading.value = true;

				// Fetch the health_data with pagination.
				userHealthDataPagination.value =
					await health_data.getUserHealthDataWithPagination(
						pageNumber.value,
						numRecords,
					);

				// Set the loading variable to false.
				isHealthDataUpdatingLoading.value = false;
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(`${t("generalItems.errorFetchingInfo")} - ${error}`);
			}
		}

		async function fetchHealthData() {
			try {
				// Get the total number of user health_data.
				userHealthDataNumber.value =
					await health_data.getUserHealthDataNumber();

				// Fetch the health_data
				userHealthData.value = await health_data.getUserHealthData();

				// Fetch the health_data with pagination.
				await updateHealthData();

				// Update total pages
				totalPages.value = Math.ceil(userHealthDataNumber.value / numRecords);
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(`${t("generalItems.errorFetchingInfo")} - ${error}`);
			}
		}

		async function fetchHealthTargets() {
			try {
				// Fetch the health_targets
				userHealthTargets.value = await health_targets.getUserHealthTargets();
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(`${t("generalItems.errorFetchingInfo")} - ${error}`);
			}
		}

		function updateWeightListAdded(createdWeight) {
			// Function to update or add an entry in the array
			const updateOrAdd = (array, newEntry) => {
				const index = array.findIndex((item) => item.id === newEntry.id);
				if (index !== -1) {
					// Update existing entry
					array[index] = newEntry;
				} else {
					// Add new entry
					array.unshift(newEntry);
				}
			};

			// Check and update both arrays
			if (userHealthDataPagination.value) {
				updateOrAdd(userHealthDataPagination.value, createdWeight);
			} else {
				userHealthDataPagination.value = [createdWeight];
			}

			if (userHealthData.value) {
				updateOrAdd(userHealthData.value, createdWeight);
			} else {
				userHealthData.value = [createdWeight];
			}

			userHealthDataNumber.value = userHealthData.value.length; // Update the count
		}

		function updateWeightListDeleted(deletedWeight) {
			// Update the weight in the userHealthDataPagination and userHealthData arrays.
			for (const data of userHealthDataPagination.value) {
				if (data.id === deletedWeight) {
					data.weight = null;
				}
			}
			for (const data of userHealthData.value) {
				if (data.id === deletedWeight) {
					data.weight = null;
				}
			}
		}

		function updateWeightListEdited(editedWeight) {
			// Update the weight in the userHealthDataPagination and userHealthData arrays.
			for (const data of userHealthDataPagination.value) {
				if (data.id === editedWeight.id) {
					data.weight = editedWeight.weight;
					data.created_at = editedWeight.created_at;
				}
			}
			for (const data of userHealthData.value) {
				if (data.id === editedWeight.id) {
					data.weight = editedWeight.weight;
					data.created_at = editedWeight.created_at;
				}
			}
		}

		function setPageNumber(page) {
			// Set the page number.
			pageNumber.value = page;
		}

		// Watch the page number variable.
		watch(pageNumber, updateHealthData, { immediate: false });

		onMounted(async () => {
			// Fetch health_data and health_targets
			await fetchHealthData();
			await fetchHealthTargets();

			// Set the isLoading variables to false.
			isHealthDataUpdatingLoading.value = false;
			isLoading.value = false;
		});

		return {
			activeSection,
			isLoading,
			isHealthDataUpdatingLoading,
			userHealthDataPagination,
			userHealthData,
			userHealthTargets,
			pageNumber,
			totalPages,
			updateActiveSection,
			updateWeightListAdded,
			updateWeightListDeleted,
			updateWeightListEdited,
			setPageNumber,
		};
	},
};
</script>