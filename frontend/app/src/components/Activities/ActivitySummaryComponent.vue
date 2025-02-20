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
                        <span v-if="activity.activity_type == 1 || activity.activity_type == 2">
                            <font-awesome-icon class="me-1" :icon="['fas', 'person-running']" />
                        </span>
                        <span v-else-if="activity.activity_type == 3">
                            <font-awesome-icon class="me-1" :icon="['fas', 'person-running']" />{{ $t("activitySummaryComponent.labelVirtual") }}
                        </span>
                        <span v-else-if="activity.activity_type == 4 || activity.activity_type == 5 || activity.activity_type == 6">
                            <font-awesome-icon class="me-1" :icon="['fas', 'fa-person-biking']" />
                        </span>
                        <span v-else-if="activity.activity_type == 7">
                            <font-awesome-icon class="me-1" :icon="['fas', 'fa-person-biking']" />{{ $t("activitySummaryComponent.labelVirtual") }}
                        </span>
                        <span v-else-if="activity.activity_type == 8 || activity.activity_type == 9">
                            <font-awesome-icon class="me-1" :icon="['fas', 'fa-person-swimming']" />
                        </span>
                        <span v-else-if="activity.activity_type == 11">
                            <font-awesome-icon class="me-1" :icon="['fas', 'person-walking']" />
                        </span>
                        <span v-else-if="activity.activity_type == 12">
                            <font-awesome-icon class="me-1" :icon="['fas', 'person-hiking']" />
                        </span>
                        <span v-else-if="activity.activity_type == 13">
                            <font-awesome-icon class="me-1" :icon="['fas', 'sailboat']" />
                        </span>
                        <span v-else-if="activity.activity_type == 14">
                            <font-awesome-icon class="me-1" :icon="['fas', 'hands-praying']" />
                        </span>
                        <span v-else-if="activity.activity_type == 15">
                            <font-awesome-icon class="me-1" :icon="['fas', 'person-skiing']" />
                        </span>
                        <span v-else-if="activity.activity_type == 16">
                            <font-awesome-icon class="me-1" :icon="['fas', 'person-skiing-nordic']" />
                        </span>
                        <span v-else-if="activity.activity_type == 17">
                            <font-awesome-icon class="me-1" :icon="['fas', 'person-snowboarding']" />
                        </span>
                        <span v-else>
                            <font-awesome-icon class="me-1" :icon="['fas', 'fa-dumbbell']" />
                        </span>

                        <!-- Display the date and time -->  
                        <span>{{ formatDateMed(activity.start_time) }}</span> @
                        <span>{{ formatTime(activity.start_time) }}</span>
                        <!-- Conditionally display city and country -->
                        <span v-if="activity.town || activity.city || activity.country">
                            - 
                            <span v-if="activity.town">{{ activity.town }},</span>
                            <span v-else-if="activity.city">{{ activity.city }},</span>
                            <span v-if="activity.country">{{ " " + activity.country }}</span>
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
                <div v-if="source === 'activity'">
                    <button class="btn btn-link btn-lg link-body-emphasis" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                        <font-awesome-icon :icon="['fas', 'fa-ellipsis-vertical']" />
                    </button>
                    <ul class="dropdown-menu">
                        <li>
                            <a class="dropdown-item" href="#" data-bs-toggle="modal" data-bs-target="#editActivityModal">
                                {{ $t("activitySummaryComponent.buttonEditActivity") }}
                            </a>
                        </li>
                        <li><hr class="dropdown-divider"></li>
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
            <div class="col" v-if="activity.activity_type != 10 && activity.activity_type != 14">
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityDistance") }}
                </span>
                <br>
                <span v-if="Number(units) === 1">
                    <!-- Check if activity_type is not 9 and 8 -->
                    {{ activity.activity_type != 9 && activity.activity_type != 8
                        ? metersToKm(activity.distance) + ' ' + $t("generalItems.unitsKm") : activity.distance + ' ' + $t("generalItems.unitsM")
                    }}
                </span>
                <span v-else>
                    <!-- Check if activity_type is not 9 and 8 -->
                    {{ activity.activity_type != 9 && activity.activity_type != 8
                        ? metersToMiles(activity.distance) + ' ' + $t("generalItems.unitsMiles") : metersToYards(activity.distance) + ' ' + $t("generalItems.unitsYards")
                    }}
                </span>
            </div>
            <div class="col" v-else>
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityCalories") }}
                </span>
                <br>
                <span v-if="activity.calories">{{ activity.calories }}{{ ' ' + $t("generalItems.unitsCalories") }}</span>
                <span v-else>{{ $t("activitySummaryComponent.activityNoData") }}</span>
            </div>
            <div class="col border-start border-opacity-50">
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityTime") }}
                </span>
                <br>
                <span>{{ calculateTimeDifference(activity.start_time, activity.end_time) }}</span>
            </div>
            <div class="col border-start border-opacity-50">
                <div v-if="activity.activity_type != 1 && activity.activity_type != 2 && activity.activity_type != 3 && activity.activity_type != 8 && activity.activity_type != 9 && activity.activity_type != 10 && activity.activity_type != 13 && activity.activity_type != 14">
                    <span class="fw-lighter">
                        {{ $t("activitySummaryComponent.activityElevationGain") }}
                    </span>
                    <br>
                    <span v-if="Number(units) === 1">{{ activity.elevation_gain }}{{ ' ' + $t("generalItems.unitsM") }}</span>
                    <span v-else>{{ metersToFeet(activity.elevation_gain) }}{{ ' ' + $t("generalItems.unitsFeetShort") }}</span>
                </div>
                <div v-else-if="activity.activity_type != 10 && activity.activity_type != 14">
                    <span class="fw-lighter">
                        {{ $t("activitySummaryComponent.activityPace") }}
                    </span>
                    <br>
                    {{ formattedPace }}
                </div>
                <div v-else>
                    <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityAvgHR") }}
                    </span>
                    <br>
                    <span v-if="activity.average_hr">{{ activity.average_hr }}{{ ' ' + $t("generalItems.unitsBpm") }}</span>
                    <span v-else>{{ $t("activitySummaryComponent.activityNoData") }}</span>
                </div>
            </div>
        </div>        
        <div class="row d-flex mt-3" v-if="source === 'activity' && activity.activity_type != 10 && activity.activity_type != 14">
            <!-- avg_power running and cycling activities-->
            <div class="col" v-if="activity.activity_type == 1 || activity.activity_type == 2 || activity.activity_type == 3 || activity.activity_type == 4 || activity.activity_type == 5 || activity.activity_type == 6 || activity.activity_type == 7">
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityAvgPower") }}
                </span>
                <br>
                <span v-if="activity.average_power">{{ activity.average_power }}{{ ' ' + $t("generalItems.unitsWattsShort") }}</span>
                <span v-else>{{ $t("activitySummaryComponent.activityNoData") }}</span>
            </div>
            <!-- avg_hr not running and cycling activities-->
            <div class="col" v-if="activity.activity_type != 1 && activity.activity_type != 2 && activity.activity_type != 3 && activity.activity_type != 4 && activity.activity_type != 5 && activity.activity_type != 6 && activity.activity_type != 7">
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityAvgHR") }}
                </span>
                <br>
                <span v-if="activity.average_hr">{{ activity.average_hr }}{{ ' ' + $t("generalItems.unitsBpm") }}</span>
                <span v-else>{{ $t("activitySummaryComponent.activityNoData") }}</span>
            </div>
            <!-- max_hr not running and cycling activities-->
            <div class="col border-start border-opacity-50" v-if="activity.activity_type != 1 && activity.activity_type != 2 && activity.activity_type != 3 && activity.activity_type != 4 && activity.activity_type != 5 && activity.activity_type != 6 && activity.activity_type != 7">
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityMaxHR") }}
                </span>
                <br>
                <span v-if="activity.max_hr">{{ activity.max_hr }}{{ ' ' + $t("generalItems.unitsBpm") }}</span>
                <span v-else>{{ $t("activitySummaryComponent.activityNoData") }}</span>
            </div>
            <!-- ele gain running activities -->
            <div class="col border-start border-opacity-50" v-if="activity.activity_type == 1 || activity.activity_type == 2 || activity.activity_type == 3">
                <span class="fw-lighter">{{ $t("activitySummaryComponent.activityEleGain") }}</span>
                <br>
                <span v-if="Number(units) === 1">{{ activity.elevation_gain }}{{ ' ' + $t("generalItems.unitsM") }}</span>
                <span v-else>{{ metersToFeet(activity.elevation_gain) }}{{ ' ' + $t("generalItems.unitsFeetShort") }}</span>
            </div>
            <!-- avg_speed cycling activities -->
            <div class="col border-start border-opacity-50" v-if="activity.activity_type == 4 || activity.activity_type == 5 || activity.activity_type == 6 || activity.activity_type == 7">
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityAvgSpeed") }}
                </span>
                <br>
                <span v-if="activity.average_speed && Number(units) === 1">{{ formatAverageSpeedMetric(activity.average_speed) }}{{ ' ' + $t("generalItems.unitsKmH") }}</span>
                <span v-else-if="activity.average_speed && Number(units) === 2">{{ formatAverageSpeedImperial(activity.average_speed) }}{{ ' ' + $t("generalItems.unitsMph") }}</span>
                <span v-else>{{ $t("activitySummaryComponent.activityNoData") }}</span>
            </div>
            <!-- calories -->
            <div class="col border-start border-opacity-50">
                <span class="fw-lighter">
                    {{ $t("activitySummaryComponent.activityCalories") }}
                </span>
                <br>
                <span v-if="activity.calories">{{ activity.calories }}{{ ' ' + $t("generalItems.unitsCalories") }}</span>
                <span v-else>{{ $t("activitySummaryComponent.activityNoData") }}</span>
            </div>
        </div>
    </div>
</template>

<script>
import { ref, onMounted, computed } from "vue";
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
import {
	formatDateMed,
	formatTime,
	calculateTimeDifference,
} from "@/utils/dateTimeUtils";
import { formatPaceMetric, formatPaceImperial, formatPaceSwimMetric, formatPaceSwimImperial, formatAverageSpeedMetric, formatAverageSpeedImperial } from "@/utils/activityUtils";
import { metersToKm, metersToMiles, metersToYards, metersToFeet } from "@/utils/unitsUtils";

export default {
	components: {
		LoadingComponent,
		UserAvatarComponent,
		EditActivityModalComponent,
        ModalComponent,
	},
	props: {
		activity: {
			type: Object,
			required: true,
		},
		source: {
			type: String,
			required: true,
		},
	},
	emits: ["activityEditedFields"],
	setup(props, { emit }) {
		const router = useRouter();
		const authStore = useAuthStore();
        const serverSettingsStore = useServerSettingsStore();
		const { t } = useI18n();
		const isLoading = ref(true);
		const userActivity = ref(null);
		const formattedPace = ref(null);
        const units = ref(1)

		onMounted(async () => {
			try {
                if (authStore.isAuthenticated) {
                    userActivity.value = await users.getUserById(props.activity.user_id);
                    units.value = authStore.user.units;
                } else {
                    if (serverSettingsStore.serverSettings.public_shareable_links_user_info) {
                        userActivity.value = await users.getPublicUserById(props.activity.user_id);
                    }
                    units.value = serverSettingsStore.serverSettings.units;
                }

                if (
                    props.activity.activity_type === 8 ||
                    props.activity.activity_type === 9 ||
                    props.activity.activity_type === 13
                ) {
                    if (Number(units.value) === 1) {
                        formattedPace.value = computed(() => formatPaceSwimMetric(props.activity.pace));
                    } else {
                        formattedPace.value = computed(() => formatPaceSwimImperial(props.activity.pace));
                    }
                } else {
                    if (Number(units.value) === 1) {
                        formattedPace.value = computed(() => formatPaceMetric(props.activity.pace));
                    } else {
                        formattedPace.value = computed(() => formatPaceImperial(props.activity.pace));
                    }
                }
			} catch (error) {
				push.error(`${t("activitySummaryComponent.errorFetchingUserById")} - ${error}`);
			} finally {
				isLoading.value = false;
			}
		});

		async function submitDeleteActivity() {
			try {
				userActivity.value = await activities.deleteActivity(props.activity.id);
				return router.push({
					path: "/",
					query: { activityDeleted: "true", activityId: props.activity.id },
				});
			} catch (error) {
				push.error(`${t("activitySummaryComponent.errorDeletingActivity")} - ${error}`);
			}
		}

		function updateActivityFieldsOnEdit(data) {
			// Emit the activityEditedFields event to the parent component
			emit("activityEditedFields", data);
		}

		return {
			authStore,
			isLoading,
			t,
			userActivity,
			formatDateMed,
			formatTime,
			calculateTimeDifference,
			formattedPace,
            units,
			submitDeleteActivity,
			updateActivityFieldsOnEdit,
            metersToKm,
            metersToMiles,
            metersToYards,
            metersToFeet,
            formatAverageSpeedMetric,
            formatAverageSpeedImperial,
		};
	},
};
</script>