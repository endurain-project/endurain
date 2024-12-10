<template>
    <LoadingComponent v-if="isLoading"/>

    <div v-else>
        <ActivitySummaryComponent v-if="activity" :activity="activity" :source="'activity'" />
    </div>

    <!-- map zone -->
    <div class="mt-3 mb-3" v-if="isLoading">
        <LoadingComponent />
    </div>
    <div class="mt-3 mb-3" v-else-if="activity">
        <ActivityMapComponent :activity="activity" :source="'activity'"/>
    </div>
    
    <!-- gear zone -->
    <hr class="mb-2 mt-2">
    <div class="mt-3 mb-3" v-if="isLoading">
        <LoadingComponent />
    </div>
    <div class="d-flex justify-content-between align-items-center" v-else-if="activity">
        <p class="pt-2">
            <span class="fw-lighter">
                {{ $t("activity.labelGear") }}
            </span>
            <br>
            <span v-if="activity.activity_type === 1 || activity.activity_type === 2 || activity.activity_type === 3">
                <font-awesome-icon :icon="['fas', 'person-running']" />
            </span>
            <span v-else-if="activity.activity_type === 4 || activity.activity_type === 5 || activity.activity_type === 6 || activity.activity_type === 7">
                <font-awesome-icon :icon="['fas', 'fa-person-biking']" />
            </span>
            <span v-else-if="activity.activity_type === 8 || activity.activity_type === 9">
                <font-awesome-icon :icon="['fas', 'fa-person-swimming']" />
            </span>
            <span class="ms-2" v-if="activity.gear_id">{{ gear.nickname }}</span>
            <span class="ms-2" v-else>{{ $t("activity.labelGearNotSet") }}</span>
        </p>
        <div class="justify-content-end">
            <!-- add gear button -->
            <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addGearToActivityModal" v-if="!activity.gear_id && activity.user_id === authStore.user.id">
                <font-awesome-icon :icon="['fas', 'fa-plus']" />
            </a>

            <!-- modal -->
            <div class="modal fade" id="addGearToActivityModal" tabindex="-1" aria-labelledby="addGearToActivityModal" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h1 class="modal-title fs-5" id="addGearToActivityModal">
                                {{ $t("activity.modalLabelAddGear") }}
                            </h1>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"
                                aria-label="Close"></button>
                        </div>
                        <form @submit.prevent="submitAddGearToActivityForm">
                            <div class="modal-body">
                                <!-- gear type fields -->
                                <label for="gearIDAdd"><b>* {{ $t("activity.modalLabelSelectGear") }}</b></label>
                                <select class="form-control" name="gearIDAdd" v-model="gearId" required>
                                    <option v-for="gear in gearsByType" :key="gear.id" :value="gear.id">
                                        {{ gear.nickname }}
                                    </option>
                                </select>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                    {{ $t("generalItems.buttonClose") }}
                                </button>
                                <button type="submit" class="btn btn-success" data-bs-dismiss="modal" name="addGearToActivity">
                                    {{ $t("activity.modalButtonAddGear") }}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>


            <!-- edit gear button -->
            <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addGearToActivityModal" v-if="activity.gear_id && activity.user_id === authStore.user.id">
                <font-awesome-icon :icon="['far', 'fa-pen-to-square']" />
            </a>

            <!-- Delete zone -->
            <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" data-bs-target="#deleteGearActivityModal" v-if="activity.gear_id && activity.user_id === authStore.user.id">
                <font-awesome-icon :icon="['fas', 'fa-trash']" />
            </a>

            <!-- Modal delete gear -->
            <div class="modal fade" id="deleteGearActivityModal" tabindex="-1" aria-labelledby="deleteGearActivityModal"
                aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h1 class="modal-title fs-5" id="deleteGearActivityModal">
                                {{ $t("activity.modalLabelDeleteGear") }}
                            </h1>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <span>{{ $t("activity.modalLabelDeleteGearBody") }}</span>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                {{ $t("generalItems.buttonClose") }}
                            </button>
                            <a @click="submitDeleteGearFromActivity" type="button" class="btn btn-danger" data-bs-dismiss="modal">
                                {{ $t("activity.modalLabelDeleteGearButton") }}
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- graphs -->
    <hr class="mb-2 mt-2">
    <div class="row">
        <div class="col-md-2">
            <p>{{ $t("activity.labelGraph") }}</p>
            <ul class="nav nav-pills flex-column mb-auto" id="sidebarLineGraph">
                <li class="nav-item" v-for="item in graphItems" :key="item.type">
                    <a href="javascript:void(0);" class="nav-link text-secondary"
                    :class="{ 'active text-white': graphSelection === item.type }"
                    @click="selectGraph(item.type)">
                        {{ item.label }}
                    </a>
                </li>
            </ul>
            <p class="mt-2">{{ $t("activity.labelDownsampling") }}</p>
        </div>
        <div class="col">
            <LoadingComponent v-if="isLoading"/>
            <div v-else-if="activity">
                <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="graphSelection" :activityStreams="activityActivityStreams" v-if="graphSelection === 'hr' && hrPresent"/>
                <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="graphSelection" :activityStreams="activityActivityStreams" v-if="graphSelection === 'power' && powerPresent"/>
                <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="graphSelection" :activityStreams="activityActivityStreams" v-if="graphSelection === 'cad' && cadPresent"/>
                <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="graphSelection" :activityStreams="activityActivityStreams" v-if="graphSelection === 'ele' && elePresent"/>
                <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="graphSelection" :activityStreams="activityActivityStreams" v-if="graphSelection === 'vel' && velPresent"/>
                <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="graphSelection" :activityStreams="activityActivityStreams" v-if="graphSelection === 'pace' && pacePresent"/>
            </div>
        </div>
    </div>

    <!-- back button -->
    <BackButtonComponent />
</template>

<script>
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
// Importing the stores
import { useAuthStore } from '@/stores/authStore';
// Import Notivue push
import { push } from 'notivue'
// Importing the components
import ActivitySummaryComponent from '@/components/Activities/ActivitySummaryComponent.vue';
import ActivityMapComponent from '@/components/Activities/ActivityMapComponent.vue';
import ActivityStreamsLineChartComponent from '@/components/Activities/ActivityStreamsLineChartComponent.vue';
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue';
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue';
// Importing the services
import { gears } from '@/services/gearsService';
import { activities } from '@/services/activitiesService';
import { activityStreams } from '@/services/activityStreams';

export default {
    components: {
        ActivitySummaryComponent,
        ActivityMapComponent,
        ActivityStreamsLineChartComponent,
        LoadingComponent,
        BackButtonComponent,
    },
    setup (){
        const { t } = useI18n();
        const authStore = useAuthStore();
        const route = useRoute();
        const router = useRouter();
        const isLoading = ref(true);
        const activity = ref(null);
        const gear = ref(null);
        const gearsByType = ref([]);
        const gearId = ref(null);
        const activityActivityStreams = ref([]);
        const graphSelection = ref('hr');
        const graphItems = ref([]);
        const hrPresent = ref(false);
        const powerPresent = ref(false);
        const elePresent = ref(false);
        const cadPresent = ref(false);
        const velPresent = ref(false);
        const pacePresent = ref(false);
        
        function selectGraph(type) {
            graphSelection.value = type;
        }

        async function submitAddGearToActivityForm() {
            try {
                // Add the gear to the activity
                await activities.addGearToActivity(route.params.id, gearId.value);
                
                // Show the success message
                push.success(t('activity.successMessageGearAdded'))

                // Update the activity gear
                gear.value = await gears.getGearById(gearId.value);
                activity.value.gear_id = gearId.value;
            } catch (error) {
                push.error(`${t('generalItems.errorEditingInfo')} - ${error}`)
            }
        }

        async function submitDeleteGearFromActivity() {
            try {
                // Delete the gear from the activity
                await activities.deleteGearFromActivity(route.params.id);
                
                // Show the success message
                push.success(t('activity.successMessageGearDeleted'))

                // Update the activity gear
                activity.value.gear_id = null;
            } catch (error) {
                push.error(`${t('generalItems.errorEditingInfo')} - ${error}`)
            }
        }

        onMounted(async () => {
            try{
                // Get the activity by id
                activity.value = await activities.getActivityById(route.params.id);
                
                // Get the activity streams by activity id
                activityActivityStreams.value = await activityStreams.getActivitySteamsByActivityId(route.params.id);

                // Check if the activity has the streams
                for (let i = 0; i < activityActivityStreams.value.length; i++) {
                    if (activityActivityStreams.value[i].stream_type === 1) {
                        hrPresent.value = true;
                        graphItems.value.push({ type: 'hr', label: 'HR' });
                    }
                    if (activityActivityStreams.value[i].stream_type === 2) {
                        powerPresent.value = true;
                        graphItems.value.push({ type: 'power', label: 'Power' });
                    }
                    if (activityActivityStreams.value[i].stream_type === 3) {
                        cadPresent.value = true;
                        graphItems.value.push({ type: 'cad', label: 'Cadence' });
                    }
                    if (activityActivityStreams.value[i].stream_type === 4) {
                        elePresent.value = true;
                        graphItems.value.push({ type: 'ele', label: 'Elevation' });
                    }
                    if (activityActivityStreams.value[i].stream_type === 5) {
                        velPresent.value = true;
                        if (activity.value.activity_type === 4 || activity.value.activity_type === 5 || activity.value.activity_type === 6 || activity.value.activity_type === 7) {
                            graphItems.value.push({ type: 'vel', label: 'Velocity' });
                        }
                    }
                    if (activityActivityStreams.value[i].stream_type === 6) {
                        pacePresent.value = true;
                        if (activity.value.activity_type !== 4 && activity.value.activity_type !== 5 && activity.value.activity_type !== 6 && activity.value.activity_type !== 7) {
                            graphItems.value.push({ type: 'pace', label: 'Pace' });
                        }
                    }
                }

                if (!activity.value) {
                    router.push({ path: '/', query: { activityFound: 'false', id: route.params.id } });
                }
                if (activity.value.gear_id) {
                    gear.value = await gears.getGearById(activity.value.gear_id);
                    gearId.value = activity.value.gear_id;
                }

                if (activity.value.activity_type === 1 || activity.value.activity_type === 2 || activity.value.activity_type === 3 || activity.value.activity_type === 11 || activity.value.activity_type === 12) {
                    gearsByType.value = await gears.getGearFromType(2);
                } else {
                    if (activity.value.activity_type === 4 || activity.value.activity_type === 5 || activity.value.activity_type === 6 || activity.value.activity_type === 7) {
                        gearsByType.value = await gears.getGearFromType(1);
                    } else {
                        if (activity.value.activity_type === 8 || activity.value.activity_type === 9) {
                            gearsByType.value = await gears.getGearFromType(3);
                        }
                    }
                }
            } catch (error) {
                if (error.toString().includes('422')) {
                    router.push({ path: '/', query: { activityFound: 'false', id: route.params.id } });
                }
                // If there is an error, set the error message and show the error alert.
                push.error(`${t('generalItems.errorEditingInfo')} - ${error}`)
            }

            isLoading.value = false;
        });

        return {
            authStore,
            isLoading,
            activity,
            gear,
            gearId,
            activityActivityStreams,
            gearsByType,
            submitAddGearToActivityForm,
            submitDeleteGearFromActivity,
            graphSelection,
            graphItems,
            selectGraph,
            hrPresent,
            powerPresent,
            elePresent,
            cadPresent,
            velPresent,
            pacePresent,
        };
    }
};
</script>