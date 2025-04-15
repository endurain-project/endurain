<template>
    <ul class="nav nav-pills mb-3 mt-3 justify-content-center" id="pills-tab" role="tablist">
        <li class="nav-item" role="presentation" v-if="graphItems && graphItems.length > 0">
            <button class="nav-link active link-body-emphasis" id="pills-graphs-tab" data-bs-toggle="pill" data-bs-target="#pills-graphs" type="button" role="tab" aria-controls="pills-graphs" aria-selected="true">
                {{ $t("activityMandAbovePillsComponent.labelPillGraphs") }}
            </button>
        </li>
        <li class="nav-item" role="presentation" v-if="activityActivityLaps && activityActivityLaps.length > 0">
            <button class="nav-link link-body-emphasis" id="pills-laps-tab" data-bs-toggle="pill" data-bs-target="#pills-laps" type="button" role="tab" aria-controls="pills-laps" aria-selected="false">
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
        <div class="tab-pane fade show active" id="pills-graphs" role="tabpanel" aria-labelledby="pills-graphs-tab" tabindex="0" v-if="graphItems && graphItems.length > 0">
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

        <div class="tab-pane fade" id="pills-laps" role="tabpanel" aria-labelledby="pills-laps-tab" tabindex="1" v-if="activityActivityLaps && activityActivityLaps.length > 0">
            <ActivityLapsComponent :activity="activity" :activityActivityLaps="activityActivityLaps" :units="units" />
        </div>

		<div class="tab-pane fade" id="pills-workout-steps" role="tabpanel" aria-labelledby="pills-workout-steps-tab" tabindex="2" v-if="activityActivityWorkoutSteps && activityActivityWorkoutSteps.length > 0">
			<ActivityWorkoutStepsComponent :activity="activity" :activityActivityWorkoutSteps="activityActivityWorkoutSteps" :units="units" :activityActivityExerciseTitles="activityActivityExerciseTitles" :activityActivitySets="activityActivitySets" />
		</div>
    </div>
</template>

<script>
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
// Importing the components
import ActivityLapsComponent from "@/components/Activities/ActivityLapsComponent.vue";
import ActivityStreamsLineChartComponent from "@/components/Activities/ActivityStreamsLineChartComponent.vue";
import ActivityWorkoutStepsComponent from "@/components/Activities/ActivityWorkoutStepsComponent.vue";
// Import Notivue push
import { push } from "notivue";

export default {
	components: {
		ActivityLapsComponent,
		ActivityStreamsLineChartComponent,
		ActivityWorkoutStepsComponent,
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
	},
	setup(props) {
		const { t } = useI18n();
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

        onMounted(async () => {
			try {
                if (props.activityActivityStreams && props.activityActivityStreams.length > 0) {
					// Check if the activity has the streams
					for (let i = 0; i < props.activityActivityStreams.length; i++) {
						if (props.activityActivityStreams[i].stream_type === 1) {
							hrPresent.value = true;
							graphItems.value.push({ type: "hr", label: `${t("activityMandAbovePillsComponent.labelGraphHR")}` });
						}
						if (props.activityActivityStreams[i].stream_type === 2) {
							powerPresent.value = true;
							graphItems.value.push({ type: "power", label: `${t("activityMandAbovePillsComponent.labelGraphPower")}` });
						}
						if (props.activityActivityStreams[i].stream_type === 3) {
							cadPresent.value = true;
							graphItems.value.push({ type: "cad", label: `${t("activityMandAbovePillsComponent.labelGraphCadence")}` });
						}
						if (props.activityActivityStreams[i].stream_type === 4) {
							elePresent.value = true;
							graphItems.value.push({ type: "ele", label: `${t("activityMandAbovePillsComponent.labelGraphElevation")}` });
						}
						if (props.activityActivityStreams[i].stream_type === 5) {
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
						if (props.activityActivityStreams[i].stream_type === 6) {
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
            } catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(
					`${t("activityMandAbovePillsComponent.errorMessageProcessingActivityStreams")} - ${error}`,
				);
			}
        });

		return {
			graphSelection,
            graphItems,
			hrPresent,
			powerPresent,
			elePresent,
			cadPresent,
			velPresent,
			pacePresent,
			selectGraph,
		};
	},
};
</script>