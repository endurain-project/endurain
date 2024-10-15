<template>
    <div class="row row-gap-3">
        <h1>{{ $t("healthView.title") }}</h1>

        <!-- Include the HealthSideBarComponent -->
        <HealthSideBarComponent :activeSection="activeSection" @update-active-section="updateActiveSection" />

        <LoadingComponent v-if="isLoading" />

        <!-- Include the HealthDashboardZone -->
        <HealthDashboardZone :userHealthData="userHealthData[0]" :userHealthTargets="userHealthTargets" v-if="activeSection === 'dashboard' && !isLoading && userHealthData"/>

        <!-- Include the SettingsUserProfileZone -->
        <HealthWeightZone :userHealthData="userHealthData" :userHealthTargets="userHealthTargets" :isLoading="isLoading" :totalPages="totalPages" :pageNumber="pageNumber" @createdWeight="updateWeightListAdded" @deletedWeight="updateWeightListDeleted" @editedWeight="updateWeightListEdited" v-if="activeSection === 'weight' && !isLoading" />
    </div>
    <!-- back button -->
    <BackButtonComponent />
</template>

<script>
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
// Import Notivue push
import { push } from "notivue";
// Importing the components
import HealthSideBarComponent from '../components/Health/HealthSideBarComponent.vue';
import HealthDashboardZone from '../components/Health/HealthDashboardZone.vue';
import HealthWeightZone from '../components/Health/HealthWeightZone.vue';
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue';
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue';
// Importing the services
import { health_data } from '@/services/health_dataService';
import { health_targets } from '@/services/health_targetsService';

export default {
    components: {
        HealthSideBarComponent,
        HealthDashboardZone,
        HealthWeightZone,
        BackButtonComponent,
        LoadingComponent,
    },
    setup () {
        const { t } = useI18n();
        const activeSection = ref('weight');
        const isLoading = ref(true);
        const isHealthDataUpdatingLoading = ref(true);
        const userHealthDataNumber = ref(0);
        const userHealthData = ref([]);
        const userHealthTargets = ref(null);
        const pageNumber = ref(1);
        const totalPages = ref(1);
        const numRecords = 5;

        function updateActiveSection(section) {
            // Update the active section.
            activeSection.value = section;

            if(pageNumber.value !== 1){
                pageNumber.value = 1;
                updateHealthData();
            }
        }

        async function updateHealthData() {
            try {
                // Set the loading variable to true.
                isHealthDataUpdatingLoading.value = true;

                // Fetch the health_data with pagination.
                userHealthData.value = await health_data.getUserHealthDataWithPagination(pageNumber.value, numRecords);

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
                userHealthDataNumber.value = await health_data.getUserHealthDataNumber();

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
			if (userHealthData.value){
                userHealthData.value.unshift(createdWeight);
            } else {
                userHealthData.value = [createdWeight];
            }
            userHealthDataNumber.value++;
		}

        function updateWeightListDeleted(deletedWeight) {
            for(const data of userHealthData.value){
                if(data.id === deletedWeight){
                    data.weight = null;
                }
            }
        }

        function updateWeightListEdited(editedWeight) {
            for(const data of userHealthData.value){
                if(data.id === editedWeight.id){
                    data.weight = editedWeight.weight;
                    data.created_at = editedWeight.created_at;
                }
            }
        }

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
            userHealthData,
            userHealthTargets,
            pageNumber,
            totalPages,
            updateActiveSection,
            updateWeightListAdded,
            updateWeightListDeleted,
            updateWeightListEdited,
        };
    },
};
</script>