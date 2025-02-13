<template>
    <LoadingComponent v-if="isLoading"/>

    <div v-else>
        <ActivitySummaryComponent v-if="activity" :activity="activity" :source="'activity'" @activityEditedFields="updateActivityFieldsOnEdit"/>
    </div>

    <!-- map zone -->
    <div class="mt-3 mb-3" v-if="isLoading">
        <LoadingComponent />
    </div>
    <div class="mt-3 mb-3" v-else-if="activity">
        <ActivityMapComponent :activity="activity" :source="'activity'"/>
    </div>
    
    <!-- gear zone -->
    <hr class="mb-2 mt-2" v-if="activity && authStore.isAuthenticated">
    <div class="mt-3 mb-3" v-if="isLoading && authStore.isAuthenticated">
        <LoadingComponent />
    </div>
    <div class="d-flex justify-content-between align-items-center" v-else-if="activity && authStore.isAuthenticated">
        <p class="pt-2">
            <span class="fw-lighter">
                {{ $t("activityView.labelGear") }}
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
            <span class="ms-2" v-if="activity.gear_id && gear">{{ gear.nickname }}</span>
            <span class="ms-2" v-else>{{ $t("activityView.labelGearNotSet") }}</span>
        </p>
        <div class="justify-content-end">
            <!-- add gear button -->
            <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addGearToActivityModal" v-if="!activity.gear_id && activity.user_id === authStore.user.id">
                <font-awesome-icon :icon="['fas', 'fa-plus']" />
            </a>

            <!-- add gear to activity modal -->
            <AddGearToActivityModalComponent :activity="activity" :gearsByType="gearsByType" :gear="gearId" @gearId="updateGearIdOnAddGearToActivity"/>

            <!-- edit gear button -->
            <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addGearToActivityModal" v-if="activity.gear_id && activity.user_id === authStore.user.id">
                <font-awesome-icon :icon="['far', 'fa-pen-to-square']" />
            </a>

            <!-- Delete zone -->
            <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" data-bs-target="#deleteGearActivityModal" v-if="activity.gear_id && activity.user_id === authStore.user.id">
                <font-awesome-icon :icon="['fas', 'fa-trash']" />
            </a>

            <!-- Modal delete gear -->
            <ModalComponent modalId="deleteGearActivityModal" :title="t('activityView.modalLabelDeleteGear')" :body="`${t('activityView.modalLabelDeleteGearBody')}`" actionButtonType="danger" :actionButtonText="t('activityView.modalLabelDeleteGearButton')" @submitAction="submitDeleteGearFromActivity"/>
        </div>
    </div>

    <!-- graphs -->
    <hr class="mb-2 mt-2">
    <div class="row">
        <div class="col-md-2">
            <p>{{ $t("activityView.labelGraph") }}</p>
            <ul class="nav nav-pills flex-column mb-auto" id="sidebarLineGraph">
                <li class="nav-item" v-for="item in graphItems" :key="item.type">
                    <a href="javascript:void(0);" class="nav-link text-secondary"
                    :class="{ 'active text-white': graphSelection === item.type }"
                    @click="selectGraph(item.type)">
                        {{ item.label }}
                    </a>
                </li>
            </ul>
            <p class="mt-2">{{ $t("activityView.labelDownsampling") }}</p>
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
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
import { useServerSettingsStore } from "@/stores/serverSettingsStore";
// Import Notivue push
import { push } from "notivue";
// Importing the components
import ActivitySummaryComponent from "@/components/Activities/ActivitySummaryComponent.vue";
import ActivityMapComponent from "@/components/Activities/ActivityMapComponent.vue";
import ActivityStreamsLineChartComponent from "@/components/Activities/ActivityStreamsLineChartComponent.vue";
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import BackButtonComponent from "@/components/GeneralComponents/BackButtonComponent.vue";
import ModalComponent from "@/components/Modals/ModalComponent.vue";
import AddGearToActivityModalComponent from "@/components/Activities/Modals/AddGearToActivityModalComponent.vue";
// Importing the services
import { gears } from "@/services/gearsService";
import { activities } from "@/services/activitiesService";
import { activityStreams } from "@/services/activityStreams";

export default {
	components: {
		ActivitySummaryComponent,
		ActivityMapComponent,
		ActivityStreamsLineChartComponent,
		LoadingComponent,
		BackButtonComponent,
		ModalComponent,
		AddGearToActivityModalComponent,
	},
	setup() {
		const { t } = useI18n();
		const authStore = useAuthStore();
		const serverSettingsStore = useServerSettingsStore();
		const route = useRoute();
		const router = useRouter();
		const isLoading = ref(true);
		const activity = ref(null);
		const gear = ref(null);
		const gearsByType = ref([]);
		const gearId = ref(null);
		const activityActivityStreams = ref([]);
		const graphSelection = ref("hr");
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

		async function submitDeleteGearFromActivity() {
			try {
				// Delete the gear from the activity
				const auxActivity = activity.value;
				auxActivity.gear_id = null;
				await activities.editActivity(auxActivity);

				// Show the success message
				push.success(t("activityView.successMessageGearDeleted"));

				// Update the activity gear
				activity.value.gear_id = null;
			} catch (error) {
				push.error(`${t("activityView.errorMessageDeleteGear")} - ${error}`);
			}
		}

		async function updateGearIdOnAddGearToActivity(gearId) {
			// Update the activity gear
			gear.value = await gears.getGearById(gearId);
			activity.value.gear_id = gearId;

			// Show the success message
			push.success(t("activityView.successMessageGearAdded"));
		}

		function updateActivityFieldsOnEdit(data) {
			// Update the activity fields
			activity.value.name = data.name;
			activity.value.description = data.description;
			activity.value.activity_type = data.activity_type;
			activity.value.visibility = data.visibility;
		}

		onMounted(async () => {
			try {
				// Get the activity by id
				if (authStore.isAuthenticated) {
					activity.value = await activities.getActivityById(route.params.id);
				} else {
					if (serverSettingsStore.serverSettings.public_shareable_links) {
						activity.value = await activities.getPublicActivityById(route.params.id);
						if (!activity.value) {
							return router.push({ 
								path: "/login",
								query: { errorPublicActivityNotFound: "true" },
							});
						}
					} else {
						return router.push({ 
							path: "/login",
							query: { errorPublicShareableLinks: "true" },
						});
					}
				}

				// Check if the activity exists
				if (!activity.value) {
					return router.push({
						path: "/",
						query: { activityFound: "false", id: route.params.id },
					});
				}
					
				// Get the activity streams by activity id
				if (authStore.isAuthenticated) {
					activityActivityStreams.value =
						await activityStreams.getActivitySteamsByActivityId(route.params.id);
				} else {
					activityActivityStreams.value =
						await activityStreams.getPublicActivityStreamsByActivityId(route.params.id);
				}

				if (activityActivityStreams.value) {
					// Check if the activity has the streams
					for (let i = 0; i < activityActivityStreams.value.length; i++) {
						if (activityActivityStreams.value[i].stream_type === 1) {
							hrPresent.value = true;
							graphItems.value.push({ type: "hr", label: "HR" });
						}
						if (activityActivityStreams.value[i].stream_type === 2) {
							powerPresent.value = true;
							graphItems.value.push({ type: "power", label: "Power" });
						}
						if (activityActivityStreams.value[i].stream_type === 3) {
							cadPresent.value = true;
							graphItems.value.push({ type: "cad", label: "Cadence" });
						}
						if (activityActivityStreams.value[i].stream_type === 4) {
							elePresent.value = true;
							graphItems.value.push({ type: "ele", label: "Elevation" });
						}
						if (activityActivityStreams.value[i].stream_type === 5) {
							velPresent.value = true;
							if (
								activity.value.activity_type === 4 ||
								activity.value.activity_type === 5 ||
								activity.value.activity_type === 6 ||
								activity.value.activity_type === 7
							) {
								graphItems.value.push({ type: "vel", label: "Velocity" });
							}
						}
						if (activityActivityStreams.value[i].stream_type === 6) {
							pacePresent.value = true;
							if (
								activity.value.activity_type !== 4 &&
								activity.value.activity_type !== 5 &&
								activity.value.activity_type !== 6 &&
								activity.value.activity_type !== 7
							) {
								graphItems.value.push({ type: "pace", label: "Pace" });
							}
						}
					}
				}
				
				if (authStore.isAuthenticated) {
					if (activity.value.gear_id) {
						gear.value = await gears.getGearById(activity.value.gear_id);
						gearId.value = activity.value.gear_id;
					}

					if (
						activity.value.activity_type === 1 ||
						activity.value.activity_type === 2 ||
						activity.value.activity_type === 3 ||
						activity.value.activity_type === 11 ||
						activity.value.activity_type === 12
					) {
						gearsByType.value = await gears.getGearFromType(2);
					} else {
						if (
							activity.value.activity_type === 4 ||
							activity.value.activity_type === 5 ||
							activity.value.activity_type === 6 ||
							activity.value.activity_type === 7
						) {
							gearsByType.value = await gears.getGearFromType(1);
						} else {
							if (
								activity.value.activity_type === 8 ||
								activity.value.activity_type === 9
							) {
								gearsByType.value = await gears.getGearFromType(3);
							}
						}
					}
				}
			} catch (error) {
				if (error.toString().includes("422")) {
					router.push({
						path: "/",
						query: { activityFound: "false", id: route.params.id },
					});
				}
				// If there is an error, set the error message and show the error alert.
				push.error(`${t("activityView.errorMessageActivityNotFound")} - ${error}`);
			}

			isLoading.value = false;
		});

		return {
			t,
			authStore,
			isLoading,
			activity,
			gear,
			gearId,
			activityActivityStreams,
			gearsByType,
			submitDeleteGearFromActivity,
			updateGearIdOnAddGearToActivity,
			updateActivityFieldsOnEdit,
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
	},
};
</script>