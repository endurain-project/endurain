<template>
    <div if="activity" class="fw-lighter">
        <!-- Pace values -->
        <div v-if="pacePresent">
            <span class="fw-lighter">
                Pace
            </span>
            <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="'pace'" :activityStreams="activityActivityStreams" />
            <div class="d-flex justify-content-between mt-3" v-if="formattedPace">
                <span>
                    Avg Pace
                </span>
                <span>
                    <b>{{ formattedPace }}</b>
                </span>
            </div>
            <div class="d-flex justify-content-between mt-3" v-if="activity.total_elapsed_time">
                <span>
                    Moving time
                </span>
                <span>
                    <b>{{ formatSecondsToMinutes(activity.total_elapsed_time) }}</b>
                </span>
            </div>
            <div class="d-flex justify-content-between mt-3" v-if="activity.total_timer_time">
                <span>
                    Elapsed time
                </span>
                <span>
                    <b>{{ formatSecondsToMinutes(activity.total_timer_time) }}</b>
                </span>
            </div>
            <hr>
        </div>
        <!-- Velocity values -->
        <div v-if="velPresent">
            <span class="fw-lighter">
                Velocity
            </span>
            <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="'vel'" :activityStreams="activityActivityStreams" />
            <div class="d-flex justify-content-between mt-3" v-if="activity.average_speed">
                <span>
                    Avg Speed
                </span>
                <span>
                    <span v-if="activity.average_speed && Number(units) === 1"><b>{{ formatAverageSpeedMetric(activity.average_speed) }}{{ ' ' + $t("generalItems.unitsKmH") }}</b></span>
                    <span v-else-if="activity.average_speed && Number(units) === 2"><b>{{ formatAverageSpeedImperial(activity.average_speed) }}{{ ' ' + $t("generalItems.unitsMph") }}</b></span>
                </span>
            </div>
            <div class="d-flex justify-content-between mt-3" v-if="activity.max_speed">
                <span>
                    Max Speed
                </span>
                <span>
                    <span v-if="activity.max_speed && Number(units) === 1"><b>{{ formatAverageSpeedMetric(activity.max_speed) }}{{ ' ' + $t("generalItems.unitsKmH") }}</b></span>
                    <span v-else-if="activity.max_speed && Number(units) === 2"><b>{{ formatAverageSpeedImperial(activity.max_speed) }}{{ ' ' + $t("generalItems.unitsMph") }}</b></span>
                </span>
            </div>
            <div class="d-flex justify-content-between mt-3" v-if="activity.total_elapsed_time">
                <span>
                    Moving time
                </span>
                <span>
                    <b>{{ formatSecondsToMinutes(activity.total_elapsed_time) }}</b>
                </span>
            </div>
            <div class="d-flex justify-content-between mt-3" v-if="activity.total_timer_time">
                <span>
                    Elapsed time
                </span>
                <span>
                    <b>{{ formatSecondsToMinutes(activity.total_timer_time) }}</b>
                </span>
            </div>
            <hr>
        </div>
        <!-- Heart rate values -->
        <div v-if="hrPresent">
            <span class="fw-lighter">
                Heart Rate
            </span>
            <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="'hr'" :activityStreams="activityActivityStreams" />
            <div class="d-flex justify-content-between mt-3" v-if="activity.average_hr">
                <span>
                    Avg Heart Rate
                </span>
                <span>
                    <b>{{ activity.average_hr }}{{ ' ' + $t("generalItems.unitsBpm") }}</b>
                </span>
            </div>
            <div class="d-flex justify-content-between mt-3" v-if="activity.max_hr">
                <span>
                    Max Heart Rate
                </span>
                <span>
                    <b>{{ activity.max_hr }}{{ ' ' + $t("generalItems.unitsBpm") }}</b>
                </span>
            </div>
            <hr>
        </div>
        <!-- Power values -->
        <div v-if="powerPresent">
            <span class="fw-lighter">
                Power
            </span>
            <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="'power'" :activityStreams="activityActivityStreams" />
            <div class="d-flex justify-content-between mt-3" v-if="activity.average_power">
                <span>
                    Avg Power
                </span>
                <span>
                    <b>{{ activity.average_power }}{{ ' ' + $t("generalItems.unitsWattsShort") }}</b>
                </span>
            </div>
            <div class="d-flex justify-content-between mt-3" v-if="activity.max_power">
                <span>
                    Max Power
                </span>
                <span>
                    <b>{{ activity.max_power }}{{ ' ' + $t("generalItems.unitsWattsShort") }}</b>
                </span>
            </div>
            <div class="d-flex justify-content-between mt-3" v-if="activity.normalized_power">
                <span>
                    Normalized Power
                </span>
                <span>
                    <b>{{ activity.normalized_power }}{{ ' ' + $t("generalItems.unitsWattsShort") }}</b>
                </span>
            </div>
            <hr>
        </div>
        <!-- Cadence values -->
        <div v-if="cadPresent">
            <span class="fw-lighter">
                Cadence
            </span>
            <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="'cad'" :activityStreams="activityActivityStreams" />
            <div class="d-flex justify-content-between mt-3" v-if="activity.average_cad">
                <span>
                    Avg Cadence
                </span>
                <span>
                    <b>{{ activity.average_cad }}{{ ' ' + $t("generalItems.unitsSpm") }}</b>
                </span>
            </div>
            <div class="d-flex justify-content-between mt-3" v-if="activity.max_cad">
                <span>
                    Max Cadence
                </span>
                <span>
                    <b>{{ activity.max_cad }}{{ ' ' + $t("generalItems.unitsSpm") }}</b>
                </span>
            </div>
            <hr>
        </div>
        <!-- Elevation values -->
        <div v-if="elePresent">
            <span class="fw-lighter">
                Elevation
            </span>
            <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="'ele'" :activityStreams="activityActivityStreams" />
            <div class="d-flex justify-content-between mt-3" v-if="activity.elevation_gain">
                <span>
                    Elevation Gain
                </span>
                <span>
                    <b>{{ activity.elevation_gain }}{{ ' ' + $t("generalItems.unitsM") }}</b>
                </span>
            </div>
            <div class="d-flex justify-content-between mt-3" v-if="activity.elevation_loss">
                <span>
                    Elevation Loss
                </span>
                <span>
                    <b>{{ activity.elevation_loss }}{{ ' ' + $t("generalItems.unitsM") }}</b>
                </span>
            </div>
            <hr>
        </div>
    </div>
</template>

<script>
import { ref, onMounted, computed } from "vue";
import { useI18n } from "vue-i18n";
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
import { useServerSettingsStore } from "@/stores/serverSettingsStore";
// Importing the components
import ActivityLapsComponent from "@/components/Activities/ActivityLapsComponent.vue";
import ActivityStreamsLineChartComponent from "@/components/Activities/ActivityStreamsLineChartComponent.vue";
// Import Notivue push
import { push } from "notivue";
import { formatPaceMetric, formatPaceImperial, formatPaceSwimMetric, formatPaceSwimImperial, formatAverageSpeedMetric, formatAverageSpeedImperial } from "@/utils/activityUtils";
import { formatSecondsToMinutes } from "@/utils/dateTimeUtils";

export default {
	components: {
		ActivityLapsComponent,
		ActivityStreamsLineChartComponent,
	},
	props: {
		activity: {
			type: Object,
			required: true,
		},
        activityActivityLaps: {
			type: [Object, null],
			required: true,
		},
        activityActivityStreams: {
			type: Object,
			required: true,
		},
	},
	setup(props) {
		const { t } = useI18n();
		const authStore = useAuthStore();
        const serverSettingsStore = useServerSettingsStore();
		const hrPresent = ref(false);
		const powerPresent = ref(false);
		const elePresent = ref(false);
		const cadPresent = ref(false);
		const velPresent = ref(false);
		const pacePresent = ref(false);
        const formattedPace = ref(null);
        const units = ref(1)

        onMounted(async () => {
			try {
                if (props.activityActivityStreams && props.activityActivityStreams.length > 0) {
					// Check if the activity has the streams
					for (let i = 0; i < props.activityActivityStreams.length; i++) {
						if (props.activityActivityStreams[i].stream_type === 1) {
							hrPresent.value = true;
						}
						if (props.activityActivityStreams[i].stream_type === 2) {
							powerPresent.value = true;
						}
						if (props.activityActivityStreams[i].stream_type === 3) {
							cadPresent.value = true;
						}
						if (props.activityActivityStreams[i].stream_type === 4) {
							elePresent.value = true;
						}
						if (props.activityActivityStreams[i].stream_type === 5) {
                            if (
								props.activity.activity_type === 4 ||
								props.activity.activity_type === 5 ||
								props.activity.activity_type === 6 ||
								props.activity.activity_type === 7
							) {
                                velPresent.value = true;
                            }
						}
						if (props.activityActivityStreams[i].stream_type === 6) {
                            if (
								props.activity.activity_type !== 4 &&
								props.activity.activity_type !== 5 &&
								props.activity.activity_type !== 6 &&
								props.activity.activity_type !== 7
							) {
                                pacePresent.value = true;
                            }
						}
					}
				}
            } catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(
					`${t("activityMandAbovePillsComponent.errorMessageProcessingActivityStreams")} - ${error}`,
				);
			}

            try {
                if (authStore.isAuthenticated) {
                    //userActivity.value = await users.getUserById(props.activity.user_id);
                    units.value = authStore.user.units;
                } else {
                    //if (serverSettingsStore.serverSettings.public_shareable_links_user_info) {
                    //    userActivity.value = await users.getPublicUserById(props.activity.user_id);
                    //}
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
			}
        });

		return {
            units,
			hrPresent,
			powerPresent,
			elePresent,
			cadPresent,
			velPresent,
			pacePresent,
            formattedPace,
            formatSecondsToMinutes,
            formatAverageSpeedMetric,
            formatAverageSpeedImperial,
		};
	},
};
</script>