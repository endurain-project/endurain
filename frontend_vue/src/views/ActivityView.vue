<template>
    <LoadingComponent v-if="isLoading"/>
    <div v-else>
        <ActivitySummaryComponent v-if="activity" :activity="activity" :source="'activity'" />
    </div>

    <!-- map zone -->
    <div class="mt-3 mb-3" v-if="isLoading">
        <LoadingComponent />
    </div>
    <div class="mt-3 mb-3" v-else>
        <ActivityMapComponent :activity="activity" :source="'activity'"/>
    </div>
    
    <!-- gear zone -->
    <hr class="mb-2 mt-2">
    <div class="mt-3 mb-3" v-if="isLoading">
        <LoadingComponent />
    </div>
    <div class="d-flex justify-content-between align-items-center" v-else>
        <p class="pt-2">
            <span class="fw-lighter">
                {{ $t("activity.labelGear") }}
            </span>
            <br>
            <span v-if="activity.activity_type == 1 || activity.activity_type == 2 || activity.activity_type == 3">
                <font-awesome-icon :icon="['fas', 'person-running']" />
            </span>
            <span v-else-if="activity.activity_type == 4 || activity.activity_type == 5 || activity.activity_type == 6 || activity.activity_type == 7">
                <font-awesome-icon :icon="['fas', 'fa-person-biking']" />
            </span>
            <span v-else-if="activity.activity_type == 8 || activity.activity_type == 9">
                <font-awesome-icon :icon="['fas', 'fa-person-swimming']" />
            </span>
            <span class="ms-2" v-if="activity.gear_id">{{ gear.nickname }}</span>
            <span class="ms-2" v-else>{{ $t("activity.labelGearNotSet") }}</span>
        </p>
        <div class="justify-content-end">
            <!-- add gear button -->
            <a class="btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addGearToActivityModal" v-if="!activity.gear_id">
                <font-awesome-icon :icon="['fas', 'fa-plus']" />
            </a>


            <!-- edit gear button -->
            <a class="btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#editGearActivityModal" v-if="activity.gear_id">
                <font-awesome-icon :icon="['far', 'fa-pen-to-square']" />
            </a>

            <!-- Delete zone -->
            <a class="btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#deleteGearActivityModal" v-if="activity.gear_id">
                <font-awesome-icon :icon="['fas', 'fa-trash']" />
            </a>
        </div>
    </div>

    <!-- graphs -->
    <hr class="mb-2 mt-2">

    <div>
        <br>
        <button @click="goBack" type="button" class="w-100 btn btn-primary d-lg-none">{{ $t("generalItens.buttonBack") }}</button>
    </div>
</template>

<script>
import { ref, onMounted, onUnmounted, watchEffect, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
// Importing the stores
import { useSuccessAlertStore } from '@/stores/Alerts/successAlert';
import { useErrorAlertStore } from '@/stores/Alerts/errorAlert';
// Importing the components
import ActivitySummaryComponent from '@/components/Activities/ActivitySummaryComponent.vue';
import ActivityMapComponent from '@/components/Activities/ActivityMapComponent.vue';
import NoItemsFoundComponent from '@/components/NoItemsFoundComponents.vue';
import ErrorAlertComponent from '@/components/Alerts/ErrorAlertComponent.vue';
import SuccessAlertComponent from '@/components/Alerts/SuccessAlertComponent.vue';
import LoadingComponent from '@/components/LoadingComponent.vue';
// Importing the services
import { gears } from '@/services/gears';
import { activities } from '@/services/activities';

export default {
    components: {
        NoItemsFoundComponent,
        ActivitySummaryComponent,
        ActivityMapComponent,
        LoadingComponent,
        ErrorAlertComponent,
        SuccessAlertComponent,
    },
    setup (){
        const { t } = useI18n();
        const route = useRoute();
        const router = useRouter();
        const errorAlertStore = useErrorAlertStore();
        const successAlertStore = useSuccessAlertStore();
        const isLoading = ref(true);
        const errorMessage = ref('');
        const successMessage = ref('');
        const activity = ref(null);
        const gear = ref(null);

        /**
         * Function to navigate back to the previous page.
         */
         function goBack() {
            route.go(-1);
        }

        onMounted(async () => {
            try{
                activity.value = await activities.getActivityById(route.params.id);
                if (!activity.value) {
                    router.push({ path: '/', query: { activityFound: 'false' } });
                }
                if (activity.value.gear_id) {
                    gear.value = await gears.getGearById(activity.value.gear_id);
                }
            } catch (error) {
                if (error.toString().includes('422')) {
                    router.push({ path: '/', query: { activityFound: 'false' } });
                }
                // If there is an error, set the error message and show the error alert.
                errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }

            isLoading.value = false;
        });

        return {
            isLoading,
            activity,
            gear,
            errorMessage,
            successMessage,
            goBack,
        };
    }
};
</script>