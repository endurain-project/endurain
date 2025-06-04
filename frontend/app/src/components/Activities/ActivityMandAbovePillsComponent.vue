<template>
    <ul class="nav nav-pills mb-3 mt-3 justify-content-center" id="pills-tab" role="tablist">
        <li class="nav-item" role="presentation" v-if="graphItems && graphItems.length > 0">
            <button class="nav-link link-body-emphasis" :class="{ active: graphItems || graphItems.length > 0 }" id="pills-graphs-tab" data-bs-toggle="pill" data-bs-target="#pills-graphs" type="button" role="tab" aria-controls="pills-graphs" :aria-selected="graphItems && graphItems.length > 0 ? true : false">
                {{ $t("activityMandAbovePillsComponent.labelPillGraphs") }}
            </button>
        </li>
        <li class="nav-item" role="presentation" v-if="activityActivityLaps && activityActivityLaps.length > 0">
            <button class="nav-link link-body-emphasis" :class="{ active: !graphItems || graphItems.length === 0 }" id="pills-laps-tab" data-bs-toggle="pill" data-bs-target="#pills-laps" type="button" role="tab" aria-controls="pills-laps" :aria-selected="!graphItems || graphItems.length === 0 ? 'true' : 'false'">
                {{ $t("activityMandAbovePillsComponent.labelPillLaps") }}
            </button>
        </li>
		<li class="nav-item" role="presentation" v-if="activityActivityWorkoutSteps && activityActivityWorkoutSteps.length > 0">
            <button class="nav-link link-body-emphasis" id="pills-workout-steps-tab" data-bs-toggle="pill" data-bs-target="#pills-workout-steps" type="button" role="tab" aria-controls="pills-workout-steps" aria-selected="false">
                {{ $t("activityMandAbovePillsComponent.labelPillWorkoutSets") }}
            </button>
        </li>
    </ul>

    <div class="tab-content" id="pills-tabContent">
        <div class="tab-pane fade show" :class="{ active: graphItems || graphItems.length > 0 }" id="pills-graphs" role="tabpanel" aria-labelledby="pills-graphs-tab" tabindex="0" v-if="graphItems && graphItems.length > 0">
            <div class="row">
                <div class="col-md-2">
                    <p>{{ $t("activityMandAbovePillsComponent.labelGraph") }}</p>
                    <ul class="nav nav-pills flex-column mb-auto" id="sidebarLineGraph">
                        <li class="nav-item" v-for="item in graphItems" :key="item.type">
                            <a href="javascript:void(0);" class="nav-link text-secondary"
                            :class="{ 'active text-white': graphSelection === item.type }"
                            @click="selectGraph(item.type)">
                                {{ item.label }}
                            </a>
                        </li>
                    </ul>
                    <p class="mt-2">{{ $t("activityMandAbovePillsComponent.labelDownsampling") }}</p>
                </div>
                <div class="col">
                    <div if="activity">
                        <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="graphSelection" :activityStreams="activityActivityStreams" v-if="graphSelection === 'hr' && hrPresent"/>
                        <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="graphSelection" :activityStreams="activityActivityStreams" v-if="graphSelection === 'power' && powerPresent"/>
                        <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="graphSelection" :activityStreams="activityActivityStreams" v-if="graphSelection === 'cad' && cadPresent"/>
                        <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="graphSelection" :activityStreams="activityActivityStreams" v-if="graphSelection === 'ele' && elePresent"/>
                        <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="graphSelection" :activityStreams="activityActivityStreams" v-if="graphSelection === 'vel' && velPresent"/>
                        <ActivityStreamsLineChartComponent :activity="activity" :graphSelection="graphSelection" :activityStreams="activityActivityStreams" v-if="graphSelection === 'pace' && pacePresent"/>
                    </div>
                </div>
            </div>
        </div>

        <div class="tab-pane fade" :class="{ 'show active': !graphItems || graphItems.length === 0 }" id="pills-laps" role="tabpanel" aria-labelledby="pills-laps-tab" tabindex="1" v-if="activityActivityLaps && activityActivityLaps.length > 0">
            <ActivityLapsComponent :activity="activity" :activityActivityLaps="activityActivityLaps" :units="units" />
        </div>

		<div class="tab-pane fade" id="pills-workout-steps" role="tabpanel" aria-labelledby="pills-workout-steps-tab" tabindex="2" v-if="activityActivityWorkoutSteps && activityActivityWorkoutSteps.length > 0">
			<ActivityWorkoutStepsComponent :activity="activity" :activityActivityWorkoutSteps="activityActivityWorkoutSteps" :units="units" :activityActivityExerciseTitles="activityActivityExerciseTitles" :activityActivitySets="activityActivitySets" />
		</div>
    </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
// Importing the components
import ActivityLapsComponent from "@/components/Activities/ActivityLapsComponent.vue";
import ActivityStreamsLineChartComponent from "@/components/Activities/ActivityStreamsLineChartComponent.vue";
import ActivityWorkoutStepsComponent from "@/components/Activities/ActivityWorkoutStepsComponent.vue";
import { activityTypeIsSwimming } from "@/utils/activityUtils";
import { useAuthStore } from "@/stores/authStore";
// Import Notivue push
import { push } from "notivue";

// Props
const props = defineProps({
	activity: {
		type: Object,
		required: true,
	},
	activityActivityLaps: {
		type: [Object, null],
		required: true,
	},
	activityActivityWorkoutSteps: {
		type: [Object, null],
		required: true,
	},
	activityActivityStreams: {
		type: Object,
		required: true,
	},
	units: {
		type: Number,
		default: 1,
	},
	activityActivityExerciseTitles: {
		type: [Object, null],
		required: true,
	},
	activityActivitySets: {
		type: [Object, null],
		required: true,
	},
});

// Composables
const { t } = useI18n();
const authStore = useAuthStore();

// Reactive state
const graphSelection = ref("hr");
const graphItems = ref([]);
const hrPresent = ref(false);
const powerPresent = ref(false);
const elePresent = ref(false);
const cadPresent = ref(false);
const velPresent = ref(false);
const pacePresent = ref(false);

// Methods
function selectGraph(type) {
	graphSelection.value = type;
}

// Lifecycle
onMounted(async () => {
	try {
		if (props.activityActivityStreams && props.activityActivityStreams.length > 0) {
			// Check if the activity has the streams
			for (let i = 0; i < props.activityActivityStreams.length; i++) {
				if (props.activityActivityStreams[i].stream_type === 1 && ((authStore.isAuthenticated && authStore.user.id === props.activity.user_id) || (authStore.isAuthenticated && authStore.user.id !== props.activity.user_id && props.activity.hide_hr === false) || (!authStore.isAuthenticated && props.activity.hide_hr === false))) {
					hrPresent.value = true;
					graphItems.value.push({ type: "hr", label: `${t("activityMandAbovePillsComponent.labelGraphHR")}` });
				}
				if (props.activityActivityStreams[i].stream_type === 2 && ((authStore.isAuthenticated && authStore.user.id === props.activity.user_id) || (authStore.isAuthenticated && authStore.user.id !== props.activity.user_id && props.activity.hide_power === false) || (!authStore.isAuthenticated && props.activity.hide_power === false))) {
					powerPresent.value = true;
					graphItems.value.push({ type: "power", label: `${t("activityMandAbovePillsComponent.labelGraphPower")}` });
				}
				if (props.activityActivityStreams[i].stream_type === 3 && ((authStore.isAuthenticated && authStore.user.id === props.activity.user_id) || (authStore.isAuthenticated && authStore.user.id !== props.activity.user_id && props.activity.hide_cadence === false) || (!authStore.isAuthenticated && props.activity.hide_cadence === false))) {
					cadPresent.value = true;
					// Label as "Stroke Rate" over "Cadence" for swimming activities
					if (activityTypeIsSwimming(props.activity)) {
						graphItems.value.push({ type: "cad", label: `${t("activityMandAbovePillsComponent.labelGraphStrokeRate")}` });
					} else {
						graphItems.value.push({ type: "cad", label: `${t("activityMandAbovePillsComponent.labelGraphCadence")}` });
					}
				}
				if (props.activityActivityStreams[i].stream_type === 4 && ((authStore.isAuthenticated && authStore.user.id === props.activity.user_id) || (authStore.isAuthenticated && authStore.user.id !== props.activity.user_id && props.activity.hide_elevation === false) || (!authStore.isAuthenticated && props.activity.hide_elevation === false))) {
					// Do not show elevation for swimming activities
					if (!activityTypeIsSwimming(props.activity)) {
						elePresent.value = true;
						graphItems.value.push({ type: "ele", label: `${t("activityMandAbovePillsComponent.labelGraphElevation")}` });
					}
				}
				if (props.activityActivityStreams[i].stream_type === 5 && ((authStore.isAuthenticated && authStore.user.id === props.activity.user_id) || (authStore.isAuthenticated && authStore.user.id !== props.activity.user_id && props.activity.hide_speed === false) || (!authStore.isAuthenticated && props.activity.hide_speed === false))) {
					velPresent.value = true;
					if (
						props.activity.activity_type === 4 ||
						props.activity.activity_type === 5 ||
						props.activity.activity_type === 6 ||
						props.activity.activity_type === 7 ||
						props.activity.activity_type === 27
					) {
						graphItems.value.push({ type: "vel", label: `${t("activityMandAbovePillsComponent.labelGraphVelocity")}` });
					}
				}
				if (props.activityActivityStreams[i].stream_type === 6 && ((authStore.isAuthenticated && authStore.user.id === props.activity.user_id) || (authStore.isAuthenticated && authStore.user.id !== props.activity.user_id && props.activity.hide_pace === false) || (!authStore.isAuthenticated && props.activity.hide_pace === false))) {
					pacePresent.value = true;
					if (
						props.activity.activity_type !== 4 &&
						props.activity.activity_type !== 5 &&
						props.activity.activity_type !== 6 &&
						props.activity.activity_type !== 7 &&
						props.activity.activity_type !== 27
					) {
						graphItems.value.push({ type: "pace", label: `${t("activityMandAbovePillsComponent.labelGraphPace")}` });
					}
				}
			}
		}
		if (graphItems.value.length > 0) {
			graphSelection.value = graphItems.value[0].type;
		}
	} catch (error) {
		// If there is an error, set the error message and show the error alert.
		push.error(
			`${t("activityMandAbovePillsComponent.errorMessageProcessingActivityStreams")} - ${error}`,
		);
	}
});
</script>