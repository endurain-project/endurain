<template>
    <div v-if="isLoading">
        <LoadingComponent />
    </div>
    <div v-else>
        <div class="d-flex justify-content-between">
            <!-- user name and photo zone -->
            <div class="d-flex align-items-center">
                <UserAvatarComponent :user="userActivity" :width=55 :height=55  />
                <div class="ms-3 me-3">
                    <div class="fw-bold">
                        <router-link :to="{ name: 'activity', params: { id: activity.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover" v-if="source === 'home'">
                            {{ activity.name}}
                        </router-link>
                        <span v-if="userActivity">
                            <router-link :to="{ name: 'user', params: { id: userActivity.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover" v-if="source === 'activity'">
                                {{ userActivity.name}}
                            </router-link>
                        </span>
                        <span v-else>
                            {{ $t("activitySummaryComponent.userNameHidden") }}
                        </span>
                    </div>
                    <h6>
                        <!-- Display the visibility of the activity -->
                        <span v-if="activity.visibility == 0">
                            <font-awesome-icon :icon="['fas', 'globe']"/> {{ $t("activitySummaryComponent.visibilityPublic") }}
                        </span>
                        <span v-if="activity.visibility == 1">
                            <font-awesome-icon :icon="['fas', 'users']" v-if="activity.visibility == 1" /> {{ $t("activitySummaryComponent.visibilityFollowers") }}
                        </span>
                        <span v-if="activity.visibility == 2">
                            <font-awesome-icon :icon="['fas', 'lock']" v-if="activity.visibility == 2" /> {{ $t("activitySummaryComponent.visibilityPrivate") }}
                        </span>
                        <span> - </span>

                        <!-- Display the activity type -->
                        <span>
                            <font-awesome-icon class="me-1" :icon="getIcon(activity.activity_type)" />
                            <span v-if="activity.activity_type === 3 || activity.activity_type === 7">{{ $t("activitySummaryComponent.labelVirtual") }}</span>
                        </span>

                        <!-- Display the date and time -->
                        <span v-if="activity.start_time">
                            {{ formatDateMed(activity.start_time) }} @ {{ formatTime(activity.start_time) }}
                        </span>
                        <!-- Conditionally display city and country -->
                        <span v-if="activity.town || activity.city || activity.country">
                            - 
                            <span>{{ formatLocation(activity) }}</span>
                        </span>
                    </h6>
                </div>
            </div>
            <div class="dropdown d-flex" v-if="activity.user_id == authStore.user.id">
                <a class="btn btn-link btn-lg link-body-emphasis" :href="`https://www.strava.com/activities/${activity.strava_activity_id}`" role="button" v-if="activity.strava_activity_id">
                    <font-awesome-icon :icon="['fab', 'fa-strava']" />
                </a>
                <a class="btn btn-link btn-lg link-body-emphasis" :href="`https://connect.garmin.com/modern/activity/${activity.garminconnect_activity_id}`" role="button" v-if="activity.garminconnect_activity_id">
                    <img src="/src/assets/garminconnect/Garmin_Connect_app_1024x1024-02.png" alt="Garmin Connect logo" height="22" />
                </a>
                <div>
                    <button class="btn btn-link btn-lg link-body-emphasis" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                        <font-awesome-icon :icon="['fas', 'fa-ellipsis-vertical']" />
                    </button>
                    <ul class="dropdown-menu">
                        <li v-if="source === 'activity'">
                            <a class="dropdown-item" href="#" data-bs-toggle="modal" data-bs-target="#editActivityModal">
                                {{ $t("activitySummaryComponent.buttonEditActivity") }}
                            </a>
                        </li>
                        <li v-if="source === 'activity'"><hr class="dropdown-divider"></li>
                        <li>
                            <a class="dropdown-item" href="#" data-bs-toggle="modal" data-bs-target="#deleteActivityModal">
                                {{ $t("activitySummaryComponent.buttonDeleteActivity") }}
                            </a>
                        </li>
                    </ul>
                </div>
            </div>
        </div>

        <!-- Modal edit activity -->
        <EditActivityModalComponent :activity="activity" @activityEditedFields="updateActivityFieldsOnEdit"/>

        <!-- Modal delete activity -->
        <ModalComponent modalId="deleteActivityModal" :title="t('activitySummaryComponent.buttonDeleteActivity')" :body="`${t('activitySummaryComponent.modalDeleteBody1')}<b>${activity.name}</b>?<br>${t('activitySummaryComponent.modalDeleteBody2')}`" :actionButtonType="`danger`" :actionButtonText="t('activitySummaryComponent.buttonDeleteActivity')" @submitAction="submitDeleteActivity"/>

        <!-- Activity title -->
        <h1 class="mt-3" v-if="source === 'activity'">
            {{ activity.name }}
        </h1>

        <!-- Activity description -->
        <p v-if="activity.description">{{ activity.description }}</p>

        <!-- Activity summary -->
        <div class="row mt-3 align-items-center text-start">
            <!-- distance -->
            <div class="col border-start border-opacity-50" v-if="activity.activity_type != 10 && activity.activity_type != 14 && activity.activity_type != 18 && activity.activity_type != 19 && activity.activity_type != 20 && activity.activity_type != 21 && activity.activity_type != 22 && activity.activity_type != 23 && activity.activity_type != 24 && activity.activity_type != 25 && activity.activity_type != 26">
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityDistance") }}
                </span>
                <br>
                <span>{{ formatDistance(activity, authStore.user.units) }}</span>
            </div>
            <!-- calories -->
            <div class="col" v-else>
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityCalories") }}
                </span>
                <br>
                <span>{{ formatCalories(activity.calories) }}</span>
            </div>
            <!-- activity time-->
            <div class="col border-start border-opacity-50">
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityTime") }}
                </span>
                <br>
                <span>
                    {{$t('activitySummaryComponent.activityMovingTime')}}: {{ formatSecondsToMinutes(activity.total_timer_time) }} <br>
                    {{$t('activitySummaryComponent.activityTotalTime')}}: {{ formatSecondsToMinutes(activity.total_elapsed_time) }}
                </span>
            </div>
            <div class="col border-start border-opacity-50">
                <!-- elevation -->
                <div v-if="activity.activity_type != 1 && activity.activity_type != 2 && activity.activity_type != 3 && activity.activity_type != 8 && activity.activity_type != 9 && activity.activity_type != 10 && activity.activity_type != 13 && activity.activity_type != 14 && activity.activity_type != 18 && activity.activity_type != 19 && activity.activity_type != 20 && activity.activity_type != 21 && activity.activity_type != 22 && activity.activity_type != 23 && activity.activity_type != 24 && activity.activity_type != 25 && activity.activity_type != 26">
                    <span class="fw-lighter">
                        {{ $t("activitySummaryComponent.activityElevationGain") }}
                    </span>
                    <br>
                    <span>{{ formatElevation(activity.elevation_gain, authStore.user.units) }}</span>
                </div>
                <!-- pace -->
                <div v-else-if="activity.activity_type != 10 && activity.activity_type != 14 && activity.activity_type != 18 && activity.activity_type != 19 && activity.activity_type != 20 && activity.activity_type != 21 && activity.activity_type != 22 && activity.activity_type != 23 && activity.activity_type != 24 && activity.activity_type != 25 && activity.activity_type != 26">
                    <span class="fw-lighter">
                        {{ $t("activitySummaryComponent.activityPace") }}
                    </span>
                    <br>
                    {{ formatPace(activity, authStore.user.units) }}
                </div>
            </div>
        </div>        
        <div class="row d-flex mt-3" v-if="source === 'activity' && activity.activity_type != 10 && activity.activity_type != 14 && activity.activity_type != 18 && activity.activity_type != 19 && activity.activity_type != 20 && activity.activity_type != 21 && activity.activity_type != 22 && activity.activity_type != 23 && activity.activity_type != 24 && activity.activity_type != 25 && activity.activity_type != 26">
            <!-- avg_power running and cycling activities-->
            <div class="col border-start border-opacity-50" v-if="activity.activity_type == 1 || activity.activity_type == 2 || activity.activity_type == 3 || activity.activity_type == 4 || activity.activity_type == 5 || activity.activity_type == 6 || activity.activity_type == 7 || activity.activity_type == 27">
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityAvgPower") }}
                </span>
                <br>
                <span>{{ formatPower(activity.average_power) }}</span>
            </div>
            <!-- avg_hr not running and cycling activities-->
            <div class="col" v-if="activity.activity_type != 1 && activity.activity_type != 2 && activity.activity_type != 3 && activity.activity_type != 4 && activity.activity_type != 5 && activity.activity_type != 6 && activity.activity_type != 7 && activity.activity_type != 27">
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityAvgHR") }}
                </span>
                <br>
                <span>{{ formatHr(activity.average_hr) }}</span>
            </div>
            <!-- max_hr not running and cycling activities-->
            <div class="col border-start border-opacity-50" v-if="activity.activity_type != 1 && activity.activity_type != 2 && activity.activity_type != 3 && activity.activity_type != 4 && activity.activity_type != 5 && activity.activity_type != 6 && activity.activity_type != 7 && activity.activity_type != 27">
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityMaxHR") }}
                </span>
                <br>
                <span>{{ formatHr(activity.max_hr) }}</span>
            </div>
            <!-- ele gain running activities -->
            <div class="col border-start border-opacity-50" v-if="activity.activity_type == 1 || activity.activity_type == 2 || activity.activity_type == 3">
                <span class="fw-lighter">{{ $t("activitySummaryComponent.activityEleGain") }}</span>
                <br>
                <span>{{ formatElevation(activity.elevation_gain, authStore.user.units) }}</span>
            </div>
            <!-- avg_speed cycling activities -->
            <div class="col border-start border-opacity-50" v-if="activity.activity_type == 4 || activity.activity_type == 5 || activity.activity_type == 6 || activity.activity_type == 7 || activity.activity_type == 27">
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityAvgSpeed") }}
                </span>
                <br>
                <span>{{ formatAverageSpeed(activity, authStore.user.units) }}</span>
            </div>
            <!-- calories -->
            <div class="col border-start border-opacity-50">
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityCalories") }}
                </span>
                <br>
                <span>{{ formatCalories(activity.calories) }}</span>
            </div>
        </div>
        <div class="row d-flex mt-3" v-if="source === 'activity' && activity.activity_type != 10 && activity.activity_type != 14 && activity.activity_type != 18 && activity.activity_type != 19 && activity.activity_type != 20 && activity.activity_type != 21 && activity.activity_type != 22 && activity.activity_type != 23 && activity.activity_type != 24 && activity.activity_type != 25 && activity.activity_type != 26">
            <div class="col border-start border-opacity-50">
                <!-- hr -->
                <div>
                    <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityHR") }}
                    </span>
                    <br>
                    <span>{{ $t("activitySummaryComponent.activityAvgHR") }}: {{ formatHr(activity.average_hr) }}</span> <br>
                    <span>{{ $t("activitySummaryComponent.activityMaxHR") }}: {{ formatHr(activity.max_hr) }}</span> <br><br>
                    <span v-for="(value, zone, index) in hrZones" :key="zone"
                          :style="{ color: getZoneColor(index) }">
                      {{ $t("activitySummaryComponent.activityHRZone") }} {{ index + 1 }} ({{ value.hr }}) : {{ value.percent }}%<br>
                    </span>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
import { useServerSettingsStore } from "@/stores/serverSettingsStore";
// Import Notivue push
import { push } from "notivue";
// Importing the components
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import UserAvatarComponent from "@/components/Users/UserAvatarComponent.vue";
import EditActivityModalComponent from "@/components/Activities/Modals/EditActivityModalComponent.vue";
import ModalComponent from "@/components/Modals/ModalComponent.vue";
// Importing the services
import { users } from "@/services/usersService";
import { activities } from "@/services/activitiesService";
// Importing the utils
import {
	formatDistance,
	formatElevation,
	formatPace,
	formatHr,
	formatCalories,
	getIcon,
	formatLocation,
    formatAverageSpeed,
    formatPower,
} from "@/utils/activityUtils";
import {
	formatDateMed,
	formatTime,
    formatSecondsToMinutes,
} from "@/utils/dateTimeUtils";

// Props
const props = defineProps({
	activity: {
		type: Object,
		required: true,
	},
    activityActivityStreams: {
		type: [Object, null],
		required: true,
	},
	source: {
		type: String,
		required: true,
	},
    units: {
        type: Number,
        default: 1,
    },
});

// Emits
const emit = defineEmits(["activityEditedFields", "activityDeleted"]);

// Composables
const router = useRouter();
const authStore = useAuthStore();
const serverSettingsStore = useServerSettingsStore();
const { t } = useI18n();

// Reactive data
const isLoading = ref(true);
const userActivity = ref(null);
const hrZones = ref({
    zone_1: 0,
    zone_2: 0,
    zone_3: 0,
    zone_4: 0,
});

// Lifecycle
onMounted(async () => {
	try {
        hrZones.value = props.activityActivityStreams.find(stream => stream.hr_zone_percentages).hr_zone_percentages || {};

        if (authStore.isAuthenticated) {
            userActivity.value = await users.getUserById(props.activity.user_id);
        } else {
            if (serverSettingsStore.serverSettings.public_shareable_links_user_info) {
                userActivity.value = await users.getPublicUserById(props.activity.user_id);
            }
        }
	} catch (error) {
		push.error(`${t("activitySummaryComponent.errorFetchingUserById")} - ${error}`);
	} finally {
		isLoading.value = false;
	}
});

// Methods
async function submitDeleteActivity() {
	try {
		userActivity.value = await activities.deleteActivity(props.activity.id);
        if (props.source === 'activity') {
            return router.push({
                path: "/",
                query: { activityDeleted: "true", activityId: props.activity.id },
            });
        }
        emit("activityDeleted", props.activity.id);
	} catch (error) {
		push.error(`${t("activitySummaryComponent.errorDeletingActivity")} - ${error}`);
	}
}

function updateActivityFieldsOnEdit(data) {
	// Emit the activityEditedFields event to the parent component
	emit("activityEditedFields", data);
}

function getZoneColor(index) {
  // Example colors for 5 HR zones
  const colors = [
    '#1e90ff', // Zone 1: blue
    '#28a745', // Zone 2: green
    '#ffc107', // Zone 3: yellow
    '#fd7e14', // Zone 4: orange
    '#dc3545', // Zone 5: red
  ];
  return colors[index] || '#000';
}
</script>